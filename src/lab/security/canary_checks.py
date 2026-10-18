"""Canary markers: fake secrets planted in prompts/data, searched for in outputs and logs.
Limitation: they only catch verbatim (case-insensitive) leaks of known markers, not
paraphrased or obfuscated ones; those need extra checks and human review."""
from __future__ import annotations

import re
import secrets
from typing import Mapping

MIN_CANARY_LENGTH = 16


def generate_canary(canary_id: str) -> str:
    return f"{canary_id}-{secrets.token_hex(8)}"


def _validate(canaries: Mapping[str, str]) -> None:
    for cid, value in canaries.items():
        if len(value) < MIN_CANARY_LENGTH:
            raise ValueError(f"canary {cid!r} is too short; short markers would cause false matches")


def find_canaries(text: str, canaries: Mapping[str, str]) -> list[str]:
    """Return ids of canaries present in text (ids only, never the values)."""
    _validate(canaries)
    return [cid for cid, value in canaries.items() if re.search(re.escape(value), text, re.IGNORECASE)]
