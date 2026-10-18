"""Map adapter failures to safe, fixed messages. Provider text, keys and env-var names never reach callers."""
from __future__ import annotations

from dataclasses import dataclass

from .adapter import EMPTY_CONTENT, FailureKind, ModelCallError


@dataclass(frozen=True)
class SafeError:
    code: str
    message: str
    http_status: int  # used by the HTTP API; the evaluation runner records code and message only
    stops_run: bool  # infrastructure problem: later evaluation cases would fail for the same reason


def _bad_response_message(detail: str) -> str:
    """Fixed texts only. The detail comes from adapter._empty_detail, which uses a closed vocabulary."""
    if not detail.startswith(EMPTY_CONTENT):
        return "provider response contained no usable message"
    base = "the model answered, but its reply text was empty"
    if "finish_reason=length" in detail:
        return (f"{base}: it stopped at the output-token limit (finish_reason=length)"
                + (", and the response carries a separate reasoning field, so a reasoning model most likely spent the whole "
                   "budget on hidden thinking" if "reasoning_field=present" in detail else "")
                + ". Raise max_output_tokens for this endpoint or use a model that does not reason first.")
    if "finish_reason=content_filter" in detail:
        return f"{base}: the provider's content filter withheld the reply (finish_reason=content_filter)."
    if "reasoning_field=present" in detail:
        return f"{base}, but the response carries a separate reasoning field: the model put its output there instead of in the reply."
    return f"{base} (finish_reason={detail.split('finish_reason=')[1].split(';')[0]}). The provider returned no text for this request."


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
        return SafeError("INVALID_PROVIDER_RESPONSE", _bad_response_message(detail), 502, True)
    return SafeError("MODEL_ERROR", "model call failed", 502, False)
