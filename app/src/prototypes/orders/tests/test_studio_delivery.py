import json

import pytest

from pipeline.studio.delivery import SHOTS, install, install_many, validate
from pipeline.studio.schema import sha256


@pytest.fixture
def package(tmp_path):
    views = []
    studio = tmp_path / "studio-reference.png"
    studio.write_bytes(b"shared studio anchor")
    for shot in SHOTS:
        source, export = tmp_path / f"{shot}.png", tmp_path / f"{shot}.webp"
        source.write_bytes(b"reviewed original")
        export.write_bytes(b"reviewed derivative")
        views.append(
            {
                "shot": shot,
                "source": str(source),
                "sha256": sha256(source),
                "export": str(export),
                "export_sha256": sha256(export),
                "passed": True,
                "review": {"geometry": True, "material": True, "lighting": True, "background": True},
            }
        )
    catalogue = tmp_path / "catalogue.json"
    catalogue.write_text(
        json.dumps(
            {
                "cats": [
                    {"code": "001", "items": [{"c": "A"}, {"c": "B"}]},
                    {"code": "002", "items": [{"c": "C"}]},
                ]
            }
        )
    )
    index = tmp_path / "index.json"
    index.write_text(
        json.dumps(
            {
                "sets": {"001-hr": [f"{shot}.webp" for shot in SHOTS]},
                "items": {"A": "001-hr", "B": None},
                "variantTypes": ["001"],
            }
        )
    )
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "export_index": str(index),
                "studio": {"reference": str(studio), "sha256": sha256(studio), "background": "#E4E2DE"},
                "sets": [
                    {"type_code": "001", "visual_key": "001-hr", "passed": True, "views": views},
                ],
            }
        )
    )
    return manifest, catalogue, index


def test_delivery_preserves_explicit_holds_and_excludes_private_evidence(package, tmp_path):
    manifest, catalogue, _ = package
    output = tmp_path / "public"
    result = install(manifest, catalogue, output)
    assert result["mapped_skus"] == 1 and result["images"] == 1
    public = json.loads((output / "index.json").read_text())
    assert public["items"]["B"] is None
    assert str(tmp_path) not in (output / "index.json").read_text()
    assert len(list(output.iterdir())) == len(SHOTS) + 1


def test_delivery_rejects_changed_original_before_writing(package, tmp_path):
    manifest, catalogue, _ = package
    (tmp_path / "angled.png").write_bytes(b"changed")
    with pytest.raises(ValueError, match="hash changed"):
        install(manifest, catalogue, tmp_path / "public")
    assert not (tmp_path / "public").exists()


def test_delivery_rejects_cross_family_assignment(package):
    manifest, catalogue, path = package
    index = json.loads(path.read_text())
    index["variantTypes"].append("002")
    index["items"]["C"] = "001-hr"
    path.write_text(json.dumps(index))
    with pytest.raises(ValueError, match="another product family"):
        validate(manifest, catalogue)


def test_delivery_requires_explicit_mapping_for_unresolved_items(package):
    manifest, catalogue, path = package
    index = json.loads(path.read_text())
    del index["items"]["B"]
    path.write_text(json.dumps(index))
    with pytest.raises(ValueError, match="every SKU"):
        validate(manifest, catalogue)


def test_delivery_rejects_held_view(package):
    manifest, catalogue, _ = package
    data = json.loads(manifest.read_text())
    data["sets"][0]["views"][0]["review"]["material"] = False
    manifest.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="held review"):
        validate(manifest, catalogue)


def second_batch(package, tmp_path, mapping):
    original, _, _ = package
    manifest = json.loads(original.read_text())
    row = manifest["sets"][0]
    row["visual_key"] = "001-cr"
    for view in row["views"]:
        export = tmp_path / ("cr-" + view["shot"] + ".webp")
        export.write_bytes(b"another reviewed finish")
        view["export"] = str(export)
        view["export_sha256"] = sha256(export)
    index = tmp_path / "cr-index.json"
    index.write_text(
        json.dumps(
            {
                "sets": {"001-cr": ["cr-" + shot + ".webp" for shot in SHOTS]},
                "items": mapping,
                "variantTypes": ["001"],
            }
        )
    )
    manifest["export_index"] = str(index)
    path = tmp_path / "cr-manifest.json"
    path.write_text(json.dumps(manifest))
    return path


def test_batch_merge_promotes_holds_and_preserves_existing_assignment(package, tmp_path):
    manifest, catalogue, _ = package
    other = second_batch(package, tmp_path, {"A": None, "B": "001-cr"})
    output = tmp_path / "public"
    receipt = install_many([manifest, other], catalogue, output)
    assert receipt["sets"] == 2 and receipt["mapped_skus"] == 2
    assert json.loads((output / "index.json").read_text())["items"] == {"A": "001-hr", "B": "001-cr"}


def test_conflicting_approved_mapping_fails_before_output(package, tmp_path):
    manifest, catalogue, _ = package
    other = second_batch(package, tmp_path, {"A": "001-cr", "B": None})
    output = tmp_path / "public"
    with pytest.raises(ValueError, match="Conflicting approved SKU"):
        install_many([manifest, other], catalogue, output)
    assert not output.exists()


def test_repeated_batch_is_idempotent_for_assets(package, tmp_path):
    manifest, catalogue, _ = package
    assert install_many([manifest, manifest], catalogue, tmp_path / "public")["images"] == 1


def test_delivery_rejects_frontal_and_extra_private_views(package):
    manifest, catalogue, _ = package
    data = json.loads(manifest.read_text())
    data["sets"][0]["views"][0]["shot"] = "cut_end"
    manifest.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="one angled"):
        validate(manifest, catalogue)
    data["sets"][0]["views"][0]["shot"] = "angled"
    data["sets"][0]["views"].append({"shot": "surface_macro"})
    manifest.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="one angled"):
        validate(manifest, catalogue)


def test_batches_reject_different_studio_references(package, tmp_path):
    manifest, catalogue, _ = package
    other = second_batch(package, tmp_path, {"A": None, "B": "001-cr"})
    data = json.loads(other.read_text())
    studio = tmp_path / "other-studio.png"
    studio.write_bytes(b"different background and light")
    data["studio"].update(reference=str(studio), sha256=sha256(studio))
    other.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="same reviewed studio"):
        install_many([manifest, other], catalogue, tmp_path / "public")
    assert not (tmp_path / "public").exists()
