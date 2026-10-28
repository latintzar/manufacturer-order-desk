"""The laser-cutting estimate: one formula, written here and in laser_quote.mjs.

    net   = the larger of: the minimum, or setup + quantity x (material + cutting + piercing)
    material   bounding sheet (w x h) x thickness x density x the price of one kilogram
    cutting    cut length x the price of one metre in that material and thickness
    piercing   one pierce per contour x the price of one pierce in that material and thickness
    gross = net + VAT

The server prices an order line with `quote` below; the order page recomputes with the same
arithmetic, in the same order, in laser_quote.mjs. tests/fixtures/laser-price-vectors.json holds
both to the same cent. Every amount is rounded half up to the cent before it is added, so the
lines of a summary add up to its total.

A company's `laser` block in company.json carries what the formula needs:

    {"status": "assumed", "gap": 1.0, "kerf": 0.2,
     "materials": [{"id", "bg", "en", "density", "look": {"color", "metalness", "roughness"},
                    "thicknesses": [...]}],
     "default": {"material", "thickness"},
     "tariff": {"currency", "vat", "setup", "minimum",
                "rates": {"<material id>": {"kg", "cut": [...], "pierce": [...]}}}}

`cut` and `pierce` hold one price per entry of the material's `thicknesses`, in the same order.
`status` reads `assumed` until the company confirms its tariff, and travels with every answer.
"""
from __future__ import annotations

import math
import re

MAX_QUANTITY = 999
STATUSES = ("assumed", "confirmed")
MATERIAL_ID = re.compile(r"[a-z][a-z0-9-]{0,23}")
COLOR = re.compile(r"#[0-9a-fA-F]{6}")


def cents(value: float) -> float:
    """Half up to the cent, the way laser_quote.mjs rounds."""
    return math.floor(value * 100 + 0.5) / 100


def grams(value: float) -> float:
    return math.floor(value * 1000 + 0.5) / 1000


def _number(value: object, least: float, most: float) -> bool:
    return (not isinstance(value, bool) and isinstance(value, (int, float))
            and math.isfinite(value) and least <= value <= most)


def block(config: object) -> dict | None:
    """The company's laser block, checked. None when the company has none; ValueError when it is malformed."""
    if config is None:
        return None
    if not isinstance(config, dict):
        raise ValueError("laser: an object is required")
    status = config.get("status", "assumed")
    if status not in STATUSES:
        raise ValueError("laser.status: assumed or confirmed")
    gap, kerf = config.get("gap", 1.0), config.get("kerf", 0.2)
    if not _number(gap, 0.01, 5) or not _number(kerf, 0.01, 2):
        raise ValueError("laser.gap and laser.kerf: millimetres")
    tariff = config.get("tariff")
    if not isinstance(tariff, dict) or not isinstance(tariff.get("rates"), dict):
        raise ValueError("laser.tariff.rates is required")
    if not isinstance(tariff.get("currency"), str) or not re.fullmatch(r"[A-Z]{3}", tariff["currency"]):
        raise ValueError("laser.tariff.currency: a three-letter code")
    if not _number(tariff.get("vat"), 0, 1):
        raise ValueError("laser.tariff.vat: a rate between 0 and 1")
    for key in ("setup", "minimum"):
        if not _number(tariff.get(key), 0, 100000):
            raise ValueError(f"laser.tariff.{key}: an amount")
    materials = config.get("materials")
    if not isinstance(materials, list) or not 1 <= len(materials) <= 24:
        raise ValueError("laser.materials: 1 to 24 materials")
    seen, cleaned, rates = set(), [], {}
    for material in materials:
        if not isinstance(material, dict):
            raise ValueError("laser.materials: each one is an object")
        identifier = material.get("id")
        if not isinstance(identifier, str) or not MATERIAL_ID.fullmatch(identifier) or identifier in seen:
            raise ValueError("laser.materials: each id is unique, lowercase letters, digits and hyphens")
        seen.add(identifier)
        where = f"laser.materials.{identifier}"
        names = {language: material.get(language) for language in ("bg", "en")}
        if any(not isinstance(name, str) or not 1 <= len(name) <= 80 for name in names.values()):
            raise ValueError(f"{where}: a name in bg and en")
        if not _number(material.get("density"), 100, 25000):
            raise ValueError(f"{where}.density: kilograms per cubic metre")
        look = material.get("look")
        if (not isinstance(look, dict) or not isinstance(look.get("color"), str)
                or not COLOR.fullmatch(look["color"])
                or not _number(look.get("metalness"), 0, 1) or not _number(look.get("roughness"), 0, 1)):
            raise ValueError(f"{where}.look: color, metalness and roughness")
        thicknesses = material.get("thicknesses")
        if (not isinstance(thicknesses, list) or not 1 <= len(thicknesses) <= 40
                or any(not _number(t, 0.1, 100) for t in thicknesses)
                or any(a >= b for a, b in zip(thicknesses, thicknesses[1:]))):
            raise ValueError(f"{where}.thicknesses: rising millimetres")
        rate = tariff["rates"].get(identifier)
        if not isinstance(rate, dict) or not _number(rate.get("kg"), 0, 10000):
            raise ValueError(f"laser.tariff.rates.{identifier}.kg: the price of one kilogram")
        for key in ("cut", "pierce"):
            prices = rate.get(key)
            if (not isinstance(prices, list) or len(prices) != len(thicknesses)
                    or any(not _number(price, 0, 10000) for price in prices)):
                raise ValueError(f"laser.tariff.rates.{identifier}.{key}: one price per thickness")
        cleaned.append({
            "id": identifier, "bg": names["bg"], "en": names["en"], "density": material["density"],
            "look": {"color": look["color"], "metalness": look["metalness"], "roughness": look["roughness"]},
            "thicknesses": list(thicknesses),
        })
        rates[identifier] = {"kg": rate["kg"], "cut": list(rate["cut"]), "pierce": list(rate["pierce"])}
    default = config.get("default")
    chosen = next((m for m in cleaned if isinstance(default, dict) and m["id"] == default.get("material")), None)
    if chosen is None or default.get("thickness") not in chosen["thicknesses"]:
        raise ValueError("laser.default: one listed material and one of its thicknesses")
    return {
        "status": status, "gap": gap, "kerf": kerf, "materials": cleaned,
        "default": {"material": chosen["id"], "thickness": default["thickness"]},
        "tariff": {"currency": tariff["currency"], "vat": tariff["vat"], "setup": tariff["setup"],
                   "minimum": tariff["minimum"], "rates": rates},
    }


def quote(measure: dict, material: dict, tariff: dict, thickness: float, quantity: int) -> dict:
    """The estimate for `quantity` pieces of one measured drawing. {"ok": False} names nothing priced."""
    rate = (tariff.get("rates") or {}).get(material.get("id")) if isinstance(tariff, dict) else None
    thicknesses = material.get("thicknesses") or []
    if rate is None or not _number(thickness, 0, 1000) or thickness not in thicknesses:
        return {"ok": False}
    if isinstance(quantity, float) and quantity.is_integer():
        quantity = int(quantity)                       # JSON's 3.0 is the page's 3
    if isinstance(quantity, bool) or not isinstance(quantity, int) or not 1 <= quantity <= MAX_QUANTITY:
        return {"ok": False}
    bounds, cut = measure.get("bounds") or {}, measure.get("cut") or {}
    width, height = bounds.get("w"), bounds.get("h")
    length, pierces = cut.get("length_mm"), cut.get("pierces")
    if not all(_number(value, 0, 1e7) for value in (width, height, length, pierces)):
        return {"ok": False}
    index = thicknesses.index(thickness)
    weight = width * height * thickness * material["density"] / 1e9
    material_cost = cents(weight * rate["kg"] * quantity)
    cutting = cents(length / 1000 * rate["cut"][index] * quantity)
    piercing = cents(pierces * rate["pierce"][index] * quantity)
    setup = cents(tariff["setup"])
    subtotal = cents(material_cost + cutting + piercing + setup)
    least = cents(tariff["minimum"])
    net = least if subtotal < least else subtotal
    vat = cents(net * tariff["vat"])
    return {
        "ok": True, "quantity": quantity, "weight_kg": grams(weight),
        "material": material_cost, "cutting": cutting, "piercing": piercing, "setup": setup,
        "minimum": subtotal < least, "piece": cents(net / quantity),
        "net": net, "vat": vat, "gross": cents(net + vat),
        "vat_rate": tariff["vat"], "currency": tariff["currency"],
    }
