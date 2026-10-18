import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from lab.data import analyze_csv
from lab.models import ModelEndpoint, OpenAICompatAdapter, PROMPT_VERSION

ROOT = Path(__file__).resolve().parents[2]
DEMO = ROOT / "datasets" / "demo" / "sample_campaigns.csv"
KEY = "sk-TESTKEY0123456789abcdefABCDEF"  # matches the profile's openai_style_key pattern on purpose


def chat_body(content, *, usage=True, model="served-model-1", finish_reason="stop"):
    """finish_reason=None leaves the key out (some providers do)."""
    body = {"model": model, "choices": [{"index": 0, "message": {"role": "assistant", "content": content}}]}
    if finish_reason is not None:
        body["choices"][0]["finish_reason"] = finish_reason
    if usage:
        body["usage"] = {"prompt_tokens": 1000, "completion_tokens": 200}
    return json.dumps(body).encode()


def good_report(analysis, **over):
    m = analysis.get("roas")
    rep = {
        "agent_status": "RECOMMEND", "summary": "Overall ROAS is healthy; keep monitoring.",
        "evidence": [{"claim": "Overall ROAS", "metric_id": m.metric_id, "source_calc_id": m.calc_id, "value": m.value,
                      "period": {"start": str(m.period.start), "end": str(m.period.end)}}],
        "limitations_uncertainty": ["three days of data"], "risks": ["ROAS may fall"],
        "action_plan": [{"action": "Raise brand budget 20%", "action_type": "change_budget", "rationale": "high ROAS",
                         "expected_outcome": "more revenue", "risk_level": "MEDIUM", "requires_approval_claimed": False}],
    }
    rep.update(over)
    return rep


class FakeTransport:
    def __init__(self, *responses, raises=None):
        self.responses, self.raises, self.calls = list(responses), raises, []

    def __call__(self, url, headers, body, timeout):
        self.calls.append(dict(url=url, headers=headers, body=json.loads(body), timeout=timeout))
        if self.raises:
            raise self.raises
        status, payload = self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]
        return status, payload


def endpoint(provider="LOCAL", **kw):
    base = dict(name="ep", provider=provider, base_url="http://localhost:1234/v1", model_id="m-1")
    if provider == "CLOUD":
        base.update(base_url="https://api.example.com/v1", api_key_env="TEST_KEY_VAR")
    base.update(kw)
    return ModelEndpoint(**base)


def adapter(ep, profile, transport, **kw):
    return OpenAICompatAdapter(ep, profile, prompt_version=PROMPT_VERSION, transport=transport,
                               env={"TEST_KEY_VAR": KEY}, **kw)


@pytest.fixture(scope="session")
def analysis():
    return analyze_csv(DEMO)


@pytest.fixture(scope="session")
def bench_profile(registry):
    return registry.get("benchmark", 1)


class FakeServer:
    """Real HTTP server on 127.0.0.1, standing in for LM Studio."""

    def __init__(self, handler):
        self.hits = []
        outer = self

        class H(BaseHTTPRequestHandler):
            def do_POST(self):
                self.rfile.read(int(self.headers.get("Content-Length", 0)))
                outer.hits.append((self.path, self.headers.get("Authorization")))
                handler(self)

            def log_message(self, *a):
                pass

        self.srv = HTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.srv.server_port}/v1"
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def close(self):
        self.srv.shutdown()
        self.srv.server_close()


def reply(h, status, payload=b"", extra=None):
    h.send_response(status)
    h.send_header("Content-Length", str(len(payload)))
    for k, v in (extra or {}).items():
        h.send_header(k, v)
    h.end_headers()
    h.wfile.write(payload)
