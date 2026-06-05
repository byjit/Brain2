"""Tests for the settings/config module."""

from pathlib import Path

from brain2.config import Settings


def test_data_dir_defaults_to_local_data_users():
    s = Settings(_env_file=None)
    assert str(s.data_dir).endswith("data/users")


def test_external_keys_optional_and_default_none():
    s = Settings(_env_file=None)
    assert s.gemini_api_key is None
    assert s.google_client_id is None
    assert s.google_client_secret is None


def test_env_overrides_data_dir(tmp_path, monkeypatch):
    target = tmp_path / "custom"
    monkeypatch.setenv("DATA_DIR", str(target))
    s = Settings(_env_file=None)
    assert s.data_dir == target


def test_dev_user_id_has_a_default():
    s = Settings(_env_file=None)
    assert isinstance(s.dev_user_id, str) and s.dev_user_id


def test_worker_knobs_have_sensible_defaults():
    s = Settings(_env_file=None)
    # Verified against the gemini-api-dev skill (current Flash model).
    assert s.gemini_summary_model == "gemini-3.5-flash"
    assert s.worker_max_attempts >= 1


def test_worker_knobs_overridable_by_env(monkeypatch):
    monkeypatch.setenv("GEMINI_SUMMARY_MODEL", "gemini-3.1-flash-lite-preview")
    monkeypatch.setenv("WORKER_MAX_ATTEMPTS", "5")
    s = Settings(_env_file=None)
    assert s.gemini_summary_model == "gemini-3.1-flash-lite-preview"
    assert s.worker_max_attempts == 5
