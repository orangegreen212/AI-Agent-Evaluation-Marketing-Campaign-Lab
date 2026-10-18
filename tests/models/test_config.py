import pytest
from pydantic import ValidationError

from lab.models import PROMPT_VERSION, load_endpoints
from model_helpers import ROOT, endpoint

CFG = ROOT / "configs" / "models.yaml"


def test_shipped_config_loads_and_holds_no_secret():
    eps = load_endpoints(CFG, env={})
    assert set(eps) == {"local_lmstudio", "cloud_default", "hf_inference"}
    assert eps["cloud_default"].api_key_env == "CLOUD_MODEL_API_KEY"
    assert "sk-" not in CFG.read_text() and "Bearer" not in CFG.read_text()


def test_env_overrides_url_and_model_id():
    eps = load_endpoints(CFG, env={"LM_STUDIO_BASE_URL": "http://127.0.0.1:9999/v1", "LM_STUDIO_MODEL_ID": "qwen/q4"})
    assert eps["local_lmstudio"].base_url.endswith(":9999/v1") and eps["local_lmstudio"].model_id == "qwen/q4"


@pytest.mark.parametrize("url", ["http://example.com/v1", "http://192.168.1.5:1234/v1"])
def test_local_must_be_loopback(url):
    with pytest.raises(ValidationError):
        endpoint("LOCAL", base_url=url)  # a remote host labelled LOCAL would bypass the transfer policy


@pytest.mark.parametrize("kw", [dict(base_url="http://api.example.com/v1"), dict(api_key_env=None),
                                dict(base_url="https://user:pw@api.example.com/v1"),
                                dict(base_url="https://api.example.com/v1?key=abc")])
def test_cloud_needs_https_key_variable_and_clean_url(kw):
    with pytest.raises(ValidationError):
        endpoint("CLOUD", **kw)


def test_schema_mode_is_rejected_not_silently_downgraded():
    with pytest.raises(ValidationError):
        endpoint(structured_output_mode="SCHEMA")


def test_config_hash_is_stable_and_sensitive():
    a, b = endpoint().run_config(PROMPT_VERSION), endpoint().run_config(PROMPT_VERSION)
    assert a.fingerprint() == b.fingerprint() and len(a.fingerprint()) == 64
    assert endpoint(temperature=0.5).run_config(PROMPT_VERSION).fingerprint() != a.fingerprint()
    assert endpoint().run_config("advisor-v1").fingerprint() != a.fingerprint()  # a different prompt label changes the hash
    assert endpoint(model_version="Q4_K_M").run_config(PROMPT_VERSION).model_version == "Q4_K_M"
