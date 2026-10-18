import copy

import pytest
import yaml
from pydantic import ValidationError

from conftest import ROOT
from lab.schemas import ProfileRegistry, SecurityProfile, UnknownSecurityProfileError


def raw(name="default_v1.yaml"):
    return yaml.safe_load((ROOT / "configs" / "security_profiles" / name).read_text(encoding="utf-8"))


def test_default_profile_validates_and_is_locked_down(profile):
    assert profile.external_data_transfer is False
    assert "change_budget" not in profile.allowed_tools
    assert {"access_ad_account", "execute_untrusted_code", "send_data_external"} <= set(profile.forbidden_actions)
    assert profile.logging_policy.store_raw_output is False


def test_raw_output_storage_cannot_be_enabled():
    data = raw()
    data["logging_policy"]["store_raw_output"] = True
    with pytest.raises(ValidationError):
        SecurityProfile.model_validate(data)


def test_external_transfer_requires_notice():
    data = raw()
    data["external_data_transfer"] = True
    with pytest.raises(ValidationError, match="external_transfer_notice"):
        SecurityProfile.model_validate(data)


def test_overlapping_policy_lists_rejected():
    data = raw()
    data["forbidden_actions"].append("change_budget")
    with pytest.raises(ValidationError, match="disjoint"):
        SecurityProfile.model_validate(data)
    data = raw()
    data["forbidden_actions"].append("compute_aggregates")
    with pytest.raises(ValidationError, match="both allowed and forbidden"):
        SecurityProfile.model_validate(data)


def test_constraints_only_for_allowed_tools():
    data = raw()
    data["tool_constraints"]["send_email"] = {"read_only": False, "max_calls_per_run": 1}
    with pytest.raises(ValidationError, match="not in allowed_tools"):
        SecurityProfile.model_validate(data)


def test_bad_secret_regex_rejected():
    data = raw()
    data["secret_detection_policy"]["patterns"].append({"name": "bad", "regex": "("})
    with pytest.raises(ValidationError, match="invalid secret regex"):
        SecurityProfile.model_validate(data)


def test_registry_lookup_and_duplicates(registry):
    assert registry.has("default", 1) and not registry.has("default", 2)
    with pytest.raises(UnknownSecurityProfileError):
        registry.get("default", 2)
    p = registry.get("default", 1)
    with pytest.raises(ValueError, match="duplicate"):
        ProfileRegistry([p, p])


def test_new_version_does_not_change_old_one(registry):
    data = raw()
    data["version"] = 2
    data["allowed_tools"].append("export_report")
    v2 = SecurityProfile.model_validate(data)
    both = ProfileRegistry([registry.get("default", 1), v2])
    assert "export_report" not in both.get("default", 1).allowed_tools
    assert "export_report" in both.get("default", 2).allowed_tools


def test_benchmark_profile_allows_cloud_with_notice(registry):
    b = registry.get("benchmark", 1)
    assert b.external_data_transfer and "synthetic" in b.external_transfer_notice
    assert b.allowed_tools == registry.get("default", 1).allowed_tools
