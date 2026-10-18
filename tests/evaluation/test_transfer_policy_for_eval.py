"""Cloud evaluation goes through the adapter's transfer guard: with the default profile nothing is sent."""
from lab.evaluation.runner import run_safety_suite
from lab.evaluation.suite import CASES
from lab.models.adapter import OpenAICompatAdapter
from lab.models.config import ModelEndpoint


def test_cloud_endpoint_under_default_profile_never_touches_the_network(profile):
    sent = []

    def transport(url, headers, body, timeout):  # must never be called
        sent.append(url)
        return 200, b"{}"

    ep = ModelEndpoint(name="hf_inference", provider="CLOUD", base_url="https://router.example.invalid/v1",
                       model_id="m", api_key_env="HF_TOKEN")
    ad = OpenAICompatAdapter(ep, profile, prompt_version="safety-suite-1.0.0", transport=transport,
                             env={"HF_TOKEN": "hf_not_a_real_token_for_tests"})
    run = run_safety_suite(ad, profile=profile, cases=CASES)
    assert sent == []
    assert run["cases"][0]["status"] == "ERROR" and run["cases"][0]["failure"].startswith("TRANSFER_BLOCKED")
    assert [c["status"] for c in run["cases"][1:]] == ["SKIPPED"] * 3
    assert run["status"] == "FAILED"
