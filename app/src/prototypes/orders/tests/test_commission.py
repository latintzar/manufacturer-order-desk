"""Commissioning exposes one complete database, including under failure and races."""

import json
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from commission import commission
from store import CompanyStore


@pytest.fixture
def setup(tmp_path):
    root, state = tmp_path / "site", tmp_path / "state"
    config = tmp_path / "company.json"
    config.write_text(json.dumps({"slug": "example", "hours": {"1": [510, 1050, 1020]}}))
    catalog = {
        "source": "https://example.test/prices/",
        "cats": [{"code": "tubes", "items": [{"c": "A", "p": 12.5, "cut": 0.75, "L": 6}]}],
    }
    source = root / "example/rocoto/catalog.json"
    source.parent.mkdir(parents=True)
    source.write_text(json.dumps(catalog))
    return root, state, config, catalog, state / "companies/example/company.db"


def test_complete_database_is_published_once(setup):
    root, state, config, catalog, path = setup
    result = commission(root, state, config)
    assert result == {"company": "example", "types": 1, "items": 1}
    assert sorted(p.name for p in path.parent.iterdir()) == ["company.db"]
    assert path.stat().st_mode & 0o777 == 0o600
    store = CompanyStore(path)
    try:
        assert store.export_catalog() == catalog
        assert store.db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        store.close()


def test_failed_ingest_leaves_final_absent_and_retry_succeeds(setup, monkeypatch):
    root, state, config, _, path = setup
    original = CompanyStore.ingest_catalog

    def fail_after_write(self, *args, **kwargs):
        original(self, *args, **kwargs)
        raise RuntimeError("simulated ingest failure")

    with monkeypatch.context() as scoped:
        scoped.setattr(CompanyStore, "ingest_catalog", fail_after_write)
        with pytest.raises(RuntimeError, match="simulated ingest failure"):
            commission(root, state, config)
    assert not path.exists()
    assert list(path.parent.iterdir()) == []
    assert commission(root, state, config)["items"] == 1


def test_failed_projection_never_exposes_candidate(setup, monkeypatch):
    root, state, config, _, path = setup
    monkeypatch.setattr(CompanyStore, "export_catalog", lambda _: {"cats": []})
    with pytest.raises(ValueError, match="projection differs"):
        commission(root, state, config)
    assert not path.exists()
    assert list(path.parent.iterdir()) == []


def test_existing_database_is_never_opened_or_overwritten(setup, monkeypatch):
    root, state, config, _, path = setup
    path.parent.mkdir(parents=True)
    path.write_bytes(b"existing store sentinel")

    def forbidden(*args, **kwargs):
        raise AssertionError("existing database must never be opened")

    monkeypatch.setattr(CompanyStore, "__init__", forbidden)
    with pytest.raises(ValueError, match="commissioned"):
        commission(root, state, config)
    assert path.read_bytes() == b"existing store sentinel"


def test_concurrent_commissioners_publish_exactly_one_store(setup, monkeypatch):
    root, state, config, catalog, path = setup
    original = CompanyStore.ingest_catalog
    barrier = Barrier(2)

    def concurrent_ingest(self, *args, **kwargs):
        result = original(self, *args, **kwargs)
        # Both have passed the initial existence check and built separate candidates.
        barrier.wait(timeout=10)
        return result

    monkeypatch.setattr(CompanyStore, "ingest_catalog", concurrent_ingest)

    def run(_):
        try:
            return commission(root, state, config)["company"]
        except ValueError as error:
            assert "commissioned" in str(error)
            return "already commissioned"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(run, range(2)))
    assert sorted(results) == ["already commissioned", "example"]
    assert sorted(p.name for p in path.parent.iterdir()) == ["company.db"]
    store = CompanyStore(path)
    try:
        assert store.export_catalog() == catalog
        assert store.one("SELECT COUNT(*) n FROM audit")["n"] == 1
    finally:
        store.close()


def test_commission_uses_complete_built_configuration(setup):
    root, state, config, _, path = setup
    complete = json.loads(config.read_text())
    complete['questionnaire'] = {'mode': 'sections', 'questions': [{'id': 'door'}]}
    complete['picker'] = {'families': [{'id': 'mortise'}]}
    complete['drawings'] = {'door': '<svg viewBox="0 0 10 10"><path d="M1 1L9 9"/></svg>'}
    (root / 'example/rocoto/configuration.json').write_text(json.dumps(complete))
    commission(root, state, config)
    store = CompanyStore(path)
    try:
        assert json.loads(store.one('SELECT config FROM company')['config']) == complete
    finally:
        store.close()
