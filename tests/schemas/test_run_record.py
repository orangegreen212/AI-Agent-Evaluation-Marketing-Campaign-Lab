import pytest
from pydantic import ValidationError

from lab.schemas import (
    AgentStatus, RunRecord, UnknownSecurityProfileError, validate_run_references,
)
from lab.schemas.enums import RunStatus, TestVerdict


def test_invalid_agent_status_rejected(make_run):
    with pytest.raises(ValidationError):
        make_run(agent_status="MAYBE")


@pytest.mark.parametrize("status", ["TIMEOUT", "CANCELLED", "ERROR"])
def test_noncompleted_run_forces_error(make_run, status):
    run = make_run(run_status=status, test_verdict=None, error_details="boom")
    assert run.test_verdict == TestVerdict.ERROR


@pytest.mark.parametrize("verdict", ["PASS", "FAIL", "REVIEW"])
def test_noncompleted_run_cannot_be_given_a_passing_verdict(make_run, verdict):
    with pytest.raises(ValidationError, match="forces test_verdict=ERROR"):
        make_run(run_status="TIMEOUT", test_verdict=verdict, error_details="slow")


def test_completed_run_needs_a_verdict(make_run):
    with pytest.raises(ValidationError, match="needs a test_verdict"):
        make_run(test_verdict=None)


def test_statuses_remain_independent(make_run):
    run = make_run(agent_status="INSUFFICIENT_DATA", test_verdict="PASS")
    assert run.agent_status == AgentStatus.INSUFFICIENT_DATA
    assert run.run_status == RunStatus.COMPLETED and run.test_verdict == TestVerdict.PASS


def test_run_requires_security_profile_version(make_run):
    with pytest.raises(ValidationError):
        RunRecord.model_validate({**make_run().model_dump(), "security_profile_version": None})
    data = make_run().model_dump()
    del data["security_profile_version"]
    with pytest.raises(ValidationError):
        RunRecord.model_validate(data)


def test_security_profile_version_must_exist(make_run, registry):
    assert validate_run_references(make_run(), registry).security_profile_id == "default"
    with pytest.raises(UnknownSecurityProfileError):
        validate_run_references(make_run(security_profile_version=99), registry)
    with pytest.raises(UnknownSecurityProfileError):
        validate_run_references(make_run(security_profile_id="nope"), registry)


def test_cloud_model_needs_a_profile_that_allows_external_transfer(make_run, make_config, registry):
    cloud = make_config(provider="CLOUD", model_id="cloud/some-model")
    with pytest.raises(ValueError, match="forbids external data transfer"):
        validate_run_references(make_run(run_config=cloud), registry)
    ok = make_run(run_config=cloud, security_profile_id="benchmark")
    assert validate_run_references(ok, registry).external_data_transfer is True


def test_raw_output_never_persisted(make_run):
    with pytest.raises(ValidationError, match="raw output must never be persisted"):
        make_run(output_reference="outputs/run-1.txt", output_sanitized=False)
    assert make_run(output_reference="outputs/run-1.txt", output_sanitized=True,
                    sanitization_summary={"secret:bearer_token": 1}).output_sanitized


def test_decision_report_absent_on_error_run(make_run):
    run = make_run(run_status="ERROR", test_verdict=None, error_details="adapter failed")
    assert run.agent_status is None and run.decision_report_ref is None
    with pytest.raises(ValidationError, match="no agent_status or DecisionReport"):
        make_run(run_status="ERROR", test_verdict=None, error_details="x", decision_report_ref="reports/run-1.json")
    with pytest.raises(ValidationError, match="no agent_status or DecisionReport"):
        make_run(run_status="TIMEOUT", test_verdict=None, error_details="x", agent_status="RECOMMEND")


def test_error_runs_require_details(make_run):
    with pytest.raises(ValidationError, match="error_details"):
        make_run(run_status="ERROR", test_verdict=None)


def test_review_run_must_point_to_its_reason(make_run):
    with pytest.raises(ValidationError, match="REVIEW must reference"):
        make_run(test_verdict="REVIEW")
    assert make_run(test_verdict="REVIEW", evaluation_ids=["ev-1"]).test_verdict == TestVerdict.REVIEW


def test_run_config_is_saved_and_hash_is_verified(make_run, make_config):
    run = make_run()
    assert run.run_config.temperature == 0.7 and run.model_id == "lmstudio/test-model"
    other = make_config(temperature=0.0)
    with pytest.raises(ValidationError, match="run_config_hash"):
        make_run(run_config=other, run_config_hash=run.run_config_hash)
    assert make_config().fingerprint() == make_config().fingerprint()
    assert make_config().fingerprint() != make_config(seed=1).fingerprint()


def test_finished_before_started_rejected(make_run):
    from datetime import timedelta
    run = make_run()
    with pytest.raises(ValidationError, match="finished_at"):
        make_run(finished_at=run.started_at - timedelta(seconds=1))


def test_unknown_fields_are_rejected(make_run):
    with pytest.raises(ValidationError):
        RunRecord.model_validate({**make_run().model_dump(), "raw_output": "secret"})
