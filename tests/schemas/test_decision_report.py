import pytest
from pydantic import ValidationError

from lab.schemas import (
    ComputedMetric, DecisionReport, EvidenceValidationError, apply_approval_policy, validate_evidence,
)

PERIOD = {"start": "2026-09-01", "end": "2026-09-30"}


def computed(**kw):
    base = dict(calc_id="calc-1", metric_id="roas", value=2.5, period=PERIOD)
    base.update(kw)
    return ComputedMetric(**base)


def test_unknown_metric_reference_rejected(make_report):
    report = make_report()
    with pytest.raises(EvidenceValidationError, match="unknown source_calc_id"):
        validate_evidence(report, [computed(calc_id="calc-other")])
    with pytest.raises(EvidenceValidationError, match="metric_id"):
        validate_evidence(report, [computed(metric_id="cpa")])
    validate_evidence(report, [computed()])  # the happy path passes


def test_evidence_value_must_match_computed_value(make_report):
    """Existence is not enough: an invented number attached to a real metric is rejected."""
    with pytest.raises(EvidenceValidationError, match="value 2.5 != computed 1.9"):
        validate_evidence(make_report(), [computed(value=1.9)])
    with pytest.raises(EvidenceValidationError, match="period"):
        validate_evidence(make_report(), [computed(period={"start": "2026-08-01", "end": "2026-08-31"})])


def test_undefined_metric_must_stay_undefined(make_report, make_evidence):
    """spend = 0 gives undefined ROAS: the agent may not invent a number for it."""
    report = make_report(evidence=[make_evidence(value=3.0)])
    with pytest.raises(EvidenceValidationError, match="value presence"):
        validate_evidence(report, [computed(value=None)])
    honest = make_report(evidence=[make_evidence(value=None, value_undefined_reason="spend is zero")])
    validate_evidence(honest, [computed(value=None)])


def test_evidence_without_value_needs_a_reason(make_evidence):
    from lab.schemas import Evidence
    with pytest.raises(ValidationError, match="value_undefined_reason"):
        Evidence(**make_evidence(value=None))


def test_nan_values_are_rejected(make_evidence):
    from lab.schemas import Evidence
    with pytest.raises(ValidationError):
        Evidence(**make_evidence(value=float("nan")))


def test_approval_policy_overrides_model_claim(make_report, profile):
    risky = dict(action="Raise budget by 50%", action_type="change_budget", rationale="high ROAS",
                 expected_outcome="more revenue", risk_level="HIGH", requires_approval_claimed=False)
    unknown = {**risky, "action": "Do something new", "action_type": "brand_new_action"}
    report = apply_approval_policy(make_report(action_plan=[risky, unknown]), profile)
    a, b = report.action_plan
    assert a.requires_approval_claimed is False
    assert a.requires_approval_effective is True and a.approval_mismatch is True
    assert b.requires_approval_effective is True  # unknown actions fail safe
    # an action the profile exempts is not forced, and a matching claim is no mismatch
    ok = apply_approval_policy(make_report(), profile).action_plan[0]
    assert ok.requires_approval_effective is False and ok.approval_mismatch is False


def test_overclaiming_approval_is_also_recorded_as_mismatch(make_report, profile):
    item = dict(action="Monitor ROAS", action_type="monitor_metric", rationale="r", expected_outcome="e",
                risk_level="LOW", requires_approval_claimed=True)
    out = apply_approval_policy(make_report(action_plan=[item]), profile).action_plan[0]
    assert out.requires_approval_effective is False and out.approval_mismatch is True


def test_forged_effective_flags_are_rejected(make_report):
    item = dict(action="Raise budget", action_type="change_budget", rationale="r", expected_outcome="e",
                risk_level="HIGH", requires_approval_claimed=False,
                requires_approval_effective=False, approval_mismatch=True)
    with pytest.raises(ValidationError, match="inconsistent"):
        make_report(action_plan=[item])


def test_status_dependent_requirements(make_report):
    with pytest.raises(ValidationError, match="RECOMMEND requires"):
        make_report(evidence=[])
    with pytest.raises(ValidationError, match="requires limitations_uncertainty"):
        make_report(agent_status="CAUTION", limitations_uncertainty=[])
    with pytest.raises(ValidationError, match="requires limitations_uncertainty"):
        make_report(agent_status="INSUFFICIENT_DATA", evidence=[], limitations_uncertainty=[])
    ok = make_report(agent_status="INSUFFICIENT_DATA", evidence=[], limitations_uncertainty=["one record only"])
    assert ok.agent_status.value == "INSUFFICIENT_DATA"


def test_invalid_agent_status_in_report_rejected(make_report):
    with pytest.raises(ValidationError):
        make_report(agent_status="SURE_THING")
