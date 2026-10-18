"""Structured answer of the AI Ad Budget Advisor and its validators."""
from __future__ import annotations

import math
from datetime import date
from typing import Iterable

from pydantic import Field, model_validator

from .base import Id, LabModel, ModelId, NonEmptyStr, VersionedModel
from .enums import AgentStatus, RiskLevel
from .security_profile import SecurityProfile


class Period(LabModel):
    start: date
    end: date

    @model_validator(mode="after")
    def _ordered(self) -> "Period":
        if self.end < self.start:
            raise ValueError("period end is before start")
        return self


class Evidence(LabModel):
    claim: NonEmptyStr
    metric_id: Id
    source_calc_id: Id
    value: float | None = Field(default=None, allow_inf_nan=False)
    value_undefined_reason: NonEmptyStr | None = None
    period: Period
    limitations: list[NonEmptyStr] = Field(default_factory=list)

    @model_validator(mode="after")
    def _undefined_needs_reason(self) -> "Evidence":
        if self.value is None and not self.value_undefined_reason:
            raise ValueError("value is None: value_undefined_reason is required")
        if self.value is not None and self.value_undefined_reason:
            raise ValueError("value_undefined_reason set although value is present")
        return self


class ActionItem(LabModel):
    action: NonEmptyStr
    action_type: Id
    rationale: NonEmptyStr
    expected_outcome: NonEmptyStr
    risk_level: RiskLevel
    # The model's claim. Never a source of truth; see apply_approval_policy().
    requires_approval_claimed: bool
    requires_approval_effective: bool | None = None
    approval_mismatch: bool | None = None

    @model_validator(mode="after")
    def _policy_fields_together(self) -> "ActionItem":
        eff, mis = self.requires_approval_effective, self.approval_mismatch
        if (eff is None) != (mis is None):
            raise ValueError("requires_approval_effective and approval_mismatch are set together")
        if eff is not None and mis != (eff != self.requires_approval_claimed):
            raise ValueError("approval_mismatch is inconsistent with claimed/effective values")
        return self


class Traceability(LabModel):
    run_id: Id
    test_id: Id | None = None
    model_id: ModelId
    model_version: NonEmptyStr
    prompt_version: NonEmptyStr
    security_profile_id: Id
    security_profile_version: int = Field(ge=1)
    dataset_ref: NonEmptyStr


class DecisionReport(VersionedModel):
    agent_status: AgentStatus
    summary: NonEmptyStr
    evidence: list[Evidence] = Field(default_factory=list)
    limitations_uncertainty: list[NonEmptyStr] = Field(default_factory=list)
    risks: list[NonEmptyStr] = Field(default_factory=list)
    action_plan: list[ActionItem] = Field(default_factory=list)
    traceability: Traceability

    @model_validator(mode="after")
    def _status_rules(self) -> "DecisionReport":
        if self.agent_status == AgentStatus.RECOMMEND and not self.evidence:
            raise ValueError("RECOMMEND requires at least one evidence item")
        if self.agent_status in (AgentStatus.CAUTION, AgentStatus.INSUFFICIENT_DATA) and not self.limitations_uncertainty:
            raise ValueError(f"{self.agent_status.value} requires limitations_uncertainty")
        return self


# ---- validation against deterministic calculations -------------------------

class ComputedMetric(LabModel):
    calc_id: Id
    metric_id: Id
    value: float | None = Field(default=None, allow_inf_nan=False)
    period: Period


class EvidenceValidationError(ValueError):
    def __init__(self, issues: list[str]) -> None:
        super().__init__("; ".join(issues))
        self.issues = issues


def validate_evidence(
    report: DecisionReport,
    computed: Iterable[ComputedMetric],
    *,
    rel_tol: float = 1e-6,
    abs_tol: float = 1e-9,
) -> None:
    """Every evidence item must point to a metric the analytics engine really
    computed, with the same value and period. Anything else is rejected
    (callers may route a rejection to REVIEW)."""
    by_id = {c.calc_id: c for c in computed}
    issues: list[str] = []
    for i, ev in enumerate(report.evidence):
        calc = by_id.get(ev.source_calc_id)
        if calc is None:
            issues.append(f"evidence[{i}]: unknown source_calc_id {ev.source_calc_id!r}")
            continue
        if calc.metric_id != ev.metric_id:
            issues.append(f"evidence[{i}]: metric_id {ev.metric_id!r} != computed {calc.metric_id!r}")
        if calc.period != ev.period:
            issues.append(f"evidence[{i}]: period differs from computed period")
        if (calc.value is None) != (ev.value is None):
            issues.append(f"evidence[{i}]: value presence differs from computed value")
        elif calc.value is not None and not math.isclose(calc.value, ev.value, rel_tol=rel_tol, abs_tol=abs_tol):
            issues.append(f"evidence[{i}]: value {ev.value} != computed {calc.value}")
    if issues:
        raise EvidenceValidationError(issues)


def apply_approval_policy(report: DecisionReport, profile: SecurityProfile) -> DecisionReport:
    """Resolve the effective approval requirement from the profile and record
    any mismatch with the model's claim. The claim never lowers the requirement."""
    items = []
    for item in report.action_plan:
        effective = profile.action_requires_approval(item.action_type)
        items.append(
            ActionItem.model_validate(
                {
                    **item.model_dump(),
                    "requires_approval_effective": effective,
                    "approval_mismatch": effective != item.requires_approval_claimed,
                }
            )
        )
    return report.model_copy(update={"action_plan": items})
