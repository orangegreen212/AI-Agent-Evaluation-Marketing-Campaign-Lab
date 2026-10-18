"""One live advisor-v3 call. Prints (1) what the MODEL returned as evidence claims and (2) the evidence Python
ASSEMBLED from the deterministic metrics. Those are different things and are labelled differently.

  $env:PYTHONPATH = "$PWD\\src"        # from the project root (lab folder)
  python scripts\\diagnose_evidence_v3.py [--endpoint local_lmstudio] [--dataset datasets/demo/sample_campaigns.csv] [--show-text]

Diagnostic only: writes no file, changes no state. Prints ids, values, periods and statuses. Model prose (claims,
summary, risks) is printed only with --show-text, from the SANITIZED output.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from lab.data import analyze_csv
from lab.models import OpenAICompatAdapter, load_endpoints
from lab.models.advisor import _extract_json
from lab.models.advisor_v3 import MANDATORY_OVERALL, NO_MODEL_CLAIM_LIMITATION, PROMPT_VERSION_V3, advise_v3, assemble_evidence
from lab.models.smoke import ROOT, data_origin_for
from lab.schemas import ProfileRegistry

FACTUAL_FIELDS = ("metric_id", "value", "value_undefined_reason", "period")


def describe(res, analysis, show_text: bool = False) -> list[str]:
    out = [f"PROMPT: {res.run_config.prompt_version}  input_hash: {res.input_hash[:16]}",
           f"RUN: {res.run_status.value}  failure: {res.failure_kind.value if res.failure_kind else None}  "
           f"detail: {res.error_details}"]
    if res.sanitized_output is None:
        return out + ["no model text (the call itself failed)"]
    try:
        content = _extract_json(res.sanitized_output.text)
    except ValueError:
        return out + ["model text is not a JSON object (first 300 chars follow)", res.sanitized_output.text[:300]]

    by_calc = {m.calc_id: m for m in analysis.metrics}
    out.append("\n== MODEL OUTPUT (raw, not authoritative) ==")
    model_items = content.get("evidence") or []
    if not isinstance(model_items, list):
        model_items = []
    for i, ev in enumerate(model_items):
        if not isinstance(ev, dict):
            out.append(f"  model evidence[{i}]: not an object")
            continue
        cid = ev.get("source_calc_id")
        m = by_calc.get(cid)
        target = (f"{m.scope}/{m.group_key or '-'} {m.metric_id}" if m else "NOT a computed metric")
        out.append(f"  model evidence[{i}]: source_calc_id={cid!r} -> {target}")
        forbidden = [k for k in FACTUAL_FIELDS if k in ev]
        if forbidden:
            out.append(f"    WARNING model supplied factual field(s) {forbidden}; they are ignored and reported as a mismatch")

    out.append("\n== PYTHON-ASSEMBLED EVIDENCE (authoritative) ==")
    evidence, issues = assemble_evidence(content, analysis)
    model_ids = {ev.get("source_calc_id") for ev in model_items if isinstance(ev, dict)}
    for e in evidence:
        origin = "model claim" if e.source_calc_id in model_ids else "system claim (no model claim)"
        limited = NO_MODEL_CLAIM_LIMITATION in e.limitations
        m = by_calc[e.source_calc_id]
        out.append(f"  {e.metric_id:<12} {m.scope}/{m.group_key or '-'}  value={e.value!r}  status={m.status.value}  "
                   f"undefined_reason={e.value_undefined_reason!r}  period={e.period.start}..{e.period.end}  "
                   f"[{origin}{'; no interpretation' if limited else ''}]")
    missing = [mid for mid in MANDATORY_OVERALL if not any(e.metric_id == mid for e in evidence)]
    out.append(f"  mandatory metrics present: {len(MANDATORY_OVERALL) - len(missing)}/{len(MANDATORY_OVERALL)}"
               + (f"  missing: {missing}" if missing else ""))
    if issues:
        out.append("  model-side issues: " + "; ".join(issues)[:500])

    if show_text and res.sanitized_output.text:
        out.append("\n--- sanitized model text ---\n" + res.sanitized_output.text)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--endpoint", default="local_lmstudio")
    ap.add_argument("--dataset", default=str(ROOT / "datasets" / "demo" / "sample_campaigns.csv"))
    ap.add_argument("--config", default=str(ROOT / "configs" / "models.yaml"))
    ap.add_argument("--show-text", action="store_true", help="also print the sanitized model text (prose)")
    a = ap.parse_args(argv)
    ep = load_endpoints(a.config)[a.endpoint]
    profile = ProfileRegistry.from_directory(ROOT / "configs" / "security_profiles").get("default", 1)
    path = Path(a.dataset)
    analysis = analyze_csv(path)
    res = advise_v3(OpenAICompatAdapter(ep, profile, prompt_version=PROMPT_VERSION_V3), analysis, profile,
                    run_id="diagnose-v3", data_origin=data_origin_for(path))
    print("\n".join(describe(res, analysis, show_text=a.show_text)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
