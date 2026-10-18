"""Hugging Face is configured as a CLOUD endpoint in the existing adapter. These tests pin its behaviour with a fake
transport. Nothing here needs a Hugging Face token or network access.

UNVERIFIED in this repository: the default router base URL and whether a given model accepts the OpenAI-style
request body. Verify both on the live service before relying on them."""
import pytest

from lab.models import DataOrigin, FailureKind, ModelCallError, OpenAICompatAdapter, load_endpoints
from lab.models.errors import describe_model_error
from model_helpers import ROOT, FakeTransport, bench_profile, chat_body

CFG = ROOT / "configs" / "models.yaml"
TOKEN = "hf_UNITTEST_TOKEN_0123456789abcdef"
MSG = [{"role": "user", "content": "synthetic question"}]


def _hf(**env):
    eps = load_endpoints(CFG, env={"HF_TOKEN": TOKEN, **env})
    return eps["hf_inference"]


def test_hf_endpoint_reads_model_and_base_url_from_environment_and_key_by_name_only():
    ep = _hf(HF_MODEL_ID="org/chat-model", HF_BASE_URL="https://router.example.invalid/v1")
    assert ep.model_id == "org/chat-model" and ep.base_url == "https://router.example.invalid/v1"
    assert ep.api_key_env == "HF_TOKEN"
    assert TOKEN not in ep.model_dump_json()


def test_success_sends_token_only_in_header_and_tolerates_missing_usage(bench_profile):
    t = FakeTransport((200, chat_body("ok", usage=False, model="served-hf")))
    ep = _hf(HF_MODEL_ID="org/chat-model")
    ad = OpenAICompatAdapter(ep, bench_profile, prompt_version="p", transport=t, env={"HF_TOKEN": TOKEN})
    comp = ad.complete(MSG, data_origin=DataOrigin.SYNTHETIC_DEMO)
    assert comp.text == "ok" and comp.tokens_in is None and comp.tokens_out is None and comp.cost_usd is None
    assert comp.served_model == "served-hf"
    assert t.calls[0]["headers"]["Authorization"] == f"Bearer {TOKEN}"
    assert TOKEN not in str(t.calls[0]["body"])


@pytest.mark.parametrize("status,code", [(429, "RATE_LIMITED"), (503, "MODEL_UNAVAILABLE"), (401, "PROVIDER_AUTH_FAILED"), (500, "PROVIDER_ERROR")])
def test_provider_status_codes_map_to_explicit_safe_errors(bench_profile, status, code):
    t = FakeTransport((status, b'{"error": "provider text must not leak"}'))
    ad = OpenAICompatAdapter(_hf(HF_MODEL_ID="m"), bench_profile, prompt_version="p", transport=t, env={"HF_TOKEN": TOKEN})
    with pytest.raises(ModelCallError) as e:
        ad.complete(MSG, data_origin=DataOrigin.SYNTHETIC_DEMO)
    safe = describe_model_error(e.value)
    assert safe.code == code and "provider text" not in safe.message and TOKEN not in safe.message


def test_timeout_is_reported_as_timeout(bench_profile):
    t = FakeTransport(raises=TimeoutError())
    ad = OpenAICompatAdapter(_hf(HF_MODEL_ID="m"), bench_profile, prompt_version="p", transport=t, env={"HF_TOKEN": TOKEN})
    with pytest.raises(ModelCallError) as e:
        ad.complete(MSG, data_origin=DataOrigin.SYNTHETIC_DEMO)
    assert e.value.kind == FailureKind.TIMEOUT


@pytest.mark.parametrize("payload", [b"<html>cold start page</html>", b'{"choices": []}', b'{"choices":[{"message":{"content":""}}]}'])
def test_malformed_provider_payload_is_bad_response_not_a_result(bench_profile, payload):
    t = FakeTransport((200, payload))
    ad = OpenAICompatAdapter(_hf(HF_MODEL_ID="m"), bench_profile, prompt_version="p", transport=t, env={"HF_TOKEN": TOKEN})
    with pytest.raises(ModelCallError) as e:
        ad.complete(MSG, data_origin=DataOrigin.SYNTHETIC_DEMO)
    assert e.value.kind == FailureKind.BAD_RESPONSE


def test_user_data_is_never_sent_to_hf_even_under_benchmark_profile(bench_profile):
    t = FakeTransport((200, chat_body("should not be requested")))
    ad = OpenAICompatAdapter(_hf(HF_MODEL_ID="m"), bench_profile, prompt_version="p", transport=t, env={"HF_TOKEN": TOKEN})
    with pytest.raises(ModelCallError) as e:
        ad.complete(MSG)  # default data_origin is USER_DATA
    assert e.value.kind == FailureKind.TRANSFER_BLOCKED and t.calls == []


def test_synthetic_data_is_blocked_under_default_profile(profile):
    t = FakeTransport((200, chat_body("nope")))
    ad = OpenAICompatAdapter(_hf(HF_MODEL_ID="m"), profile, prompt_version="p", transport=t, env={"HF_TOKEN": TOKEN})
    with pytest.raises(ModelCallError) as e:
        ad.complete(MSG, data_origin=DataOrigin.SYNTHETIC_DEMO)
    assert e.value.kind == FailureKind.TRANSFER_BLOCKED and t.calls == []


def test_missing_token_is_config_error_naming_no_value(bench_profile):
    eps = load_endpoints(CFG, env={"HF_MODEL_ID": "m"})
    ad = OpenAICompatAdapter(eps["hf_inference"], bench_profile, prompt_version="p", transport=FakeTransport((200, b"{}")), env={})
    with pytest.raises(ModelCallError) as e:
        ad.complete(MSG, data_origin=DataOrigin.SYNTHETIC_DEMO)
    assert e.value.kind == FailureKind.CONFIG and TOKEN not in e.value.detail
