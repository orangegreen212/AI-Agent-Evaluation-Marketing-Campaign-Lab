"""One adapter for any OpenAI-compatible chat endpoint (LM Studio locally, a configurable cloud provider).

Safety properties enforced here, immediately before the network call:
  * CLOUD needs a profile with external_data_transfer=true AND synthetic-demo data origin;
  * outbound text with secret patterns (or protected canaries) is never sent to the cloud;
  * redirects are not followed (the API key must not travel to another host);
  * response bodies of failed calls are discarded, so errors can never echo prompts or keys;
  * the API key is read from the environment per call and kept in no attribute, log or message.
No tools are offered to the model, so a recommendation cannot execute anything.
"""
from __future__ import annotations

import http.client
import json
import logging
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from enum import StrEnum
from typing import Callable, Mapping, Protocol, Sequence

from lab.schemas.enums import ModelProvider, StructuredOutputMode
from lab.schemas.run_record import RunConfig
from lab.schemas.security_profile import SecurityProfile
from lab.security.canary_checks import find_canaries
from lab.security.secret_detection import find_secret_types

from .config import ModelEndpoint

MAX_RESPONSE_BYTES = 5_000_000
log = logging.getLogger("lab.models")


class DataOrigin(StrEnum):
    SYNTHETIC_DEMO = "SYNTHETIC_DEMO"
    USER_DATA = "USER_DATA"  # fail-safe default everywhere


class FailureKind(StrEnum):
    TRANSFER_BLOCKED = "TRANSFER_BLOCKED"
    CONFIG = "CONFIG"
    CONNECTION = "CONNECTION"
    TIMEOUT = "TIMEOUT"
    HTTP_ERROR = "HTTP_ERROR"
    BAD_RESPONSE = "BAD_RESPONSE"          # provider payload has no usable message
    MALFORMED_OUTPUT = "MALFORMED_OUTPUT"  # model text is not a JSON object
    SCHEMA_INVALID = "SCHEMA_INVALID"      # JSON does not satisfy DecisionReport
    EVIDENCE_MISMATCH = "EVIDENCE_MISMATCH"  # evidence disagrees with the deterministic metrics


class ModelCallError(Exception):
    """`detail` is built by this package from types and codes only: never from payloads or keys."""

    def __init__(self, kind: FailureKind, detail: str, latency_ms: float | None = None) -> None:
        super().__init__(f"{kind.value}: {detail}")
        self.kind, self.detail, self.latency_ms = kind, detail, latency_ms


@dataclass(frozen=True)
class Completion:
    text: str  # raw model text: keep in memory only; sanitize before any write
    served_model: str | None
    tokens_in: int | None
    tokens_out: int | None
    latency_ms: float
    cost_usd: float | None
    finish_reason: str | None = None  # provider's reason the generation stopped; "length" means cut off by max_tokens


Messages = Sequence[Mapping[str, str]]
Transport = Callable[[str, dict, bytes, float], "tuple[int, bytes]"]  # (url, headers, body, timeout_s) -> (status, body)


class ModelAdapter(Protocol):
    """What an orchestrator needs; identical for local and cloud."""

    endpoint: ModelEndpoint
    run_config: RunConfig

    def complete(self, messages: Messages, *, data_origin: DataOrigin = DataOrigin.USER_DATA) -> Completion: ...


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):  # noqa: D401
        return None


def urllib_transport(url: str, headers: dict, body: bytes, timeout: float) -> tuple[int, bytes]:
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.build_opener(_NoRedirect).open(req, timeout=timeout) as r:
            data = r.read(MAX_RESPONSE_BYTES + 1)
            return r.status, data
    except urllib.error.HTTPError as e:
        e.close()
        return e.code, b""  # body deliberately dropped


def _emit(event: str, **fields) -> None:
    log.info(json.dumps({"event": event, **fields}, sort_keys=True, default=str))


def enforce_transfer_policy(
    profile: SecurityProfile, endpoint: ModelEndpoint, messages: Messages, data_origin: DataOrigin,
    canaries: Mapping[str, str] | None = None, *, allow_user_data_to_cloud: bool = False,
) -> None:
    if endpoint.provider == ModelProvider.LOCAL:
        return  # data stays on this machine
    if not profile.external_data_transfer:
        raise ModelCallError(FailureKind.TRANSFER_BLOCKED,
                             f"profile {profile.security_profile_id} v{profile.version} forbids external data transfer")
    # USER_DATA reaches a cloud model only when the operator has opted in (LAB_ALLOW_CLOUD_CHAT=1, chat route only).
    # The secret-pattern and canary checks below still apply.
    if data_origin != DataOrigin.SYNTHETIC_DEMO and not allow_user_data_to_cloud:
        raise ModelCallError(FailureKind.TRANSFER_BLOCKED, "only synthetic demo data may be sent to a cloud model")
    text = "\n".join(m.get("content", "") for m in messages)
    if find_secret_types(text, profile.secret_detection_policy):
        raise ModelCallError(FailureKind.TRANSFER_BLOCKED, "outbound text matches a secret pattern")
    if canaries and find_canaries(text, canaries):
        raise ModelCallError(FailureKind.TRANSFER_BLOCKED, "outbound text contains a protected canary")


# Prefixes of BAD_RESPONSE details. models/errors.py maps them to fixed, user-facing explanations.
EMPTY_CONTENT = "empty content"
_KNOWN_FINISH_REASONS = ("length", "stop", "content_filter")


def _empty_detail(raw: bytes) -> str:
    """Why a 200 response carried no usable text, as a fixed-vocabulary string (never provider text).

    Only three facts are read: the finish reason (accepted only if it is one of a known set), and whether the
    message carried a separate reasoning field (presence only, content never read). This tells the operator
    apart "the model spent its whole output budget on hidden reasoning" from "the payload is malformed".
    """
    try:
        choice = json.loads(raw)["choices"][0]
        message = choice["message"]
        if not isinstance(message, dict) or "content" not in message:
            return "response has no usable message content"
    except (ValueError, KeyError, IndexError, TypeError):
        return "response has no usable message content"
    reason = choice.get("finish_reason") if isinstance(choice, dict) else None
    reason = reason if reason in _KNOWN_FINISH_REASONS else "unknown"
    reasoning = any(isinstance(message.get(k), str) and message.get(k).strip() for k in ("reasoning", "reasoning_content"))
    return f"{EMPTY_CONTENT}; finish_reason={reason}; reasoning_field={'present' if reasoning else 'absent'}"


class OpenAICompatAdapter:
    def __init__(
        self, endpoint: ModelEndpoint, profile: SecurityProfile, *, prompt_version: str,
        transport: Transport = urllib_transport, env: Mapping[str, str] | None = None,
        canaries: Mapping[str, str] | None = None, allow_user_data_to_cloud: bool = False,
    ) -> None:
        self.endpoint = endpoint
        self.run_config = endpoint.run_config(prompt_version)
        self._profile, self._transport, self._env, self._canaries = profile, transport, env, canaries
        self._allow_user_data_to_cloud = allow_user_data_to_cloud

    def __repr__(self) -> str:
        return f"OpenAICompatAdapter({self.endpoint.name}, {self.endpoint.provider.value}, {self.endpoint.model_id})"

    def complete(self, messages: Messages, *, data_origin: DataOrigin = DataOrigin.USER_DATA) -> Completion:
        ep, cfg = self.endpoint, self.run_config
        meta = dict(endpoint=ep.name, provider=ep.provider.value, model_id=ep.model_id,
                    config_hash=cfg.fingerprint(), prompt_version=cfg.prompt_version)
        try:
            enforce_transfer_policy(self._profile, ep, messages, data_origin, self._canaries,
                                    allow_user_data_to_cloud=self._allow_user_data_to_cloud)
            comp = self._call(messages)
        except ModelCallError as e:
            _emit("model_call_failed", kind=e.kind.value, latency_ms=e.latency_ms, **meta)
            raise
        _emit("model_call_ok", latency_ms=round(comp.latency_ms, 1), tokens_in=comp.tokens_in,
              tokens_out=comp.tokens_out, cost_usd=comp.cost_usd, served_model=comp.served_model, **meta)
        return comp

    def _call(self, messages: Messages) -> Completion:
        ep, cfg = self.endpoint, self.run_config
        headers = {"Content-Type": "application/json"}
        if ep.api_key_env:
            key = (os.environ if self._env is None else self._env).get(ep.api_key_env)
            if not key:
                raise ModelCallError(FailureKind.CONFIG, f"environment variable {ep.api_key_env} is not set")
            headers["Authorization"] = f"Bearer {key}"
        body: dict = {"model": ep.model_id, "messages": [dict(m) for m in messages], "stream": False,
                      "temperature": cfg.temperature, "max_tokens": cfg.max_output_tokens}
        if cfg.seed is not None:
            body["seed"] = cfg.seed
        if cfg.structured_output_mode == StructuredOutputMode.JSON_MODE:
            body["response_format"] = {"type": "json_object"}
        t0 = time.perf_counter()
        ms = lambda: (time.perf_counter() - t0) * 1000  # noqa: E731
        try:
            status, raw = self._transport(ep.base_url.rstrip("/") + "/chat/completions", headers,
                                          json.dumps(body).encode(), cfg.timeout_s)
        except TimeoutError:
            raise ModelCallError(FailureKind.TIMEOUT, f"no response within {cfg.timeout_s}s", ms()) from None
        except urllib.error.URLError as e:
            kind = FailureKind.TIMEOUT if isinstance(e.reason, TimeoutError) else FailureKind.CONNECTION
            raise ModelCallError(kind, f"{type(e.reason).__name__}", ms()) from None
        except (OSError, http.client.HTTPException) as e:
            raise ModelCallError(FailureKind.CONNECTION, type(e).__name__, ms()) from None
        latency = ms()
        if status != 200:
            raise ModelCallError(FailureKind.HTTP_ERROR, f"HTTP {status}", latency)
        if len(raw) > MAX_RESPONSE_BYTES:
            raise ModelCallError(FailureKind.BAD_RESPONSE, "response too large", latency)
        try:
            data = json.loads(raw)
            message = data["choices"][0]["message"]
            text = message["content"]
            if not isinstance(text, str) or not text.strip():
                raise ValueError
        except (ValueError, KeyError, IndexError, TypeError):
            raise ModelCallError(FailureKind.BAD_RESPONSE, _empty_detail(raw), latency) from None
        usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
        tin, tout = usage.get("prompt_tokens"), usage.get("completion_tokens")
        tin = tin if isinstance(tin, int) and tin >= 0 else None
        tout = tout if isinstance(tout, int) and tout >= 0 else None
        served = data.get("model") if isinstance(data.get("model"), str) else None
        reason = data["choices"][0].get("finish_reason")  # choices[0] is a dict here: ["message"] succeeded above
        reason = reason if isinstance(reason, str) else None
        cost = None
        if None not in (tin, tout, ep.price_per_1m_input_usd, ep.price_per_1m_output_usd):
            cost = (tin * ep.price_per_1m_input_usd + tout * ep.price_per_1m_output_usd) / 1e6
        return Completion(text=text, served_model=served, tokens_in=tin, tokens_out=tout, latency_ms=latency, cost_usd=cost,
                          finish_reason=reason)
