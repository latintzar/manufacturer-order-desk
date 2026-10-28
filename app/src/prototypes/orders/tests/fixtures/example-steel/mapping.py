"""Example Steel: an invented company with an English price list, for the tests."""
from __future__ import annotations

import re

TABLE = r'<table class="prices"[^>]*>(.*?)</table>'
COLUMNS = {"code": "Code", "size": "Size", "price": "Price", "stock": "Length m", "sold": "Sold in",
           "cut": "Cut", "weight": "kg"}
PARKED = {"P9": "wire, sold by rules of its own"}
SHAPES = {"T1": ("sq_tube", "hr", "", "Square tubes"), "S2": ("sheet", "cr", "", "Sheets"),
          "P9": ("special", "hr", "", "Wire")}
METALS = [("steel", "Steel", "Steel")]
FORMS = [("tubes", "Tubes", "Tubes"), ("sheets", "Sheets", "Sheets")]
SHAPE_FORM = {"sq_tube": "tubes", "sheet": "sheets"}
MAT_METAL = {"hr": "steel", "cr": "steel"}
RULES = {"source": "https://example-steel.test/how-we-sell/",
         "partLength": {"quote": "A part length pays more by its share of the bar.",
                        "table": {"6": {"3": 0.3}}}}


def title(first_row):
    code, _, name = first_row[0].partition(" ")
    return code, name.strip()


def form_of(name):
    return "other"


def tail_en(text):
    return text


def surface(default, raw, tail):
    return default


def sale(raw, stock, shape):
    text = raw.strip().lower()
    if shape == "sheet":
        return {"k": "half"} if text.startswith("half") else {"k": "whole"}
    if text == "any length":
        return {"k": "any"}
    listed = [float(value) for value in re.findall(r"\d+(?:\.\d+)?", text)]
    return {"k": "len", "l": sorted({value for value in listed if value <= stock} | {stock})} if stock else {"k": "whole"}


def local_image(url):
    return url


def as_of(site):
    match = re.search(r"Prices valid on (\d{4}-\d{2}-\d{2})", (site / "price-list/index.html").read_text())
    return match.group(1) if match else ""


def site_map(site, price_list):
    """Each table names its product page in a data attribute."""
    ids = {code: page for code, page in re.findall(r'data-code="(\w+)" data-page="([^"]+)"', price_list)}
    pages = {}
    for page in set(ids.values()):
        if (site / page.strip("/") / "index.html").is_file():
            pages[page] = {"en": {"form": "tubes", "metal": "steel", "url": page, "img": "/assets/tube.svg"}}
    return ids, pages
