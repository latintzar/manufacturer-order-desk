"""Saved configurator previews use the snapshot and keep browser effects isolated."""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1] / "verticals/manufacturer"
spec = importlib.util.spec_from_file_location(
    "manufacturer_preview_under_test", ROOT / "manufacturer_preview.py"
)
preview = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = preview
spec.loader.exec_module(preview)


def fake_fetch(calls):
    def fetch(url, limit):
        calls.append(url)
        if url.endswith("configurator.js"):
            return (
                b'/* actual widget contract */\nwindow.RocotoConfig={"accent":"#123456",'
                b'"base":"/sample-hardware/rocoto/","root":"/sample-hardware","logo":"/sample-hardware/logo.png"};\n'
                b"window.RocotoPick={};/* window.RocotoPick.ui .pick-entry */window.rendererExecuted=true;"
            )
        return b"{}"

    return fetch


def test_snapshot_catalogue_questions_and_colour_replace_baked_configuration(tmp_path):
    calls = []
    doc = {
        "configuration": {
            "accent": "#654321",
            "questionnaire": {"questions": [{"id": "door", "title": {"en": "Saved question"}}]},
        },
        "catalogue": {"cats": [], "forms": [], "metals": [], "company": {"en": "Saved company"}},
    }
    page, headers = preview.html(tmp_path, "sample-hardware", doc, fetch=fake_fetch(calls))
    assert "Saved question" in page and "Saved company" in page
    assert '"accent":"#654321"' in page
    assert "window.rendererExecuted=true" in page
    assert "connect-src 'none'" in headers["Content-Security-Policy"]
    assert "form-action 'none'" in headers["Content-Security-Policy"]
    assert headers["Cache-Control"] == "private, no-store"
    # A second saved revision reuses the same renderer, even if the public page changed.
    other, other_headers = preview.html(
        tmp_path, "sample-hardware", doc, fetch=lambda *_: pytest.fail("renderer already pinned")
    )
    assert other_headers["X-Configurator-Renderer"] == headers["X-Configurator-Renderer"]
    assert len(calls) == 3


def test_snapshot_text_cannot_close_the_script_or_insert_markup(tmp_path):
    hostile = "</script><img src=x onerror=alert(1)>"
    page, _ = preview.html(
        tmp_path,
        "sample-hardware",
        {"configuration": {"headline": hostile}, "catalogue": {"cats": []}},
        {"headline": hostile},
        fetch=fake_fetch([]),
    )
    assert hostile not in page
    assert "\\u003c/script\\u003e" in page


def test_renderer_pin_detects_tampering_and_rejects_foreign_company_paths(tmp_path):
    entry = preview.renderer(tmp_path, "sample-hardware", fetch=fake_fetch([]))
    (tmp_path / "manufacturer-preview/sample-hardware" / (entry["sha256"] + ".js")).write_text("changed")
    with pytest.raises(ValueError, match="verification"):
        preview.renderer(tmp_path, "sample-hardware", fetch=lambda *_: pytest.fail("tampering must fail closed"))
    for slug in ("../metal-m", "https://example.com", "sample-hardware/../../x"):
        with pytest.raises(ValueError, match="bound company"):
            preview.renderer(tmp_path, slug, fetch=lambda *_: pytest.fail("foreign path"))


def test_browser_adapter_has_only_snapshot_reads_and_parent_scoped_updates():
    script = (ROOT / "web/manufacturer-preview.js").read_text()
    assert "event.source !== parent" in script
    assert "relative === 'catalog.json'" in script
    assert "saved.catalogue" in script
    assert "nativeFetch" not in script
    assert "XMLHttpRequest" not in script


def test_legacy_renderer_migrates_to_complete_bundle_without_rewriting_original(tmp_path):
    import hashlib

    folder = tmp_path / "manufacturer-preview/sample-hardware"
    folder.mkdir(parents=True)
    legacy = b"window.RocotoConfig={};/* legacy shop only */"
    digest = hashlib.sha256(legacy).hexdigest()
    original = json.dumps({"sha256": digest, "config": {}, "indexes": {}, "source": "legacy"})
    (folder / (digest + ".js")).write_bytes(legacy)
    (folder / "renderer.json").write_text(original)
    entry = preview.renderer(tmp_path, "sample-hardware", fetch=fake_fetch([]))
    assert entry["schema"] == 2 and "window.RocotoPick=" in entry["script"]
    assert (folder / "renderer.json").read_text() == original
    assert (folder / (digest + ".js")).read_bytes() == legacy


def test_snapshot_keeps_its_renderer_pin_across_a_later_default_renderer(tmp_path):
    doc = {"configuration": {"picker": {"families": []}}, "catalogue": {"cats": []}}
    first, headers = preview.html(tmp_path, "sample-hardware", doc, fetch=fake_fetch([]))
    folder = tmp_path / "manufacturer-preview/sample-hardware"
    (folder / "renderer-v2.json").unlink()
    second, next_headers = preview.html(
        tmp_path, "sample-hardware", doc, fetch=lambda *_: pytest.fail("snapshot is pinned")
    )
    assert headers["X-Configurator-Renderer"] == next_headers["X-Configurator-Renderer"]
    assert "window.RocotoPick=" in first and "window.RocotoPick=" in second


def test_incomplete_bundle_is_rejected_before_pinning(tmp_path):
    with pytest.raises(ValueError, match="complete picker bundle"):
        preview.renderer(tmp_path, "sample-hardware", fetch=lambda *_: b"window.RocotoConfig={};")
    assert not (tmp_path / "manufacturer-preview/sample-hardware/renderer-v2.json").exists()


def test_older_snapshot_keeps_its_absent_optional_picker(tmp_path):
    import re

    def current_bundle(url, limit):
        body = fake_fetch([])(url, limit)
        return body.replace(b'"accent":"#123456"', b'"picker":{"families":[]},"accent":"#123456"')

    page, _ = preview.html(
        tmp_path, "sample-hardware", {"configuration": {}, "catalogue": {"cats": []}}, fetch=current_bundle
    )
    config = json.loads(re.search(r"window\.RocotoConfig=(\{[^\n]*\});", page).group(1))
    assert "picker" not in config


@pytest.mark.parametrize("language", ["en", "bg"])
def test_saved_preview_document_keeps_its_configured_language(tmp_path, language):
    page, _ = preview.html(tmp_path, "sample-hardware",
        {"configuration": {"defaultLanguage": language}, "catalogue": {"cats": []}},
        fetch=fake_fetch([]))
    assert f'<html lang="{language}">' in page
