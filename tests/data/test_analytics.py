import math

import pytest

from lab.data import MetricStatus, Totals, analyze_csv, compute_group_metrics
from lab.schemas import validate_evidence
from lab.schemas.decision_report import Period

from data_helpers import GOOD, HEADER, write_csv  # noqa: F401  (write_csv is a fixture)

P = Period(start="2026-09-01", end="2026-09-30")
SHA = "a" * 64


def metrics(**totals):
    base = dict(impressions=0, clicks=0, spend=0.0, conversions=0, revenue=0.0)
    base.update(totals)
    return {m.metric_id: m for m in compute_group_metrics(scope="overall", group_key=None, totals=Totals(**base),
                                                          period=P, dataset_sha256=SHA)}


def test_zero_spend_gives_undefined_roas_not_zero_or_inf():
    m = metrics(spend=0.0, revenue=50.0)["roas"]
    assert m.status == MetricStatus.UNDEFINED and m.value is None and "zero" in m.value_undefined_reason
    assert m.model_dump_json()  # serializes: no NaN/inf anywhere


def test_zero_conversions_gives_undefined_cpa():
    m = metrics(spend=10.0, conversions=0)["cpa"]
    assert m.status == MetricStatus.UNDEFINED and m.value is None


def test_zero_impressions_gives_undefined_ctr():
    m = metrics(impressions=0, clicks=0)["ctr"]
    assert m.status == MetricStatus.UNDEFINED and m.value is None


def test_true_zero_is_a_value_not_undefined():
    roas = metrics(spend=10.0, revenue=0.0)["roas"]
    assert roas.status == MetricStatus.OK and roas.value == 0.0
    assert metrics(impressions=10, clicks=0)["ctr"].value == 0.0


def test_formulas_and_ctr_is_percent():
    m = metrics(impressions=2000, clicks=50, spend=100.0, conversions=4, revenue=250.0)
    assert (m["roas"].value, m["cpa"].value, m["ctr"].value) == (2.5, 25.0, 2.5)
    assert m["ctr"].unit == "percent"


def test_empty_group_is_unavailable_not_error_or_zero(write_csv):
    ms = compute_group_metrics(scope="campaign", group_key="ghost", totals=None, period=P, dataset_sha256=SHA)
    assert {m.status for m in ms} == {MetricStatus.UNAVAILABLE} and all(m.value is None for m in ms)
    a = analyze_csv(write_csv())
    assert {m.status for m in a.metrics_for("campaign", "nope")} == {MetricStatus.UNAVAILABLE}


def test_ratios_use_aggregated_values_not_row_averages(write_csv):
    # row ROAS 10 and 1: mean of ratios = 5.5, ratio of sums = 200/110
    path = write_csv(rows=["2026-09-01,a,s,1000,10,10.00,1,100.00", "2026-09-02,a,s,1000,10,100.00,1,100.00"])
    roas = analyze_csv(path).get("roas")
    assert roas.value == pytest.approx(200 / 110) and roas.value != pytest.approx(5.5)
    assert (roas.numerator, roas.denominator) == (200.0, 110.0)


def test_group_with_zero_spend_is_undefined_but_other_groups_unaffected(write_csv):
    path = write_csv(rows=["2026-09-01,a,s,100,10,0.00,0,0.00", "2026-09-01,b,s,100,10,10.00,1,30.00"])
    a = analyze_csv(path)
    assert a.get("roas", "campaign", "a").status == MetricStatus.UNDEFINED
    assert a.get("roas", "campaign", "b").value == 3.0
    assert a.get("roas").value == 3.0  # overall: 30 / 10


def test_aggregation_levels_and_periods(write_csv):
    a = analyze_csv(write_csv())
    assert a.get("spend").value == pytest.approx(450.5)
    assert a.get("spend", "channel", "search").value == pytest.approx(250.5)
    assert a.get("spend", "campaign", "promo").value == 200.0
    d = a.get("spend", "date", "2026-09-02")
    assert d.value == pytest.approx(350.5) and d.period.start == d.period.end
    promo = a.get("roas", "campaign", "promo")
    assert str(promo.period.start) == "2026-09-02"  # observed span of that group, not the dataset span
    assert str(a.get("roas").period.start) == "2026-09-01"


def test_stable_metric_and_calc_ids(write_csv):
    a, b = analyze_csv(write_csv()), analyze_csv(write_csv(name="copy.csv"))
    assert {"roas", "cpa", "ctr", "impressions", "clicks", "spend", "conversions", "revenue"} <= {m.metric_id for m in a.metrics}
    assert a.get("roas").calc_id == b.get("roas").calc_id and a.get("roas").calc_id.startswith("calc.roas.overall.")
    ids = [m.calc_id for m in a.metrics]
    assert len(ids) == len(set(ids))
    c = analyze_csv(write_csv(rows=GOOD[:2], name="other.csv"))
    assert c.get("roas").calc_id != a.get("roas").calc_id  # different data, different id


def test_metrics_feed_phase0_evidence_validation(write_csv, make_report, make_evidence):
    a = analyze_csv(write_csv())
    m = a.get("roas")
    ev = make_evidence(metric_id=m.metric_id, source_calc_id=m.calc_id, value=m.value,
                       period={"start": str(m.period.start), "end": str(m.period.end)})
    validate_evidence(make_report(evidence=[ev]), a.metrics)  # raises on mismatch
    bad = make_evidence(metric_id=m.metric_id, source_calc_id=m.calc_id, value=m.value + 1,
                        period={"start": str(m.period.start), "end": str(m.period.end)})
    with pytest.raises(Exception):
        validate_evidence(make_report(evidence=[bad]), a.metrics)


def test_results_are_deterministic_and_finite(write_csv):
    path = write_csv()
    a, b = analyze_csv(path), analyze_csv(path)
    assert a.model_dump() == b.model_dump() and a.model_dump_json() == b.model_dump_json()
    assert all(m.value is None or math.isfinite(m.value) for m in a.metrics)


def test_invalid_data_is_refused_with_full_report(write_csv):
    from lab.data import DataNotAnalyzableError
    with pytest.raises(DataNotAnalyzableError) as e:
        analyze_csv(write_csv(rows=[GOOD[0], "2026-09-01,a,s,1,2,1,1,1"]))
    assert e.value.result.fatal_errors
