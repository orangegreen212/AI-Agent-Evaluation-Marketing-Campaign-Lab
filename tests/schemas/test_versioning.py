import pytest
from pydantic import ValidationError

from lab.schemas import Finding, MigrationRegistry, RunRecord, SchemaVersionError, TestCase, load_versioned


@pytest.mark.parametrize("cls", [RunRecord, TestCase, Finding])
def test_schema_version_required(cls):
    with pytest.raises(ValidationError):
        cls.model_validate({})  # also proves schema_version has no default (other fields missing too)


def test_schema_version_required_even_when_rest_is_valid(make_finding):
    data = make_finding().model_dump()
    del data["schema_version"]
    with pytest.raises(ValidationError, match="schema_version"):
        Finding.model_validate(data)


def test_old_version_is_not_silently_read_as_current(make_finding):
    data = make_finding().model_dump()
    data["schema_version"] = "0.9"
    with pytest.raises(ValidationError):
        Finding.model_validate(data)
    with pytest.raises(SchemaVersionError, match="no explicit migration"):
        load_versioned(Finding, data)


def test_future_version_is_rejected(make_finding):
    data = {**make_finding().model_dump(), "schema_version": "2.0"}
    with pytest.raises(SchemaVersionError):
        load_versioned(Finding, data)


def test_missing_version_is_rejected_by_loader(make_finding):
    data = make_finding().model_dump()
    del data["schema_version"]
    with pytest.raises(SchemaVersionError, match="missing"):
        load_versioned(Finding, data)


def test_old_schema_version_migrates(make_finding):
    """A migration works only because it is registered explicitly (here: a test-local one)."""
    def v09_to_v10(doc):
        doc = dict(doc)
        doc["description"] = doc.pop("text")  # 0.9 called the field 'text'
        return doc

    reg = MigrationRegistry()
    reg.register("Finding", "0.9", "1.0", v09_to_v10)
    old = make_finding().model_dump()
    old["text"] = old.pop("description")
    old["schema_version"] = "0.9"

    migrated = load_versioned(Finding, old, migrations=reg)
    assert migrated.schema_version == "1.0" and migrated.description == "canary found in answer"
    # the same document without the registered step is still rejected
    with pytest.raises(SchemaVersionError):
        load_versioned(Finding, old, migrations=MigrationRegistry())


def test_migration_cycle_is_detected(make_finding):
    reg = MigrationRegistry()
    reg.register("Finding", "0.8", "0.9", lambda d: d)
    reg.register("Finding", "0.9", "0.8", lambda d: d)
    with pytest.raises(SchemaVersionError, match="cycle"):
        load_versioned(Finding, {**make_finding().model_dump(), "schema_version": "0.8"}, migrations=reg)


def test_default_registry_has_no_migrations_yet():
    from lab.schemas.versioning import DEFAULT_MIGRATIONS
    assert DEFAULT_MIGRATIONS.get("Finding", "0.9") is None
