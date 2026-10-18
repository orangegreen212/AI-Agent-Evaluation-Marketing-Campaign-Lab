"""Vercel serverless entry point: serves the FastAPI app under /v1/* (see vercel.json rewrites).

The lab package lives in ../src (not installed as a package on Vercel), so it is added to sys.path here.

If the app cannot be imported or created (missing dependency, wrong Python version, bad config), a tiny fallback ASGI
app answers every request with HTTP 500 and the real reason in the usual error envelope, so the UI shows it instead
of Vercel's generic "A server error has occurred". The reason contains only exception text and module names.

`app` is assigned at module top level on purpose: Vercel finds the ASGI entry point by scanning for it there.
"""
import importlib.util
import json
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def _build():
    try:
        from lab.api.app import create_app

        return create_app()
    except BaseException as exc:  # noqa: BLE001 - anything at import time must be reported, not crash the function
        tb = traceback.format_exc().strip().splitlines()
        missing = [m for m in ("fastapi", "pydantic", "yaml", "starlette") if importlib.util.find_spec(m) is None]
        reason = (
            f"Backend failed to start: {type(exc).__name__}: {exc} "
            f"[python {sys.version.split()[0]}; modules not installed: {', '.join(missing) or 'none'}; "
            f"src present: {(ROOT / 'src' / 'lab').is_dir()}, configs present: {(ROOT / 'configs').is_dir()}] "
            f"at {' | '.join(line.strip() for line in tb[-4:])}"
        )

        async def fallback(scope, receive, send):  # minimal ASGI app, no third-party imports
            if scope["type"] != "http":
                return
            body = json.dumps({"error": {"code": "STARTUP_FAILED", "message": reason[:1500]}}).encode()
            await send({"type": "http.response.start", "status": 500,
                        "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]})
            await send({"type": "http.response.body", "body": body})

        return fallback


app = _build()
