#!/usr/bin/env python3
"""Write the example drawing for laser cutting: the two Dippers in a round steel plate.

    python3 app/src/prototypes/orders/examples/make_constellation.py [--check]

Writes  constellation-400mm.dxf and constellation-400mm.svg beside this script
        (`--check` writes nothing and exits 1 when either file differs from what this script draws)

The drawing is a plate of 400 mm diameter for 2 mm steel. The Big Dipper and the Little Dipper are
cut out of it where they stand in the sky: each star's catalogue position (right ascension and
declination, J2000) is laid flat with an azimuthal equidistant projection centred between the two
figures, north up and east to the left, the way the sky is seen. The pointers Merak and Dubhe lead
to Polaris. Ten stars are five-pointed cut-outs in three sizes by brightness; the four faint stars
of the Little Dipper are round holes of 4 mm; a 6 mm hole near the rim hangs the plate.

It is drawn the way a customer's file arrives. Seven stars are closed polylines; three were drawn
line by line. Those three carry the faults a workshop meets every week:

    Mizar    its last line stops 0.42 mm before the first: an open contour
    Kochab   its last line stops 0.65 mm before the first: an open contour
    Phecda   one of its lines is drawn twice

laser.py finds these three, joins the two gaps, removes the repeated line, and the corrected
drawing then reads clean (tests/test_laser.py holds that).
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PLATE = 400.0                                          # millimetres across
CENTRE = (13.0, 69.5)                                  # hours of right ascension, degrees of declination
MM_PER_DEGREE = 7.2
SHIFT = (-18.0, 0.0)                                   # centres the two figures on the plate
HANG = (200.0, 386.0, 3.0)                             # the hanging hole: x, y, radius
FAINT = 2.0                                            # radius of a faint star's round hole
SIZES = {"large": 12.0, "medium": 9.0, "small": 6.5}   # a star's outer radius
INNER = math.sin(math.radians(18)) / math.sin(math.radians(54))   # a regular five-pointed star
TITLE = "CONSTELLATION PLATE D400 - STEEL S235 2 MM - LASER CUT"

# name, right ascension (h, m, s), declination (deg, arcmin, arcsec), visual magnitude, how it is drawn
STARS = [
    ("Dubhe", (11, 3, 43.67), (61, 45, 3.7), 1.79, "polyline"),
    ("Merak", (11, 1, 50.48), (56, 22, 56.7), 2.37, "polyline"),
    ("Phecda", (11, 53, 49.85), (53, 41, 41.1), 2.44, "lines"),
    ("Megrez", (12, 15, 25.56), (57, 1, 57.4), 3.31, "polyline"),
    ("Alioth", (12, 54, 1.75), (55, 57, 35.4), 1.77, "polyline"),
    ("Mizar", (13, 23, 55.54), (54, 55, 31.3), 2.27, "lines"),
    ("Alkaid", (13, 47, 32.44), (49, 18, 48.0), 1.86, "polyline"),
    ("Polaris", (2, 31, 49.09), (89, 15, 50.8), 1.98, "polyline"),
    ("Yildun", (17, 32, 12.99), (86, 35, 11.3), 4.36, "hole"),
    ("Epsilon UMi", (16, 45, 58.24), (82, 2, 14.1), 4.23, "hole"),
    ("Zeta UMi", (15, 44, 3.52), (77, 47, 40.2), 4.32, "hole"),
    ("Kochab", (14, 50, 42.33), (74, 9, 19.8), 2.08, "lines"),
    ("Pherkad", (15, 20, 43.72), (71, 50, 2.5), 3.05, "polyline"),
    ("Eta UMi", (16, 17, 30.29), (75, 45, 19.2), 4.95, "hole"),
]
GAPS = {"Mizar": 0.42, "Kochab": 0.65}                 # millimetres left open
REPEATED = ("Phecda", 3)                               # the star and which of its ten lines is drawn twice


def place(right_ascension: tuple, declination: tuple) -> tuple[float, float]:
    """A star's place on the plate, in millimetres from its lower left corner."""
    a0, d0 = math.radians(CENTRE[0] * 15), math.radians(CENTRE[1])
    a = math.radians((right_ascension[0] + right_ascension[1] / 60 + right_ascension[2] / 3600) * 15)
    d = math.radians(declination[0] + declination[1] / 60 + declination[2] / 3600)
    away = math.acos(math.sin(d0) * math.sin(d) + math.cos(d0) * math.cos(d) * math.cos(a - a0))
    k = away / math.sin(away) if away else 1.0
    east = k * math.cos(d) * math.sin(a - a0)
    north = k * (math.cos(d0) * math.sin(d) - math.sin(d0) * math.cos(d) * math.cos(a - a0))
    return (PLATE / 2 + SHIFT[0] - math.degrees(east) * MM_PER_DEGREE,
            PLATE / 2 + SHIFT[1] + math.degrees(north) * MM_PER_DEGREE)


def size_of(magnitude: float) -> str:
    return "large" if magnitude < 2.2 else "medium" if magnitude < 3.0 else "small"


def star(x: float, y: float, radius: float) -> list[tuple[float, float]]:
    """Ten corners of a five-pointed star, one point up, anticlockwise from the top."""
    corners = []
    for k in range(10):
        angle = math.pi / 2 + k * math.pi / 5
        r = radius if k % 2 == 0 else radius * INNER
        corners.append((round(x + r * math.cos(angle), 3), round(y + r * math.sin(angle), 3)))
    return corners


def drawing() -> list[tuple]:
    """Everything on the plate, in the order it is drawn: (kind, name, numbers)."""
    shapes: list[tuple] = [("circle", "plate", (PLATE / 2, PLATE / 2, PLATE / 2)), ("circle", "hang", HANG)]
    for name, right_ascension, declination, magnitude, how in STARS:
        x, y = place(right_ascension, declination)
        if how == "hole":
            shapes.append(("circle", name, (round(x, 3), round(y, 3), FAINT)))
            continue
        corners = star(x, y, SIZES[size_of(magnitude)])
        if how == "polyline":
            shapes.append(("polyline", name, corners))
            continue
        lines = [(corners[k], corners[(k + 1) % 10]) for k in range(10)]
        if name in GAPS:                               # the last line stops short of the first corner
            (x0, y0), (x1, y1) = lines[9]
            length = math.hypot(x1 - x0, y1 - y0)
            short = GAPS[name] / length
            lines[9] = ((x0, y0), (round(x1 + (x0 - x1) * short, 3), round(y1 + (y0 - y1) * short, 3)))
        if name == REPEATED[0]:
            lines.append(lines[REPEATED[1]])
        shapes.extend(("line", name, line) for line in lines)
    return shapes


def number(value: float) -> str:
    return f"{value:.3f}"


def dxf() -> str:
    out = ["0", "SECTION", "2", "HEADER",
           "9", "$INSUNITS", "70", "4", "9", "$MEASUREMENT", "70", "1",
           "9", "$EXTMIN", "10", "0.0", "20", "-24.0", "9", "$EXTMAX", "10", number(PLATE), "20", number(PLATE),
           "0", "ENDSEC", "0", "SECTION", "2", "ENTITIES"]
    for kind, _, numbers in drawing():
        if kind == "circle":
            x, y, radius = numbers
            out += ["0", "CIRCLE", "8", "CUT", "10", number(x), "20", number(y), "40", number(radius)]
        elif kind == "polyline":
            out += ["0", "LWPOLYLINE", "8", "CUT", "90", str(len(numbers)), "70", "1"]
            for x, y in numbers:
                out += ["10", number(x), "20", number(y)]
        else:
            (x0, y0), (x1, y1) = numbers
            out += ["0", "LINE", "8", "CUT", "10", number(x0), "20", number(y0), "11", number(x1), "21", number(y1)]
    out += ["0", "TEXT", "8", "TITLE", "10", "0.0", "20", "-20.0", "40", "8.0", "1", TITLE,
            "0", "ENDSEC", "0", "EOF"]
    return "\n".join(out) + "\n"


def svg() -> str:
    """The same drawing; SVG counts y downward from the top of the page."""
    def flip(y: float) -> str:
        return number(PLATE - y)

    out = ['<?xml version="1.0" encoding="UTF-8"?>',
           f'<svg xmlns="http://www.w3.org/2000/svg" width="{PLATE:g}mm" height="{PLATE + 30:g}mm" '
           f'viewBox="0 0 {PLATE:g} {PLATE + 30:g}">',
           f"<title>{TITLE}</title>",
           '<g fill="none" stroke="#000000" stroke-width="0.2">']
    for kind, name, numbers in drawing():
        if kind == "circle":
            x, y, radius = numbers
            out.append(f'<circle cx="{number(x)}" cy="{flip(y)}" r="{number(radius)}"/>')
        elif kind == "polyline":
            points = " ".join(f"{number(x)},{flip(y)}" for x, y in numbers)
            out.append(f'<polygon points="{points}"/>')
        else:
            (x0, y0), (x1, y1) = numbers
            out.append(f'<line x1="{number(x0)}" y1="{flip(y0)}" x2="{number(x1)}" y2="{flip(y1)}"/>')
    out += ["</g>", f'<text x="0" y="{PLATE + 22:g}" font-family="sans-serif" font-size="8">{TITLE}</text>',
            "</svg>"]
    return "\n".join(out) + "\n"


def main(argv: list[str]) -> int:
    made = {"constellation-400mm.dxf": dxf(), "constellation-400mm.svg": svg()}
    if argv[1:] == ["--check"]:
        stale = [name for name, text in made.items()
                 if not (HERE / name).is_file() or (HERE / name).read_text(encoding="utf-8") != text]
        for name in stale:
            print(f"{name} differs from this script: run it again")
        return 1 if stale else 0
    for name, text in made.items():
        (HERE / name).write_text(text, encoding="utf-8")
        print(f"{HERE / name}: {len(text.encode())} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
