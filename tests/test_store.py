from pathlib import Path

from zoneguard.store import NetworkStore


def test_upsert_and_get_roundtrip(tmp_path: Path):
    store = NetworkStore(path=tmp_path / "networks.json")
    store.upsert("wifi:Home", label="Home", zone="home", confirmed=True)

    entry = store.get("wifi:Home")
    assert entry is not None
    assert entry.zone == "home"
    assert entry.confirmed is True


def test_persists_to_disk(tmp_path: Path):
    path = tmp_path / "networks.json"
    store = NetworkStore(path=path)
    store.upsert("wifi:Cafe", label="Cafe", zone="drop", confirmed=False)

    reloaded = NetworkStore(path=path)
    entry = reloaded.get("wifi:Cafe")
    assert entry is not None
    assert entry.zone == "drop"
    assert entry.confirmed is False


def test_remove(tmp_path: Path):
    store = NetworkStore(path=tmp_path / "networks.json")
    store.upsert("wifi:Temp", label="Temp", zone="drop", confirmed=False)
    store.remove("wifi:Temp")
    assert store.get("wifi:Temp") is None


def test_unknown_fingerprint_returns_none(tmp_path: Path):
    store = NetworkStore(path=tmp_path / "networks.json")
    assert store.get("nope") is None


def test_upsert_stores_explicit_uuid(tmp_path: Path):
    store = NetworkStore(path=tmp_path / "networks.json")
    store.upsert("wifi:Home", label="Home", zone="home", confirmed=True, uuid="abc-123")
    assert store.get("wifi:Home").uuid == "abc-123"


def test_upsert_without_uuid_preserves_existing_uuid(tmp_path: Path):
    store = NetworkStore(path=tmp_path / "networks.json")
    store.upsert("wifi:Home", label="Home", zone="home", confirmed=True, uuid="abc-123")
    store.upsert("wifi:Home", label="Home", zone="work", confirmed=True)
    assert store.get("wifi:Home").zone == "work"
    assert store.get("wifi:Home").uuid == "abc-123"


def test_entries_written_without_uuid_default_to_empty_string(tmp_path: Path):
    path = tmp_path / "networks.json"
    path.write_text(
        '{"wifi:Old": {"label": "Old", "zone": "drop", '
        '"confirmed": false, "last_seen": "2026-01-01T00:00:00+00:00"}}'
    )
    store = NetworkStore(path=path)
    assert store.get("wifi:Old").uuid == ""


def test_reload_picks_up_writes_from_another_store_instance(tmp_path: Path):
    path = tmp_path / "networks.json"
    writer = NetworkStore(path=path)
    reader = NetworkStore(path=path)

    writer.upsert("wifi:New", label="New", zone="drop", confirmed=False)
    assert reader.get("wifi:New") is None  # reader's in-memory copy is stale

    reader.reload()
    assert reader.get("wifi:New") is not None
