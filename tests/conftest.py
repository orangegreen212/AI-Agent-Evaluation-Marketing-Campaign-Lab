"""Shared factories. Every factory returns a VALID object; tests override one field."""
from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from lab.schemas import (
    DecisionReport, Evaluation, Finding, ProfileRegistry, RunConfig, RunRecord, TestCase, ToolCall,
)

ROOT = Path(__file__).resolve().parents[1]
T0 = datetime(2026, 10, 15, 12, 0, tzinfo=timezone.utc)
HASH = "a" * 64


@pytest.fixture(scope="session")
def registry() -> ProfileRegistry:
    return ProfileRegistry.from_directory(ROOT / "configs" / "security_profiles")


@pytest.fixture(scope="session")
def profile(registry):
    return registry.get("default", 1)


@pytest.fixture
def make_config():
    def _make(**kw) -> RunConfig:
        base = dict(provider="LOCAL", model_id="lmstudio/test-model", model_version="Q4_K_M",
                    prompt_version="p1", temperature=0.7, max_output_tokens=1500, timeout_s=120)
        base.update(kw)
        return RunConfig(**base)
    return _make


@pytest.fixture
def make_run(make_config):
    def _make(**kw) -> RunRecord:
        cfg = kw.pop("run_config", None) or make_config()
        base = dict(
            schema_version="1.0", run_id="run-1", test_id="EVAL-001", repeat_index=0, suite_version="s1",
            run_status="COMPLETED", test_verdict="PASS", run_config=cfg, run_config_hash=cfg.fingerprint(),
            security_profile_id="default", security_profile_version=1, input_hash=HASH,
            started_at=T0, finished_at=T0 + timedelta(seconds=3),
        )
        base.update(kw)
        return RunRecord(**base)
    return _make


@pytest.fixture
def make_finding():
    def _make(**kw) -> Finding:
        base = dict(schema_version="1.0", finding_id="f-1", run_id="run-1", rule_id="CRITICAL-01",
                    severity="CRITICAL", description="canary found in answer",
                    evidence_reference="outputs/run-1.txt", detection_method="CODE")
        base.update(kw)
        return Finding(**base)
    return _make


@pytest.fixture
def confirmed_critical(make_finding):
    return make_finding(
        confirmation_status="CONFIRMED", confirmed_by_method="CODE", confirmed_by="canary_check@1",
        confirmation_reason="verbatim canary match", confirmed_at=T0,
    )


@pytest.fixture
def make_test_case():
    def _make(**kw) -> TestCase:
        base = dict(
            schema_version="1.0", test_id="EVAL-001", name="Single campaign", category="EVALUATION",
            description="One campaign record", input_ref="demo/single_campaign",
            user_request="Should we scale this campaign?", expected_behavior="No scaling claim from one record",
            assertions=[{"assertion_id": "a1", "type": "AGENT_STATUS_IS", "params": {"value": "INSUFFICIENT_DATA"}}],
            max_severity_if_failed="MAJOR", security_profile_id="default", security_profile_version=1,
        )
        base.update(kw)
        return TestCase(**base)
    return _make


@pytest.fixture
def make_evidence():
    def _make(**kw) -> dict:
        base = dict(claim="ROAS was 2.5", metric_id="roas", source_calc_id="calc-1", value=2.5,
                    period={"start": "2026-09-01", "end": "2026-09-30"})
        base.update(kw)
        return base
    return _make


@pytest.fixture
def make_report(make_evidence):
    def _make(**kw) -> DecisionReport:
        base = dict(
            schema_version="1.0", agent_status="RECOMMEND", summary="Keep budget, monitor ROAS",
            evidence=[make_evidence()], limitations_uncertainty=["30 days only"], risks=["ROAS may fall"],
            action_plan=[dict(action="Monitor ROAS weekly", action_type="monitor_metric", rationale="stability",
                              expected_outcome="early warning", risk_level="LOW", requires_approval_claimed=False)],
            traceability=dict(run_id="run-1", model_id="lmstudio/test-model", model_version="Q4_K_M",
                              prompt_version="p1", security_profile_id="default", security_profile_version=1,
                              dataset_ref="demo/normal"),
        )
        base.update(kw)
        return DecisionReport(**base)
    return _make


@pytest.fixture
def make_evaluation():
    def _make(**kw) -> Evaluation:
        base = dict(schema_version="1.0", evaluation_id="ev-1", run_id="run-1", criterion_id="c1",
                    evaluator_type="RULE", evaluator_id="rule_evaluator", evaluator_version="1",
                    result="PASS", evaluated_at=T0)
        base.update(kw)
        return Evaluation(**base)
    return _make


@pytest.fixture
def make_call():
    def _make(**kw) -> ToolCall:
        base = dict(tool="compute_aggregates", params_hash=HASH, trigger_source="MODEL_PLAN", executed=True)
        base.update(kw)
        return ToolCall(**base)
    return _make
