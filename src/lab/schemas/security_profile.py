"""Versioned security profile: what a run may do, see and store."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable, Literal

import yaml
from pydantic import AwareDatetime, Field, model_validator

from .base import Id, LabModel, NonEmptyStr, VersionedModel


class ToolConstraint(LabModel):
    read_only: bool = True
    max_calls_per_run: int = Field(default=10, ge=1)


class SecretPattern(LabModel):
    name: Id
    regex: NonEmptyStr

    @model_validator(mode="after")
    def _regex_compiles(self) -> "SecretPattern":
        try:
            re.compile(self.regex)
        except re.error as exc:
            raise ValueError(f"invalid secret regex {self.name!r}: {exc}") from exc
        return self


class SecretDetectionPolicy(LabModel):
    enabled: bool = True
    patterns: list[SecretPattern] = Field(default_factory=list)

    @model_validator(mode="after")
    def _patterns_when_enabled(self) -> "SecretDetectionPolicy":
        if self.enabled and not self.patterns:
            raise ValueError("secret detection is enabled but no patterns are defined")
        return self


class PiiPolicy(LabModel):
    minimize_before_model: bool = True
    allowed_fields: list[Id] = Field(default_factory=list)
    blocked_fields: list[Id] = Field(default_factory=list)
    detect_in_output: bool = True

    @model_validator(mode="after")
    def _disjoint(self) -> "PiiPolicy":
        if set(self.allowed_fields) & set(self.blocked_fields):
            raise ValueError("pii allowed_fields and blocked_fields overlap")
        return self


class LoggingPolicy(LabModel):
    # Literal types make unsafe settings unrepresentable.
    store_raw_output: Literal[False] = False
    mask_secrets: Literal[True] = True
    mask_canaries: Literal[True] = True


class RetentionPolicy(LabModel):
    audit_log_days: int = Field(ge=1)
    output_days: int = Field(ge=1)


class SecurityProfile(VersionedModel):
    security_profile_id: Id
    version: int = Field(ge=1)
    name: NonEmptyStr
    created_at: AwareDatetime
    allowed_tools: list[Id] = Field(default_factory=list)
    tool_constraints: dict[Id, ToolConstraint] = Field(default_factory=dict)
    approval_required_for: list[Id] = Field(default_factory=list)
    forbidden_actions: list[Id] = Field(default_factory=list)
    # Actions that never need human approval. Anything not listed here requires it (fail-safe).
    no_approval_actions: list[Id] = Field(default_factory=list)
    protected_canary_ids: list[Id] = Field(default_factory=list)
    secret_detection_policy: SecretDetectionPolicy
    pii_policy: PiiPolicy
    logging_policy: LoggingPolicy
    retention_policy: RetentionPolicy
    external_data_transfer: bool = False
    external_transfer_notice: NonEmptyStr | None = None

    @model_validator(mode="after")
    def _consistency(self) -> "SecurityProfile":
        allowed = set(self.allowed_tools)
        if len(allowed) != len(self.allowed_tools):
            raise ValueError("allowed_tools contains duplicates")
        unknown = set(self.tool_constraints) - allowed
        if unknown:
            raise ValueError(f"tool_constraints for tools not in allowed_tools: {sorted(unknown)}")
        approval, forbidden, free = (
            set(self.approval_required_for),
            set(self.forbidden_actions),
            set(self.no_approval_actions),
        )
        if allowed & forbidden:
            raise ValueError(f"tools both allowed and forbidden: {sorted(allowed & forbidden)}")
        if approval & forbidden or approval & free or forbidden & free:
            raise ValueError("approval_required_for, forbidden_actions and no_approval_actions must be disjoint")
        if self.external_data_transfer and not self.external_transfer_notice:
            raise ValueError("external_data_transfer=true requires external_transfer_notice")
        if not self.external_data_transfer and self.external_transfer_notice:
            raise ValueError("external_transfer_notice set while external_data_transfer=false")
        return self

    def action_requires_approval(self, action_type: str) -> bool:
        """Policy is the source of truth; unknown actions require approval."""
        return action_type not in set(self.no_approval_actions)


class UnknownSecurityProfileError(LookupError):
    pass


class ProfileRegistry:
    def __init__(self, profiles: Iterable[SecurityProfile]) -> None:
        self._profiles: dict[tuple[str, int], SecurityProfile] = {}
        for p in profiles:
            key = (p.security_profile_id, p.version)
            if key in self._profiles:
                raise ValueError(f"duplicate security profile {key}")
            self._profiles[key] = p

    @classmethod
    def from_directory(cls, directory: str | Path) -> "ProfileRegistry":
        profiles = []
        for path in sorted(Path(directory).glob("*.yaml")):
            with path.open(encoding="utf-8") as fh:
                profiles.append(SecurityProfile.model_validate(yaml.safe_load(fh)))
        return cls(profiles)

    def all(self) -> list[SecurityProfile]:
        """Every loaded profile, sorted by (id, version). Read-only view for listing endpoints."""
        return [self._profiles[k] for k in sorted(self._profiles)]

    def has(self, profile_id: str, version: int) -> bool:
        return (profile_id, version) in self._profiles

    def get(self, profile_id: str, version: int) -> SecurityProfile:
        try:
            return self._profiles[(profile_id, version)]
        except KeyError:
            raise UnknownSecurityProfileError(
                f"security profile {profile_id!r} version {version} does not exist"
            ) from None
