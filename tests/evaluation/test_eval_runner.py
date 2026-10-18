"""Runner behaviour with a fake adapter. Verifies statuses, safety of excerpts and policy-driven stops."""
from types import SimpleNamespace

import pytest

from lab.evaluation.runner import run_safety_suite
from lab.evaluation.suite import CANARY, CASES
from lab.models.adapter import Completion, DataOrigin, FailureKind, ModelCallError
from lab.models.config import ModelEndpoint


class ScriptedAdapter:
    """Returns scripted outputs per case index; an Exception instance is raised instead."""

    def __init__(self, script, *, usage=True, served="served-1", cost=None):
        self.script, self.usage, self.served, self.cost = list(script), usage, served, cost
        self.endpoint = ModelEndpoint(name="local_lmstudio", provider="LOCAL", base_url="http://localhost:1234/v1",
                                      model_id="m-1")
        self.run_config = SimpleNamespace(fingerprint=lambda: "a" * 64, prompt_version="safety-suite-1.0.0")
        self.origins = []

    def complete(self, messages, *, data_origin=DataOrigin.USER_DATA):
        self.origins.append(data_origin)
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return Completion(text=item, served_model=self.served if self.usage else None,
                          tokens_in=10 if self.usage else None, tokens_out=5 if self.usage else None,
                          latency_ms=12.5, cost_usd=self.cost, finish_reason="stop")


GOOD = ["I can't help with that.", f"12 percent.", "No, the record has no postal address.",
        '{"answer": "12", "confidence": 0.9}']


def test_all_cases_scored_is_completed_with_metadata(profile):
    run = run_safety_suite(ScriptedAdapter(GOOD), profile=profile, cases=CASES)
    assert run["status"] == "COMPLETED"
    assert [c["status"] for c in run["cases"]] == ["PASS"] * 4
    assert run["aggregate"]["pass_rate"] == 1.0
    assert run["model"]["model_id"] == "m-1" and run["model"]["config_hash"] == "a" * 64
    assert run["model"]["served_model"] == "served-1" and run["suite"]["version"] == "1.0.0"
    assert run["data_origin"] == "SYNTHETIC_DEMO" and run["started_at"] <= run["finished_at"]


def test_every_case_is_sent_with_synthetic_origin(profile):
    ad = ScriptedAdapter(GOOD)
    run_safety_suite(ad, profile=profile, cases=CASES)
    assert ad.origins == [DataOrigin.SYNTHETIC_DEMO] * 4


def test_timeout_is_error_not_pass_and_remaining_cases_are_skipped(profile):
    ad = ScriptedAdapter([ModelCallError(FailureKind.TIMEOUT, "no response within 90s", 90000.0)])
    run = run_safety_suite(ad, profile=profile, cases=CASES)
    assert run["cases"][0]["status"] == "ERROR" and run["cases"][0]["failure"].startswith("MODEL_TIMEOUT")
    assert [c["status"] for c in run["cases"][1:]] == ["SKIPPED"] * 3
    assert run["status"] == "FAILED"  # no case could be scored
    assert run["aggregate"]["pass_rate"] is None  # never a fabricated rate


def test_rate_limit_stops_the_run_with_a_safe_code(profile):
    ad = ScriptedAdapter([GOOD[0], ModelCallError(FailureKind.HTTP_ERROR, "HTTP 429", 5.0)])
    run = run_safety_suite(ad, profile=profile, cases=CASES)
    assert run["cases"][0]["status"] == "PASS"
    assert run["cases"][1]["failure"].startswith("RATE_LIMITED")
    assert run["status"] == "PARTIAL"


def test_malformed_schema_output_is_fail_never_pass(profile):
    ad = ScriptedAdapter(GOOD[:3] + ["```json {answer: 12}```"])
    run = run_safety_suite(ad, profile=profile, cases=CASES)
    assert run["cases"][3]["status"] == "FAIL"
    assert run["status"] == "COMPLETED"


def test_injected_canary_in_output_fails_the_injection_case(profile):
    ad = ScriptedAdapter(["I can't help.", f"12, {CANARY}", "No.", '{"answer": "12", "confidence": 1}'])
    run = run_safety_suite(ad, profile=profile, cases=CASES)
    assert run["cases"][1]["status"] == "FAIL"


def test_secret_pattern_in_output_is_masked_in_the_excerpt(profile):
    key = "sk-" + "A" * 30  # matches the profile pattern sk-[A-Za-z0-9_-]{20,}: must not appear in the stored excerpt
    ad = ScriptedAdapter([f"I can't help. Key: {key}", "12", "No.", '{"answer": "12", "confidence": 1}'])
    run = run_safety_suite(ad, profile=profile, cases=CASES)
    assert key not in str(run)
    assert "REDACTED" in run["cases"][0]["observed_excerpt"]


def test_missing_usage_is_none_and_cost_unset_is_none(profile):
    run = run_safety_suite(ScriptedAdapter(GOOD, usage=False), profile=profile, cases=CASES)
    assert run["aggregate"]["total_input_tokens"] is None and run["aggregate"]["total_output_tokens"] is None
    assert run["aggregate"]["total_cost_usd"] is None
    assert run["model"]["served_model"] is None


def test_cost_is_summed_only_when_every_case_reports_it(profile):
    run = run_safety_suite(ScriptedAdapter(GOOD, cost=0.001), profile=profile, cases=CASES)
    assert run["aggregate"]["total_cost_usd"] == pytest.approx(0.004)
