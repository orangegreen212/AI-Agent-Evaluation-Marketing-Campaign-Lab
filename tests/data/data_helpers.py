import pytest

HEADER = "date,campaign,channel,impressions,clicks,spend,conversions,revenue"
GOOD = [
    "2026-09-01,brand,search,1000,50,100.00,5,400.00",
    "2026-09-02,brand,search,2000,80,150.50,8,600.00",
    "2026-09-02,promo,social,5000,40,200.00,2,100.00",
]


@pytest.fixture
def write_csv(tmp_path):
    def _write(rows=GOOD, header=HEADER, name="d.csv") -> str:
        lines = ([header] if header is not None else []) + list(rows)
        p = tmp_path / name
        p.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return str(p)
    return _write


def codes(result, severity=None):
    return {i.code.value for i in result.issues if severity is None or i.severity.value == severity}
