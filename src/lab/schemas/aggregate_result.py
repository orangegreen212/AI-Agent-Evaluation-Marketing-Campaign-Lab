"""Result for one test on one model across its repeats."""
from __future__ import annotations

from typing import Sequence

from pydantic import Field, model_validator

from .base import SCHEMA_VERSION, Id, LabModel, ModelId, NonEmptyStr, VersionedModel
from .enums import AggregateStatus, ConfirmationStatus, RunStatus, Severity, TestVerdict
from .finding import Finding
from .run_record import RunRecord


class VerdictCounts(LabModel):
    passed: int = Field(default=0, ge=0)
    failed: int = Field(default=0, ge=0)
    review: int = Field(default=0, ge=0)
    error: int = Field(default=0, ge=0)  # runs with verdict ERROR, includes the two below
    timeout: int = Field(default=0, ge=0)
    cancelled: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def _subsets(self) -> "VerdictCounts":
        if self.timeout + self.cancelled > self.error:
            raise ValueError("timeout + cancelled cannot exceed error")
        return self

    @property
    def substantive(self) -> int:
        return self.passed + self.failed + self.review


class AggregateResult(VersionedModel):
    test_id: Id
    model_id: ModelId
    suite_version: NonEmptyStr
    security_profile_id: Id
    security_profile_version: int = Field(ge=1)
    aggregate_status: AggregateStatus
    counts: VerdictCounts
    expected_repeats: int = Field(ge=1)
    completed_repeats: int = Field(ge=0)  # runs that completed with PASS/FAIL/REVIEW
    blocking_finding_ids: list[Id] = Field(default_factory=list)
    unconfirmed_critical_finding_ids: list[Id] = Field(default_factory=list)

    @model_validator(mode="after")
    def _consistency(self) -> "AggregateResult":
        c, s = self.counts, self.aggregate_status
        if c.substantive != self.completed_repeats:
            raise ValueError("completed_repeats must equal passed + failed + review")
        if c.substantive + c.error > self.expected_repeats:
            raise ValueError("more runs than expected_repeats")
        if bool(self.blocking_finding_ids) != (s == AggregateStatus.BLOCKED):
            raise ValueError("BLOCKED if and only if blocking_finding_ids is non-empty")
        full = c.substantive == self.expected_repeats and c.error == 0
        if s in (AggregateStatus.PASS, AggregateStatus.FAIL, AggregateStatus.REVIEW):
            n = {AggregateStatus.PASS: c.passed, AggregateStatus.FAIL: c.failed, AggregateStatus.REVIEW: c.review}[s]
            if not (full and n == self.expected_repeats):
                raise ValueError(f"{s.value} requires all expected repeats to carry that verdict")
        if s == AggregateStatus.FLAKY and not (full and sum(x > 0 for x in (c.passed, c.failed, c.review)) > 1):
            raise ValueError("FLAKY requires all repeats completed with differing verdicts")
        if s == AggregateStatus.ERROR and not (c.substantive == 0 and c.error > 0):
            raise ValueError("ERROR requires runs and no substantive result")
        if s == AggregateStatus.INCOMPLETE and full:
            raise ValueError("INCOMPLETE requires missing repeats or technical failures")
        return self

    def report_line(self) -> str:
        """Absolute numbers with denominators, e.g. 'PASS 4/5, FAIL 1/5, REVIEW 0/5, ERROR 0/5'."""
        n, c = self.expected_repeats, self.counts
        return f"PASS {c.passed}/{n}, FAIL {c.failed}/{n}, REVIEW {c.review}/{n}, ERROR {c.error}/{n}"


def aggregate_runs(
    runs: Sequence[RunRecord],
    *,
    expected_repeats: int,
    findings: Sequence[Finding] = (),
) -> AggregateResult:
    """Priority: BLOCKED > ERROR > INCOMPLETE > FLAKY > uniform PASS/FAIL/REVIEW."""
    if expected_repeats < 1:
        raise ValueError("expected_repeats must be >= 1")
    if not runs:
        raise ValueError("no runs to aggregate")
    first = runs[0]
    key = lambda r: (r.test_id, r.model_id, r.suite_version, r.security_profile_id, r.security_profile_version)  # noqa: E731
    if any(key(r) != key(first) for r in runs):
        raise ValueError("runs differ in test, model, suite or security profile")
    indices = [r.repeat_index for r in runs]
    if len(set(indices)) != len(indices):
        raise ValueError("duplicate repeat_index")
    if any(i >= expected_repeats for i in indices):
        raise ValueError("repeat_index exceeds expected_repeats")

    run_ids = {r.run_id for r in runs}
    relevant = [f for f in findings if f.run_id in run_ids and f.severity == Severity.CRITICAL]
    blocking = [f.finding_id for f in relevant if f.confirmation_status == ConfirmationStatus.CONFIRMED]
    unconfirmed = [f.finding_id for f in relevant if f.confirmation_status == ConfirmationStatus.UNCONFIRMED]

    counts = VerdictCounts(
        passed=sum(r.test_verdict == TestVerdict.PASS for r in runs),
        failed=sum(r.test_verdict == TestVerdict.FAIL for r in runs),
        review=sum(r.test_verdict == TestVerdict.REVIEW for r in runs),
        error=sum(r.test_verdict == TestVerdict.ERROR for r in runs),
        timeout=sum(r.run_status == RunStatus.TIMEOUT for r in runs),
        cancelled=sum(r.run_status == RunStatus.CANCELLED for r in runs),
    )
    if blocking:
        status = AggregateStatus.BLOCKED
    elif counts.substantive == 0:
        status = AggregateStatus.ERROR
    elif counts.error > 0 or counts.substantive < expected_repeats:
        status = AggregateStatus.INCOMPLETE
    elif sum(x > 0 for x in (counts.passed, counts.failed, counts.review)) > 1:
        status = AggregateStatus.FLAKY
    else:
        status = (AggregateStatus.PASS if counts.passed else
                  AggregateStatus.FAIL if counts.failed else AggregateStatus.REVIEW)
    return AggregateResult(
        schema_version=SCHEMA_VERSION, test_id=first.test_id, model_id=first.model_id,
        suite_version=first.suite_version, security_profile_id=first.security_profile_id,
        security_profile_version=first.security_profile_version, aggregate_status=status,
        counts=counts, expected_repeats=expected_repeats, completed_repeats=counts.substantive,
        blocking_finding_ids=blocking, unconfirmed_critical_finding_ids=unconfirmed,
    )
