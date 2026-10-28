"""Compute trusted server totals with the browser's shared pricing engine."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path


def quote(catalog: dict, lines: list, laser=None) -> dict:
    """Price an order. `laser` turns the {"laser": {...}} a page sends into a line the server measured.

    Measured lines travel to the engine beside the order, by their place in it, and join the totals
    as they are. A request line cannot name itself measured: the engine looks it up as an item.
    """
    if not isinstance(lines, list) or not 1 <= len(lines) <= 100:
        raise ValueError("Choose 1 to 100 order lines.")
    prepared, measured = [], {}
    for index, line in enumerate(lines):
        if isinstance(line, dict) and line.get("laser") is not None:
            if laser is None:
                raise ValueError("Laser cutting is being prepared for this company.")
            measured[str(index)] = laser(line["laser"])
            line = {"laser": True}
        prepared.append(line)
    try:
        result = subprocess.run(
            ["node", str(Path(__file__).with_name("quote.mjs"))],
            input=json.dumps({"catalog": catalog, "lines": prepared, "measured": measured}, allow_nan=False),
            capture_output=True, text=True, timeout=8, check=False,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        raise ValueError("The quote service is preparing this order. Try again.") from exc
    if result.returncode:
        raise ValueError("Check the selected items, sizes and quantities.")
    return json.loads(result.stdout)
