"""Secret-pattern detection driven by the SecurityProfile."""
from __future__ import annotations

import re

from lab.schemas.security_profile import SecretDetectionPolicy


def find_secret_types(text: str, policy: SecretDetectionPolicy) -> dict[str, int]:
    """Pattern name -> number of matches. Never returns matched values."""
    if not policy.enabled:
        return {}
    found: dict[str, int] = {}
    for p in policy.patterns:
        n = len(re.findall(p.regex, text))
        if n:
            found[p.name] = n
    return found


def mask_secrets(text: str, policy: SecretDetectionPolicy) -> tuple[str, dict[str, int]]:
    summary: dict[str, int] = {}
    if not policy.enabled:
        return text, summary
    for p in policy.patterns:
        text, n = re.subn(p.regex, f"[REDACTED:{p.name}]", text)
        if n:
            summary[p.name] = n
    return text, summary
