"""Explicit schema migration. Old versions are never reinterpreted implicitly:
a document is migrated only through a registered step, otherwise it is rejected."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping, TypeVar

from .base import SCHEMA_VERSION, VersionedModel

Migration = Callable[[dict[str, Any]], dict[str, Any]]


class SchemaVersionError(ValueError):
    pass


@dataclass(frozen=True)
class MigrationStep:
    to_version: str
    fn: Migration


class MigrationRegistry:
    def __init__(self) -> None:
        self._steps: dict[tuple[str, str], MigrationStep] = {}

    def register(self, model_name: str, from_version: str, to_version: str, fn: Migration) -> None:
        if from_version == to_version:
            raise ValueError("migration must change the version")
        key = (model_name, from_version)
        if key in self._steps:
            raise ValueError(f"migration already registered for {key}")
        self._steps[key] = MigrationStep(to_version, fn)

    def get(self, model_name: str, from_version: str) -> MigrationStep | None:
        return self._steps.get((model_name, from_version))


# Intentionally empty: 1.0 is the first version. Each real migration must be
# added here together with a test (see tests/schemas/test_versioning.py).
DEFAULT_MIGRATIONS = MigrationRegistry()

T = TypeVar("T", bound=VersionedModel)


def load_versioned(
    model_cls: type[T],
    data: Mapping[str, Any],
    *,
    migrations: MigrationRegistry = DEFAULT_MIGRATIONS,
) -> T:
    doc = dict(data)
    version = doc.get("schema_version")
    if not isinstance(version, str) or not version:
        raise SchemaVersionError("schema_version is missing; refusing to guess the version")
    seen = {version}
    while version != SCHEMA_VERSION:
        step = migrations.get(model_cls.__name__, version)
        if step is None:
            raise SchemaVersionError(
                f"{model_cls.__name__}: no explicit migration from schema_version "
                f"{version!r} to {SCHEMA_VERSION!r}; refusing to interpret it as current"
            )
        doc = step.fn(dict(doc))
        doc["schema_version"] = step.to_version
        version = step.to_version
        if version in seen:
            raise SchemaVersionError("migration cycle detected")
        seen.add(version)
    return model_cls.model_validate(doc)
