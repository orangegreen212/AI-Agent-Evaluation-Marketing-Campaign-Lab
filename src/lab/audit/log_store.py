"""File-backed output store that refuses anything not sanitized."""
from __future__ import annotations

from pathlib import Path
from typing import Mapping

from lab.schemas.base import Id  # noqa: F401  (documents the id format)
from lab.schemas.security_profile import SecurityProfile
from lab.security.canary_checks import find_canaries
from lab.security.secret_detection import find_secret_types

from .sanitization import SanitizedOutput

import re

_RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


class UnsanitizedOutputError(ValueError):
    pass


class LogStore:
    def __init__(self, root: str | Path, profile: SecurityProfile, canaries: Mapping[str, str]) -> None:
        self._root = Path(root)
        self._profile = profile
        self._canaries = dict(canaries)

    def save_output(self, run_id: str, output: SanitizedOutput) -> str:
        if not isinstance(output, SanitizedOutput):
            raise TypeError("save_output accepts only SanitizedOutput; sanitize before writing")
        if not _RUN_ID_RE.match(run_id) or ".." in run_id:
            raise ValueError("invalid run_id for a file name")
        # Defense in depth: re-scan even if someone built a SanitizedOutput by hand.
        if find_canaries(output.text, self._canaries) or find_secret_types(
            output.text, self._profile.secret_detection_policy
        ):
            raise UnsanitizedOutputError("output still contains a canary or secret; refusing to write")
        out_dir = self._root / "outputs"
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / f"{run_id}.txt").write_text(output.text, encoding="utf-8")
        return f"outputs/{run_id}.txt"

    def read_output(self, reference: str) -> str:
        path = (self._root / reference).resolve()
        if self._root.resolve() not in path.parents:
            raise ValueError("reference points outside the store")
        return path.read_text(encoding="utf-8")
