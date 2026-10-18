"""Shared base classes and constrained types for all lab contracts."""
from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, StringConstraints

SCHEMA_VERSION = "1.0"
SchemaVersion = Literal["1.0"]


class LabModel(BaseModel):
    """Immutable, strict base: unknown fields are errors, instances are frozen."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        protected_namespaces=(),
        str_strip_whitespace=True,
    )


class VersionedModel(LabModel):
    """Persisted object. `schema_version` is required and has no default, so an
    old or missing version can never be silently read as the current one."""

    schema_version: SchemaVersion


Id = Annotated[
    str,
    StringConstraints(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$"),
]
ModelId = Annotated[
    str,
    StringConstraints(min_length=1, max_length=200, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:/@+-]*$"),
]
NonEmptyStr = Annotated[str, StringConstraints(min_length=1, strip_whitespace=True)]
Sha256Hex = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
