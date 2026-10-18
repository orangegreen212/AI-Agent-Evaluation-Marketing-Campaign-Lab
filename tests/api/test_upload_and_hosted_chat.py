"""CSV upload route and the opt-in hosted-chat mode (what a Vercel deployment uses). Fake transport, no network."""
import json

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
import fastapi.testclient as fastapi_testclient  # noqa: E402

import lab.api.app as api_app  # noqa: E402
from lab.api.app import DEFAULT_DEMO, MAX_UPLOAD_BYTES, create_app  # noqa: E402

KEY = "sk-test-HOSTED-KEY-never-return-0123456789"


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    for var in ("LAB_ALLOW_CLOUD_CHAT", "LAB_ALLOW_CLOUD_EVALUATION", "HF_TOKEN", "HF_MODEL_ID", "HF_BASE_URL",
                "CLOUD_MODEL_API_KEY", "CLOUD_MODEL_BASE_URL", "CLOUD_MODEL_ID", "VERCEL"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(api_app, "ON_VERCEL", False)


class Recorder:
    def __init__(self):
        self.calls = []

    def __call__(self, url, headers, body, timeout):
        self.calls.append((url, headers, body))
        payload = {"model": "served-x", "usage": {"prompt_tokens": 5, "completion_tokens": 2},
                   "choices": [{"message": {"role": "assistant", "content": "hello from the hosted model"},
                                "finish_reason": "stop"}]}
        return 200, json.dumps(payload).encode()


def _post_csv(client, data: bytes, **params):
    return client.post("/v1/datasets/analyze", content=data, params=params, headers={"Content-Type": "text/csv"})


# ---- upload ------------------------------------------------------------------------------------------------------

def test_upload_valid_csv_returns_validation_and_overall_metrics():
    client = fastapi_testclient.TestClient(create_app())
    r = _post_csv(client, DEFAULT_DEMO.read_bytes(), filename="my campaigns.csv")
    assert r.status_code == 200
    body = r.json()
    assert body["dataset"]["origin"] == "USER_DATA" and body["dataset"]["filename"] == "my campaigns.csv"
    assert body["dataset"]["validation"]["can_analyze"] is True
    ids = {m["metric_id"] for m in body["analysis"]["metrics"]}
    assert {"roas", "cpa", "ctr", "spend", "revenue"} <= ids
    assert all(m["scope"] == "overall" for m in body["analysis"]["metrics"])


def test_upload_with_missing_column_is_reported_not_crashed():
    client = fastapi_testclient.TestClient(create_app())
    r = _post_csv(client, b"date,campaign\n2026-09-01,a\n")
    assert r.status_code == 200
    body = r.json()
    assert body["analysis"] is None and body["dataset"]["validation"]["status"] == "INVALID"
    assert any(i["code"] == "MISSING_COLUMN" for i in body["issues"])


def test_upload_filename_is_sanitized_and_never_a_path():
    client = fastapi_testclient.TestClient(create_app())
    r = _post_csv(client, DEFAULT_DEMO.read_bytes(), filename="..\\..\\etc/<script>passwd.csv")
    assert r.json()["dataset"]["filename"] == "_script_passwd.csv"


def test_upload_rejects_empty_and_oversized_bodies():
    client = fastapi_testclient.TestClient(create_app())
    assert _post_csv(client, b"   \n").status_code == 400
    r = _post_csv(client, b"x" * (MAX_UPLOAD_BYTES + 1))
    assert r.status_code == 413 and r.json()["error"]["code"] == "FILE_TOO_LARGE"


# ---- hosted chat (LAB_ALLOW_CLOUD_CHAT=1) ------------------------------------------------------------------------

def _enable_hosted_chat(monkeypatch):
    monkeypatch.setenv("LAB_ALLOW_CLOUD_CHAT", "1")
    monkeypatch.setenv("CLOUD_MODEL_API_KEY", KEY)
    monkeypatch.setenv("CLOUD_MODEL_BASE_URL", "https://api.example.com/v1")
    monkeypatch.setenv("CLOUD_MODEL_ID", "some-chat-model")


def test_hosted_chat_stays_blocked_unless_operator_opts_in(monkeypatch):
    monkeypatch.setenv("CLOUD_MODEL_API_KEY", KEY)
    t = Recorder()
    client = fastapi_testclient.TestClient(create_app(transport=t))
    r = client.post("/v1/chat", json={"endpoint": "cloud_default", "message": "hi"})
    assert r.status_code == 403 and r.json()["error"]["code"] == "TRANSFER_BLOCKED" and t.calls == []


def test_hosted_chat_works_when_enabled_and_never_returns_the_key(monkeypatch):
    _enable_hosted_chat(monkeypatch)
    t = Recorder()
    client = fastapi_testclient.TestClient(create_app(transport=t))
    r = client.post("/v1/chat", json={"endpoint": "cloud_default", "message": "hi"})
    assert r.status_code == 200
    assert r.json()["reply"] == "hello from the hosted model" and r.json()["provider"] == "CLOUD"
    assert KEY not in r.text
    assert t.calls[0][0] == "https://api.example.com/v1/chat/completions"


def test_hosted_chat_still_blocks_messages_that_contain_secrets(monkeypatch):
    _enable_hosted_chat(monkeypatch)
    t = Recorder()
    client = fastapi_testclient.TestClient(create_app(transport=t))
    r = client.post("/v1/chat", json={"endpoint": "cloud_default", "message": "my key is sk-abcdefghijklmnopqrstuvwx"})
    assert r.status_code == 403 and r.json()["error"]["code"] == "TRANSFER_BLOCKED" and t.calls == []


def test_endpoint_list_marks_hosted_chat_and_hides_local_on_vercel(monkeypatch):
    _enable_hosted_chat(monkeypatch)
    monkeypatch.setattr(api_app, "ON_VERCEL", True)
    client = fastapi_testclient.TestClient(create_app())
    eps = {e["name"]: e for e in client.get("/v1/endpoints").json()["endpoints"]}
    assert "local_lmstudio" not in eps
    assert eps["cloud_default"]["accepts_user_data"] is True
    assert eps["hf_inference"]["accepts_user_data"] is False  # no HF_TOKEN set
