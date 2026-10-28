import json
from pathlib import Path

import pytest

from pipeline.studio.geometry.catalogue import family_spec, plan_catalogue, write_manifest


def category(code="011", shape="round_tube", dims=None):
    return {
        "code": code,
        "shape": shape,
        "mat": "hr",
        "items": [{"c": code + "-1", "d": dims or [40, 2], "s": "source row"}],
    }


def test_seam_contract_distinguishes_welded_seamless_and_spiral():
    assert family_spec(category("011"))["seam"] == "longitudinal"
    assert family_spec(category("012"))["seam"] == "none"
    assert family_spec(category("013"))["seam"] == "spiral"


def test_special_and_missing_dimensions_are_rejected_instead_of_modelled():
    with pytest.raises(ValueError, match="source-specified"):
        family_spec(category("009", "special", [48, 24, 1.5]))
    with pytest.raises(ValueError, match="dimensions"):
        family_spec(category("001", "sq_tube", [40, 40]))


@pytest.mark.parametrize("dims", ([40, 40, 20], [40, 40, -2], [40, 40, float("nan")]))
def test_invalid_tube_dimensions_are_rejected(dims):
    with pytest.raises(ValueError):
        family_spec(category("001", "sq_tube", dims))


def test_chequer_requires_the_catalogue_pattern_and_beams_require_a_standard_entry():
    chequer = category("024", "chequer", [3, 1000, 2000])
    with pytest.raises(ValueError, match="raised-pattern"):
        family_spec(chequer)
    chequer["pat"] = "tear"
    assert family_spec(chequer)["pattern"] == "tear"
    with pytest.raises(ValueError, match="standard table"):
        family_spec(category("054", "ipe", [123]))
    with pytest.raises(ValueError, match="standard table"):
        family_spec(category("054", "ipe", [120.5]))
    assert family_spec(category("054", "ipe", [120.0]))["dimensions_mm"] == [120.0]


def test_vendored_scene_retains_proven_mesh_pattern_and_camera_runtime():
    scene = Path(__file__).parents[1] / "pipeline/studio/geometry/scene.py"
    source = scene.read_text(encoding="utf-8")
    for marker in (
        "def build_profile",
        "def build_bar",
        "def build_pattern",
        "def build_camera",
        "def build_rig",
    ):
        assert marker in source
    assert "weld_mode == 'spiral'" in source


def test_plan_uses_parameterized_paths_and_records_output_hash(tmp_path):
    source = tmp_path / "company-catalogue.json"
    source.write_text(json.dumps({"cats": [category(), category("009", "special", [1])]}), encoding="utf-8")
    output = tmp_path / "technical"
    plan = plan_catalogue(source, output)
    assert len(plan["jobs"]) == 1 and len(plan["rejected"]) == 1
    assert plan["jobs"][0]["output"] == str(output / "011-technical.png")
    output.mkdir()
    Path(plan["jobs"][0]["output"]).write_bytes(b"technical-reference")
    manifest = write_manifest(output / "geometry-manifest.json", plan, plan["jobs"])
    assert len(manifest["rendered"][0]["output_sha256"]) == 64


def test_family_filter_keeps_one_requested_family(tmp_path):
    source = tmp_path / "catalogue.json"
    source.write_text(json.dumps({"cats": [category("011"), category("012")]}), encoding="utf-8")
    plan = plan_catalogue(source, tmp_path / "out", ["012"])
    assert [job["family"] for job in plan["jobs"]] == ["012"]
