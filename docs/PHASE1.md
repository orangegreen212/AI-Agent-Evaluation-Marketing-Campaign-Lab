# Phase 1 - CSV validation and deterministic analytics

Code: `src/lab/data/` (`validation.py`, `analytics.py`, `__main__.py`). Tests: `tests/data/`.
No LLM, no network, no persistence. Phase 0 contracts are reused unchanged (`Period`, `ComputedMetric`, `Evidence`, `validate_evidence`).

## Accepted CSV

UTF-8 (BOM allowed), comma-separated, header required, column names exact and case-sensitive.

| column | rule |
|---|---|
| `date` | strict `YYYY-MM-DD`, a real calendar date. `2026-1-5`, `01/09/2026`, timestamps are invalid. |
| `campaign`, `channel` | 1-128 chars, `[A-Za-z0-9 _.:/&+-]`, must start with a letter/digit and not end in a space (blocks `=`/`+`/`-`/`@` formula injection). Values are never trimmed or case-folded, so `Search` and `search` are different groups. |
| `impressions`, `clicks`, `conversions` | finite, whole, >= 0, <= 1e15. `100.0` is accepted, `100.5` is not. |
| `spend`, `revenue` | finite, >= 0, <= 1e15, fractions allowed. Currency is not recorded in the file. |

## Severity

Result status: `VALID` (no issues), `VALID_WITH_WARNINGS`, `INVALID` (any fatal issue). `can_analyze` is true unless there is a fatal issue.
**Any fatal issue blocks analysis of the whole file.** Rows are never dropped or repaired; `rows_accepted` is the number of rows without a fatal issue and is reported next to `rows_read`.

| Severity | Codes |
|---|---|
| FATAL | `EMPTY_FILE`, `NO_DATA_ROWS`, `ENCODING_ERROR`, `PARSE_ERROR`, `MISSING_COLUMN`, `MISSING_VALUE`, `INVALID_DATE`, `INVALID_NUMBER`, `NEGATIVE_VALUE`, `FRACTIONAL_COUNT`, `INVALID_IDENTIFIER`, `CLICKS_EXCEED_IMPRESSIONS` |
| WARNING | `UNEXPECTED_COLUMN` (ignored), `DUPLICATE_ROWS`, `CONVERSIONS_EXCEED_CLICKS` (can be legitimate, e.g. view-through) |

Each issue carries `code`, `severity`, `column`, `count`, a message and up to 5 `sample_rows` (1-based data-row numbers). Raw values and exception texts are never included.
The summary also has `missing_by_column`, `invalid_by_column`, `date_range`, `duplicate_row_count`, `duplicate_group_count` and `dataset_sha256` (hash of the file bytes, for traceability).

`PARSE_ERROR` (malformed row, e.g. wrong number of fields, unterminated quote) stops parsing: later rows are not read, so `rows_read` covers only chunks parsed before the error. A missing required column also stops before any row is read (`rows_read = 0`).

## Duplicates

A duplicate is a row identical to an earlier row in all 8 required columns (compared by a 64-bit row hash; collision odds at 1M rows are about 3e-8). It is reported as a warning and **kept** in every total; the metric `limitations` say so. Decide upstream whether repeated rows are real.

## Metrics

| metric_id | formula | unit |
|---|---|---|
| `roas` | sum(revenue) / sum(spend) | ratio |
| `cpa` | sum(spend) / sum(conversions) | currency per conversion |
| `ctr` | sum(clicks) / sum(impressions) x 100 | percent (2.5 means 2.5%) |
| `impressions`, `clicks`, `spend`, `conversions`, `revenue` | sums | count / currency |

Ratios are always built from aggregated sums for the group, never by averaging row ratios.
Scopes: `overall`, `channel`, `campaign`, `date` (`group_key` is the name, or the ISO date). A metric's `period` is the observed first/last date inside that group (overall: the dataset range). Campaign x channel combinations are not output.

Each `MetricResult` is a Phase 0 `ComputedMetric` (`calc_id`, `metric_id`, `value`, `period`) plus `status`, `unit`, `scope`, `group_key`, `formula`, `numerator`, `denominator`, `calculation_version` and `limitations`. It can be passed straight to `validate_evidence`.
`calc_id` = `calc.<metric_id>.<scope>.<16 hex of sha256(version, dataset hash, metric, scope, key, period)>`: identical for identical file bytes, different when the data changes.

### Zero denominators: three distinct states

| status | `value` | when |
|---|---|---|
| `OK` | number (0.0 is a real value) | denominator > 0, e.g. spend > 0 and revenue 0 gives ROAS 0.0 |
| `UNDEFINED` | `None` + reason | denominator is 0: ROAS with zero spend, CPA with zero conversions, CTR with zero impressions. Never 0, never infinity. |
| `UNAVAILABLE` | `None` + reason | the group has no rows (`Analysis.metrics_for("campaign", "unknown")`) |

NaN and infinity cannot be stored in a `MetricResult` (contract rejects them).

## Large files

One streaming pass, `chunk_rows` (default 200,000) at a time; nothing is sampled or truncated. Per-chunk checks are vectorized; dates, campaigns and channels are validated on distinct values only. Analytics keeps one running (campaign, channel, date) sum table, not the rows. Duplicate detection keeps 8 bytes per row (8 MB per million).
Measured here (pandas 3.0.2, Python 3.12, no pyarrow), 1,000,000 rows / 730 days / 50 campaigns / 5 channels, 50 MB file: about 8 s, about 370 MB peak RSS. Your machine will differ.
Counts are exact (int64). Spend and revenue are float64 sums, so last-digit differences (~1e-12 relative) are possible between different `chunk_rows`; for a fixed file and chunk size results are bit-identical.

## Run

    pip install -e ".[dev]"               # or: pip install pandas pydantic pyyaml pytest and set PYTHONPATH=src
    pytest                                # normal suite (warnings are errors), scale test deselected
    pytest -m scale -s                    # explicit 1M-row test
    python -m lab.data datasets/demo/sample_campaigns.csv          # validation + overall metrics, JSON
    python -m lab.data datasets/demo/sample_campaigns.csv --all    # plus by channel / campaign / date

```python
from lab.data import analyze_csv, validate_csv, DataNotAnalyzableError
result = validate_csv("data.csv")          # never raises for bad content
analysis = analyze_csv("data.csv")         # raises DataNotAnalyzableError(.result) on fatal issues
analysis.get("roas", "campaign", "brand_search")
```

Exit code of the CLI: 0 analyzed, 1 not analyzable (validation JSON printed), 2 usage.

## Known limitations

- Input is a file path only. A future upload API must spool the stream to a temporary file; this phase never writes or keeps uploads.
- First malformed row ends parsing (see above). Other issue types are all counted across the whole file.
- Dates are ISO only; other formats are reported as invalid, not converted.
- Fractional `conversions` (e.g. fractional attribution) are rejected as fatal.
- One fatal row blocks the whole analysis; there is no "analyze the valid subset" mode (an explicit, reported opt-in could be added later).
- Duplicates stay in totals (by design, see above).
- Only checks that the data is internally consistent; it cannot detect wrong-but-plausible numbers.
- `rows_read` for a file stopped by a parse error is approximate (whole chunks only).
- Requires pandas >= 3.0 (verified only with 3.0.2).
