from pathlib import Path

import pytest

from lab.data import DataNotAnalyzableError, analyze_csv, validate_csv

from data_helpers import GOOD, HEADER, codes, write_csv  # noqa: F401  (write_csv is a fixture)


def row(**kw):
    base = dict(date="2026-09-01", campaign="brand", channel="search", impressions="1000", clicks="50",
                spend="100.00", conversions="5", revenue="400.00")
    base.update(kw)
    return ",".join(base.values())


def test_valid_csv_accepted(write_csv):
    r = validate_csv(write_csv())
    assert (r.status, r.can_analyze, r.rows_read, r.rows_accepted) == ("VALID", True, 3, 3)
    assert r.issues == [] and r.duplicate_row_count == 0
    assert (str(r.date_range.start), str(r.date_range.end)) == ("2026-09-01", "2026-09-02")
    assert len(r.dataset_sha256) == 64


def test_missing_required_column_rejected(write_csv):
    r = validate_csv(write_csv(rows=["2026-09-01,a,s,1,1,1,1"], header="date,campaign,channel,impressions,clicks,spend,conversions"))
    assert not r.can_analyze and r.status == "INVALID"
    assert [i.column for i in r.fatal_errors if i.code.value == "MISSING_COLUMN"] == ["revenue"]


def test_unexpected_column_is_only_a_warning(write_csv):
    r = validate_csv(write_csv(rows=[g + ",x" for g in GOOD], header=HEADER + ",notes"))
    assert r.can_analyze and r.status == "VALID_WITH_WARNINGS"
    assert codes(r, "WARNING") == {"UNEXPECTED_COLUMN"} and not r.fatal_errors


def test_empty_and_header_only_files(tmp_path, write_csv):
    p = tmp_path / "empty.csv"
    p.write_bytes(b"")
    assert codes(validate_csv(p)) == {"EMPTY_FILE"}
    r = validate_csv(write_csv(rows=[]))
    assert codes(r) == {"NO_DATA_ROWS"} and not r.can_analyze and r.rows_read == 0
    with pytest.raises(DataNotAnalyzableError):
        analyze_csv(write_csv(rows=[], name="h.csv"))


@pytest.mark.parametrize("bad", ["01/09/2026", "2026-1-5", "2026-02-30", "not-a-date", "2026-09-01 10:00"])
def test_invalid_or_inconsistent_date_reported(write_csv, bad):
    r = validate_csv(write_csv(rows=[GOOD[0], row(date=bad)]))
    assert not r.can_analyze and r.rows_accepted == 1 and r.invalid_by_column["date"] == 1
    issue = next(i for i in r.issues if i.code.value == "INVALID_DATE")
    assert issue.sample_rows == [2]


def test_missing_required_value_reported(write_csv):
    r = validate_csv(write_csv(rows=[GOOD[0], row(campaign=""), row(spend=" ")]))
    assert not r.can_analyze and r.missing_by_column["campaign"] == 1 and r.missing_by_column["spend"] == 1
    assert r.rows_accepted == 1


@pytest.mark.parametrize("bad", ["abc", "nan", "inf", "1,000", "1e999"])
def test_invalid_numeric_reported(write_csv, bad):
    r = validate_csv(write_csv(rows=[row(clicks=f'"{bad}"')]))
    assert "INVALID_NUMBER" in codes(r, "FATAL") and r.invalid_by_column["clicks"] == 1


def test_negative_values_are_fatal(write_csv):
    r = validate_csv(write_csv(rows=[row(spend="-1.00"), row(revenue="-5")]))
    assert not r.can_analyze
    assert {i.column for i in r.issues if i.code.value == "NEGATIVE_VALUE"} == {"spend", "revenue"}


def test_fractional_counts_fatal_but_fractional_money_fine(write_csv):
    r = validate_csv(write_csv(rows=[row(impressions="100.5"), row(conversions="2.25"), row(spend="1.25")]))
    assert {i.column for i in r.issues if i.code.value == "FRACTIONAL_COUNT"} == {"impressions", "conversions"}
    assert r.rows_accepted == 1
    assert validate_csv(write_csv(rows=[row(impressions="100.0")], name="w.csv")).can_analyze  # whole value written as 100.0


def test_duplicates_reported_and_not_removed(write_csv):
    path = write_csv(rows=[GOOD[0], GOOD[0], GOOD[0], GOOD[1]])
    r = validate_csv(path)
    assert (r.duplicate_row_count, r.duplicate_group_count) == (2, 1)
    assert codes(r, "WARNING") == {"DUPLICATE_ROWS"} and r.can_analyze and r.rows_accepted == 4
    a = analyze_csv(path)
    assert a.get("impressions").value == 5000  # 3 x 1000 + 2000: nothing dropped
    assert any("duplicate" in lim for lim in a.get("roas").limitations)


def test_clicks_greater_than_impressions_reported(write_csv):
    r = validate_csv(write_csv(rows=[GOOD[0], row(impressions="10", clicks="11")]))
    assert "CLICKS_EXCEED_IMPRESSIONS" in codes(r, "FATAL") and not r.can_analyze


def test_conversions_greater_than_clicks_is_warning(write_csv):
    r = validate_csv(write_csv(rows=[row(clicks="2", conversions="3")]))
    assert r.can_analyze and codes(r, "WARNING") == {"CONVERSIONS_EXCEED_CLICKS"}


@pytest.mark.parametrize("bad", ["=SUM(A1)", "+cmd", "-x", "@x", " lead", "trail ", "a" * 200])
def test_invalid_identifiers_reported(write_csv, bad):
    r = validate_csv(write_csv(rows=[row(campaign=f'"{bad}"')]))
    assert "INVALID_IDENTIFIER" in codes(r, "FATAL")


def test_malformed_row_is_fatal_parse_error(write_csv):
    r = validate_csv(write_csv(rows=[GOOD[0], GOOD[1] + ",extra"]))
    assert "PARSE_ERROR" in codes(r, "FATAL") and not r.can_analyze


def test_every_row_having_an_extra_field_is_not_silently_accepted(write_csv):
    # pandas would otherwise treat the first column as an index or drop the extra field without error
    r = validate_csv(write_csv(rows=[g + ",x" for g in GOOD]))
    assert "PARSE_ERROR" in codes(r, "FATAL") and not r.can_analyze


def test_non_utf8_file_is_fatal(tmp_path):
    p = tmp_path / "x.csv"
    p.write_bytes(HEADER.encode() + b"\n2026-09-01,caf\xe9,s,1,1,1,1,1\n")
    assert "ENCODING_ERROR" in codes(validate_csv(p))


def test_result_never_contains_raw_values(write_csv):
    secret = "SECRET-TOKEN-123"
    r = validate_csv(write_csv(rows=[row(clicks=secret), row(date=secret), row(campaign=f'"={secret}"')]))
    assert secret not in r.model_dump_json()


def test_input_is_not_modified(write_csv):
    path = write_csv(rows=[GOOD[0], row(spend="-1")])
    before = Path(path).read_bytes()
    validate_csv(path)
    assert Path(path).read_bytes() == before


def test_large_input_not_truncated_and_chunk_independent(write_csv):
    n = 25_000
    rows = [f"2026-09-{1 + i % 28:02d},c{i % 7},ch{i % 3},{100 + i},{i % 50},{i % 13}.50,{i % 5},{i % 17}.25" for i in range(n)]
    path = write_csv(rows=rows)
    small, big = validate_csv(path, chunk_rows=999), validate_csv(path, chunk_rows=1_000_000)
    assert small == big and small.rows_read == small.rows_accepted == n
    a = analyze_csv(path, chunk_rows=999)
    assert a.get("impressions").value == sum(100 + i for i in range(n))
    assert a.get("clicks").value == sum(i % 50 for i in range(n))
    assert analyze_csv(path, chunk_rows=1_000_000).model_dump() == a.model_dump()


def test_duplicates_detected_across_chunks(write_csv):
    r = validate_csv(write_csv(rows=[GOOD[0]] + [GOOD[1]] * 3 + [GOOD[0]]), chunk_rows=2)
    assert (r.duplicate_row_count, r.duplicate_group_count) == (3, 2)
