"""Describe-derived frames and explicit geometry/material composition roles."""

import hashlib
from pathlib import Path

from PIL import Image

from .materials import material_clause
from .schema import SHOTS, sha256

COMPOSITIONS = {
    "whole_piece": "Show the complete piece with clear silhouette and grounded contact shadow.",
    "cut_end": "Focus on the exact cut section, wall thickness and integral topology.",
    "surface_macro": "Actual exterior material fills at least 90% of frame. Retain one distinctive section feature. Keep large openings outside the frame. Hard directional light and shallow depth of field reveal fine low-amplitude grain.",
    "stack": "Show a small orderly stack of identical pieces with consistent section geometry.",
}


def frame_prompt(description, replacements, *, shot, geometry, finish, condition):
    """Retain the saved provider description; replace only explicitly identified clauses."""
    if shot not in SHOTS or not all(
        isinstance(x, str) and x.strip() for x in (description, geometry, finish, condition)
    ):
        raise ValueError("Saved description, geometry, finish, condition and known shot required")
    frame = description
    for before, after in replacements:
        if not before or frame.count(before) != 1:
            raise ValueError("Each frame edit must match exactly once")
        frame = frame.replace(before, after, 1)
    prompt = "\n\n".join(
        (
            frame,
            "STRUCTURE input controls exact geometry: " + geometry,
            "MATERIAL input controls finish class, colour and grain direction: " + finish,
            "The native small compressed material image establishes finish rather than magnified compression, ringing, pitting or scuffs. Photoreal cleaned studio surface preserves the metal class and subtle industrial finish. Avoid invented lacquer or mirror polish. Condition: "
            + condition,
            COMPOSITIONS[shot],
        )
    )
    return {
        "prompt": prompt,
        "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
        "frame_source_sha256": hashlib.sha256(description.encode()).hexdigest(),
        "frame_edits": replacements,
    }


def structural_crop(source, output, rect):
    """Procedural technical-render crop; preserve originals and native pixel scale."""
    source, output = Path(source).resolve(), Path(output).resolve()
    if source == output or output.exists():
        raise ValueError("Use a new output path")
    with Image.open(source) as image:
        if len(rect) != 4 or any(type(x) is not int for x in rect):
            raise ValueError("Four integer crop coordinates required")
        x0, y0, x1, y1 = rect
        if not 0 <= x0 < x1 <= image.width or not 0 <= y0 < y1 <= image.height:
            raise ValueError("Crop is outside original render")
        output.parent.mkdir(parents=True, exist_ok=True)
        image.crop(rect).save(output, format="PNG")
    return {
        "source": str(source),
        "source_sha256": sha256(source),
        "path": str(output),
        "sha256": sha256(output),
        "rect": list(rect),
        "role": "STRUCTURE",
    }


def production_prompt(description, replacements, *, shot, geometry, finish, condition, zones):
    """One native GPT photography system; material zones vary, owner frame stays locked."""
    result = frame_prompt(
        description, replacements, shot=shot, geometry=geometry, finish=finish, condition=condition
    )
    result["prompt"] += "\n\n" + material_clause(zones)
    result["prompt"] += (
        "\n\nPreserve the actual owner-reference lighting: hard directional key, controlled metal reflections, "
        "deep contrast and quiet warm grey background; shallow depth of field for macro views. "
        "Lighting reveals the documented finish; it does not turn fine plate skin into coarse pits "
        "or transform industrial metal into polished mirror material."
    )
    result["prompt_sha256"] = hashlib.sha256(result["prompt"].encode()).hexdigest()
    result["model_requested"] = "gpt_image_native"
    result["material_zones"] = zones
    return result
