import json
from pathlib import Path

from zoneguard.config import Settings, write_json_atomic
from zoneguard.zone_manager import SAFE_FALLBACK_ZONE


def test_defaults_when_file_is_missing(tmp_path: Path):
    settings = Settings.load(path=tmp_path / "settings.json")
    assert settings.default_zone == SAFE_FALLBACK_ZONE
    assert settings.notify is True


def test_save_and_load_roundtrip(tmp_path: Path):
    path = tmp_path / "settings.json"
    Settings(default_zone="home", notify=False).save(path=path)

    reloaded = Settings.load(path=path)
    assert reloaded.default_zone == "home"
    assert reloaded.notify is False


def test_save_creates_parent_directory(tmp_path: Path):
    path = tmp_path / "nested" / "settings.json"
    Settings().save(path=path)
    assert path.exists()


def test_unknown_keys_are_ignored(tmp_path: Path):
    path = tmp_path / "settings.json"
    path.write_text('{"default_zone": "work", "from_a_newer_version": 1}')
    assert Settings.load(path=path).default_zone == "work"


def test_missing_keys_fall_back_to_defaults(tmp_path: Path):
    path = tmp_path / "settings.json"
    path.write_text('{"notify": false}')

    settings = Settings.load(path=path)
    assert settings.default_zone == SAFE_FALLBACK_ZONE
    assert settings.notify is False


def test_malformed_file_falls_back_to_defaults(tmp_path: Path):
    path = tmp_path / "settings.json"
    path.write_text("{ this is not json")
    assert Settings.load(path=path).default_zone == SAFE_FALLBACK_ZONE


def test_non_object_json_falls_back_to_defaults(tmp_path: Path):
    path = tmp_path / "settings.json"
    path.write_text("[1, 2, 3]")
    assert Settings.load(path=path).default_zone == SAFE_FALLBACK_ZONE


def test_write_json_atomic_leaves_no_temp_file(tmp_path: Path):
    path = tmp_path / "settings.json"
    write_json_atomic(path, {"a": 1})

    assert json.loads(path.read_text()) == {"a": 1}
    assert list(tmp_path.iterdir()) == [path]


def test_write_json_atomic_replaces_existing_content(tmp_path: Path):
    path = tmp_path / "settings.json"
    write_json_atomic(path, {"first": True})
    write_json_atomic(path, {"second": True})
    assert json.loads(path.read_text()) == {"second": True}
