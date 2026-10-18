"""FastAPI API (local, single-user prototype). Analytics routes are read-only; model routes live in model_routes.py.

Every handler delegates to existing lab functions. No analytics, model-adapter or policy logic lives here.

Reused:
  lab.models.config.load_endpoints      endpoint configuration (secrets stay in environment variables)
  lab.schemas.ProfileRegistry           security profiles (`.all()` for listing)
  lab.models.smoke.ROOT, data_origin_for  project root and origin rule for the demo dataset
  lab.data.analyze_csv                  validation + deterministic metrics

Error envelope (all non-2xx responses):  {"error": {"code": "...", "message": "..."}}
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from lab import __version__
from lab.data import DataNotAnalyzableError, analyze_csv
from lab.models.adapter import Transport
from lab.models.config import load_endpoints
from lab.models.smoke import ROOT, data_origin_for
from lab.schemas import ProfileRegistry
from lab.schemas.enums import ModelProvider

from .cors import configure_cors
from .errors import ApiError
from .model_routes import add_model_routes

API_VERSION = "v1"
DEMO_DATASET_ID = "demo-sample-campaigns"
DEFAULT_CONFIG = ROOT / "configs" / "models.yaml"
DEFAULT_PROFILES = ROOT / "configs" / "security_profiles"
DEFAULT_DEMO = ROOT / "datasets" / "demo" / "sample_campaigns.csv"


def _envelope(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message}})


def _origin(url: str) -> str:
    """scheme://host[:port] only: no path, query, or credentials."""
    u = urlsplit(url)
    host = u.hostname or ""
    if ":" in host:  # IPv6 literal
        host = f"[{host}]"
    return f"{u.scheme}://{host}" + (f":{u.port}" if u.port else "")


def create_app(
    *,
    config_path: str | Path = DEFAULT_CONFIG,
    profiles_dir: str | Path = DEFAULT_PROFILES,
    dataset_path: str | Path = DEFAULT_DEMO,
    transport: Transport | None = None,
) -> FastAPI:
    app = FastAPI(title="AI Agent Evaluation & Safety Lab API", version=API_VERSION, docs_url="/docs")
    analysis_cache: dict[str, Any] = {}

    def endpoints() -> dict:
        try:
            return load_endpoints(config_path)
        except Exception:  # fixed message: the underlying error may echo configuration values
            raise ApiError(503, "CONFIG_UNAVAILABLE", "model endpoint configuration could not be loaded") from None

    def profiles() -> ProfileRegistry:
        try:
            return ProfileRegistry.from_directory(profiles_dir)
        except Exception:
            raise ApiError(503, "CONFIG_UNAVAILABLE", "security profiles could not be loaded") from None

    def demo_analysis():
        if "analysis" not in analysis_cache:
            try:
                analysis_cache["analysis"] = analyze_csv(dataset_path)
            except (DataNotAnalyzableError, OSError):
                raise ApiError(503, "DATASET_UNAVAILABLE", "demo dataset could not be analyzed") from None
        return analysis_cache["analysis"]

    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError) -> JSONResponse:
        return _envelope(exc.status, exc.code, exc.message)

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        codes = {404: "NOT_FOUND", 405: "METHOD_NOT_ALLOWED"}
        return _envelope(exc.status_code, codes.get(exc.status_code, "HTTP_ERROR"), "request could not be served")

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        fields = sorted({".".join(str(p) for p in err["loc"][1:]) for err in exc.errors()})
        return _envelope(422, "VALIDATION_ERROR", f"invalid request parameters: {', '.join(fields)}")

    @app.exception_handler(Exception)
    async def _unexpected(_: Request, exc: Exception) -> JSONResponse:
        return _envelope(500, "INTERNAL_ERROR", "internal error")  # no traceback or exception text

    @app.get("/v1/health")
    def health() -> dict:
        return {
            "status": "ok", "api_version": API_VERSION, "package_version": __version__,
            "endpoints_configured": len(endpoints()), "security_profiles_loaded": len(profiles().all()),
        }

    @app.get("/v1/endpoints")
    def list_endpoints() -> dict:
        items = []
        for name, ep in sorted(endpoints().items()):
            is_local = ep.provider == ModelProvider.LOCAL
            api_key_configured = None
            if ep.api_key_env:  # report presence only; the value and the variable name are never returned
                api_key_configured = bool(os.environ.get(ep.api_key_env))
            items.append({
                "name": name,
                "provider": ep.provider.value,
                "data_locality": "LOCAL_MACHINE" if is_local else "EXTERNAL_PROVIDER",
                # Policy, not a promise about the request: user-uploaded data may go only to LOCAL endpoints.
                "accepts_user_data": is_local,
                "model_id": ep.model_id,
                "model_version": ep.model_version,
                "base_url_origin": _origin(ep.base_url),
                "temperature": ep.temperature,
                "max_output_tokens": ep.max_output_tokens,
                "timeout_s": ep.timeout_s,
                "structured_output_mode": ep.structured_output_mode.value,
                "api_key_configured": api_key_configured,  # null when the endpoint needs no key
            })
        return {"endpoints": items}

    @app.get("/v1/security/profiles")
    def list_profiles() -> dict:
        items = []
        for p in profiles().all():
            items.append({
                "security_profile_id": p.security_profile_id,
                "version": p.version,
                "name": p.name,
                "created_at": p.created_at.isoformat(),
                "external_data_transfer": p.external_data_transfer,
                # Enforced by enforce_transfer_policy: USER_DATA is refused by every cloud endpoint, whatever the profile.
                "user_data_cloud_transfer": False,
                "allowed_tools": list(p.allowed_tools),
                "approval_required_for": list(p.approval_required_for),
                "forbidden_actions": list(p.forbidden_actions),
                "no_approval_actions": list(p.no_approval_actions),
            })
        return {"profiles": items}

    @app.get("/v1/datasets/demo")
    def demo_dataset() -> dict:
        a = demo_analysis()
        v = a.validation
        return {
            "dataset_id": DEMO_DATASET_ID,
            "origin": data_origin_for(Path(dataset_path)).value,
            "filename": Path(dataset_path).name,  # file name only, never the server path
            "validation": {
                "status": v.status, "can_analyze": v.can_analyze, "dataset_sha256": v.dataset_sha256,
                "rows_read": v.rows_read, "rows_accepted": v.rows_accepted,
                "duplicate_row_count": v.duplicate_row_count,
                "issue_count": len(v.issues), "fatal_error_count": len(v.fatal_errors), "warning_count": len(v.warnings),
            },
            "period": {"start": a.period.start.isoformat(), "end": a.period.end.isoformat()},
            "analysis_url": f"/{API_VERSION}/datasets/demo/analysis",
        }

    @app.get("/v1/datasets/demo/analysis")
    def demo_dataset_analysis(include_groups: bool = False) -> dict:
        a = demo_analysis()
        selected = [m for m in a.metrics if include_groups or m.scope == "overall"]
        metrics = []
        for m in selected:
            metrics.append({
                "calc_id": m.calc_id, "metric_id": m.metric_id, "scope": m.scope, "group_key": m.group_key,
                "value": m.value, "status": m.status.value, "unit": m.unit, "formula": m.formula,
                "period": {"start": m.period.start.isoformat(), "end": m.period.end.isoformat()},
                "value_undefined_reason": m.value_undefined_reason, "limitations": list(m.limitations),
            })
        return {
            "dataset_id": DEMO_DATASET_ID,
            "origin": data_origin_for(Path(dataset_path)).value,
            "period": {"start": a.period.start.isoformat(), "end": a.period.end.isoformat()},
            "include_groups": include_groups,
            "metric_count": len(metrics),
            "metrics": metrics,
        }

    configure_cors(app, os.environ.get("LAB_CORS_ORIGINS"))
    add_model_routes(
        app,
        endpoints=endpoints,
        profiles=profiles,
        transport=transport,
        allow_cloud_evaluation=os.environ.get("LAB_ALLOW_CLOUD_EVALUATION") == "1",
    )
    return app
