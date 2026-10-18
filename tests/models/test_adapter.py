import json
import logging
import time

import pytest

from lab.models import DataOrigin, FailureKind, ModelCallError
from model_helpers import KEY, bench_profile, FakeServer, FakeTransport, adapter, chat_body, endpoint, reply

MSG = [{"role": "user", "content": "hello"}]


def fail(ad, **kw):
    with pytest.raises(ModelCallError) as e:
        ad.complete(MSG, **kw)
    return e.value


# ---- LM Studio (real local HTTP server standing in for it) ----------------------------------

def test_lm_studio_connection_success(profile):
    srv = FakeServer(lambda h: reply(h, 200, chat_body("hi")))
    try:
        c = adapter(endpoint(base_url=srv.url), profile, __import__("lab.models.adapter", fromlist=["x"]).urllib_transport).complete(MSG)
    finally:
        srv.close()
    assert (c.text, c.served_model, c.tokens_in, c.tokens_out) == ("hi", "served-model-1", 1000, 200)
    assert c.latency_ms > 0 and c.cost_usd is None and srv.hits[0][0] == "/v1/chat/completions"


def test_lm_studio_connection_refused(profile):
    from lab.models.adapter import urllib_transport
    srv = FakeServer(lambda h: None)
    url = srv.url
    srv.close()  # nothing listens any more
    e = fail(adapter(endpoint(base_url=url), profile, urllib_transport))
    assert e.kind == FailureKind.CONNECTION


def test_timeout_is_reported_as_timeout(profile):
    from lab.models.adapter import urllib_transport
    srv = FakeServer(lambda h: (time.sleep(1.5), None)[1])
    try:
        t0 = time.perf_counter()
        e = fail(adapter(endpoint(base_url=srv.url, timeout_s=0.3), profile, urllib_transport))
        elapsed = time.perf_counter() - t0
    finally:
        srv.close()
    assert e.kind == FailureKind.TIMEOUT and elapsed < 1.2


def test_redirects_are_not_followed_so_the_key_cannot_travel(profile):
    from lab.models.adapter import urllib_transport
    srv = FakeServer(lambda h: reply(h, 302, b"", {"Location": "/other"}) if h.path != "/other" else reply(h, 200, b"{}"))
    try:
        e = fail(adapter(endpoint(base_url=srv.url), profile, urllib_transport))
    finally:
        srv.close()
    assert (e.kind, e.detail) == (FailureKind.HTTP_ERROR, "HTTP 302") and [h[0] for h in srv.hits] == ["/v1/chat/completions"]


# ---- cloud (mocked) ---------------------------------------------------------------------------

def test_cloud_success_sends_key_only_in_header_and_estimates_cost(bench_profile):
    t = FakeTransport((200, chat_body("ok")))
    ad = adapter(endpoint("CLOUD", price_per_1m_input_usd=2.0, price_per_1m_output_usd=10.0), bench_profile, t)
    c = ad.complete(MSG, data_origin=DataOrigin.SYNTHETIC_DEMO)
    call = t.calls[0]
    assert call["headers"]["Authorization"] == f"Bearer {KEY}" and KEY not in json.dumps(call["body"])
    assert call["url"] == "https://api.example.com/v1/chat/completions" and call["timeout"] == 60
    assert c.cost_usd == pytest.approx((1000 * 2.0 + 200 * 10.0) / 1e6)
    assert "tools" not in call["body"]  # the model is never offered tools


def test_cost_and_tokens_none_when_unavailable(bench_profile):
    c = adapter(endpoint("CLOUD"), bench_profile, FakeTransport((200, chat_body("ok", usage=False)))).complete(
        MSG, data_origin=DataOrigin.SYNTHETIC_DEMO)
    assert (c.tokens_in, c.tokens_out, c.cost_usd) == (None, None, None)


@pytest.mark.parametrize("status", [401, 429, 500, 503])
def test_cloud_http_failures(bench_profile, status):
    e = fail(adapter(endpoint("CLOUD"), bench_profile, FakeTransport((status, b'{"error":"secret body"}'))),
             data_origin=DataOrigin.SYNTHETIC_DEMO)
    assert (e.kind, e.detail) == (FailureKind.HTTP_ERROR, f"HTTP {status}")


def test_missing_api_key_is_a_config_error_naming_only_the_variable(bench_profile):
    from lab.models import OpenAICompatAdapter
    ad = OpenAICompatAdapter(endpoint("CLOUD"), bench_profile, prompt_version="p", transport=FakeTransport((200, b"")), env={})
    e = fail(ad, data_origin=DataOrigin.SYNTHETIC_DEMO)
    assert e.kind == FailureKind.CONFIG and "TEST_KEY_VAR" in e.detail


@pytest.mark.parametrize("payload", [b"not json", b"{}", b'{"choices": []}', b'{"choices":[{"message":{"content":""}}]}',
                                     b'{"choices":[{"message":{"content":null}}]}', b'[1,2]'])
def test_malformed_provider_payloads(profile, payload):
    assert fail(adapter(endpoint(), profile, FakeTransport((200, payload)))).kind == FailureKind.BAD_RESPONSE


@pytest.mark.parametrize("exc,kind", [(TimeoutError(), FailureKind.TIMEOUT), (ConnectionRefusedError(), FailureKind.CONNECTION),
                                      (OSError(f"boom {KEY}"), FailureKind.CONNECTION)])
def test_transport_exceptions_never_leak_their_text(profile, exc, kind):
    e = fail(adapter(endpoint(), profile, FakeTransport(raises=exc)))
    assert e.kind == kind and KEY not in str(e) and KEY not in e.detail


# ---- external transfer policy ---------------------------------------------------------------

def test_cloud_blocked_by_default_profile_and_network_never_touched(profile):
    t = FakeTransport((200, chat_body("x")))
    e = fail(adapter(endpoint("CLOUD"), profile, t), data_origin=DataOrigin.SYNTHETIC_DEMO)
    assert e.kind == FailureKind.TRANSFER_BLOCKED and t.calls == []


def test_cloud_blocked_for_user_data_even_under_benchmark(bench_profile):
    t = FakeTransport((200, chat_body("x")))
    for origin in (DataOrigin.USER_DATA, ):
        assert fail(adapter(endpoint("CLOUD"), bench_profile, t), data_origin=origin).kind == FailureKind.TRANSFER_BLOCKED
    assert fail(adapter(endpoint("CLOUD"), bench_profile, t)).kind == FailureKind.TRANSFER_BLOCKED  # default origin is USER_DATA
    assert t.calls == []


def test_cloud_blocked_when_prompt_contains_secret_or_canary(bench_profile):
    t = FakeTransport((200, chat_body("x")))
    ad = adapter(endpoint("CLOUD"), bench_profile, t, canaries={"CANARY_FAKE_API_KEY": "CANARY_FAKE_API_KEY-0123456789abcdef"})
    for text in (f"here is my key {KEY}", "note CANARY_FAKE_API_KEY-0123456789abcdef"):
        with pytest.raises(ModelCallError) as e:
            ad.complete([{"role": "user", "content": text}], data_origin=DataOrigin.SYNTHETIC_DEMO)
        assert e.value.kind == FailureKind.TRANSFER_BLOCKED and text[-20:] not in e.value.detail
    assert t.calls == []


def test_local_model_may_receive_user_data_under_default_profile(profile):
    t = FakeTransport((200, chat_body("x")))
    adapter(endpoint(), profile, t).complete(MSG, data_origin=DataOrigin.USER_DATA)
    assert len(t.calls) == 1


# ---- logging --------------------------------------------------------------------------------

def test_logs_are_structured_and_contain_no_secret_or_prompt(bench_profile, caplog):
    caplog.set_level(logging.INFO, logger="lab.models")
    secret_prompt = "PRIVATE-PROMPT-TEXT"
    ad = adapter(endpoint("CLOUD"), bench_profile, FakeTransport((200, chat_body("RESPONSE-TEXT"))))
    ad.complete([{"role": "user", "content": secret_prompt}], data_origin=DataOrigin.SYNTHETIC_DEMO)
    with pytest.raises(ModelCallError):
        ad.complete([{"role": "user", "content": secret_prompt}])  # blocked: USER_DATA
    events = [json.loads(r.message) for r in caplog.records]
    assert [e["event"] for e in events] == ["model_call_ok", "model_call_failed"]
    assert events[0]["config_hash"] and events[0]["tokens_in"] == 1000 and events[1]["kind"] == "TRANSFER_BLOCKED"
    assert KEY not in caplog.text and secret_prompt not in caplog.text and "RESPONSE-TEXT" not in caplog.text
    assert KEY not in repr(ad) and KEY not in repr(ad.endpoint)
