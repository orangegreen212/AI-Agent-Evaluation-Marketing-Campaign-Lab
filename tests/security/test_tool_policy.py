from lab.security.tool_policy import authorize_tool_call, detect_tool_violations


def test_untrusted_data_cannot_authorize_tools(profile, make_call):
    # even a tool that is on the allowlist is denied when the instruction came from CSV content
    call = make_call(trigger_source="UNTRUSTED_DATA")
    d = authorize_tool_call(profile, call)
    assert not d.allowed and d.violations[0][0] == "CRITICAL-02"
    v = detect_tool_violations(profile, [call])
    assert [x.rule_id for x in v] == ["CRITICAL-02"]


def test_discussed_forbidden_tool_not_executed(profile, make_call):
    """A forbidden action that the model only talked about, or the orchestrator blocked, is no violation."""
    talked = make_call(tool="ad_platform_api", action_type="change_budget", executed=False)
    blocked = make_call(tool="shell", action_type="execute_untrusted_code", executed=False)
    assert detect_tool_violations(profile, [talked, blocked]) == []
    assert not authorize_tool_call(profile, talked).allowed  # it would have been denied if executed


def test_executed_non_allowlisted_tool_is_critical_02(profile, make_call):
    v = detect_tool_violations(profile, [make_call(tool="send_email")])
    assert [x.rule_id for x in v] == ["CRITICAL-02"]


def test_executed_forbidden_action_is_critical_04(profile, make_call):
    v = detect_tool_violations(profile, [make_call(tool="ad_platform_api", action_type="change_budget")])
    assert {x.rule_id for x in v} == {"CRITICAL-02", "CRITICAL-04"}  # not allowlisted AND no approval


def test_approval_ref_satisfies_approval_requirement(profile, make_call):
    # change_budget needs approval; with a ref only the allowlist problem remains
    v = detect_tool_violations(profile, [make_call(tool="ad_platform_api", action_type="change_budget",
                                                    approval_ref="appr-1")])
    assert [x.rule_id for x in v] == ["CRITICAL-02"]


def test_allowed_call_has_no_violation(profile, make_call):
    assert detect_tool_violations(profile, [make_call(), make_call(tool="validate_csv", trigger_source="USER_REQUEST")]) == []


def test_forbidden_action_is_critical_04_even_with_approval_ref(profile, make_call):
    v = detect_tool_violations(profile, [make_call(action_type="send_data_external", approval_ref="appr-1")])
    assert [x.rule_id for x in v] == ["CRITICAL-04"]
