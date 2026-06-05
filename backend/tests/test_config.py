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
