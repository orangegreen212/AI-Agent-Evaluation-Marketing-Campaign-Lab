"""One verifiable scenario. Expected behaviour (text) and assertions (code) are separate."""
from __future__ import annotations

import re
from typing import Any

from pydantic import Field, model_validator

from .base import Id, LabModel, NonEmptyStr, VersionedModel
from .enums import AssertionType, Severity, TestCategory

CATEGORY_PREFIX = {
    TestCategory.EVALUATION: "EVAL",
    TestCategory.SECURITY: "SEC",
    TestCategory.PRIVACY: "PRIV",
    TestCategory.ETHICS: "ETH",
    TestCategory.BIAS: "BIAS",
}
# Decision: SECURITY and PRIVACY run 5 times, everything else 3 times.
DEFAULT_REPEATS = {
    TestCategory.SECURITY: 5,
    TestCategory.PRIVACY: 5,
    TestCategory.EVALUATION: 3,
    TestCategory.ETHICS: 3,
    TestCategory.BIAS: 3,
}
REQUIRED_REPEATS = {TestCategory.SECURITY: 5, TestCategory.PRIVACY: 5}
_TEST_ID_RE = re.compile(r"^(EVAL|SEC|PRIV|ETH|BIAS)-\d{3}$")


class Assertion(LabModel):
    assertion_id: Id
    type: AssertionType
    params: dict[str, Any] = Field(default_factory=dict)
    blocking: bool = True


class TestCase(VersionedModel):
    __test__ = False  # not a pytest class

    test_id: str
    name: NonEmptyStr
    category: TestCategory
    description: NonEmptyStr
    input_ref: NonEmptyStr
    user_request: NonEmptyStr
    expected_behavior: NonEmptyStr
    assertions: list[Assertion] = Field(default_factory=list)
    # Worst severity this scenario can reveal. The Finding carries the actual severity.
    max_severity_if_failed: Severity
    security_profile_id: Id
    security_profile_version: int = Field(ge=1)
    repeat_count: int = Field(ge=1, le=5)
    enabled: bool = True

    @model_validator(mode="before")
    @classmethod
    def _default_repeats(cls, data: Any) -> Any:
        if isinstance(data, dict) and data.get("repeat_count") is None:
            try:
                category = TestCategory(data.get("category"))
            except (ValueError, TypeError):
                return data
            return {**data, "repeat_count": DEFAULT_REPEATS[category]}
        return data

    @model_validator(mode="after")
    def _rules(self) -> "TestCase":
        m = _TEST_ID_RE.match(self.test_id)
        if not m:
            raise ValueError("test_id must look like SEC-001")
        if m.group(1) != CATEGORY_PREFIX[self.category]:
            raise ValueError(f"test_id prefix {m.group(1)!r} does not match category {self.category.value}")
        required = REQUIRED_REPEATS.get(self.category)
        if required is not None and self.repeat_count != required:
            raise ValueError(f"{self.category.value} tests require repeat_count={required}")
        if self.enabled and not self.assertions:
            raise ValueError("an enabled test needs at least one machine-checkable assertion")
        ids = [a.assertion_id for a in self.assertions]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate assertion_id")
        return self
