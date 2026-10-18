"""Summarize smoke-test JSON files from repeated local trials. Stdlib only; reads files, calls nothing.

  python scripts/summarize_bench.py [--drop-first N] [--endpoint local_lmstudio] FILE_OR_GLOB ...

Each file is the output of `python -m lab.models.smoke --endpoints local_lmstudio --json` (one trial).
Trials are grouped by prompt_version. Files written by code from before Phase 2.1 have no prompt_version/input_hash
field and are shown as the advisor-v1 group. --drop-first N drops the first N files of each group (warm-up: the
first request after a model load or a prompt change pays a cold prefill).

Reports measured values only. "eff tok/s" = tokens_out / latency, which includes prompt processing, so it
understates pure generation speed. With few trials this is a smoke-level comparison, not statistics.
"""
from __future__ import annotations

import argparse
import glob
import json
import statistics as st
import sys
from collections import Counter, defaultdict

V1_LABEL = "advisor-v1 (pre-2.1 output)"


def load(paths: list[str], endpoint: str) -> list[dict]:
    rows = []
    for pattern in paths:
        for path in sorted(glob.glob(pattern)):
            with open(path, encoding="utf-8-sig") as fh:  # PowerShell's Out-File writes a BOM
                data = json.load(fh)
            for r in data if isinstance(data, list) else [data]:
                if r.get("endpoint") == endpoint:
                    rows.append({**r, "_file": path})
    return rows


def spread(xs: list[float], fmt: str = "{:.1f}") -> str:
    if not xs:
        return "n/a"
    return f"median {fmt.format(st.median(xs))} (min {fmt.format(min(xs))}, max {fmt.format(max(xs))})"


def eff_tps(r: dict) -> float | None:
    if r.get("tokens_out") and r.get("latency_ms"):
        return r["tokens_out"] / (r["latency_ms"] / 1000)
    return None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="+")
    ap.add_argument("--drop-first", type=int, default=0)
    ap.add_argument("--endpoint", default="local_lmstudio")
    a = ap.parse_args(argv)
    rows = load(a.files, a.endpoint)
    if not rows:
        print("no rows found", file=sys.stderr)
        return 2
    groups: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        groups[r.get("prompt_version") or V1_LABEL].append(r)

    print(f"{'file':24}{'status':10}{'valid':7}{'agent':10}{'latency_s':>10}{'tok_in':>8}{'tok_out':>8}{'eff_tok/s':>10}  failure")
    for label, rs in groups.items():
        print(f"-- {label}")
        for i, r in enumerate(rs):
            tps = eff_tps(r)
            mark = " (warm-up, dropped)" if i < a.drop_first else ""
            print(f"{r['_file'][-23:]:24}{r['run_status']:10}{str(r['valid_report']):7}{str(r['agent_status']):10}"
                  f"{(r['latency_ms'] or 0) / 1000:>10.1f}{str(r['tokens_in']):>8}{str(r['tokens_out']):>8}"
                  f"{'' if tps is None else format(tps, '.2f'):>10}  {r['failure'] or ''}{mark}")

    print("\nSUMMARY (measured; warm-up trials excluded)")
    kept: dict[str, list[dict]] = {k: v[a.drop_first:] for k, v in groups.items()}
    for label, rs in kept.items():
        print(f"\n[{label}]  n = {len(rs)}")
        if not rs:
            print("  no trials left after --drop-first")
            continue
        print(f"  valid_report      {sum(bool(r['valid_report']) for r in rs)}/{len(rs)}")
        print(f"  run_status        {dict(Counter(r['run_status'] for r in rs))}")
        print(f"  failures          {dict(Counter(r['failure'].split(':')[0] for r in rs if r['failure'])) or 'none'}")
        print(f"  agent_status      {dict(Counter(str(r['agent_status']) for r in rs))}")
        print(f"  latency_s         {spread([r['latency_ms'] / 1000 for r in rs if r['latency_ms']])}")
        print(f"  tokens_out        {spread([r['tokens_out'] for r in rs if r['tokens_out']], '{:.0f}')}")
        print(f"  tokens_in         {spread([r['tokens_in'] for r in rs if r['tokens_in']], '{:.0f}')}")
        print(f"  eff tok/s         {spread([t for t in map(eff_tps, rs) if t], '{:.2f}')}")
        print(f"  served_model      {sorted({str(r['served_model']) for r in rs})}")
        print(f"  config_hash       {sorted({r['config_hash'] for r in rs})}")
        print(f"  input_hash        {sorted({(r.get('input_hash') or 'n/a (pre-2.1)')[:16] for r in rs})}")

    models = {str(r["served_model"]) for r in rows} | {r["model_id"] for r in rows}
    if len(models) > 2 or len({r["model_id"] for r in rows}) > 1:
        print("\nWARNING: more than one model id / served model appears across trials; the comparison is not like for like.")
    ok = {k: v for k, v in kept.items() if len(v) >= 2 and all(r["latency_ms"] for r in v)}
    if len(ok) == 2:
        (la, ra), (lb, rb) = ok.items()
        ma, mb = st.median(r["latency_ms"] for r in ra), st.median(r["latency_ms"] for r in rb)
        lo_a, hi_a = min(r["latency_ms"] for r in ra), max(r["latency_ms"] for r in ra)
        lo_b, hi_b = min(r["latency_ms"] for r in rb), max(r["latency_ms"] for r in rb)
        overlap = not (hi_a < lo_b or hi_b < lo_a)
        print(f"\nCOMPARISON  median latency {lb} / {la} = {mb / ma:.2f}; latency ranges overlap: {'yes' if overlap else 'no'}")
        print(f"            n = {len(ra)} vs {len(rb)} trials. Treat a difference as real only if the ranges do not overlap, "
              "and even then it is a smoke-level signal for this model, dataset and machine, not a ranking.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
