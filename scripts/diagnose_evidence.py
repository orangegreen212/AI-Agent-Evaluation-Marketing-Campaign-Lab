"""One live call; prints the model's evidence items next to the computed metrics they cite. Diagnostic only.

  $env:PYTHONPATH = "$PWD\\src"        # from the project root (lab folder)
  python scripts\\diagnose_evidence.py [--endpoint local_lmstudio] [--dataset datasets/demo/sample_campaigns.csv] [--show-text]

Prints only evidence fields (ids, values, periods). Synthetic demo data. The text comes from the SANITIZED output
(secrets/canaries already masked). It does not print the prompt or the summary/risks prose unless --show-text is given.
Changes nothing and writes no file.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from lab.data import analyze_csv
from lab.models import OpenAICompatAdapter, load_endpoints
from lab.models.advisor_v3 import PROMPT_VERSION_V3, advise_v3
from lab.models.advisor import _extract_json
from lab.models.smoke import ROOT, data_origin_for
from lab.schemas import ProfileRegistry


def describe(res, analysis) -> list[str]:
    out = [f"PROMPT: {res.run_config.prompt_version}  input_hash: {res.input_hash[:16]}",
           f"RUN: {res.run_status.value}  failure: {res.failure_kind.value if res.failure_kind else None}  detail: {res.error_details}"]
    if res.sanitized_output is None:
        return out + ["no model text (the call itself failed)"]
    try:
        content = _extract_json(res.sanitized_output.text)
    except ValueError:
        return out + ["model text is not a JSON object (first 300 chars follow)", res.sanitized_output.text[:300]]
    by_id = {m.calc_id: m for m in analysis.metrics}
    for i, ev in enumerate(content.get("evidence") or []):
        out.append(f"\nevidence[{i}] model says: metric_id={ev.get('metric_id')!r} value={ev.get('value')!r} "
                   f"(key 'value' present: {'value' in ev}) value_undefined_reason={ev.get('value_undefined_reason')!r} "
                   f"period={ev.get('period')}")
        calc = by_id.get(ev.get("source_calc_id"))
        if calc is None:
            out.append(f"  source_calc_id {ev.get('source_calc_id')!r}: NOT a computed metric")
            continue
        verdict = "OK"
        if (calc.value is None) != (ev.get("value") is None):
            verdict = "PRESENCE MISMATCH (model value null vs computed has value, or the reverse)"
        out.append(f"  computed: {calc.scope}/{calc.group_key} {calc.metric_id} value={calc.value!r} status={calc.status.value} "
                   f"undefined_reason={calc.value_undefined_reason!r}  -> {verdict}")
    if res.sanitized_output.text and "evidence" not in content:
        out.append("no 'evidence' key in the model's JSON")
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--endpoint", default="local_lmstudio")
    ap.add_argument("--dataset", default=str(ROOT / "datasets" / "demo" / "sample_campaigns.csv"))
    ap.add_argument("--config", default=str(ROOT / "configs" / "models.yaml"))
    ap.add_argument("--show-text", action="store_true", help="also print the whole sanitized model text")
    a = ap.parse_args(argv)
    eps = load_endpoints(a.config)
    ep = eps[a.endpoint]
    profile = ProfileRegistry.from_directory(ROOT / "configs" / "security_profiles").get("default", 1)
    path = Path(a.dataset)
    analysis = analyze_csv(path)
    res = advise_v3(
         OpenAICompatAdapter(ep, profile, prompt_version=PROMPT_VERSION_V3),
          analysis,
         profile,
         run_id="diagnose-v3",
         data_origin=data_origin_for(path),
                    )
    print("\n".join(describe(res, analysis)))
    if a.show_text and res.sanitized_output:
        print("\n--- sanitized model text ---\n" + res.sanitized_output.text)
    if res.report is not None:
        for metric_id in ("spend", "cpa", "profit"):
            items = [e for e in res.report.evidence if e.metric_id == metric_id]
            print(f"\n{metric_id}: {len(items)} evidence item(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
