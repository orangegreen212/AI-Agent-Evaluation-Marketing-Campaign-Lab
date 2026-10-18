"""Explicit CORS allow-list from the environment. Off by default; never wildcard; never with credentials.

LAB_CORS_ORIGINS: comma-separated exact origins, e.g. https://my-lab.vercel.app,http://localhost:5173
Each entry must be https://host[:port], or http://localhost / http://127.0.0.1 for local development.
Paths, wildcards and credentials in an origin are rejected at startup.
"""
from __future__ import annotations

import re

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

_ORIGIN = re.compile(r"^(https://[A-Za-z0-9.-]+(:\d{1,5})?|http://(localhost|127\.0\.0\.1)(:\d{1,5})?)$")


def parse_origins(raw: str | None) -> list[str]:
    origins = [o.strip() for o in (raw or "").split(",") if o.strip()]
    for o in origins:
        if not _ORIGIN.match(o):
            raise ValueError("LAB_CORS_ORIGINS contains an invalid origin (exact https origin, or localhost http)")
    return origins


def configure_cors(app: FastAPI, raw: str | None) -> list[str]:
    origins = parse_origins(raw)
    if origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_credentials=False,
            allow_methods=["GET", "POST"],
            allow_headers=["Content-Type"],
            max_age=600,
        )
    return origins
