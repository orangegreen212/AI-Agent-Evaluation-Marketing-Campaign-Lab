"""Chunked CSV validation. See docs/PHASE1.md for the rules and severities.

One streaming pass over the file: memory is bounded by `chunk_rows`, not file size.
Nothing is dropped, repaired or written to disk; raw values are never put in a result.
"""
from __future__ import annotations

import hashlib
import re
import warnings
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Callable, Literal

import numpy as np
import pandas as pd
from pydantic import Field

from lab.schemas.base import LabModel, Sha256Hex
from lab.schemas.decision_report import Period

REQUIRED_COLUMNS = ("date", "campaign", "channel", "impressions", "clicks", "spend", "conversions", "revenue")
COUNT_COLUMNS = ("impressions", "clicks", "conversions")  # whole numbers only
NUMERIC_COLUMNS = ("impressions", "clicks", "spend", "conversions", "revenue")
IDENTIFIER_COLUMNS = ("campaign", "channel")
MEASURES = NUMERIC_COLUMNS

DEFAULT_CHUNK_ROWS = 200_000
MAX_VALUE = 1e15  # keeps counts exact in float64 and safe for int64
_MAX_SAMPLES = 5

_ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
# Starts with a letter/digit (blocks "=", "+", "-", "@" spreadsheet-formula injection), no edge whitespace.
_IDENTIFIER = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9 _.:/&+-]{0,126}[A-Za-z0-9_.:/&+-])?")


class IssueSeverity(StrEnum):
    FATAL = "FATAL"
    WARNING = "WARNING"


class IssueCode(StrEnum):
    EMPTY_FILE = "EMPTY_FILE"
    NO_DATA_ROWS = "NO_DATA_ROWS"
    ENCODING_ERROR = "ENCODING_ERROR"
    PARSE_ERROR = "PARSE_ERROR"
    MISSING_COLUMN = "MISSING_COLUMN"
    UNEXPECTED_COLUMN = "UNEXPECTED_COLUMN"
    MISSING_VALUE = "MISSING_VALUE"
    INVALID_DATE = "INVALID_DATE"
    INVALID_NUMBER = "INVALID_NUMBER"
    NEGATIVE_VALUE = "NEGATIVE_VALUE"
    FRACTIONAL_COUNT = "FRACTIONAL_COUNT"
    INVALID_IDENTIFIER = "INVALID_IDENTIFIER"
    CLICKS_EXCEED_IMPRESSIONS = "CLICKS_EXCEED_IMPRESSIONS"
    CONVERSIONS_EXCEED_CLICKS = "CONVERSIONS_EXCEED_CLICKS"
    DUPLICATE_ROWS = "DUPLICATE_ROWS"


_MESSAGES = {
    IssueCode.EMPTY_FILE: "the file is empty",
    IssueCode.NO_DATA_ROWS: "the file has a header but no data rows",
    IssueCode.ENCODING_ERROR: "the file is not valid UTF-8",
    IssueCode.PARSE_ERROR: "the CSV is malformed; parsing stopped, later rows were not read",
    IssueCode.MISSING_COLUMN: "required column {col} is missing; data rows were not read",
    IssueCode.UNEXPECTED_COLUMN: "unexpected column {col} is ignored",
    IssueCode.MISSING_VALUE: "{n} row(s) have an empty value in {col}",
    IssueCode.INVALID_DATE: "{n} row(s) have a {col} that is not a real YYYY-MM-DD date",
    IssueCode.INVALID_NUMBER: "{n} row(s) have a {col} that is not a finite number within +/-1e15",
    IssueCode.NEGATIVE_VALUE: "{n} row(s) have a negative {col}",
    IssueCode.FRACTIONAL_COUNT: "{n} row(s) have a fractional {col}; whole counts are required",
    IssueCode.INVALID_IDENTIFIER: "{n} row(s) have an invalid {col} identifier",
    IssueCode.CLICKS_EXCEED_IMPRESSIONS: "{n} row(s) have clicks greater than impressions",
    IssueCode.CONVERSIONS_EXCEED_CLICKS: "{n} row(s) have conversions greater than clicks",
    IssueCode.DUPLICATE_ROWS: "{n} row(s) are exact duplicates of an earlier row; they are kept in all totals",
}
_INVALID_VALUE_CODES = {IssueCode.INVALID_DATE, IssueCode.INVALID_NUMBER, IssueCode.NEGATIVE_VALUE,
                        IssueCode.FRACTIONAL_COUNT, IssueCode.INVALID_IDENTIFIER}


class ValidationIssue(LabModel):
    code: IssueCode
    severity: IssueSeverity
    column: str | None = None
    count: int = Field(ge=0)  # affected rows (1 for file/column-level issues)
    message: str
    sample_rows: list[int] = Field(default_factory=list)  # 1-based data-row numbers, at most 5


class ValidationResult(LabModel):
    dataset_sha256: Sha256Hex
    status: Literal["VALID", "VALID_WITH_WARNINGS", "INVALID"]
    can_analyze: bool
    rows_read: int = Field(ge=0)
    rows_accepted: int = Field(ge=0)  # rows with no fatal issue
    issues: list[ValidationIssue]
    duplicate_row_count: int = Field(ge=0)  # surplus copies; the first occurrence is not counted
    duplicate_group_count: int = Field(ge=0)
    missing_by_column: dict[str, int]
    invalid_by_column: dict[str, int]  # rows with a present-but-bad value (each row counted once per column)
    date_range: Period | None = None  # over rows with a valid date

    @property
    def fatal_errors(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity == IssueSeverity.FATAL]

    @property
    def warnings(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity == IssueSeverity.WARNING]


CleanChunkSink = Callable[[pd.DataFrame], None]


def _short(name: object) -> str:
    return repr(str(name)[:64])


class _Collector:
    def __init__(self) -> None:
        self.found: dict[tuple[IssueCode, str | None], list] = {}  # key -> [severity, count, samples]
        self.missing = {c: 0 for c in REQUIRED_COLUMNS}
        self.invalid = {c: 0 for c in REQUIRED_COLUMNS}

    def add(self, code: IssueCode, severity: IssueSeverity, column: str | None, count: int, samples=()) -> None:
        entry = self.found.setdefault((code, column), [severity, 0, []])
        entry[1] += count
        entry[2].extend(list(samples)[: _MAX_SAMPLES - len(entry[2])])

    def issues(self, extra_text: dict[tuple[IssueCode, str | None], str] | None = None) -> list[ValidationIssue]:
        out = []
        for (code, col), (sev, n, samples) in sorted(self.found.items(), key=lambda kv: (kv[0][0].value, kv[0][1] or "")):
            msg = _MESSAGES[code].format(n=n, col=(extra_text or {}).get((code, col)) or col)
            out.append(ValidationIssue(code=code, severity=sev, column=col, count=n, message=msg, sample_rows=samples))
        return out


def _check_chunk(df: pd.DataFrame, offset: int, acc: _Collector):
    """Validate one chunk. Returns (ok_mask, typed columns, parsed dates, valid_date_mask)."""
    n = len(df)
    bad = np.zeros(n, dtype=bool)
    inv_cols: dict[str, np.ndarray] = {}

    def flag(code: IssueCode, col: str | None, mask: np.ndarray, *, fatal: bool = True) -> None:
        c = int(mask.sum())
        if not c:
            return
        rows = np.flatnonzero(mask)[:_MAX_SAMPLES] + offset + 1
        acc.add(code, IssueSeverity.FATAL if fatal else IssueSeverity.WARNING, col, c, rows.tolist())
        if fatal:
            np.logical_or(bad, mask, out=bad)
        if code in _INVALID_VALUE_CODES:
            u = inv_cols.setdefault(col, np.zeros(n, dtype=bool))
            np.logical_or(u, mask, out=u)

    raw = {c: df[c].fillna("") for c in REQUIRED_COLUMNS}
    miss = {c: raw[c].str.strip().eq("").to_numpy() for c in REQUIRED_COLUMNS}
    for c in REQUIRED_COLUMNS:
        m = int(miss[c].sum())
        acc.missing[c] += m
        flag(IssueCode.MISSING_VALUE, c, miss[c])

    # dates: validate the (few) distinct strings once, then parse vectorised
    valid_dates = []
    for u in raw["date"].unique():
        if _ISO_DATE.fullmatch(u):
            try:
                datetime.strptime(u, "%Y-%m-%d")
                valid_dates.append(u)
            except ValueError:
                pass
    date_ok = raw["date"].isin(valid_dates).to_numpy()
    flag(IssueCode.INVALID_DATE, "date", ~date_ok & ~miss["date"])
    dates = pd.to_datetime(raw["date"].where(date_ok), format="%Y-%m-%d")

    for c in IDENTIFIER_COLUMNS:
        good = [u for u in raw[c].unique() if _IDENTIFIER.fullmatch(u)]
        flag(IssueCode.INVALID_IDENTIFIER, c, ~raw[c].isin(good).to_numpy() & ~miss[c])

    vals: dict[str, np.ndarray] = {}
    num_ok: dict[str, np.ndarray] = {}
    for c in NUMERIC_COLUMNS:
        v = pd.to_numeric(raw[c].where(~miss[c]), errors="coerce").to_numpy(dtype="float64")
        with np.errstate(invalid="ignore"):
            fine = np.isfinite(v) & (np.abs(v) <= MAX_VALUE)
        flag(IssueCode.INVALID_NUMBER, c, ~fine & ~miss[c])
        with np.errstate(invalid="ignore"):
            flag(IssueCode.NEGATIVE_VALUE, c, fine & (v < 0))
            if c in COUNT_COLUMNS:
                flag(IssueCode.FRACTIONAL_COUNT, c, fine & (v != np.floor(v)))
        vals[c], num_ok[c] = v, fine

    with np.errstate(invalid="ignore"):
        both = num_ok["impressions"] & num_ok["clicks"]
        flag(IssueCode.CLICKS_EXCEED_IMPRESSIONS, None, both & (vals["clicks"] > vals["impressions"]))
        both = num_ok["conversions"] & num_ok["clicks"]
        flag(IssueCode.CONVERSIONS_EXCEED_CLICKS, None, both & (vals["conversions"] > vals["clicks"]), fatal=False)

    for c, u in inv_cols.items():
        acc.invalid[c] += int(u.sum())
    return ~bad, raw, vals, dates, date_ok


def _scan(path: str | Path, chunk_rows: int, sink: CleanChunkSink | None) -> ValidationResult:
    path = Path(path)
    with path.open("rb") as f:
        digest = hashlib.file_digest(f, "sha256").hexdigest()
    acc = _Collector()
    names: dict[tuple[IssueCode, str | None], str] = {}
    state = {"read": 0, "accepted": 0, "lo": None, "hi": None}
    hashes: list[np.ndarray] = []

    def finish() -> ValidationResult:
        dup_rows = dup_groups = 0
        if hashes:
            _, counts = np.unique(np.concatenate(hashes), return_counts=True)
            dup_groups = int((counts > 1).sum())
            dup_rows = int((counts[counts > 1] - 1).sum())
        if dup_rows:
            acc.add(IssueCode.DUPLICATE_ROWS, IssueSeverity.WARNING, None, dup_rows)
        if state["read"] == 0 and not any(c in (IssueCode.EMPTY_FILE, IssueCode.MISSING_COLUMN,
                                                IssueCode.ENCODING_ERROR, IssueCode.PARSE_ERROR) for c, _ in acc.found):
            acc.add(IssueCode.NO_DATA_ROWS, IssueSeverity.FATAL, None, 1)
        issues = acc.issues(names)
        fatal = any(i.severity == IssueSeverity.FATAL for i in issues)
        status = "INVALID" if fatal else "VALID_WITH_WARNINGS" if issues else "VALID"
        period = Period(start=state["lo"].date(), end=state["hi"].date()) if state["lo"] is not None else None
        return ValidationResult(
            dataset_sha256=digest, status=status, can_analyze=not fatal, rows_read=state["read"],
            rows_accepted=state["accepted"], issues=issues, duplicate_row_count=dup_rows,
            duplicate_group_count=dup_groups, missing_by_column=acc.missing, invalid_by_column=acc.invalid,
            date_range=period,
        )

    try:
        header = pd.read_csv(path, nrows=0, dtype=str, encoding="utf-8-sig").columns.tolist()
    except pd.errors.EmptyDataError:
        acc.add(IssueCode.EMPTY_FILE, IssueSeverity.FATAL, None, 1)
        return finish()
    except UnicodeDecodeError:
        acc.add(IssueCode.ENCODING_ERROR, IssueSeverity.FATAL, None, 1)
        return finish()
    except pd.errors.ParserError:
        acc.add(IssueCode.PARSE_ERROR, IssueSeverity.FATAL, None, 1)
        return finish()

    for c in header:
        if c not in REQUIRED_COLUMNS:
            acc.add(IssueCode.UNEXPECTED_COLUMN, IssueSeverity.WARNING, _short(c), 1)
    missing_cols = [c for c in REQUIRED_COLUMNS if c not in header]
    for c in missing_cols:
        acc.add(IssueCode.MISSING_COLUMN, IssueSeverity.FATAL, c, 1)
    if missing_cols:
        return finish()

    def _consume(df: pd.DataFrame) -> None:
        offset = state["read"]
        ok, raw, vals, dates, date_ok = _check_chunk(df, offset, acc)
        hashes.append(pd.util.hash_pandas_object(df[list(REQUIRED_COLUMNS)], index=False).to_numpy())
        state["read"] += len(df)
        state["accepted"] += int(ok.sum())
        if date_ok.any():
            lo, hi = dates.min(), dates.max()
            state["lo"] = lo if state["lo"] is None else min(state["lo"], lo)
            state["hi"] = hi if state["hi"] is None else max(state["hi"], hi)
        if sink is not None and ok.any():
            clean = pd.DataFrame({"date": dates[ok].to_numpy(), "campaign": raw["campaign"][ok].to_numpy(),
                                  "channel": raw["channel"][ok].to_numpy()})
            for c in NUMERIC_COLUMNS:
                clean[c] = vals[c][ok].astype("int64" if c in COUNT_COLUMNS else "float64")
            sink(clean)

    try:
        # index_col=False + ParserWarning-as-error: pandas otherwise silently drops or shifts extra fields.
        with warnings.catch_warnings():
            warnings.simplefilter("error", pd.errors.ParserWarning)
            reader = pd.read_csv(path, index_col=False, dtype=str, keep_default_na=False,
                                 encoding="utf-8-sig", chunksize=chunk_rows)
            for df in reader:
                _consume(df)
    except (pd.errors.ParserError, pd.errors.ParserWarning) as e:
        # Report only the position, never the exception text (it may echo file content).
        m = re.search(r"(?:line|row) (\d+)", str(e))
        acc.add(IssueCode.PARSE_ERROR, IssueSeverity.FATAL, None, 1, [int(m.group(1)) - 1] if m else [])
    except UnicodeDecodeError:
        acc.add(IssueCode.ENCODING_ERROR, IssueSeverity.FATAL, None, 1)
    return finish()



def validate_csv(path: str | Path, *, chunk_rows: int = DEFAULT_CHUNK_ROWS) -> ValidationResult:
    """Validate a CSV file. Never raises for bad content; inspect `.can_analyze` and `.issues`."""
    return _scan(path, chunk_rows, None)
