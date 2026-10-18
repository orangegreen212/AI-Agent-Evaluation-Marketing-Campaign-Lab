"""Run explicitly:  pytest -m scale -s   (excluded from the default run by pyproject addopts)."""
import time

import numpy as np
import pandas as pd
import pytest

from lab.data import analyze_csv

N = 1_000_000


@pytest.mark.scale
def test_one_million_rows_two_years(tmp_path):
    rng = np.random.default_rng(0)
    days = pd.date_range("2025-01-01", periods=730).strftime("%Y-%m-%d").to_numpy()
    imp = rng.integers(100, 100_000, N)
    df = pd.DataFrame({
        "date": days[rng.integers(0, 730, N)],
        "campaign": [f"camp_{i}" for i in rng.integers(0, 50, N)],
        "channel": np.array(["search", "social", "display", "email", "video"])[rng.integers(0, 5, N)],
        "impressions": imp, "clicks": imp // 50, "spend": rng.integers(1, 10_000, N) / 100,
        "conversions": rng.integers(0, 5, N), "revenue": rng.integers(0, 50_000, N) / 100,
    })
    path = tmp_path / "big.csv"
    df.to_csv(path, index=False)
    t = time.perf_counter()
    a = analyze_csv(path)
    print(f"\n1M rows analyzed in {time.perf_counter() - t:.1f}s")
    assert a.validation.rows_read == a.validation.rows_accepted == N
    assert a.get("impressions").value == int(df["impressions"].sum())
    assert a.get("conversions").value == int(df["conversions"].sum())
    assert a.get("spend").value == pytest.approx(df["spend"].sum(), rel=1e-9)
    assert str(a.period.start) == days.min() and str(a.period.end) == days.max()
