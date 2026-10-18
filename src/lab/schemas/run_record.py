"""One concrete run (one repeat of one test on one model)."""
from __future__ import annotations

import hashlib
import json
from typing import Any

from pydantic import AwareDatetime, Field, model_validator

from .base import Id, LabModel, ModelId, NonEmptyStr, Sha256Hex, VersionedModel
from .enums import (
    AgentStatus,
    ModelProvider,
    RunStatus,
    StructuredOutputMode,
    TestVerdict,
    TriggerSource,
)
from .security_profile import ProfileRegistry, SecurityProfile


class RunConfig(LabModel):
    """Everything needed to reproduce a run. Saved for every run."""

    provider: ModelProvider
    model_id: ModelId
    model_version: NonEmptyStr
    prompt_version: NonEmptyStr
    temperature: float = Field(ge=0.0, le=2.0)
    top_p: float | None = Field(default=None, gt=0.0, le=1.0)
    max_output_tokens: int = Field(gt=0)
    context_limit: int | None = Field(default=None, gt=0)
    timeout_s: float = Field(gt=0)
    seed: int | None = None
    structured_output_mode: StructuredOutputMode = StructuredOutputMode.NONE

    def fingerprint(self) -> str:
        canonical = json.dumps(self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class ToolCall(LabModel):
    tool: Id
    action_type: Id | None = None
    params_hash: Sha256Hex
    trigger_source: TriggerSource
    executed: bool  # False for calls only discussed in text or blocked by the orchestrator
    approval_ref: Id | None = None


class RunMetrics(LabModel):
    latency_ms: float | None = Field(default=None, ge=0)
    tokens_in: int | None = Field(default=None, ge=0)
    tokens_out: int | None = Field(default=None, ge=0)
    cost_usd: float | None = Field(default=None, ge=0)


class RunRecord(VersionedModel):
    run_id: Id
    test_id: Id
    repeat_index: int = Field(ge=0)
    suite_version: NonEmptyStr
    run_status: RunStatus
    test_verdict: TestVerdict | None = None  # filled with ERROR automatically for non-completed runs
    agent_status: AgentStatus | None = None
    run_config: RunConfig
    run_config_hash: Sha256Hex
    security_profile_id: Id
    security_profile_version: int = Field(ge=1)
    input_hash: Sha256Hex
    decision_report_ref: NonEmptyStr | None = None
    output_reference: NonEmptyStr | None = None
    output_sanitized: bool = False
    sanitization_summary: dict[str, int] | None = None  # types and counts only, never values
    tool_calls: list[ToolCall] = Field(default_factory=list)
    finding_ids: list[Id] = Field(default_factory=list)
    evaluation_ids: list[Id] = Field(default_factory=list)
    metrics: RunMetrics = Field(default_factory=RunMetrics)
    started_at: AwareDatetime
    finished_at: AwareDatetime
    error_details: NonEmptyStr | None = None

    # convenience accessors (single source of truth is run_config)
    @property
    def model_id(self) -> str:
        return self.run_config.model_id

    @property
    def model_version(self) -> str:
        return self.run_config.model_version

    @property
    def prompt_version(self) -> str:
        return self.run_config.prompt_version

    @model_validator(mode="before")
    @classmethod
    def _non_completed_means_error(cls, data: Any) -> Any:
        if isinstance(data, dict) and data.get("test_verdict") is None:
            try:
                status = RunStatus(data.get("run_status"))
            except (ValueError, TypeError):
                return data
            if status != RunStatus.COMPLETED:
                return {**data, "test_verdict": TestVerdict.ERROR}
        return data

    @model_validator(mode="after")
    def _rules(self) -> "RunRecord":
        completed = self.run_status == RunStatus.COMPLETED
        if completed and self.test_verdict is None:
            raise ValueError("a COMPLETED run needs a test_verdict")
        if not completed:
            if self.test_verdict != TestVerdict.ERROR:
                raise ValueError(f"run_status {self.run_status.value} forces test_verdict=ERROR")
            if self.agent_status is not None or self.decision_report_ref is not None:
                raise ValueError("a non-completed run has no agent_status or DecisionReport")
        if self.run_status in (RunStatus.ERROR, RunStatus.TIMEOUT) and not self.error_details:
            raise ValueError("ERROR/TIMEOUT runs require error_details")
        if self.test_verdict == TestVerdict.ERROR and not self.error_details:
            raise ValueError("verdict ERROR requires error_details")
        if self.test_verdict == TestVerdict.REVIEW and not (self.evaluation_ids or self.finding_ids):
            raise ValueError("REVIEW must reference the evaluation or finding that holds the reason")
        if self.output_reference and not self.output_sanitized:
            raise ValueError("raw output must never be persisted: output_reference requires output_sanitized=true")
        if self.sanitization_summary is not None and not self.output_sanitized:
            raise ValueError("sanitization_summary without output_sanitized=true")
        if self.finished_at < self.started_at:
            raise ValueError("finished_at is before started_at")
        if self.run_config_hash != self.run_config.fingerprint():
            raise ValueError("run_config_hash does not match run_config")
        return self


def validate_run_references(run: RunRecord, registry: ProfileRegistry) -> SecurityProfile:
    """Checks that cannot be done from the record alone: the referenced profile
    version must exist, and cloud runs need a profile that allows external transfer."""
    profile = registry.get(run.security_profile_id, run.security_profile_version)
    if run.run_config.provider == ModelProvider.CLOUD and not profile.external_data_transfer:
        raise ValueError(
            f"profile {profile.security_profile_id} v{profile.version} forbids external data transfer; "
            "a CLOUD model cannot run under it"
        )
    return profile
