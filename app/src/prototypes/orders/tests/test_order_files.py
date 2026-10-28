import os
import stat
import time

import order_files
import pytest

pytest_plugins = ["test_store"]

PDF = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\n%%EOF\n"


def stage(store, key="upload-key-00001", name="bracket.pdf", body=PDF):
    return order_files.stage(store, name, body, key)


def custom(upload):
    return {
        "item_id": None,
        "kind": "custom",
        "description": "Laser-cut mounting bracket",
        "quantity": 1,
        "configuration": {"custom": "Laser-cut mounting bracket"},
        "cuts": 0,
        "gross": 0,
        "confirmation": True,
        "upload_id": upload["id"],
    }


def claimed_metadata(upload):
    return {key: value for key, value in upload.items() if key != "discard_token"}


def submit(store, lines, key="file-order-0001"):
    return store.submit_order(
        {"name": "Buyer", "email": "buyer@example.test"},
        lines,
        {"gross": 12, "currency": "EUR", "confirmation": True},
        key,
        "web",
        "server quote",
    )


def test_stage_validates_content_is_private_and_idempotent(store):
    upload = stage(store, name="../customer bracket.pdf")
    path = store.path.parent / "order-files" / upload["id"]
    assert upload["name"] == "customer bracket.pdf"
    assert path.read_bytes() == PDF
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
    assert stage(store, name="../customer bracket.pdf") == upload
    with pytest.raises(ValueError, match="different file"):
        stage(store, name="other.pdf", body=PDF + b"changed")
    with pytest.raises(ValueError, match="design file"):
        stage(store, key="upload-key-00002", name="payload.exe", body=b"MZpayload")
    with pytest.raises(ValueError, match="does not match"):
        stage(store, key="upload-key-00003", name="drawing.pdf", body=b"<html>active</html>")


def test_pending_expiry_count_and_company_storage_are_bounded(store, monkeypatch):
    expired = stage(store, "expired-upload-01")
    expired_path = store.path.parent / "order-files" / expired["id"]
    store.db.execute(
        "UPDATE order_files SET created_at=? WHERE id=?",
        (time.time() - order_files.PENDING_TTL_SECONDS - 1, expired["id"]),
    )
    current = stage(store, "current-upload-01")
    assert not expired_path.exists()
    assert store.one("SELECT id FROM order_files WHERE id=?", (expired["id"],)) is None

    monkeypatch.setattr(order_files, "MAX_PENDING_FILES", 1)
    with pytest.raises(ValueError, match="staged design file"):
        stage(store, "current-upload-02")
    monkeypatch.setattr(order_files, "MAX_PENDING_FILES", 20)
    monkeypatch.setattr(order_files, "MAX_COMPANY_BYTES", current["size"])
    with pytest.raises(ValueError, match="storage is full"):
        stage(store, "current-upload-03")


def test_mixed_order_claims_upload_once_and_keeps_exact_metadata(store):
    upload = stage(store)
    lines = [
        {"item_id": "A", "quantity": 1, "cuts": 0},
        custom(upload),
    ]
    order = submit(store, lines)
    saved = store.read_order(order["id"])
    assert saved["lines"][0]["item_id"] == "A"
    assert saved["lines"][1]["description"] == "Laser-cut mounting bracket"
    assert saved["lines"][1]["file"] == claimed_metadata(upload)
    assert "upload_id" not in saved["lines"][1]
    assert order_files.list_for_order(store, order["id"]) == [claimed_metadata(upload)]

    path, metadata = order_files.read_for_customer(store, order["id"], upload["id"])
    assert path.read_bytes() == PDF and metadata == claimed_metadata(upload)
    with pytest.raises(ValueError, match="Unknown order file"):
        order_files.read_for_customer(store, "0" * 32, upload["id"])

    with pytest.raises(ValueError, match="Choose the design file again"):
        submit(store, [custom(upload)], "file-order-0002")
    assert store.one("SELECT COUNT(*) AS n FROM orders")["n"] == 1


def test_order_file_count_is_enforced_before_submission(store, monkeypatch):
    monkeypatch.setattr(order_files, "MAX_ORDER_FILES", 1)
    first = stage(store, "order-cap-upload-1")
    second = stage(store, "order-cap-upload-2", "second.pdf")
    with pytest.raises(ValueError, match="up to 1 design files"):
        order_files.validate_pending(store, [custom(first), custom(second)])
    assert store.one("SELECT COUNT(*) AS n FROM orders")["n"] == 0


def test_custody_rejects_public_permissions(store):
    upload = stage(store)
    order = submit(store, [custom(upload)])
    path = store.path.parent / "order-files" / upload["id"]
    os.chmod(path, 0o644)
    with pytest.raises(PermissionError, match="custody"):
        order_files.read_for_customer(store, order["id"], upload["id"])


def test_discard_capability_frees_more_than_the_global_pending_limit(store):
    for number in range(order_files.MAX_PENDING_FILES + 5):
        upload = stage(store, f"discard-cycle-{number:04d}")
        path = store.path.parent / "order-files" / upload["id"]
        order_files.discard(store, upload["id"], upload["discard_token"])
        assert not path.exists()
    assert store.one("SELECT COUNT(*) AS n FROM order_files")["n"] == 0


def test_wrong_capability_and_claimed_file_cannot_be_discarded(store):
    upload = stage(store)
    path = store.path.parent / "order-files" / upload["id"]
    with pytest.raises(PermissionError, match="Choose the design file again"):
        order_files.discard(store, upload["id"], "A" * 43)
    assert path.exists()

    order = submit(store, [custom(upload)])
    with pytest.raises(PermissionError, match="Choose the design file again"):
        order_files.discard(store, upload["id"], upload["discard_token"])
    assert path.exists()
    assert order_files.list_for_order(store, order["id"])
