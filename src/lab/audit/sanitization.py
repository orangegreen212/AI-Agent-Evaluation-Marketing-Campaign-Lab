"""Masking before anything is written. Output is sanitized first, stored second."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Mapping

from lab.schemas.security_profile import SecurityProfile
from lab.security.canary_checks import find_canaries
from lab.security.secret_detection import mask_secrets


@dataclass(frozen=True)
class SanitizedOutput:
    text: str
    summary: dict[str, int]  # e.g. {"canary:CANARY_FAKE_API_KEY": 1, "secret:bearer_token": 2}
    canary_hits: tuple[str, ...]  # ids found BEFORE masking: feeds CRITICAL-01/03 detection


def sanitize_output(text: str, profile: SecurityProfile, canaries: Mapping[str, str]) -> SanitizedOutput:
    hits = tuple(find_canaries(text, canaries))
    summary: dict[str, int] = {}
    for cid in hits:
        text, n = re.subn(re.escape(canaries[cid]), f"[REDACTED:canary:{cid}]", text, flags=re.IGNORECASE)
        summary[f"canary:{cid}"] = n
    text, secret_summary = mask_secrets(text, profile.secret_detection_policy)
    summary.update({f"secret:{k}": v for k, v in secret_summary.items()})
    return SanitizedOutput(text=text, summary=summary, canary_hits=hits)
