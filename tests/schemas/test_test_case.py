import pytest
from pydantic import ValidationError


@pytest.mark.parametrize("category,test_id,expected", [
    ("EVALUATION", "EVAL-001", 3), ("ETHICS", "ETH-001", 3), ("BIAS", "BIAS-001", 3),
    ("SECURITY", "SEC-001", 5), ("PRIVACY", "PRIV-001", 5),
])
def test_default_repeat_counts_by_category(make_test_case, category, test_id, expected):
    assert make_test_case(category=category, test_id=test_id).repeat_count == expected


@pytest.mark.parametrize("category,test_id", [("SECURITY", "SEC-001"), ("PRIVACY", "PRIV-001")])
def test_security_and_privacy_must_run_five_times(make_test_case, category, test_id):
    with pytest.raises(ValidationError, match="require repeat_count=5"):
        make_test_case(category=category, test_id=test_id, repeat_count=3)


def test_repeat_count_range(make_test_case):
    for bad in (0, 6):
        with pytest.raises(ValidationError):
            make_test_case(repeat_count=bad)
    assert make_test_case(repeat_count=4).repeat_count == 4


def test_test_id_must_match_category(make_test_case):
    with pytest.raises(ValidationError, match="does not match category"):
        make_test_case(test_id="SEC-001")
    with pytest.raises(ValidationError, match="must look like"):
        make_test_case(test_id="EVAL-1")


def test_enabled_test_needs_machine_checkable_assertions(make_test_case):
    with pytest.raises(ValidationError, match="assertion"):
        make_test_case(assertions=[])
    assert make_test_case(assertions=[], enabled=False).enabled is False


def test_potential_severity_is_named_max_severity_if_failed(make_test_case):
    case = make_test_case()
    assert case.max_severity_if_failed.value == "MAJOR"
    assert not hasattr(case, "severity")
    with pytest.raises(ValidationError):
        make_test_case(severity="MAJOR")  # the old, ambiguous field name is gone


def test_test_case_requires_profile_reference(make_test_case, registry):
    case = make_test_case()
    assert registry.has(case.security_profile_id, case.security_profile_version)
    assert not registry.has(case.security_profile_id, 7)
