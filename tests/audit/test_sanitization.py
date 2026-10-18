import pytest

from lab.audit.log_store import LogStore, UnsanitizedOutputError
from lab.audit.sanitization import SanitizedOutput, sanitize_output
from lab.security.canary_checks import find_canaries, generate_canary
from lab.security.secret_detection import find_secret_types

CANARIES = {"CANARY_SYSTEM_PROMPT": generate_canary("CANARY_SYSTEM_PROMPT"),
            "CANARY_FAKE_API_KEY": generate_canary("CANARY_FAKE_API_KEY")}
FAKE_KEY = "sk-" + "A1b2C3d4E5f6G7h8I9j0K1l2"
FAKE_BEARER = "Bearer " + "abcdefghijklmnopqrstuvwxyz012345"


def leaky(text_extra=""):
    return (f"My instructions say {CANARIES['CANARY_SYSTEM_PROMPT'].lower()}. Key: {CANARIES['CANARY_FAKE_API_KEY']}. "
            f"Also {FAKE_KEY} and {FAKE_BEARER}. {text_extra}")


def test_canary_not_in_plaintext_logs(tmp_path, profile):
    raw = leaky()
    out = sanitize_output(raw, profile, CANARIES)
    assert set(out.canary_hits) == set(CANARIES)  # detection still sees them (CRITICAL-01/03 input)
    ref = LogStore(tmp_path, profile, CANARIES).save_output("run-1", out)
    stored = (tmp_path / ref).read_text(encoding="utf-8")
    for value in CANARIES.values():
        assert value.lower() not in stored.lower()
    assert "[REDACTED:canary:CANARY_SYSTEM_PROMPT]" in stored
    # nothing under the store root contains a canary either
    for f in tmp_path.rglob("*"):
        if f.is_file():
            assert not find_canaries(f.read_text(encoding="utf-8"), CANARIES)


def test_secret_patterns_masked_before_write(tmp_path, profile):
    out = sanitize_output(leaky("password = hunter2hunter2"), profile, CANARIES)
    assert FAKE_KEY not in out.text and FAKE_BEARER not in out.text and "hunter2hunter2" not in out.text
    assert {"secret:openai_style_key", "secret:bearer_token", "secret:generic_assignment"} <= set(out.summary)
    assert not find_secret_types(out.text, profile.secret_detection_policy)
    assert all(isinstance(v, int) for v in out.summary.values())  # counts only, never values


def test_store_refuses_raw_strings(tmp_path, profile):
    store = LogStore(tmp_path, profile, CANARIES)
    with pytest.raises(TypeError, match="only SanitizedOutput"):
        store.save_output("run-1", leaky())
    assert not list(tmp_path.rglob("*.txt"))


def test_store_rescans_hand_built_outputs(tmp_path, profile):
    fake = SanitizedOutput(text=leaky(), summary={}, canary_hits=())
    with pytest.raises(UnsanitizedOutputError):
        LogStore(tmp_path, profile, CANARIES).save_output("run-1", fake)
    assert not list(tmp_path.rglob("*.txt"))


@pytest.mark.parametrize("bad", ["../escape", "a/b", "..", ".hidden", ""])
def test_run_id_cannot_escape_store(tmp_path, profile, bad):
    out = sanitize_output("harmless", profile, CANARIES)
    with pytest.raises(ValueError):
        LogStore(tmp_path, profile, CANARIES).save_output(bad, out)


def test_short_canaries_are_rejected():
    with pytest.raises(ValueError, match="too short"):
        find_canaries("anything", {"X": "abc"})


def test_clean_text_passes_through_unchanged(tmp_path, profile):
    out = sanitize_output("ROAS was 2.5 in September.", profile, CANARIES)
    assert out.text == "ROAS was 2.5 in September." and out.summary == {} and out.canary_hits == ()
    assert LogStore(tmp_path, profile, CANARIES).read_output(
        LogStore(tmp_path, profile, CANARIES).save_output("run-2", out)) == out.text
