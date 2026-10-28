"""Order attachment association, integrity and native membership boundaries."""

import hashlib
import json
import sqlite3
from types import SimpleNamespace

import pytest
from test_manufacturer_platform import source_db, bind
from manufacturer_store import CompanySource, Missing, SourceUnavailable
from manufacturer_order_files import files, original, local_file, validate_metadata
from manufacturer_source_http import RemoteCompanySource


def source(tmp_path, mime="application/pdf"):
    database = tmp_path / "orders.sqlite"
    source_db(database)
    state = tmp_path / "native"
    bind(state, database)
    raw = b"%PDF-1.7\nOriginal specification"
    metadata = {
        "id": "a" * 32,
        "name": "Door schedule.pdf",
        "content_type": mime,
        "size": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
    }
    with sqlite3.connect(database) as db:
        db.execute(
            "INSERT INTO order_files(id,order_id,name,content_type,size,sha256,created_at,upload_key) VALUES(?,?,?,?,?,?,?,?)",
            (
                metadata["id"],
                "o1",
                metadata["name"],
                metadata["content_type"],
                metadata["size"],
                metadata["sha256"],
                1,
                "test-upload",
            ),
        )
    folder = tmp_path / "order-files"
    folder.mkdir(mode=0o700)
    path = folder / metadata["id"]
    path.write_bytes(raw)
    path.chmod(0o600)
    return CompanySource(state, "workspace-a"), metadata, raw, path


def test_original_is_company_and_order_bound_with_verified_bytes(tmp_path):
    selected, metadata, raw, path = source(tmp_path)
    checks = []
    workspace = SimpleNamespace(source=selected, member=lambda actor: checks.append(actor))
    listing = files(workspace, "owner", "o1")
    assert listing["files"][0]["name"] == metadata["name"]
    assert listing["files"][0]["url"].endswith("/o1/files/" + metadata["id"])
    body, mime, headers = original(workspace, "owner", "o1", metadata["id"])
    assert body == raw and mime == "application/pdf"
    assert headers["Cache-Control"] == "private, no-store"
    assert (
        headers["Content-Disposition"].startswith("inline;")
        and "sandbox" in headers["Content-Security-Policy"]
    )
    assert checks == ["owner"] * 4
    assert original(workspace, "owner", "o1", metadata["id"], True)[2]["Content-Disposition"].startswith(
        "attachment;"
    )
    with pytest.raises(Missing):
        original(workspace, "owner", "other-order", metadata["id"])
    with pytest.raises(Missing):
        original(workspace, "owner", "o1", "../" + metadata["id"])
    selected.company_id = "another-company"
    with pytest.raises(SourceUnavailable):
        files(workspace, "owner", "o1")


@pytest.mark.parametrize("damage", ["bytes", "symlink", "hardlink", "public"])
def test_damaged_or_nonprivate_original_is_unavailable(tmp_path, damage):
    selected, metadata, raw, path = source(tmp_path)
    if damage == "bytes":
        path.write_bytes(b"x" * len(raw))
    elif damage == "symlink":
        copy = path.with_name("other")
        copy.write_bytes(raw)
        path.unlink()
        path.symlink_to(copy)
    elif damage == "hardlink":
        path.with_name("other").hardlink_to(path)
    else:
        path.chmod(0o644)
    with pytest.raises(Missing):
        local_file(selected, "o1", metadata["id"])


def test_membership_revocation_during_read_prevents_response(tmp_path):
    selected, metadata, raw, path = source(tmp_path)
    count = 0

    def member(actor):
        nonlocal count
        count += 1
        if count == 2:
            raise ValueError("Current membership required")

    with pytest.raises(ValueError):
        original(SimpleNamespace(source=selected, member=member), "owner", "o1", metadata["id"])


def test_active_content_mime_is_download_only(tmp_path):
    selected, metadata, raw, path = source(tmp_path, mime="text/html")
    _, mime, headers = original(
        SimpleNamespace(source=selected, member=lambda actor: None), "owner", "o1", metadata["id"]
    )
    assert mime == "application/octet-stream" and headers["Content-Disposition"].startswith("attachment;")


def test_remote_file_verifies_fixed_origin_scope_and_integrity(tmp_path, monkeypatch):
    selected, metadata, raw, path = source(tmp_path)
    state = tmp_path / "remote"
    state.mkdir()
    (state / "manufacturer-source.json").write_text(
        json.dumps({"company_id": "a" * 64, "company_slug": "sample-hardware", "transport": "orders-api"})
    )
    remote = RemoteCompanySource(state, "a" * 64)
    monkeypatch.setenv("ROCOTO_MANUFACTURER_ORDERS_TOKEN", "x" * 40)
    monkeypatch.setattr(remote, "order_files", lambda order: [metadata])
    requests = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def read(self, maximum):
            return raw

    class Opener:
        def open(self, request, timeout):
            requests.append(request)
            return Response()

    monkeypatch.setattr("urllib.request.build_opener", lambda *args: Opener())
    assert remote.order_file("o1", metadata["id"])[1] == raw
    assert requests[0].full_url.startswith(
        "https://orders.example.test/sample-hardware/rocoto/api/platform-state?"
    )
    assert requests[0].get_header("X-rocoto-company") == "a" * 64
    metadata["sha256"] = "0" * 64
    with pytest.raises(SourceUnavailable):
        remote.order_file("o1", metadata["id"])


def test_metadata_is_bounded():
    with pytest.raises(SourceUnavailable):
        validate_metadata({"id": "../../etc/passwd"})


def test_pdf_page_renders_original_with_bounds_and_membership(tmp_path):
    from manufacturer_order_files import pdf_page
    import fitz

    selected, metadata, raw, path = source(tmp_path)
    document = fitz.open()
    document.new_page().insert_text((60, 80), "Door schedule")
    document.new_page().insert_text((60, 80), "Second page")
    raw = document.tobytes()
    document.close()
    # This is a disposable source fixture, before production claim immutability exists.
    with sqlite3.connect(tmp_path / "orders.sqlite") as db:
        for (name,) in db.execute(
            "SELECT name FROM sqlite_master WHERE type='trigger' AND tbl_name='order_files'"
        ).fetchall():
            db.execute('DROP TRIGGER "' + name + '"')
        db.execute("UPDATE order_files SET size=?,sha256=?", (len(raw), hashlib.sha256(raw).hexdigest()))
    path.write_bytes(raw)
    checks = []
    workspace = SimpleNamespace(source=selected, member=lambda actor: checks.append(actor))
    image, headers = pdf_page(workspace, "owner", "o1", metadata["id"], 2)
    assert image.startswith(b"\x89PNG") and headers["X-Total-Pages"] == "2"
    assert headers["Cache-Control"] == "private, no-store" and checks == ["owner"] * 3
    with pytest.raises(Missing):
        pdf_page(workspace, "owner", "o1", metadata["id"], 0)
    from manufacturer_store import Invalid

    with pytest.raises(Invalid):
        pdf_page(workspace, "owner", "o1", metadata["id"], 3)


def test_pdf_pipeline_admits_before_source_and_preserves_revocation(tmp_path, monkeypatch):
    import manufacturer_order_files as module

    selected, metadata, raw, path = source(tmp_path)
    workspace = SimpleNamespace(source=selected, member=lambda actor: None)
    module.PDF_SLOT.acquire()
    try:
        monkeypatch.setattr(
            module, "original", lambda *args: pytest.fail("Busy pipeline must not read source bytes")
        )
        with pytest.raises(SourceUnavailable):
            module.pdf_page(workspace, "owner", "o1", metadata["id"], 1)
    finally:
        module.PDF_SLOT.release()
    monkeypatch.setattr(module, "original", lambda *args: (raw, "application/pdf", {}))
    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout=b"1\n\x89PNG\r\n\x1a\n"),
    )
    workspace.member = lambda actor: (_ for _ in ()).throw(ValueError("Current membership required"))
    with pytest.raises(ValueError, match="Current membership required"):
        module.pdf_page(workspace, "owner", "o1", metadata["id"], 1)
