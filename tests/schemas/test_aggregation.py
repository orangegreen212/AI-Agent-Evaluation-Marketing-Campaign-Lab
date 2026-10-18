import pytest

from lab.schemas import AggregateResult, aggregate_runs
from lab.schemas.enums import AggregateStatus as A


@pytest.fixture
def runs(make_run):
    def _runs(*verdicts, n=None):
        out = []
        for i, v in enumerate(verdicts):
            if v in ("PASS", "FAIL", "REVIEW"):
                extra = {"evaluation_ids": ["ev-1"]} if v == "REVIEW" else {}
                out.append(make_run(run_id=f"run-{i}", repeat_index=i, test_verdict=v, **extra))
            else:  # technical failure
                status = "ERROR" if v == "ERROR" else v
                out.append(make_run(run_id=f"run-{i}", repeat_index=i, run_status=status, test_verdict=None,
                                    error_details="technical failure"))
        return out
    return _runs


def agg(rs, n=3, findings=()):
    return aggregate_runs(rs, expected_repeats=n, findings=findings)


def test_uniform_results(runs):
    assert agg(runs("PASS", "PASS", "PASS")).aggregate_status == A.PASS
    assert agg(runs("FAIL", "FAIL", "FAIL")).aggregate_status == A.FAIL
    assert agg(runs("REVIEW", "REVIEW", "REVIEW")).aggregate_status == A.REVIEW


def test_mixed_pass_fail_is_flaky(runs):
    assert agg(runs("PASS", "FAIL", "PASS")).aggregate_status == A.FLAKY


def test_pass_review_is_flaky(runs):
    assert agg(runs("PASS", "PASS", "REVIEW")).aggregate_status == A.FLAKY


def test_pass_error_is_incomplete(runs):
    assert agg(runs("PASS", "ERROR", "PASS")).aggregate_status == A.INCOMPLETE


def test_pass_fail_error_is_incomplete(runs):
    """Flakiness cannot be claimed while data is missing."""
    assert agg(runs("PASS", "FAIL", "ERROR")).aggregate_status == A.INCOMPLETE


def test_all_errors_aggregate_to_error(runs):
    r = agg(runs("ERROR", "TIMEOUT", "CANCELLED"))
    assert r.aggregate_status == A.ERROR
    assert (r.counts.error, r.counts.timeout, r.counts.cancelled) == (3, 1, 1)


def test_missing_repeats_is_incomplete(runs):
    r = agg(runs("PASS", "PASS"), n=5)
    assert r.aggregate_status == A.INCOMPLETE and r.completed_repeats == 2


def test_critical_in_any_repeat_blocks_over_everything(runs, confirmed_critical, make_finding):
    rs = runs("PASS", "FAIL", "PASS")
    finding = confirmed_critical.model_copy(update={"run_id": "run-1"})
    r = agg(rs, findings=[finding])
    assert r.aggregate_status == A.BLOCKED and r.blocking_finding_ids == ["f-1"]
    # BLOCKED also outranks ERROR and INCOMPLETE
    assert agg(runs("ERROR", "ERROR", "PASS"), findings=[confirmed_critical.model_copy(update={"run_id": "run-2"})]
               ).aggregate_status == A.BLOCKED


def test_unconfirmed_critical_does_not_block_but_is_reported(runs, make_finding):
    r = agg(runs("PASS", "PASS", "PASS"), findings=[make_finding(run_id="run-0")])
    assert r.aggregate_status == A.PASS and r.unconfirmed_critical_finding_ids == ["f-1"]


def test_findings_of_other_runs_are_ignored(runs, confirmed_critical):
    other = confirmed_critical.model_copy(update={"run_id": "someone-elses-run"})
    assert agg(runs("PASS", "PASS", "PASS"), findings=[other]).aggregate_status == A.PASS


def test_report_uses_absolute_numbers_with_denominator(runs):
    r = agg(runs("PASS", "PASS", "PASS", "FAIL", "PASS"), n=5)
    assert r.report_line() == "PASS 4/5, FAIL 1/5, REVIEW 0/5, ERROR 0/5"


def test_inputs_are_validated(runs, make_run):
    with pytest.raises(ValueError, match="no runs"):
        agg([])
    with pytest.raises(ValueError, match="duplicate repeat_index"):
        agg([make_run(run_id="a", repeat_index=0), make_run(run_id="b", repeat_index=0)])
    with pytest.raises(ValueError, match="exceeds expected_repeats"):
        agg([make_run(repeat_index=3)], n=3)
    with pytest.raises(ValueError, match="differ"):
        agg([make_run(run_id="a", repeat_index=0), make_run(run_id="b", repeat_index=1, test_id="EVAL-002")])


def test_aggregate_result_rejects_inconsistent_status():
    base = dict(schema_version="1.0", test_id="EVAL-001", model_id="m", suite_version="s1",
                security_profile_id="default", security_profile_version=1, expected_repeats=3)
    with pytest.raises(ValueError, match="requires all expected repeats"):
        AggregateResult(**base, aggregate_status="PASS", counts=dict(passed=2, failed=1), completed_repeats=3)
    with pytest.raises(ValueError, match="BLOCKED if and only if"):
        AggregateResult(**base, aggregate_status="BLOCKED", counts=dict(passed=3), completed_repeats=3)
    with pytest.raises(ValueError, match="FLAKY requires"):
        AggregateResult(**base, aggregate_status="FLAKY", counts=dict(passed=3), completed_repeats=3)
