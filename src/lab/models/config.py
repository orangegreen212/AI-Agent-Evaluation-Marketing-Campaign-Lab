"""Endpoint configuration. Holds no secrets: only the NAME of the API-key environment variable."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Mapping
from urllib.parse import urlsplit

import yaml
from pydantic import Field, model_validator

from lab.schemas.base import Id, LabModel, ModelId, NonEmptyStr
from lab.schemas.enums import ModelProvider, StructuredOutputMode
from lab.schemas.run_record import RunConfig

_LOOPBACK = {"localhost", "127.0.0.1", "::1"}


class ModelEndpoint(LabModel):
    name: Id
    provider: ModelProvider
    base_url: NonEmptyStr
    model_id: ModelId
    model_version: NonEmptyStr = "unspecified"
    api_key_env: Id | None = None
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    max_output_tokens: int = Field(default=1500, gt=0)
    timeout_s: float = Field(default=60.0, gt=0)
    seed: int | None = None
    structured_output_mode: StructuredOutputMode = StructuredOutputMode.NONE
    price_per_1m_input_usd: float | None = Field(default=None, ge=0)
    price_per_1m_output_usd: float | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _rules(self) -> "ModelEndpoint":
        u = urlsplit(self.base_url)
        if u.scheme not in ("http", "https") or not u.hostname:
            raise ValueError("base_url must be an http(s) URL with a host")
        if u.username or u.password or u.query or u.fragment:
            raise ValueError("base_url must not contain credentials, query or fragment")
        loopback = u.hostname in _LOOPBACK
        if self.provider == ModelProvider.LOCAL and not loopback:
            # A remote host labelled LOCAL would bypass the external-transfer policy.
            raise ValueError("LOCAL endpoints must use a loopback host (localhost, 127.0.0.1, ::1)")
        if self.provider == ModelProvider.CLOUD:
            if u.scheme != "https":
                raise ValueError("CLOUD endpoints must use https")
            if not self.api_key_env:
                raise ValueError("CLOUD endpoints need api_key_env (the variable NAME)")
        if self.structured_output_mode == StructuredOutputMode.SCHEMA:
            raise ValueError("structured_output_mode SCHEMA is not implemented in Phase 2")
        return self

    def run_config(self, prompt_version: str) -> RunConfig:
        """The Phase 0 RunConfig; its fingerprint() is the configuration hash."""
        return RunConfig(
            provider=self.provider, model_id=self.model_id, model_version=self.model_version,
            prompt_version=prompt_version, temperature=self.temperature,
            max_output_tokens=self.max_output_tokens, timeout_s=self.timeout_s, seed=self.seed,
            structured_output_mode=self.structured_output_mode,
        )


def load_endpoints(path: str | Path, env: Mapping[str, str] | None = None) -> dict[str, ModelEndpoint]:
    env = os.environ if env is None else env
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    out: dict[str, ModelEndpoint] = {}
    for name, raw in data["endpoints"].items():
        raw = dict(raw)
        for field, key in (("base_url", "base_url_env"), ("model_id", "model_id_env")):
            var = raw.pop(key, None)
            if var and env.get(var):
                raw[field] = env[var]
        out[name] = ModelEndpoint(name=name, **raw)
    return out
