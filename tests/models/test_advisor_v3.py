"""advisor-v3 regression tests. Deterministic: mocked transport, no network, no real model."""
import json

import pytest

from lab.data import analyze_csv
from lab.models import OpenAICompatAdapter
from lab.models.advisor_v3 import (
    MANDATORY_OVERALL, NO_MODEL_CLAIM_LIMITATION, PROMPT_VERSION_V3, _CURRENCY_ASSERTION, advise_v3, assemble_evidence,
    build_messages_v3, system_claim,
)
from lab.schemas.enums import RunStatus
from model_helpers import DEMO, FakeTransport, chat_body, endpoint

from lab.models import FailureKind


def run(text, analysis, profile, **body):
    ad = OpenAICompatAdapter(endpoint(), profile, prompt_version=PROMPT_VERSION_V3,
                             transport=FakeTransport((200, chat_body(text, **body))))
    return advise_v3(ad, analysis, profile, run_id="run-1")


def claims_for(analysis, mids=MANDATORY_OVERALL, skip=()):
    """Model output that cites every mandatory metric, except those in `skip`, with NO factual fields."""
    by = {m.metric_id: m for m in analysis.metrics if m.scope == "overall"}
    ev = [{"claim": f"{mid} overall summary", "source_calc_id": by[mid].calc_id} for mid in mids if mid not in skip]
    return {"agent_status": "CAUTION", "summary": "Overall results are mixed.",
            "evidence": ev, "limitations_uncertainty": ["three days of data"], "risks": ["ROAS may fall"],
            "action_plan": []}


@pytest.fixture(scope="module")
def analysis_():
    return analyze_csv(DEMO)


def overall(analysis, mid):
    return next(m for m in analysis.metrics if m.scope == "overall" and m.metric_id == mid)


# 1. and 2.: defined spend/CPA keep their numeric value under a currency limitation
def test_defined_spend_keeps_value_with_currency_limitation(analysis_):
    m = overall(analysis_, "spend")
    assert m.status.value == "OK" and m.value == 1400.0
    assert any("currency" in lim for lim in m.limitations)  # the currency note is present as a limitation
    evidence, issues = assemble_evidence(claims_for(analysis_), analysis_)
    ev = next(e for e in evidence if e.metric_id == "spend")
    assert ev.value == 1400.0 and ev.value_undefined_reason is None and issues == []


def test_defined_campaign_cpa_keeps_value_with_currency_limitation(analysis_):
    cpa_campaign = next(m for m in analysis_.metrics if m.scope == "campaign" and m.metric_id == "cpa"
                        and m.group_key == "spring_promo")
    assert cpa_campaign.status.value == "OK" and cpa_campaign.value == 61.0
    ev = {"claim": "spring promo CPA", "source_calc_id": cpa_campaign.calc_id}
    evidence, _ = assemble_evidence({"evidence": [ev]}, analysis_)
    got = next(e for e in evidence if e.source_calc_id == cpa_campaign.calc_id)
    assert got.value == 61.0 and got.value_undefined_reason is None


# 3. a genuinely undefined metric keeps its status reason
def test_undefined_metric_keeps_null_and_reason(tmp_path):
    p = tmp_path / "zero.csv"
    p.write_text("date,campaign,channel,impressions,clicks,spend,conversions,revenue\n"
                 "2026-09-01,a,search,100,10,50.00,0,0.00\n")
    an = analyze_csv(p)
    roas = overall(an, "roas")  # defined: revenue 0 / spend 50 = 0.0, used only as a control
    cpa = overall(an, "cpa")
    assert cpa.status.value == "UNDEFINED" and cpa.value is None and cpa.value_undefined_reason
    evidence, _ = assemble_evidence(claims_for(an), an)
    ev = next(e for e in evidence if e.metric_id == "cpa")
    assert ev.value is None and ev.value_undefined_reason == cpa.value_undefined_reason
    assert roas.value is not None


# 4. every mandatory metric is present even if the model omits it
def test_mandatory_metrics_are_present_even_when_model_omits_them(analysis_):
    evidence, issues = assemble_evidence({"evidence": []}, analysis_)
    present = {e.metric_id for e in evidence}
    assert set(MANDATORY_OVERALL) <= present
    assert issues == []  # a missing model narrative is not a model-side error
    for e in evidence:
        if e.metric_id in MANDATORY_OVERALL:
            assert NO_MODEL_CLAIM_LIMITATION in e.limitations and e.claim == system_claim(overall(analysis_, e.metric_id))


def test_cpa_omitted_by_model_is_restored_as_factual_evidence_with_limitation(analysis_, profile):
    rep = claims_for(analysis_, skip=("cpa",))
    res = run(json.dumps(rep), analysis_, profile)
    assert res.run_status == RunStatus.COMPLETED and res.report is not None
    cpa = overall(analysis_, "cpa")
    ev = next(e for e in res.report.evidence if e.source_calc_id == cpa.calc_id)
    assert ev.value == cpa.value and ev.value_undefined_reason is None
    assert NO_MODEL_CLAIM_LIMITATION in ev.limitations  # visible, not hidden


# 5. the model cannot override deterministic facts
@pytest.mark.parametrize("field,val", [("value", 999.0), ("metric_id", "cpa"), ("period", {"start": "2000-01-01", "end": "2000-01-02"}),
                                       ("value_undefined_reason", "x")])
def test_model_cannot_set_factual_fields(analysis_, profile, field, val):
    rep = claims_for(analysis_)
    rep["evidence"][0][field] = val
    res = run(json.dumps(rep), analysis_, profile)
    assert res.report is None and res.failure_kind == FailureKind.EVIDENCE_MISMATCH and field in res.error_details


# 6. valid optional per-group reference resolves to the authoritative value
def test_valid_group_reference_is_resolved(analysis_):
    cpa_c = next(m for m in analysis_.metrics if m.scope == "campaign" and m.metric_id == "cpa" and m.group_key == "spring_promo")
    evidence, issues = assemble_evidence({"evidence": [
        {"claim": "spring promo costs more per conversion", "source_calc_id": cpa_c.calc_id}]}, analysis_)
    row = next(e for e in evidence if e.source_calc_id == cpa_c.calc_id)
    assert row.value == cpa_c.value and row.period.start == cpa_c.period.start


# 7. unknown / malformed references are reported, never trusted
@pytest.mark.parametrize("item", [{"claim": "x", "source_calc_id": "calc.nope.0000"}, {"claim": "x"}, "not-an-object",
                                  {"source_calc_id": "calc.roas.overall.x"}])
def test_unknown_or_malformed_reference_is_an_issue(analysis_, item):
    _, issues = assemble_evidence({"evidence": [item]}, analysis_)
    assert issues and any("evidence[0]" in i for i in issues)


# 8. duplicate references do not create duplicate evidence
def test_duplicate_reference_does_not_duplicate_evidence(analysis_):
    roas = overall(analysis_, "roas")
    item = {"claim": "roas", "source_calc_id": roas.calc_id}
    evidence, issues = assemble_evidence({"evidence": [item, item]}, analysis_)
    assert sum(1 for e in evidence if e.source_calc_id == roas.calc_id) == 1
    assert any("duplicate" in i for i in issues)


# 9. missing mandatory claim is explicit
def test_missing_narrative_is_recorded_as_limitation_not_silently_complete(analysis_):
    evidence, issues = assemble_evidence({"evidence": []}, analysis_)
    assert issues == []
    assert all(NO_MODEL_CLAIM_LIMITATION in e.limitations for e in evidence if e.metric_id in MANDATORY_OVERALL)


def test_system_claims_never_assert_a_currency(analysis_):
    for mid in MANDATORY_OVERALL:
        assert not _CURRENCY_ASSERTION.search(system_claim(overall(analysis_, mid)))


# 10. missing currency does not invalidate a defined number (end to end, mocked model)
def test_currency_limitation_does_not_invalidate_a_report(analysis_, profile):
    res = run(json.dumps(claims_for(analysis_)), analysis_, profile)
    assert res.run_status == RunStatus.COMPLETED
    spend = next(e for e in res.report.evidence if e.metric_id == "spend")
    assert spend.value == 1400.0


# 11. unsupported currency assertion in narrative is rejected
@pytest.mark.parametrize("phrase", ["Spend is 1400 USD", "Budget of $1400", "spend in euros"])
def test_currency_assertion_in_narrative_is_rejected(analysis_, profile, phrase):
    rep = claims_for(analysis_)
    rep["summary"] = phrase
    res = run(json.dumps(rep), analysis_, profile)
    assert res.report is None and res.failure_kind == FailureKind.EVIDENCE_MISMATCH and "currency" in res.error_details


# 12. invalid model output does not bypass schema or sanitization
def test_malformed_json_is_rejected(analysis_, profile):
    res = run("not json at all", analysis_, profile)
    assert res.report is None and res.failure_kind == FailureKind.MALFORMED_OUTPUT


def test_truncated_output_is_rejected(analysis_, profile):
    res = run(json.dumps(claims_for(analysis_)), analysis_, profile, finish_reason="length")
    assert res.report is None and res.failure_kind == FailureKind.MALFORMED_OUTPUT


# 15. version dispatch
def test_v3_has_its_own_version_and_v21_is_unchanged():
    from lab.models import PROMPT_VERSION
    assert PROMPT_VERSION_V3 == "advisor-v3.2" and PROMPT_VERSION == "advisor-v2.1"


def test_v3_payload_has_no_rows_and_same_metric_keys(analysis_):
    data = json.loads(build_messages_v3(analysis_)[1]["content"].split("\n", 1)[1])
    assert "notes" not in data
    assert all({"calc_id", "metric_id", "value", "status", "period"} <= set(r) for r in data["metrics"])


# 16. timeout never reports success
def test_timeout_is_never_a_successful_run(analysis_, profile):
    ad = OpenAICompatAdapter(endpoint(), profile, prompt_version=PROMPT_VERSION_V3,
                             transport=FakeTransport(raises=TimeoutError()))
    res = advise_v3(ad, analysis_, profile, run_id="run-1")
    assert res.report is None and res.run_status == RunStatus.TIMEOUT


# ---- profitability: unsupported interpretation is rejected, correct ROAS explanations pass --------------------------

def _field_for(rep, where, text):
    """Place `text` in one narrative field of a valid report, so every checked location is exercised."""
    if where == "summary":
        rep["summary"] = text
    elif where == "risks":
        rep["risks"] = [text]
    elif where == "limitations":
        rep["limitations_uncertainty"] = [text]
    elif where == "evidence_claim":
        rep["evidence"][0]["claim"] = text
    elif where == "evidence_limitation":
        rep["evidence"][0]["limitations"] = [text]
    elif where in ("action_rationale", "action_outcome", "action_text"):
        key = {"action_rationale": "rationale", "action_outcome": "expected_outcome", "action_text": "action"}[where]
        rep["action_plan"] = [{"action": "review budget", "action_type": "review_report", "rationale": "r",
                               "expected_outcome": "o", "risk_level": "LOW", "requires_approval_claimed": False}]
        rep["action_plan"][0][key] = text
    return rep


UNSUPPORTED_PROFIT = [
    "ROAS 3.25 indicates profitable performance across all channels.",
    "Spend is profitable.",
    "The campaign is profitable overall.",
    "ROAS above 1 means the campaign makes profit.",
    "Net profit is 3.25x spend.",
    "This is unprofitable.",
    "The campaign is profitabel.",
    "Кампания прибыльна.",
    "Проект прибыльный.",
    "Окупаемость доказана.",
    "Кампания убыточна.",
]


@pytest.mark.parametrize("where", ["summary", "risks", "limitations", "evidence_claim", "evidence_limitation",
                                   "action_rationale", "action_outcome"])
@pytest.mark.parametrize("text", UNSUPPORTED_PROFIT)
def test_unsupported_profitability_is_rejected_in_every_narrative_field(analysis_, profile, where, text):
    rep = _field_for(claims_for(analysis_), where, text)
    res = run(json.dumps(rep), analysis_, profile)
    assert res.report is None and res.run_status == RunStatus.ERROR
    assert res.failure_kind == FailureKind.EVIDENCE_MISMATCH
    assert "unsupported profitability assertion" in res.error_details
    assert text not in res.error_details  # the error names the field, never echoes model text


def test_no_unsupported_profit_text_reaches_a_completed_report(analysis_, profile):
    res = run(json.dumps(_field_for(claims_for(analysis_), "summary", "Campaign is profitable.")), analysis_, profile)
    assert res.run_status != RunStatus.COMPLETED


@pytest.mark.parametrize("text", [
    "ROAS 3.25 means 3.25 units of revenue per unit of ad spend.",
    "ROAS 3.25 does not prove profitability; costs beyond ad spend are not in the data.",
    "ROAS 3.25 означает 3.25 единицы выручки на единицу рекламных расходов, но не доказывает прибыльность.",
    "Currency of spend is unknown, so net profit cannot be concluded.",
    "Misinterpretation of profitability due to missing currency context.",
    "Profitability cannot be determined from ROAS alone.",
    "Можно ли считать кампанию прибыльной?",
])
def test_correct_roas_and_negated_profit_statements_pass(analysis_, profile, text):
    res = run(json.dumps(_field_for(claims_for(analysis_), "summary", text)), analysis_, profile)
    assert res.run_status == RunStatus.COMPLETED, res.error_details


def test_roas_alone_is_not_treated_as_proof_of_profit(analysis_, profile):
    rep = _field_for(claims_for(analysis_), "evidence_claim", "ROAS 3.25 shows profitable campaigns.")
    res = run(json.dumps(rep), analysis_, profile)
    assert res.failure_kind == FailureKind.EVIDENCE_MISMATCH


def test_unknown_currency_does_not_block_a_defined_ratio_but_blocks_net_profit_claim(analysis_, profile):
    ok = run(json.dumps(_field_for(claims_for(analysis_), "summary",
                                   "Spend and revenue currency is unknown, so only the ratio is reported.")), analysis_, profile)
    assert ok.run_status == RunStatus.COMPLETED
    bad = run(json.dumps(_field_for(claims_for(analysis_), "summary", "Net profit is positive in dollars.")), analysis_, profile)
    assert bad.report is None  # currency assertion and profit assertion are both rejected


def test_profit_check_is_deterministic_and_has_no_side_effects(analysis_):
    from lab.models.advisor_v3 import _profit_issues
    parts = [("summary", "Campaign is profitable.")]
    assert _profit_issues(parts) == _profit_issues(parts) == ["unsupported profitability assertion in summary"]


def test_v21_path_is_unchanged_by_the_profitability_rule():
    import lab.models.advisor as advisor
    assert advisor.PROMPT_VERSION == "advisor-v2.1"
    assert not hasattr(advisor, "_profit_issues") and not hasattr(advisor, "MANDATORY_OVERALL")


# ---- prompt contract: ROAS is not profit, profitability is undetermined without cost data -------------------------

def test_v3_prompt_states_what_roas_does_and_does_not_establish():
    from lab.models.advisor_v3 import _SYSTEM_V3
    assert "ROAS is revenue divided by advertising spend" in _SYSTEM_V3
    assert "does not establish net profit or overall business profitability" in _SYSTEM_V3


def test_v3_prompt_forbids_profit_claims_from_roas_alone():
    from lab.models.advisor_v3 import _SYSTEM_V3
    assert "based on ROAS alone" in _SYSTEM_V3
    assert "profitable, unprofitable, or as paying back" in _SYSTEM_V3


def test_v3_prompt_requires_undetermined_profitability_without_cost_data():
    from lab.models.advisor_v3 import _SYSTEM_V3
    assert "describe profitability as undetermined" in _SYSTEM_V3
    assert "cost, margin or other expense data are not in the metrics" in _SYSTEM_V3


def test_v3_prompt_keeps_the_valid_roas_interpretation_as_an_example():
    from lab.models.advisor_v3 import _SYSTEM_V3
    assert "ROAS of 3.25 means 3.25 units of revenue per unit of advertising spend." in _SYSTEM_V3


def test_v3_prompt_keeps_the_currency_rule_and_the_evidence_contract():
    from lab.models.advisor_v3 import _SYSTEM_V3
    assert "Do not state a currency" in _SYSTEM_V3
    assert "source_calc_id must be a calc_id from the metrics" in _SYSTEM_V3


def test_v3_prompt_is_sent_in_every_request(analysis_):
    msgs = build_messages_v3(analysis_)
    assert msgs[0]["role"] == "system" and "ROAS is revenue divided by advertising spend" in msgs[0]["content"]


def test_v21_prompt_is_unchanged_by_the_v3_profitability_rules():
    import lab.models.advisor as advisor
    assert "ROAS is revenue divided by advertising spend" not in advisor._SYSTEM
    assert advisor.PROMPT_VERSION == "advisor-v2.1"


# ---- expected outcomes: margin-determination wording passes, real profit claims are still rejected -----------------

LIVE_EXPECTED_OUTCOME = "Ability to determine net profit margins and precise financial impact of budget changes."


def _with_expected_outcome(analysis, text):
    return _field_for(claims_for(analysis), "action_outcome", text)


def test_live_expected_outcome_about_margin_determination_is_accepted(analysis_, profile):
    res = run(json.dumps(_with_expected_outcome(analysis_, LIVE_EXPECTED_OUTCOME)), analysis_, profile)
    assert res.run_status == RunStatus.COMPLETED, res.error_details


@pytest.mark.parametrize("text", [
    "Budget reallocation will improve business profit.",
    "Reallocating budget increases net profit.",
    "The reallocation makes the campaign profitable.",
    "ROAS below 1 means a loss.",
])
def test_genuine_profit_claims_in_expected_outcome_are_still_rejected(analysis_, profile, text):
    res = run(json.dumps(_with_expected_outcome(analysis_, text)), analysis_, profile)
    assert res.report is None and res.failure_kind == FailureKind.EVIDENCE_MISMATCH
    assert "action_plan[0].expected_outcome" in res.error_details


@pytest.mark.parametrize("text", [
    "Enable consistent reporting in the dataset's currency and support further financial analysis.",
    "Collect currency metadata for spend and revenue so future reports state the unit.",
    "Add cost and margin data so that net profit can be assessed in a later review.",
])
def test_valid_currency_and_data_recommendations_are_accepted(analysis_, profile, text):
    res = run(json.dumps(_with_expected_outcome(analysis_, text)), analysis_, profile)
    assert res.run_status == RunStatus.COMPLETED, res.error_details


def test_roas_below_one_is_a_ratio_not_a_loss(analysis_, profile):
    ok = run(json.dumps(_field_for(claims_for(analysis_), "summary",
                                   "ROAS 0.82 means 0.82 units of revenue per unit of advertising spend.")), analysis_, profile)
    assert ok.run_status == RunStatus.COMPLETED
    bad = run(json.dumps(_field_for(claims_for(analysis_), "summary", "ROAS below 1 means a loss.")), analysis_, profile)
    assert bad.report is None


def test_predicate_rule_flags_only_assertions():
    from lab.models.advisor_v3 import _profit_issues
    assert _profit_issues([("x", LIVE_EXPECTED_OUTCOME)]) == []
    assert _profit_issues([("x", "Net profit is positive.")]) != []
    assert _profit_issues([("x", "Profitability is undetermined without cost data.")]) == []


# ---- prompt contract for the expected-outcome and ROAS-ratio rules ---------------------------------------------------

def test_v3_prompt_states_currency_metadata_alone_does_not_establish_net_profit():
    from lab.models.advisor_v3 import _SYSTEM_V3
    assert ("Collecting currency metadata alone does not establish net profit or determine net profit margins; "
            "cost, margin and expense data may also be required.") in _SYSTEM_V3


def test_v3_prompt_treats_roas_as_ratio_and_forbids_profit_from_reallocation():
    from lab.models.advisor_v3 import _SYSTEM_V3
    assert "A ROAS above or below 1 is a revenue-to-ad-spend ratio, not proof of profit or loss." in _SYSTEM_V3
    assert "Do not claim that reallocating budget will improve business profit." in _SYSTEM_V3


def test_v3_prompt_shows_a_valid_expected_outcome():
    from lab.models.advisor_v3 import _SYSTEM_V3
    assert ("Enable consistent reporting in the dataset's currency and support further financial analysis.") in _SYSTEM_V3


# ---- absence wording explains a gap; it does not excuse a direct profitability assertion ----------------------------

LIVE_LIMITATION = ("Currency metadata is missing for spend and revenue, preventing determination of absolute profit "
                   "or net margins.")


def test_live_limitation_describing_missing_currency_and_profit_is_accepted(analysis_, profile):
    rep = claims_for(analysis_)
    rep["limitations_uncertainty"] = [LIVE_LIMITATION]
    res = run(json.dumps(rep), analysis_, profile)
    assert res.run_status == RunStatus.COMPLETED, res.error_details


@pytest.mark.parametrize("text", [
    "Campaign is profitable despite missing cost data.",
    "The campaign is profitable even though costs are unavailable.",
    "Спенд отсутствует, но кампания прибыльна.",
])
def test_direct_profitability_assertion_is_not_excused_by_absence_wording(analysis_, profile, text):
    rep = _field_for(claims_for(analysis_), "summary", text)
    res = run(json.dumps(rep), analysis_, profile)
    assert res.report is None and res.failure_kind == FailureKind.EVIDENCE_MISMATCH


@pytest.mark.parametrize("text", [
    "Lack of cost data limits any profitability conclusion.",
    "Cost data is unavailable, which prevents a profit assessment.",
    "Отсутствие данных о затратах не позволяет оценить прибыльность.",
])
def test_absence_wording_about_profit_assessment_is_accepted(analysis_, profile, text):
    rep = _field_for(claims_for(analysis_), "limitations", text)
    res = run(json.dumps(rep), analysis_, profile)
    assert res.run_status == RunStatus.COMPLETED, res.error_details
