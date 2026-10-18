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
import re
import tempfile
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
MAX_UPLOAD_BYTES = 4_000_000  # Vercel rejects request bodies above ~4.5 MB, so stay below that everywhere
ON_VERCEL = bool(os.environ.get("VERCEL"))
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


def _metric_dict(m) -> dict:
    return {
        "calc_id": m.calc_id, "metric_id": m.metric_id, "scope": m.scope, "group_key": m.group_key,
        "value": m.value, "status": m.status.value, "unit": m.unit, "formula": m.formula,
        "period": {"start": m.period.start.isoformat(), "end": m.period.end.isoformat()},
        "value_undefined_reason": m.value_undefined_reason, "limitations": list(m.limitations),
    }


def _issue_dict(i) -> dict:
    # Messages are built from codes and counts only (never raw cell values), so they are safe to return.
    return {"code": i.code.value, "severity": i.severity.value, "column": i.column, "count": i.count,
            "message": i.message, "sample_rows": list(i.sample_rows)}


def _validation_dict(v) -> dict:
    return {
        "status": v.status, "can_analyze": v.can_analyze, "dataset_sha256": v.dataset_sha256,
        "rows_read": v.rows_read, "rows_accepted": v.rows_accepted,
        "duplicate_row_count": v.duplicate_row_count,
        "issue_count": len(v.issues), "fatal_error_count": len(v.fatal_errors), "warning_count": len(v.warnings),
    }


def _safe_filename(raw: str | None) -> str:
    name = Path((raw or "upload.csv").replace("\\", "/")).name
    name = re.sub(r"[^A-Za-z0-9._ -]", "_", name)[:80].strip() or "upload.csv"
    return name


def create_app(
    *,
    config_path: str | Path = DEFAULT_CONFIG,
    profiles_dir: str | Path = DEFAULT_PROFILES,
    dataset_path: str | Path = DEFAULT_DEMO,
    transport: Transport | None = None,
) -> FastAPI:
    app = FastAPI(title="AI Agent Evaluation & Safety Lab API", version=API_VERSION, docs_url="/docs")
    analysis_cache: dict[str, Any] = {}
    allow_cloud_chat = os.environ.get("LAB_ALLOW_CLOUD_CHAT") == "1"

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
            if is_local and ON_VERCEL:
                continue  # a serverless function can never reach a loopback LM Studio
            api_key_configured = None
            if ep.api_key_env:  # report presence only; the value and the variable name are never returned
                api_key_configured = bool(os.environ.get(ep.api_key_env))
            items.append({
                "name": name,
                "provider": ep.provider.value,
                "data_locality": "LOCAL_MACHINE" if is_local else "EXTERNAL_PROVIDER",
                # Policy, not a promise about the request: chat text goes to LOCAL endpoints, or to a configured
                # CLOUD endpoint only when the operator opted in with LAB_ALLOW_CLOUD_CHAT=1.
                "accepts_user_data": is_local or (allow_cloud_chat and bool(api_key_configured)),
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
            "validation": _validation_dict(v),
            "period": {"start": a.period.start.isoformat(), "end": a.period.end.isoformat()},
            "analysis_url": f"/{API_VERSION}/datasets/demo/analysis",
        }

    @app.post("/v1/datasets/analyze")
    async def analyze_upload(request: Request, filename: str | None = None, include_groups: bool = False) -> dict:
        """Validate and analyze an uploaded CSV (raw request body, Content-Type text/csv).

        The bytes are written to a temporary file for the duration of this request only and deleted afterwards.
        Nothing is stored, logged or sent to a model. Invalid files return 200 with status INVALID and the issue list,
        and `analysis: null`, so the UI can show exactly what to fix.
        """
        declared = request.headers.get("content-length")
        if declared and declared.isdigit() and int(declared) > MAX_UPLOAD_BYTES:
            raise ApiError(413, "FILE_TOO_LARGE", f"the file is larger than {MAX_UPLOAD_BYTES // 1_000_000} MB")
        body = await request.body()
        if len(body) > MAX_UPLOAD_BYTES:
            raise ApiError(413, "FILE_TOO_LARGE", f"the file is larger than {MAX_UPLOAD_BYTES // 1_000_000} MB")
        if not body.strip():
            raise ApiError(400, "EMPTY_FILE", "the uploaded file is empty")

        with tempfile.TemporaryDirectory(prefix="lab-upload-") as tmp:
            path = Path(tmp) / "upload.csv"
            path.write_bytes(body)
            try:
                a = analyze_csv(path)
                v, issues = a.validation, a.validation.issues
            except DataNotAnalyzableError as err:
                a, v, issues = None, err.result, err.result.issues

        dataset_id = f"upload-{v.dataset_sha256[:16]}"
        period = (
            {"start": v.date_range.start.isoformat(), "end": v.date_range.end.isoformat()} if v.date_range else None
        )
        metrics = [] if a is None else [_metric_dict(m) for m in a.metrics if include_groups or m.scope == "overall"]
        return {
            "dataset": {
                "dataset_id": dataset_id, "origin": "USER_DATA", "filename": _safe_filename(filename),
                "validation": _validation_dict(v), "period": period, "analysis_url": "",
            },
            "analysis": None if a is None else {
                "dataset_id": dataset_id, "origin": "USER_DATA", "period": period,
                "include_groups": include_groups, "metric_count": len(metrics), "metrics": metrics,
            },
            "issues": [_issue_dict(i) for i in issues],
        }

    @app.get("/v1/datasets/demo/analysis")
    def demo_dataset_analysis(include_groups: bool = False) -> dict:
        a = demo_analysis()
        metrics = [_metric_dict(m) for m in a.metrics if include_groups or m.scope == "overall"]
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
        allow_cloud_chat=allow_cloud_chat,
    )
    return app
