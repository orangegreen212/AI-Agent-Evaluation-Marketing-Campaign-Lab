import pytest
from pydantic import ValidationError

from conftest import T0
from lab.schemas import (
    ModelProfileRecord, apply_findings, lift_restriction, new_model_profile_record,
)
from lab.schemas.enums import ModelProfileStatus as S

M, P = "lmstudio/test-model", "default"


def fresh():
    return new_model_profile_record(M, P)


def test_critical_finding_blocks_profile(confirmed_critical):
    rec = apply_findings(fresh(), [confirmed_critical], profile_version=1, at=T0)
    assert rec.status == S.BLOCKED
    assert rec.history[-1].trigger_finding_id == "f-1"


def test_blocked_persists_across_tests(confirmed_critical):
    rec = apply_findings(fresh(), [confirmed_critical], profile_version=1, at=T0)
    # later: a different test passes, nothing new is reported -> still blocked
    again = apply_findings(rec, [], profile_version=1, at=T0)
    assert again.status == S.BLOCKED and again is rec
    assert apply_findings(rec, [confirmed_critical], profile_version=1, at=T0).history == rec.history


def test_unconfirmed_critical_sets_under_review(make_finding):
    rec = apply_findings(fresh(), [make_finding()], profile_version=1, at=T0)
    assert rec.status == S.UNDER_REVIEW
    # a later confirmation escalates to BLOCKED
    escalated = apply_findings(rec, [make_finding().confirm(method="HUMAN", by="olga", reason="seen it", at=T0)],
                               profile_version=1, at=T0)
    assert escalated.status == S.BLOCKED and len(escalated.history) == 2


def test_dismissed_and_major_findings_do_not_restrict(make_finding):
    dismissed = make_finding().dismiss(by="olga", reason="fixture text", at=T0)
    major = make_finding(finding_id="f-2", rule_id="MAJOR-PII-01", severity="MAJOR")
    assert apply_findings(fresh(), [dismissed, major], profile_version=1, at=T0).status == S.ALLOWED


def test_unblock_requires_investigation_and_retest(confirmed_critical):
    from lab.schemas import Transition
    blocked = apply_findings(fresh(), [confirmed_critical], profile_version=1, at=T0)
    kwargs = dict(profile_version=1, at=T0, reason="fixed prompt leak", approved_by="olga")
    with pytest.raises(ValidationError, match="leaving BLOCKED requires"):
        lift_restriction(blocked, investigation_ref="inv-1", **kwargs)  # no fix, no retest
    with pytest.raises(ValidationError, match="retest_run_ids"):
        lift_restriction(blocked, investigation_ref="inv-1", fix_ref="pr-12", **kwargs)
    with pytest.raises(ValidationError, match="fix_ref"):
        lift_restriction(blocked, investigation_ref="inv-1", retest_run_ids=["r9"], **kwargs)
    with pytest.raises(ValidationError):  # empty strings do not count as documentation
        lift_restriction(blocked, investigation_ref="", fix_ref="pr-12", retest_run_ids=["r9"], **kwargs)
    with pytest.raises(ValidationError, match="investigation_ref"):
        Transition(from_status="BLOCKED", to_status="ALLOWED", security_profile_version=1, actor="olga",
                   reason="r", at=T0, fix_ref="pr-12", retest_run_ids=["r9"], approved_by="olga")
    ok = lift_restriction(blocked, investigation_ref="inv-1", fix_ref="pr-12", retest_run_ids=["r9", "r10"], **kwargs)
    assert ok.status == S.ALLOWED and ok.history[-1].approved_by == "olga"


def test_clearing_review_needs_a_documented_investigation(make_finding):
    from lab.schemas import Transition
    review = apply_findings(fresh(), [make_finding()], profile_version=1, at=T0)
    with pytest.raises(ValidationError, match="clearing UNDER_REVIEW"):
        Transition(from_status="UNDER_REVIEW", to_status="ALLOWED", security_profile_version=1, actor="olga",
                   reason="looks fine", at=T0)
    cleared = lift_restriction(review, profile_version=1, at=T0, reason="false positive", approved_by="olga",
                               investigation_ref="inv-2")
    assert cleared.status == S.ALLOWED


def test_status_cannot_be_forged_without_history():
    with pytest.raises(ValidationError, match="does not match the last transition"):
        ModelProfileRecord(schema_version="1.0", model_id=M, security_profile_id=P, status="ALLOWED",
                           history=[dict(from_status="ALLOWED", to_status="BLOCKED", security_profile_version=1,
                                         actor="system", reason="r", at=T0, trigger_finding_id="f-1")])
    with pytest.raises(ValidationError, match="chain"):
        ModelProfileRecord(schema_version="1.0", model_id=M, security_profile_id=P, status="ALLOWED",
                           history=[dict(from_status="BLOCKED", to_status="ALLOWED", security_profile_version=1,
                                         actor="x", reason="r", at=T0, investigation_ref="i", fix_ref="f",
                                         retest_run_ids=["r"], approved_by="x")])
