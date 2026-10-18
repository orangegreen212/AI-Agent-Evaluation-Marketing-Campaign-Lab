"""Same synthetic input through several endpoints, side by side. NOT the evaluation benchmark.

  python -m lab.models.smoke [--endpoints local_lmstudio cloud_default] [--cloud-profile benchmark] [--json]

The dataset must live in datasets/demo/ to count as synthetic; anything else is USER_DATA and the
cloud adapter will refuse it. Cloud endpoints use the profile given by --cloud-profile (default
'default', which forbids external transfer, so the cloud row shows TRANSFER_BLOCKED until you opt in).
Prints metadata and failure kinds only, never prompts or model text.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from lab.schemas import ProfileRegistry
from lab.schemas.enums import ModelProvider

from .adapter import DataOrigin, OpenAICompatAdapter
from .advisor import PROMPT_VERSION, advise
from .config import load_endpoints

ROOT = Path(__file__).resolve().parents[3]


def data_origin_for(path: Path, demo_dir: Path = ROOT / "datasets" / "demo") -> DataOrigin:
    return DataOrigin.SYNTHETIC_DEMO if demo_dir.resolve() in path.resolve().parents else DataOrigin.USER_DATA


def run(args: argparse.Namespace) -> list[dict]:
    eps = load_endpoints(args.config)
    registry = ProfileRegistry.from_directory(ROOT / "configs" / "security_profiles")
    from lab.data import analyze_csv  # lazy: importing this module must not require pandas

    path = Path(args.dataset)
    analysis, origin = analyze_csv(path), data_origin_for(path)
    rows = []
    for name in args.endpoints:
        ep = eps[name]
        profile = registry.get(args.cloud_profile if ep.provider == ModelProvider.CLOUD else "default", 1)
        res = advise(OpenAICompatAdapter(ep, profile, prompt_version=PROMPT_VERSION), analysis, profile,
                     run_id=f"smoke-{name}", data_origin=origin)
        m = res.metrics
        row = {
            "endpoint": name, "provider": ep.provider.value, "run_status": res.run_status.value,
            "valid_report": res.report is not None, "agent_status": res.report.agent_status.value if res.report else None,
            "failure": f"{res.failure_kind.value}: {res.error_details}" if res.failure_kind else None,
            "latency_ms": None if m.latency_ms is None else round(m.latency_ms), "tokens_in": m.tokens_in,
            "tokens_out": m.tokens_out, "cost_usd": m.cost_usd, "model_id": ep.model_id, "served_model": res.served_model,
            "config_hash": res.run_config_hash[:12], "profile": f"{profile.security_profile_id}@{profile.version}",
            # sha256 of the prompt messages (aggregates only; never the prompt text, rows or model output). Lets two runs
            # prove they received the same input, and tells prompt versions apart by content, not just by label.
            "prompt_version": res.run_config.prompt_version, "input_hash": res.input_hash,
        }
        row["missing_metadata"] = [k for k in ("latency_ms", "tokens_in", "tokens_out", "served_model") if row[k] is None]
        rows.append(row)
    return rows


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default=str(ROOT / "configs" / "models.yaml"))
    ap.add_argument("--dataset", default=str(ROOT / "datasets" / "demo" / "sample_campaigns.csv"))
    ap.add_argument("--endpoints", nargs="+", default=["local_lmstudio", "cloud_default"])
    ap.add_argument("--cloud-profile", default="default")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    rows = run(args)
    if args.json:
        print(json.dumps(rows, indent=2))
    else:
        keys = ["run_status", "valid_report", "agent_status", "latency_ms", "tokens_in", "tokens_out", "cost_usd",
                "served_model", "profile", "prompt_version", "input_hash", "failure", "missing_metadata"]
        print(f"{'':18}" + "".join(f"{r['endpoint']:>26}" for r in rows))
        for k in keys:
            print(f"{k:18}" + "".join(f"{str(r[k])[:24]:>26}" for r in rows))
    return 0 if all(r["valid_report"] for r in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
