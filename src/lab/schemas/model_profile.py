"""Status of a model inside a security profile (independent of any single test)."""
from __future__ import annotations

from datetime import datetime
from typing import Sequence

from pydantic import AwareDatetime, Field, model_validator

from .base import SCHEMA_VERSION, Id, LabModel, ModelId, NonEmptyStr, VersionedModel
from .enums import ConfirmationStatus, ModelProfileStatus, Severity
from .finding import Finding


class Transition(LabModel):
    from_status: ModelProfileStatus
    to_status: ModelProfileStatus
    security_profile_version: int = Field(ge=1)
    actor: NonEmptyStr
    reason: NonEmptyStr
    at: AwareDatetime
    trigger_finding_id: Id | None = None
    investigation_ref: NonEmptyStr | None = None
    fix_ref: NonEmptyStr | None = None
    retest_run_ids: list[Id] = Field(default_factory=list)
    approved_by: NonEmptyStr | None = None

    @model_validator(mode="after")
    def _rules(self) -> "Transition":
        if self.from_status == self.to_status:
            raise ValueError("transition must change the status")
        if self.to_status in (ModelProfileStatus.BLOCKED, ModelProfileStatus.UNDER_REVIEW) \
                and self.from_status == ModelProfileStatus.ALLOWED and not self.trigger_finding_id:
            raise ValueError("restricting a model requires trigger_finding_id")
        if self.to_status == ModelProfileStatus.BLOCKED and not self.trigger_finding_id:
            raise ValueError("blocking a model requires trigger_finding_id")
        if self.from_status == ModelProfileStatus.BLOCKED:
            missing = [n for n, v in (
                ("investigation_ref", self.investigation_ref), ("fix_ref", self.fix_ref),
                ("retest_run_ids", self.retest_run_ids), ("approved_by", self.approved_by),
            ) if not v]
            if missing:
                raise ValueError(f"leaving BLOCKED requires: {', '.join(missing)}")
        if self.from_status == ModelProfileStatus.UNDER_REVIEW and self.to_status == ModelProfileStatus.ALLOWED:
            if not (self.investigation_ref and self.approved_by):
                raise ValueError("clearing UNDER_REVIEW requires investigation_ref and approved_by")
        return self


class ModelProfileRecord(VersionedModel):
    model_id: ModelId
    security_profile_id: Id
    status: ModelProfileStatus = ModelProfileStatus.ALLOWED
    history: list[Transition] = Field(default_factory=list)

    @model_validator(mode="after")
    def _history_matches_status(self) -> "ModelProfileRecord":
        current = ModelProfileStatus.ALLOWED
        for t in self.history:
            if t.from_status != current:
                raise ValueError("history is not a continuous chain of transitions")
            current = t.to_status
        if current != self.status:
            raise ValueError("status does not match the last transition")
        return self


def new_model_profile_record(model_id: str, security_profile_id: str) -> ModelProfileRecord:
    return ModelProfileRecord(
        schema_version=SCHEMA_VERSION, model_id=model_id, security_profile_id=security_profile_id,
    )


def _transition(record: ModelProfileRecord, t: Transition) -> ModelProfileRecord:
    return ModelProfileRecord.model_validate(
        {**record.model_dump(), "status": t.to_status, "history": [*record.history, t]}
    )


def apply_findings(
    record: ModelProfileRecord,
    findings: Sequence[Finding],
    *,
    profile_version: int,
    at: datetime,
    actor: str = "system",
) -> ModelProfileRecord:
    """Escalate only: a confirmed CRITICAL finding blocks the model for the whole
    profile (not just one test); an unconfirmed one puts it under review. Passing
    tests or dismissed findings never lower a restriction."""
    critical = [f for f in findings if f.severity == Severity.CRITICAL]
    confirmed = [f for f in critical if f.confirmation_status == ConfirmationStatus.CONFIRMED]
    unconfirmed = [f for f in critical if f.confirmation_status == ConfirmationStatus.UNCONFIRMED]
    if confirmed and record.status != ModelProfileStatus.BLOCKED:
        f = confirmed[0]
        return _transition(record, Transition(
            from_status=record.status, to_status=ModelProfileStatus.BLOCKED,
            security_profile_version=profile_version, actor=actor,
            reason=f"confirmed {f.rule_id}", at=at, trigger_finding_id=f.finding_id,
        ))
    if unconfirmed and record.status == ModelProfileStatus.ALLOWED:
        f = unconfirmed[0]
        return _transition(record, Transition(
            from_status=record.status, to_status=ModelProfileStatus.UNDER_REVIEW,
            security_profile_version=profile_version, actor=actor,
            reason=f"unconfirmed {f.rule_id} needs review", at=at, trigger_finding_id=f.finding_id,
        ))
    return record


def lift_restriction(
    record: ModelProfileRecord,
    *,
    to_status: ModelProfileStatus = ModelProfileStatus.ALLOWED,
    profile_version: int,
    at: datetime,
    reason: str,
    approved_by: str,
    investigation_ref: str,
    fix_ref: str | None = None,
    retest_run_ids: Sequence[str] = (),
) -> ModelProfileRecord:
    """Lowering a restriction needs a documented investigation; leaving BLOCKED also
    needs a fix and retest runs (enforced by Transition)."""
    return _transition(record, Transition(
        from_status=record.status, to_status=to_status, security_profile_version=profile_version,
        actor=approved_by, reason=reason, at=at, investigation_ref=investigation_ref,
        fix_ref=fix_ref, retest_run_ids=list(retest_run_ids), approved_by=approved_by,
    ))
