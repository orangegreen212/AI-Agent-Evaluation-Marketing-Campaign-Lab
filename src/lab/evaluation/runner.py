"""Runs the safety suite through an existing model adapter. The adapter enforces the external-transfer policy.

Case statuses:
  PASS / FAIL  scored from the model output (scoring.py)
  ERROR        no usable output: the adapter raised (timeout, rate limit, provider error, ...)
  SKIPPED      not run because the run stopped after an infrastructure failure

Run status:
  COMPLETED    every case was scored (PASS or FAIL)
  PARTIAL      at least one case was scored, but some are ERROR or SKIPPED
  FAILED       no case could be scored

Nothing is fabricated: missing usage, cost or latency is reported as None.
Model output is sanitised (secret patterns masked) before it is included as an excerpt. It is labelled untrusted.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from time import perf_counter
from typing import Any, Sequence

from lab.audit.sanitization import sanitize_output
from lab.models.adapter import DataOrigin, ModelCallError
from lab.models.errors import describe_model_error

from .scoring import SCORERS
from .suite import CASES, SUITE_ID, SUITE_VERSION, SafetyCase, describe

EXCERPT_CHARS = 400


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _case_base(case: SafetyCase) -> dict[str, Any]:
    return {
        "id": case.case_id, "name": case.name, "category": case.category, "expected": case.expected,
        "status": None, "evidence": [], "failure": None, "observed_excerpt": None,
        "observed_is": "untrusted model output", "latency_ms": None,
        "input_tokens": None, "output_tokens": None, "cost_usd": None,
    }


def run_safety_suite(adapter: Any, *, profile: Any, cases: Sequence[SafetyCase] = CASES) -> dict[str, Any]:
    """Run every case in order. `adapter` is any object with .complete() and .run_config / .endpoint."""
    started = _now()
    results: list[dict[str, Any]] = []
    stop_reason: str | None = None
    served_model: str | None = None

    for case in cases:
        row = _case_base(case)
        if stop_reason is not None:
            row.update(status="SKIPPED", failure=f"not run: {stop_reason}")
            results.append(row)
            continue

        t0 = perf_counter()
        try:
            comp = adapter.complete(case.messages(), data_origin=DataOrigin.SYNTHETIC_DEMO)
        except ModelCallError as err:
            safe = describe_model_error(err)
            row.update(status="ERROR", failure=f"{safe.code}: {safe.message}",
                       latency_ms=round((perf_counter() - t0) * 1000, 1))
            results.append(row)
            if safe.stops_run:
                stop_reason = f"run stopped after {safe.code}"
            continue

        score = SCORERS[case.scorer](comp.text)
        clean = sanitize_output(comp.text, profile, {}).text
        row.update(
            status=score.status,
            evidence=list(score.evidence),
            failure=score.failure,
            observed_excerpt=clean[:EXCERPT_CHARS],
            latency_ms=round(comp.latency_ms, 1),
            input_tokens=comp.tokens_in,
            output_tokens=comp.tokens_out,
            cost_usd=comp.cost_usd,
        )
        results.append(row)
        if comp.served_model:
            served_model = comp.served_model

    finished = _now()
    return _assemble(adapter, profile, results, started, finished, served_model)


def _assemble(adapter, profile, results, started, finished, served_model) -> dict[str, Any]:
    counts = {s: sum(1 for r in results if r["status"] == s) for s in ("PASS", "FAIL", "ERROR", "SKIPPED")}
    scored = counts["PASS"] + counts["FAIL"]
    if scored == 0:
        run_status = "FAILED"
    elif counts["ERROR"] or counts["SKIPPED"]:
        run_status = "PARTIAL"
    else:
        run_status = "COMPLETED"

    measured = [r for r in results if r["status"] in ("PASS", "FAIL", "ERROR") and r["latency_ms"] is not None]
    latencies = [r["latency_ms"] for r in measured]

    def _sum(key: str) -> int | None:
        vals = [r[key] for r in results if r["status"] in ("PASS", "FAIL")]
        if not vals or any(v is None for v in vals):
            return None  # partial usage data is not reported as a total
        return sum(vals)

    cfg = adapter.run_config
    ep = adapter.endpoint
    return {
        "run_id": uuid.uuid4().hex,
        "status": run_status,
        "started_at": started,
        "finished_at": finished,
        "suite": {"id": SUITE_ID, "version": SUITE_VERSION},
        "model": {
            "endpoint": ep.name,
            "provider": ep.provider.value,
            "model_id": ep.model_id,
            "served_model": served_model,  # the identifier the provider reported, if it reported one
            "config_hash": cfg.fingerprint(),
            "prompt_version": cfg.prompt_version,
        },
        "security_profile": f"{profile.security_profile_id}@{profile.version}",
        "data_origin": DataOrigin.SYNTHETIC_DEMO.value,
        "counts": {**counts, "scored": scored, "total": len(results)},
        "aggregate": {
            "pass_rate": round(counts["PASS"] / scored, 4) if scored else None,
            "avg_latency_ms": round(sum(latencies) / len(latencies), 1) if latencies else None,
            "total_input_tokens": _sum("input_tokens"),
            "total_output_tokens": _sum("output_tokens"),
            "total_cost_usd": _sum("cost_usd"),  # from the adapter's price configuration; None when prices are unset
        },
        "cases": results,
        "limitations": describe()["limitations"],
    }
