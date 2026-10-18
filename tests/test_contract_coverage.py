"""Phase 0 gate: every contract test named in the approved spec must exist in the suite."""
import ast
from pathlib import Path

REQUIRED = """
test_invalid_agent_status_rejected test_noncompleted_run_forces_error test_statuses_remain_independent
test_schema_version_required test_old_schema_version_migrates
test_run_requires_security_profile_version test_security_profile_version_must_exist
test_approval_policy_overrides_model_claim test_untrusted_data_cannot_authorize_tools
test_discussed_forbidden_tool_not_executed
test_finding_requires_severity test_llm_judge_cannot_confirm_critical test_code_can_confirm_validated_canary
test_human_override_requires_reason test_unconfirmed_critical_sets_under_review
test_critical_finding_blocks_profile test_blocked_persists_across_tests test_unblock_requires_investigation_and_retest
test_mixed_pass_fail_is_flaky test_pass_review_is_flaky test_pass_error_is_incomplete
test_pass_fail_error_is_incomplete test_all_errors_aggregate_to_error test_missing_repeats_is_incomplete
test_unknown_metric_reference_rejected test_evidence_value_must_match_computed_value
test_evaluation_records_judge_version test_decision_report_absent_on_error_run
test_raw_output_never_persisted test_canary_not_in_plaintext_logs test_secret_patterns_masked_before_write
""".split()


def test_every_contract_test_from_the_spec_exists():
    defined = set()
    for path in Path(__file__).parent.rglob("test_*.py"):
        defined |= {n.name for n in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
                    if isinstance(n, ast.FunctionDef)}
    assert not [name for name in REQUIRED if name not in defined]


def test_required_list_has_no_duplicates():
    assert len(REQUIRED) == len(set(REQUIRED)) == 31
