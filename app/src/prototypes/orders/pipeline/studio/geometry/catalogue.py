"""Pure catalogue validation and render planning; safe to import outside Blender."""

import hashlib
import json
import math
from pathlib import Path

SUPPORTED = {
    "sq_tube", "rect_tube", "round_tube", "round", "square", "hex", "flat", "sheet", "chequer",
    "angle", "angle_u", "tee", "channel", "upn", "ipe", "hea", "heb",
}
MIN_DIMS = {
    "sq_tube": 3, "rect_tube": 3, "round_tube": 2, "round": 1, "square": 1, "hex": 1,
    "flat": 2, "sheet": 3, "chequer": 3, "angle": 3, "angle_u": 3, "tee": 3,
    "channel": 3, "upn": 1, "ipe": 1, "hea": 1, "heb": 1,
}
MATERIALS = {"hr", "cr", "galv", "wrought", "inox", "alu", "copper", "brass", "bronze", "lead", "pvc"}
BEAM_NOMINALS = {
    "ipe": {80, 100, 120, 140, 160, 180, 200, 220, 240, 270, 300, 330, 360, 400, 450, 500, 550, 600},
    "hea": {100, 120, 140, 160, 180, 200, 220, 240, 260, 280, 300, 320, 340, 360, 400, 450},
    "heb": {100, 120, 140, 160, 180, 200, 220, 240, 260, 280, 300, 320, 340, 360, 400},
    "upn": {30, 40, 50, 65, 80, 100, 120, 140, 160, 180, 200, 220, 240, 260, 280, 300, 400},
}


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def representative(category):
    items = category.get("items") or []
    if not items:
        return None
    preferred = items[min(len(items) - 1, math.floor(len(items) * 0.42))]
    return preferred if preferred.get("d") else next((item for item in items if item.get("d")), preferred)


def family_spec(category):
    shape = category.get("shape")
    item = representative(category)
    if shape not in SUPPORTED:
        raise ValueError("special or unsupported family has no source-specified standard geometry")
    if not item or len(item.get("d") or []) < MIN_DIMS[shape]:
        raise ValueError("catalogue dimensions are missing for standard geometry")
    dims = [float(value) for value in item["d"]]
    if any(not math.isfinite(value) or value <= 0 for value in dims):
        raise ValueError("catalogue dimensions must be finite and positive")
    material = item.get("m") or category.get("mat")
    if material not in MATERIALS:
        raise ValueError("catalogue material has no approved renderer material")
    if shape in {"sq_tube", "rect_tube"} and dims[2] * 2 >= min(dims[0], dims[1]):
        raise ValueError("catalogue wall thickness leaves no hollow section")
    if shape == "round_tube" and dims[1] * 2 >= dims[0]:
        raise ValueError("catalogue wall thickness leaves no round bore")
    if shape in {"angle", "angle_u", "tee", "channel"} and dims[2] >= min(dims[0], dims[1]):
        raise ValueError("catalogue thickness is incompatible with section dimensions")
    if shape in BEAM_NOMINALS and dims[0] not in BEAM_NOMINALS[shape]:
        raise ValueError("nominal beam size has no approved standard table entry")
    pattern = category.get("pat") or ""
    if shape == "chequer" and pattern not in {"tear", "bars"}:
        raise ValueError("chequer family lacks an approved raised-pattern specification")
    seam = (
        "none"
        if category.get("code") == "012"
        else "spiral"
        if category.get("code") == "013"
        else "longitudinal"
    )
    return {
        "family": category["code"],
        "sku": item["c"],
        "shape": shape,
        "material": material,
        "dimensions_mm": dims,
        "pattern": pattern,
        "seam": seam if shape in {"sq_tube", "rect_tube", "round_tube"} else "none",
        "source": "catalogue",
    }


def plan_catalogue(catalogue_path, output_dir, families=None):
    catalogue_path, output_dir = Path(catalogue_path).resolve(), Path(output_dir).resolve()
    catalogue = json.loads(catalogue_path.read_text(encoding="utf-8"))
    wanted = set(families or [])
    jobs, rejected = [], []
    for category in catalogue.get("cats", []):
        code = str(category.get("code", ""))
        if wanted and code not in wanted:
            continue
        try:
            spec = family_spec(category)
            spec["output"] = str(output_dir / (code + "-technical.png"))
            jobs.append(spec)
        except ValueError as error:
            rejected.append({"family": code, "reason": str(error)})
    if wanted - {job["family"] for job in jobs} - {row["family"] for row in rejected}:
        known = {category.get("code") for category in catalogue.get("cats", [])}
        raise ValueError("unknown catalogue family: " + ", ".join(sorted(wanted - known)))
    return {
        "schema": "rocoto.orders.geometry-plan.v1",
        "catalogue": str(catalogue_path),
        "catalogue_sha256": sha256(catalogue_path),
        "output_dir": str(output_dir),
        "jobs": jobs,
        "rejected": rejected,
    }


def write_manifest(path, plan, rendered):
    payload = dict(plan)
    payload["rendered"] = [
        {**job, "output_sha256": sha256(job["output"])} for job in rendered
    ]
    Path(path).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return payload
