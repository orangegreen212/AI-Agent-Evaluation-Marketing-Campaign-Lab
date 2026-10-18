import pytest
from pydantic import ValidationError

from conftest import T0
from lab.schemas import Confirmer


def test_finding_requires_severity(make_finding):
    data = make_finding().model_dump()
    del data["severity"]
    from lab.schemas import Finding
    with pytest.raises(ValidationError, match="severity"):
        Finding.model_validate(data)


def test_unknown_rule_rejected(make_finding):
    with pytest.raises(ValidationError, match="unknown rule_id"):
        make_finding(rule_id="CRITICAL-99")


def test_severity_must_match_rule(make_finding):
    with pytest.raises(ValidationError, match="severity"):
        make_finding(severity="MINOR")
    with pytest.raises(ValidationError, match="severity"):
        make_finding(rule_id="MAJOR-PII-01", severity="CRITICAL")


def test_llm_judge_cannot_confirm_critical(make_finding):
    f = make_finding(detection_method="LLM_JUDGE")
    assert f.confirmation_status == "UNCONFIRMED"
    # the judge cannot even be named as a confirmer
    with pytest.raises(ValidationError):
        make_finding(detection_method="LLM_JUDGE", confirmation_status="CONFIRMED",
                     confirmed_by_method="LLM_JUDGE", confirmed_by="judge-1",
                     confirmation_reason="looks bad", confirmed_at=T0)
    # and code cannot confirm what only the judge detected
    with pytest.raises(ValidationError, match="requires a CODE detection"):
        f.confirm(method=Confirmer.CODE, by="canary_check@1", reason="match", at=T0)
    # a human can
    assert f.confirm(method=Confirmer.HUMAN, by="olga", reason="reviewed answer", at=T0).confirmation_status == "CONFIRMED"


def test_code_can_confirm_validated_canary(make_finding):
    f = make_finding(detection_method="CODE").confirm(
        method=Confirmer.CODE, by="canary_check@1", reason="verbatim canary match", at=T0)
    assert f.confirmation_status == "CONFIRMED" and f.confirmed_by_method == "CODE"


def test_code_cannot_auto_confirm_pii(make_finding):
    f = make_finding(rule_id="MAJOR-PII-01", severity="MAJOR", detection_method="CODE")
    with pytest.raises(ValidationError, match="cannot be confirmed automatically"):
        f.confirm(method=Confirmer.CODE, by="pii_detector@1", reason="regex hit", at=T0)
    assert f.confirm(method=Confirmer.HUMAN, by="olga", reason="real email", at=T0).confirmation_status == "CONFIRMED"


def test_code_cannot_dismiss(make_finding):
    with pytest.raises(ValidationError, match="never dismiss"):
        make_finding(confirmation_status="DISMISSED", confirmed_by_method="CODE", confirmed_by="x",
                     confirmation_reason="r", confirmed_at=T0)


def test_human_override_requires_reason(make_finding):
    f = make_finding()
    for status in ("CONFIRMED", "DISMISSED"):
        with pytest.raises(ValidationError, match="requires method, actor, reason and timestamp"):
            make_finding(confirmation_status=status, confirmed_by_method="HUMAN", confirmed_by="olga",
                         confirmed_at=T0)  # no reason
    assert f.dismiss(by="olga", reason="test fixture string, not a leak", at=T0).confirmation_status == "DISMISSED"


def test_unconfirmed_finding_carries_no_confirmation_fields(make_finding):
    with pytest.raises(ValidationError, match="UNCONFIRMED"):
        make_finding(confirmed_by="olga")


def test_remediation_only_for_confirmed(make_finding):
    with pytest.raises(ValidationError, match="remediation"):
        make_finding(remediation_status="FIXED")


def test_critical_alias_kept_for_spec_compatibility():
    from lab.schemas import CriticalFinding, Finding
    assert CriticalFinding is Finding
