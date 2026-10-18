"""Map adapter failures to safe, fixed messages. Provider text, keys and env-var names never reach callers."""
from __future__ import annotations

from dataclasses import dataclass

from .adapter import FailureKind, ModelCallError


@dataclass(frozen=True)
class SafeError:
    code: str
    message: str
    http_status: int  # used by the HTTP API; the evaluation runner records code and message only
    stops_run: bool  # infrastructure problem: later evaluation cases would fail for the same reason


def describe_model_error(err: ModelCallError) -> SafeError:
    kind, detail = err.kind, err.detail
    if kind == FailureKind.TRANSFER_BLOCKED:
        return SafeError("TRANSFER_BLOCKED", "blocked by the external-transfer policy", 403, True)
    if kind == FailureKind.TIMEOUT:
        return SafeError("MODEL_TIMEOUT", "no response within the configured timeout", 504, True)
    if kind == FailureKind.CONFIG:
        return SafeError("MODEL_NOT_CONFIGURED", "model endpoint is not configured on the server", 503, True)
    if kind == FailureKind.CONNECTION:
        return SafeError("MODEL_UNREACHABLE", "could not connect to the model endpoint", 503, True)
    if kind == FailureKind.HTTP_ERROR:
        if detail == "HTTP 429":
            return SafeError("RATE_LIMITED", "provider rate limit reached; try again later", 429, True)
        if detail == "HTTP 503":
            return SafeError("MODEL_UNAVAILABLE", "model unavailable or still starting; try again shortly", 503, True)
        if detail in ("HTTP 401", "HTTP 403"):
            return SafeError("PROVIDER_AUTH_FAILED", "provider rejected the server's credentials", 502, True)
        if detail == "HTTP 302":
            return SafeError("PROVIDER_ERROR", "provider answered with a redirect, which is not followed", 502, True)
        return SafeError("PROVIDER_ERROR", f"provider returned an error ({detail})", 502, True)
    if kind == FailureKind.BAD_RESPONSE:
        return SafeError("INVALID_PROVIDER_RESPONSE", "provider response contained no usable message", 502, True)
    return SafeError("MODEL_ERROR", "model call failed", 502, False)
