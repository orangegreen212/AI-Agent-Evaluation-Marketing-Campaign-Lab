"""Stage 1 API tests. No LM Studio, no cloud credentials, no network. Skipped if the api extra is not installed."""
import json
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
import fastapi.testclient as fastapi_testclient  # noqa: E402  (module alias: a bare TestClient name is collected by pytest)

import lab.api.app as api_app  # noqa: E402
from lab.api.app import ROOT, create_app  # noqa: E402
from lab.api.__main__ import main as api_main  # noqa: E402

SECRET = "sk-test-SECRET-VALUE-0123456789abcdef"


@pytest.fixture
def client():
    return fastapi_testclient.TestClient(create_app())


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for var in ("CLOUD_MODEL_API_KEY", "CLOUD_MODEL_BASE_URL", "CLOUD_MODEL_ID", "LM_STUDIO_BASE_URL", "LM_STUDIO_MODEL_ID"):
        monkeypatch.delenv(var, raising=False)


# ---- health -----------------------------------------------------------------------------------------------------------

def test_health_reports_configuration_counts(client):
    r = client.get("/v1/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok" and body["api_version"] == "v1"
    assert body["endpoints_configured"] == 3 and body["security_profiles_loaded"] == 2  # + hf_inference (added with Hugging Face support)


def test_health_fails_closed_when_endpoint_config_is_broken(monkeypatch):
    monkeypatch.setenv("CLOUD_MODEL_BASE_URL", "https://user:pass-not-to-echo@example.com/v1")
    r = fastapi_testclient.TestClient(create_app()).get("/v1/health")
    assert r.status_code == 503
    assert r.json()["error"]["code"] == "CONFIG_UNAVAILABLE"
    assert "pass-not-to-echo" not in r.text  # the credential-bearing URL must never be echoed


def test_health_fails_closed_when_config_file_is_missing(tmp_path):
    r = fastapi_testclient.TestClient(create_app(config_path=tmp_path / "missing.yaml")).get("/v1/health")
    assert r.status_code == 503 and r.json()["error"]["code"] == "CONFIG_UNAVAILABLE"


# ---- endpoints: masking -----------------------------------------------------------------------------------------------

def test_endpoints_lists_both_configured_endpoints(client):
    r = client.get("/v1/endpoints")
    assert r.status_code == 200
    names = [e["name"] for e in r.json()["endpoints"]]
    assert names == ["cloud_default", "hf_inference", "local_lmstudio"]


def test_endpoints_never_expose_env_names_urls_paths_or_keys(client):
    text = client.get("/v1/endpoints").text
    for forbidden in ("api_key_env", "base_url_env", "model_id_env", "CLOUD_MODEL_API_KEY", "LM_STUDIO_BASE_URL", "Bearer"):
        assert forbidden not in text
    for e in client.get("/v1/endpoints").json()["endpoints"]:
        assert "/" not in e["base_url_origin"].split("://", 1)[1]  # origin only: no path


def test_endpoints_do_not_leak_an_api_key_value_from_environment(monkeypatch):
    monkeypatch.setenv("CLOUD_MODEL_API_KEY", SECRET)
    r = fastapi_testclient.TestClient(create_app()).get("/v1/endpoints")
    assert SECRET not in r.text
    cloud = next(e for e in r.json()["endpoints"] if e["name"] == "cloud_default")
    assert cloud["api_key_configured"] is True  # presence only


def test_endpoints_report_missing_key_and_local_endpoint_needs_none(client):
    eps = {e["name"]: e for e in client.get("/v1/endpoints").json()["endpoints"]}
    assert eps["cloud_default"]["api_key_configured"] is False
    assert eps["local_lmstudio"]["api_key_configured"] is None


def test_user_data_policy_flags_are_correct(client):
    eps = {e["name"]: e for e in client.get("/v1/endpoints").json()["endpoints"]}
    assert eps["local_lmstudio"]["data_locality"] == "LOCAL_MACHINE"
    assert eps["local_lmstudio"]["accepts_user_data"] is True
    assert eps["cloud_default"]["data_locality"] == "EXTERNAL_PROVIDER"
    assert eps["cloud_default"]["accepts_user_data"] is False


# ---- security profiles ------------------------------------------------------------------------------------------------

def test_profiles_list_metadata_and_keep_defaults_strict(client):
    r = client.get("/v1/security/profiles")
    assert r.status_code == 200
    profiles = {p["security_profile_id"]: p for p in r.json()["profiles"]}
    assert set(profiles) == {"benchmark", "default"}
    assert profiles["default"]["external_data_transfer"] is False
    assert profiles["benchmark"]["external_data_transfer"] is True
    assert all(p["user_data_cloud_transfer"] is False for p in profiles.values())


def test_profiles_do_not_expose_canary_ids_or_secret_patterns(client):
    text = client.get("/v1/security/profiles").text
    for hidden in ("protected_canary_ids", "CANARY_", "secret_detection_policy", "regex", "sk-["):
        assert hidden not in text


# ---- demo dataset -----------------------------------------------------------------------------------------------------

def test_demo_dataset_is_synthetic_and_hides_server_paths(client):
    r = client.get("/v1/datasets/demo")
    assert r.status_code == 200
    body = r.json()
    assert body["origin"] == "SYNTHETIC_DEMO"
    assert body["filename"] == "sample_campaigns.csv"
    assert body["validation"]["can_analyze"] is True
    assert len(body["validation"]["dataset_sha256"]) == 64
    assert str(ROOT) not in r.text


def test_demo_analysis_returns_overall_metrics_with_authoritative_values(client):
    r = client.get("/v1/datasets/demo/analysis")
    assert r.status_code == 200
    body = r.json()
    assert body["include_groups"] is False
    assert all(m["scope"] == "overall" for m in body["metrics"])
    by_id = {m["metric_id"]: m for m in body["metrics"]}
    assert {"roas", "spend", "revenue", "conversions", "cpa"} <= set(by_id)
    assert by_id["spend"]["value"] == 1400.0 and by_id["spend"]["status"] == "OK"
    assert by_id["roas"]["value"] == pytest.approx(3.25)
    assert by_id["cpa"]["value"] == pytest.approx(1400.0 / 91)


def test_demo_analysis_keeps_currency_as_limitation_not_as_undefined(client):
    spend = next(m for m in client.get("/v1/datasets/demo/analysis").json()["metrics"] if m["metric_id"] == "spend")
    assert spend["value"] == 1400.0 and spend["value_undefined_reason"] is None
    assert any("currency" in lim for lim in spend["limitations"])


def test_demo_analysis_group_rows_only_when_requested(client):
    groups = client.get("/v1/datasets/demo/analysis?include_groups=true").json()
    assert groups["include_groups"] is True
    assert any(m["scope"] != "overall" for m in groups["metrics"])


def test_demo_dataset_unavailable_is_reported_not_crashing(tmp_path):
    r = fastapi_testclient.TestClient(create_app(dataset_path=tmp_path / "missing.csv")).get("/v1/datasets/demo/analysis")
    assert r.status_code == 503 and r.json()["error"]["code"] == "DATASET_UNAVAILABLE"


# ---- error envelope ---------------------------------------------------------------------------------------------------

def test_unknown_route_returns_error_envelope(client):
    r = client.get("/v1/nope")
    assert r.status_code == 404
    assert r.json() == {"error": {"code": "NOT_FOUND", "message": "request could not be served"}}


def test_wrong_method_returns_405_envelope(client):
    r = client.post("/v1/health")
    assert r.status_code == 405 and r.json()["error"]["code"] == "METHOD_NOT_ALLOWED"


def test_bad_query_parameter_returns_422_without_echoing_input(client):
    r = client.get("/v1/datasets/demo/analysis?include_groups=maybe-SENTINEL")
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "VALIDATION_ERROR"
    assert "SENTINEL" not in r.text


def test_unexpected_failure_is_500_without_internal_details(monkeypatch):
    def boom(*_a, **_k):
        raise RuntimeError("internal detail that must not leak")
    monkeypatch.setattr(api_app, "analyze_csv", boom)
    c = fastapi_testclient.TestClient(create_app(), raise_server_exceptions=False)
    r = c.get("/v1/datasets/demo/analysis")
    assert r.status_code == 500
    assert r.json() == {"error": {"code": "INTERNAL_ERROR", "message": "internal error"}}
    assert "must not leak" not in r.text


# ---- localhost-only and reuse guarantees ------------------------------------------------------------------------------

def test_entry_point_refuses_non_loopback_host(capsys):
    with pytest.raises(SystemExit) as exc:
        api_main(["--host", "0.0.0.0"])
    assert exc.value.code == 2
    assert "loopback" in capsys.readouterr().err


def test_api_has_no_cors_or_public_bind_defaults():
    source = (ROOT / "src" / "lab" / "api" / "app.py").read_text(encoding="utf-8")
    assert "CORSMiddleware" not in source and "0.0.0.0" not in source


def test_api_reuses_existing_functions_and_does_not_duplicate_analytics():
    source = (ROOT / "src" / "lab" / "api" / "app.py").read_text(encoding="utf-8")
    for reused in ("load_endpoints", "ProfileRegistry", "analyze_csv", "data_origin_for"):
        assert reused in source
    for forbidden in ("OpenAICompatAdapter", "advise(", "advise_v3", "sum(", "pd.read_csv"):
        assert forbidden not in source  # Stage 1 does not call models or recompute metrics
