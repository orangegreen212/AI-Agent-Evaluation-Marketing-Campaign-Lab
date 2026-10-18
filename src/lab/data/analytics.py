"""Deterministic metrics. No LLM, no randomness, no row-level ratios.

Every ratio is computed from summed numerators and denominators. A metric is exactly one of:
  OK          value present (0.0 is a real, valid result)
  UNDEFINED   the denominator is zero, so the ratio has no value (never 0, never infinity)
  UNAVAILABLE there is no data for this group, so nothing can be said at all
"""
from __future__ import annotations

import hashlib
from enum import StrEnum
from pathlib import Path
from typing import Literal

import pandas as pd
from pydantic import Field, model_validator

from lab.schemas.base import LabModel, NonEmptyStr
from lab.schemas.decision_report import ComputedMetric, Period

from .validation import DEFAULT_CHUNK_ROWS, IssueCode, ValidationResult, _scan

CALC_VERSION = "1"
Scope = Literal["overall", "campaign", "channel", "date"]
_KEYS = ["campaign", "channel", "date"]
_SUMS = ["impressions", "clicks", "spend", "conversions", "revenue"]


class MetricStatus(StrEnum):
    OK = "OK"
    UNDEFINED = "UNDEFINED"
    UNAVAILABLE = "UNAVAILABLE"


class Totals(LabModel):
    impressions: int = Field(ge=0)
    clicks: int = Field(ge=0)
    spend: float = Field(ge=0, allow_inf_nan=False)
    conversions: int = Field(ge=0)
    revenue: float = Field(ge=0, allow_inf_nan=False)


class MetricResult(ComputedMetric):
    """A ComputedMetric (so it feeds validate_evidence directly) plus provenance."""

    status: MetricStatus
    unit: str
    scope: Scope
    group_key: str | None = None
    formula: str
    calculation_version: str = CALC_VERSION
    numerator: float | None = Field(default=None, allow_inf_nan=False)
    denominator: float | None = Field(default=None, allow_inf_nan=False)
    value_undefined_reason: NonEmptyStr | None = None
    limitations: list[NonEmptyStr] = Field(default_factory=list)

    @model_validator(mode="after")
    def _consistent(self) -> "MetricResult":
        if (self.status == MetricStatus.OK) != (self.value is not None):
            raise ValueError("value is present if and only if status is OK")
        if (self.status != MetricStatus.OK) != bool(self.value_undefined_reason):
            raise ValueError("value_undefined_reason is required if and only if status is not OK")
        return self


# metric_id: (numerator, denominator, unit, scale, formula, name)
RATIOS = {
    "roas": ("revenue", "spend", "ratio", 1.0, "sum(revenue) / sum(spend)", "ROAS"),
    "cpa": ("spend", "conversions", "currency_per_conversion", 1.0, "sum(spend) / sum(conversions)", "CPA"),
    "ctr": ("clicks", "impressions", "percent", 100.0, "sum(clicks) / sum(impressions) * 100", "CTR"),
}
_SUM_UNITS = {"impressions": "count", "clicks": "count", "conversions": "count", "spend": "currency", "revenue": "currency"}
_CURRENCY_NOTE = "currency of spend and revenue is not specified in the CSV"


def calc_id(metric_id: str, scope: str, group_key: str | None, period: Period, dataset_sha256: str) -> str:
    """Stable for the same dataset bytes, metric, group, period and calculation version."""
    raw = "|".join([CALC_VERSION, dataset_sha256, metric_id, scope, group_key or "", period.start.isoformat(),
                    period.end.isoformat()])
    return f"calc.{metric_id}.{scope}.{hashlib.sha256(raw.encode()).hexdigest()[:16]}"


def compute_group_metrics(
    *, scope: Scope, group_key: str | None, totals: Totals | None, period: Period,
    dataset_sha256: str, limitations: tuple[str, ...] = (),
) -> list[MetricResult]:
    """All metrics for one group. `totals=None` means the group has no rows (UNAVAILABLE)."""
    out: list[MetricResult] = []

    def make(metric_id, unit, formula, name, num, den, scale, extra=()):
        lim = [*limitations, *extra]
        common = dict(calc_id=calc_id(metric_id, scope, group_key, period, dataset_sha256), metric_id=metric_id,
                      period=period, unit=unit, scope=scope, group_key=group_key, formula=formula, limitations=lim)
        if num is None:
            return MetricResult(**common, status=MetricStatus.UNAVAILABLE,
                                value_undefined_reason=f"no data rows for this {scope}; {name} is unavailable")
        if den is None:  # plain sum
            return MetricResult(**common, status=MetricStatus.OK, value=float(num), numerator=float(num))
        if den == 0:
            return MetricResult(**common, status=MetricStatus.UNDEFINED, numerator=float(num), denominator=0.0,
                                value_undefined_reason=f"denominator is zero; {name} is undefined (not 0, not infinite)")
        return MetricResult(**common, status=MetricStatus.OK, value=float(num) / float(den) * scale,
                            numerator=float(num), denominator=float(den))

    for mid, (n, d, unit, scale, formula, name) in RATIOS.items():
        extra = (_CURRENCY_NOTE,) if mid == "cpa" else ()
        out.append(make(mid, unit, formula, name, None if totals is None else getattr(totals, n),
                        None if totals is None else getattr(totals, d), scale, extra))
    for col, unit in _SUM_UNITS.items():
        extra = (_CURRENCY_NOTE,) if unit == "currency" else ()
        out.append(make(col, unit, f"sum({col})", col, None if totals is None else getattr(totals, col), None, 1.0, extra))
    return out


class Analysis(LabModel):
    validation: ValidationResult
    period: Period
    metrics: list[MetricResult]  # ordered: overall, channel, campaign, date; keys sorted

    def get(self, metric_id: str, scope: Scope = "overall", group_key: str | None = None) -> MetricResult:
        for m in self.metrics:
            if (m.metric_id, m.scope, m.group_key) == (metric_id, scope, group_key):
                return m
        raise KeyError((metric_id, scope, group_key))

    def metrics_for(self, scope: Scope, group_key: str | None) -> list[MetricResult]:
        """Metrics of one group; a group with no rows yields UNAVAILABLE metrics instead of an error."""
        found = [m for m in self.metrics if m.scope == scope and m.group_key == group_key]
        return found or compute_group_metrics(scope=scope, group_key=group_key, totals=None, period=self.period,
                                              dataset_sha256=self.validation.dataset_sha256)


class DataNotAnalyzableError(ValueError):
    def __init__(self, result: ValidationResult) -> None:
        super().__init__(f"dataset is not analyzable: {len(result.fatal_errors)} fatal error(s)")
        self.result = result


def analyze_csv(path: str | Path, *, chunk_rows: int = DEFAULT_CHUNK_ROWS) -> Analysis:
    """Validate and analyze in one pass. Raises DataNotAnalyzableError (carrying the full
    ValidationResult) if any fatal issue exists; nothing is silently dropped or repaired."""
    acc: list[pd.DataFrame] = []  # one running (campaign, channel, date) table; small vs. the row count

    def sink(chunk: pd.DataFrame) -> None:
        part = chunk.groupby(_KEYS)[_SUMS].sum()
        acc[:] = [part if not acc else pd.concat([acc[0], part]).groupby(level=_KEYS).sum()]

    result = _scan(path, chunk_rows, sink)
    if not result.can_analyze:
        raise DataNotAnalyzableError(result)

    fine = acc[0].reset_index()
    sha = result.dataset_sha256
    limits: list[str] = []
    if result.duplicate_row_count:
        limits.append(f"{result.duplicate_row_count} duplicate row(s) are included in the totals")
    if any(i.code == IssueCode.CONVERSIONS_EXCEED_CLICKS for i in result.warnings):
        limits.append("some rows report more conversions than clicks")

    def groups(key: str | None) -> list[MetricResult]:
        g = fine.assign(_all="all").groupby(key or "_all").agg(
            **{c: (c, "sum") for c in _SUMS}, start=("date", "min"), end=("date", "max"))
        res: list[MetricResult] = []
        for k, imp, clk, spd, conv, rev, start, end in g[[*_SUMS, "start", "end"]].itertuples(name=None):
            gk = None if key is None else k.date().isoformat() if key == "date" else str(k)
            res += compute_group_metrics(
                scope=key or "overall", group_key=gk, period=Period(start=start.date(), end=end.date()),
                totals=Totals(impressions=int(imp), clicks=int(clk), spend=float(spd), conversions=int(conv), revenue=float(rev)),
                dataset_sha256=sha, limitations=tuple(limits))
        return res

    metrics = groups(None) + groups("channel") + groups("campaign") + groups("date")
    return Analysis(validation=result, period=result.date_range, metrics=metrics)
