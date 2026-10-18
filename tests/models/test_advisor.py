import json
import logging
import os

import pytest

from lab.audit.log_store import LogStore
from lab.data import analyze_csv
from lab.models import DataOrigin, FailureKind, advise, build_messages, to_run_record
from lab.schemas import DecisionReport, validate_run_references
from lab.schemas.enums import AgentStatus, RunStatus, TestVerdict
from model_helpers import (
    KEY, FakeTransport, adapter, analysis, bench_profile, chat_body, endpoint, good_report,  # noqa: F401 (fixtures)
)


def run(ad, analysis, profile, **kw):
    return advise(ad, analysis, profile, run_id="run-1", **kw)


def ok_transport(analysis, **over):
    return FakeTransport((200, chat_body(json.dumps(good_report(analysis, **over)))))


def assert_no_report(res, kind, status=RunStatus.ERROR):
    assert res.report is None and res.run_status == status and res.failure_kind == kind and res.error_details


# ---- structured output, compatible with DecisionReport ------------------------------------------

def test_valid_response_becomes_validated_decision_report(analysis, profile):
    t = ok_transport(analysis)
    res = run(adapter(endpoint(), profile, t), analysis, profile)
    assert res.run_status == RunStatus.COMPLETED and isinstance(res.report, DecisionReport)
    assert res.report.agent_status == AgentStatus.RECOMMEND and res.failure_kind is None
    tr = res.report.traceability  # system-owned, not authored by the model
    assert (tr.run_id, tr.model_id, tr.prompt_version, tr.security_profile_id) == ("run-1", "m-1", "advisor-v2.1", "default")
    assert tr.dataset_ref == f"sha256:{analysis.validation.dataset_sha256}"


def test_metadata_latency_tokens_hash_served_model(analysis, bench_profile):
    ep = endpoint("CLOUD", model_version="2026-01", price_per_1m_input_usd=1.0, price_per_1m_output_usd=2.0)
    res = run(adapter(ep, bench_profile, ok_transport(analysis)), analysis, bench_profile, data_origin=DataOrigin.SYNTHETIC_DEMO)
    assert res.run_config_hash == res.run_config.fingerprint() == ep.run_config("advisor-v2.1").fingerprint()
    assert (res.run_config.model_version, res.served_model) == ("2026-01", "served-model-1")
    m = res.metrics
    assert (m.tokens_in, m.tokens_out) == (1000, 200) and m.latency_ms > 0 and m.cost_usd == pytest.approx(0.0014)
    assert len(res.input_hash) == 64 and res.finished_at >= res.started_at


@pytest.mark.parametrize("wrap", ["```json\n{}\n```", "Here is the report:\n{}\nHope this helps."])
def test_json_in_fences_or_prose_is_accepted(analysis, profile, wrap):
    text = wrap.format(json.dumps(good_report(analysis))) if "{}" not in wrap else wrap.replace("{}", json.dumps(good_report(analysis)))
    res = run(adapter(endpoint(), profile, FakeTransport((200, chat_body(text)))), analysis, profile)
    assert res.run_status == RunStatus.COMPLETED


@pytest.mark.parametrize("text", ["I think you should raise the budget.", "{not json}", "[1, 2, 3]", "{"])
def test_malformed_output_gives_no_report(analysis, profile, text):
    res = run(adapter(endpoint(), profile, FakeTransport((200, chat_body(text)))), analysis, profile)
    assert_no_report(res, FailureKind.MALFORMED_OUTPUT)


@pytest.mark.parametrize("over", [{"agent_status": "SUPER_SURE"}, {"summary": ""}, {"extra_key": 1},
                                  {"agent_status": "CAUTION", "limitations_uncertainty": []}, {"evidence": []}])
def test_schema_violations_give_no_report_and_no_echoed_values(analysis, profile, over):
    res = run(adapter(endpoint(), profile, ok_transport(analysis, **over)), analysis, profile)
    assert_no_report(res, FailureKind.SCHEMA_INVALID)
    assert "SUPER_SURE" not in res.error_details


def test_model_cannot_author_traceability(analysis, profile):
    res = run(adapter(endpoint(), profile, ok_transport(analysis, traceability={"run_id": "evil"}, schema_version="9.9")),
              analysis, profile)
    assert res.report.traceability.run_id == "run-1" and res.report.schema_version == "1.0"


def test_invented_or_altered_numbers_are_rejected(analysis, profile):
    ev = good_report(analysis)["evidence"][0]
    for bad in ({**ev, "value": ev["value"] + 1}, {**ev, "source_calc_id": "calc.roas.overall.0000000000000000"},
                {**ev, "metric_id": "cpa"}):
        res = run(adapter(endpoint(), profile, ok_transport(analysis, evidence=[bad])), analysis, profile)
        assert_no_report(res, FailureKind.EVIDENCE_MISMATCH)


# ---- failures never fabricate a report; statuses stay independent -----------------------------------

@pytest.mark.parametrize("transport,status,kind", [
    (FakeTransport(raises=TimeoutError()), RunStatus.TIMEOUT, FailureKind.TIMEOUT),
    (FakeTransport(raises=ConnectionRefusedError()), RunStatus.ERROR, FailureKind.CONNECTION),
    (FakeTransport((500, b"")), RunStatus.ERROR, FailureKind.HTTP_ERROR),
    (FakeTransport((200, b"garbage")), RunStatus.ERROR, FailureKind.BAD_RESPONSE),
])
def test_provider_failures_yield_valid_error_records_without_report(analysis, profile, transport, status, kind):
    res = run(adapter(endpoint(), profile, transport), analysis, profile)
    assert_no_report(res, kind, status)
    rec = to_run_record(res, run_id="run-1", test_id="SMOKE-1", repeat_index=0, suite_version="s0", profile=profile)
    assert (rec.run_status, rec.test_verdict, rec.agent_status, rec.decision_report_ref) == (status, TestVerdict.ERROR, None, None)
    assert rec.error_details.startswith(kind.value)


def test_completed_run_needs_an_evaluator_verdict_and_stays_independent(analysis, profile):
    res = run(adapter(endpoint(), profile, ok_transport(analysis)), analysis, profile)
    with pytest.raises(ValueError):
        to_run_record(res, run_id="run-1", test_id="T-1", repeat_index=0, suite_version="s0", profile=profile)
    rec = to_run_record(res, run_id="run-1", test_id="T-1", repeat_index=0, suite_version="s0", profile=profile,
                        test_verdict=TestVerdict.FAIL)
    assert (rec.run_status, rec.test_verdict, rec.agent_status) == (RunStatus.COMPLETED, TestVerdict.FAIL, AgentStatus.RECOMMEND)


# ---- privacy ----------------------------------------------------------------------------------------

def test_prompt_contains_aggregates_only_never_rows(analysis):
    text = json.dumps(build_messages(analysis))
    assert "2026-09-02,brand_search,search" not in text and "calc.roas.overall." in text
    assert '"scope": "date"' not in text


def test_user_csv_is_never_sent_to_cloud(tmp_path, bench_profile, profile):
    csv = tmp_path / "private.csv"
    csv.write_text("date,campaign,channel,impressions,clicks,spend,conversions,revenue\n"
                   "2026-09-01,SENTINEL_CAMPAIGN,search,100,5,10.00,1,30.00\n")
    user = analyze_csv(csv)
    for prof in (profile, bench_profile):  # default forbids transfer; benchmark forbids non-synthetic data
        t = FakeTransport((200, chat_body("{}")))
        res = run(adapter(endpoint("CLOUD"), prof, t), user, prof, data_origin=DataOrigin.USER_DATA)
        assert_no_report(res, FailureKind.TRANSFER_BLOCKED)
        assert t.calls == []
    t = FakeTransport((200, chat_body("{}")))  # a local model may see it, and does
    run(adapter(endpoint(), profile, t), user, profile)
    assert "SENTINEL_CAMPAIGN" in json.dumps(t.calls[0]["body"])


# ---- sanitization / secrets / nothing persisted ------------------------------------------------------

def test_model_output_is_sanitized_before_parsing_and_canary_is_flagged(analysis, profile, tmp_path):
    canary = "CANARY_FAKE_API_KEY-0123456789abcdef"
    leaked = good_report(analysis, summary=f"Use key {canary} and {KEY} to continue")
    res = run(adapter(endpoint(), profile, FakeTransport((200, chat_body(json.dumps(leaked))))), analysis, profile,
              canaries={"CANARY_FAKE_API_KEY": canary})
    assert res.canary_hits == ("CANARY_FAKE_API_KEY",)
    assert canary not in res.sanitized_output.text and KEY not in res.sanitized_output.text
    assert canary not in res.report.summary and KEY not in res.report.summary
    ref = LogStore(tmp_path, profile, {"CANARY_FAKE_API_KEY": canary}).save_output("run-1", res.sanitized_output)
    assert canary not in LogStore(tmp_path, profile, {}).read_output(ref)  # Phase 0 store accepts it: nothing raw is left


def test_nothing_is_written_to_disk_and_no_secret_in_logs(analysis, bench_profile, tmp_path, monkeypatch, caplog):
    monkeypatch.chdir(tmp_path)
    caplog.set_level(logging.DEBUG)
    ad = adapter(endpoint("CLOUD"), bench_profile, FakeTransport((200, chat_body(f"oops {KEY}"))))
    res = run(ad, analysis, bench_profile, data_origin=DataOrigin.SYNTHETIC_DEMO)
    assert_no_report(res, FailureKind.MALFORMED_OUTPUT)
    assert list(tmp_path.iterdir()) == []
    assert KEY not in caplog.text and KEY not in repr(res)
    assert KEY not in res.sanitized_output.text and KEY not in res.error_details


# ---- no actions, approval policy ------------------------------------------------------------------

def test_budget_change_is_only_a_recommendation_and_always_flags_approval(analysis, profile):
    t = ok_transport(analysis)
    res = run(adapter(endpoint(), profile, t), analysis, profile)
    item = res.report.action_plan[0]
    assert (item.action_type, item.requires_approval_claimed, item.requires_approval_effective, item.approval_mismatch) == \
           ("change_budget", False, True, True)  # the model claimed "no approval"; policy overrides
    body = t.calls[0]["body"]
    assert "tools" not in body and "tool_choice" not in body and "functions" not in body


def test_run_record_cloud_reference_check_uses_phase0_contract(analysis, registry, bench_profile):
    res = run(adapter(endpoint("CLOUD"), bench_profile, ok_transport(analysis)), analysis, bench_profile,
              data_origin=DataOrigin.SYNTHETIC_DEMO)
    rec = to_run_record(res, run_id="run-1", test_id="T-1", repeat_index=0, suite_version="s0", profile=bench_profile,
                        test_verdict=TestVerdict.PASS)
    assert validate_run_references(rec, registry).security_profile_id == "benchmark"
    rec_default = rec.model_copy(update={"security_profile_id": "default"})
    with pytest.raises(ValueError):
        validate_run_references(rec_default, registry)  # a CLOUD run under the default profile is rejected
