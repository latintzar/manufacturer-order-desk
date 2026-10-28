#!/usr/bin/env python3
"""Read a drawing a customer uploads for laser cutting and say what a workshop needs to know.

    python3 laser.py <drawing.dxf|drawing.svg> [--fixed <corrected.dxf>]     print the reading as JSON

Two formats, read here with the standard library alone:
  DXF  ASCII. LINE, LWPOLYLINE, POLYLINE with VERTEX, CIRCLE, ARC, ELLIPSE and SPLINE; bulge arcs.
       $INSUNITS names the unit, then $MEASUREMENT (0 reads as inches); millimetres otherwise.
  SVG  path, polyline, polygon, line, circle, ellipse, rect; transforms; viewBox with a width in
       mm, cm, in, pt, pc or px. A user unit without a physical width is one CSS pixel.
Text, dimensions, block inserts and pictures are counted under `ignored` and left out of the cut.

The reading, always in millimetres with the origin at the lower left of the drawing and y up:
  contours  the cut lines joined end to end. Ends within 0.01 mm are one point.
  issues    open_contour   two open ends stand apart. Up to the gap limit (1.0 mm unless the company
                           sets another) they are joined and the issue reads fixed; further apart
                           the contour stays open and the issue reads fixed: false
            duplicate      a line drawn again over the same line; the copy is removed
            small_feature  a closed shape narrower than twice the kerf
            junction       three or more lines meet in one point
  cut       length_mm, pierces (one per contour), area_mm2 (outer shapes less their holes) and
            smallest_mm, the narrowest closed shape
  bounds    the rectangle of sheet the drawing takes
When something was corrected, the corrected drawing is written as a DXF of LWPOLYLINE entities.

Ceilings, each with its own refusal: 4 MB (`size`), 20,000 entities and 3,000 contours
(`entities`), 200,000 points (`points`), 8 seconds (`time`). Two drawings are read at a time
(`busy`). A drawing without cut lines answers `empty`; another file type answers `format`.

The service half keeps one reading per uploaded file beside the company's orders, stages the
corrected DXF through order_files, and prices an order line with laser_quote.py. Every answer
carries the company's materials and tariff with `status`, which reads `assumed` until the company
confirms its tariff.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import sys
import threading
import time
from bisect import bisect_right
from pathlib import Path
from xml.etree import ElementTree

sys.path.insert(0, str(Path(__file__).resolve().parent))
import laser_quote  # noqa: E402
import order_files  # noqa: E402

MAX_BYTES = 4 * 1024 * 1024
MAX_ENTITIES = 20_000
MAX_POINTS = 200_000
MAX_SAMPLES = 600_000                                  # points after every arc is drawn out
MAX_CONTOURS = 3_000
MAX_SECONDS = 8.0
MAX_ISSUES = 200
JOIN_MM = 0.01                                         # ends this close are one point
CHORD_MM = 0.002                                       # how far a curve may stand from its chords
SHOW_MM = 0.02                                         # the same, for the contours the page draws
CONTOUR_POINTS, TOTAL_POINTS = 400, 12_000
LIMIT = 1e7                                            # millimetres; a coordinate beyond is a damaged file
CHECK_TTL_SECONDS = order_files.PENDING_TTL_SECONDS
STATUS = {"off": 503, "upload": 404, "format": 415, "size": 413, "entities": 422, "points": 422,
          "time": 422, "empty": 422, "busy": 429, "rate": 429, "storage": 503}
MESSAGE = {
    "off": "Laser cutting is being prepared for this company.",
    "upload": "Choose the drawing again.",
    "format": "Choose a DXF or SVG drawing.",
    "size": "Choose a drawing up to 4 MB.",
    "entities": "Choose a drawing with up to 20,000 entities and 3,000 contours.",
    "points": "Choose a drawing with up to 200,000 points.",
    "time": "The workshop reads this drawing by hand. Send it as a custom request.",
    "empty": "Draw the cut lines as lines, arcs, circles or polylines.",
    "busy": "Please try again in a minute.",
    "rate": "Please try again in a minute.",
    "storage": "Design-file storage is full. Contact the workshop.",
}
GATE = threading.BoundedSemaphore(2)
TAU = 2 * math.pi
PX = 25.4 / 96
DXF_UNITS = {1: ("in", 25.4), 2: ("ft", 304.8), 4: ("mm", 1.0), 5: ("cm", 10.0), 6: ("m", 1000.0),
             8: ("uin", 2.54e-5), 9: ("mil", 0.0254), 10: ("yd", 914.4), 13: ("um", 0.001), 14: ("dm", 100.0)}
SVG_UNITS = {"mm": 1.0, "cm": 10.0, "in": 25.4, "pt": 25.4 / 72, "pc": 25.4 / 6, "px": PX, "": PX}
NUMBER = re.compile(r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")
LENGTH = re.compile(r"\s*([-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?)\s*([a-zA-Z%]*)\s*")
TRANSFORM = re.compile(r"(matrix|translate|scale|rotate|skewX|skewY)\s*\(([^)]*)\)")
SVG_SKIP = {"defs", "clipPath", "mask", "pattern", "symbol", "marker", "metadata", "title", "desc", "style",
            "script", "filter", "linearGradient", "radialGradient", "namedview"}
SVG_GROUP = {"svg", "g", "a", "switch"}
SCHEMA = """
CREATE TABLE IF NOT EXISTS laser_checks(
 id TEXT PRIMARY KEY,
 upload_id TEXT NOT NULL UNIQUE,
 fixed_upload_id TEXT,
 result TEXT NOT NULL,
 created_at REAL NOT NULL
);
"""
CHECK_ID = re.compile(r"[a-f0-9]{32}")
WORDS = {"bg": ("Лазерно рязане", "мм"), "en": ("Laser cutting", "mm")}


class Refusal(Exception):
    """The check answers without a reading. `reason` is one of STATUS."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason, self.status, self.message = reason, STATUS[reason], MESSAGE[reason]

    def body(self) -> dict:
        return {"ok": False, "reason": self.reason, "message": self.message}


# ---------------------------------------------------------------------------------------------
# What a reader collects: runs of points in millimetres, each step straight or bent by a bulge.
# A bulge is the DXF one: the tangent of a quarter of the arc's angle, positive to the left.

def _map(m: tuple, x: float, y: float) -> tuple[float, float]:
    return (m[0] * x + m[2] * y + m[4], m[1] * x + m[3] * y + m[5])


def _mul(m: tuple, t: tuple) -> tuple:
    """The matrix that applies `t`, then `m`."""
    return (m[0] * t[0] + m[2] * t[1], m[1] * t[0] + m[3] * t[1],
            m[0] * t[2] + m[2] * t[3], m[1] * t[2] + m[3] * t[3],
            m[0] * t[4] + m[2] * t[5] + m[4], m[1] * t[4] + m[3] * t[5] + m[5])


def _scale(m: tuple) -> float:
    return math.sqrt(max(m[0] * m[0] + m[1] * m[1], m[2] * m[2] + m[3] * m[3]))


def _similar(m: tuple) -> bool:
    """True when a circle stays a circle: one scale, turned or mirrored."""
    first, second = m[0] * m[0] + m[1] * m[1], m[2] * m[2] + m[3] * m[3]
    size = max(first, second, 1e-30)
    return abs(first - second) <= 1e-9 * size and abs(m[0] * m[2] + m[1] * m[3]) <= 1e-9 * size


def _bulge3(p0: tuple, pm: tuple, p1: tuple) -> float:
    """The bulge of the arc from p0 to p1 whose middle is pm."""
    dx, dy = p1[0] - p0[0], p1[1] - p0[1]
    chord = dx * dx + dy * dy
    if chord <= 1e-18:
        return 0.0
    return -2.0 * (dx * (pm[1] - p0[1]) - dy * (pm[0] - p0[0])) / chord


def _steps(radius: float, sweep: float, chord: float = CHORD_MM) -> int:
    """How many chords draw `sweep` radians of a circle within `chord` of the curve."""
    if radius <= chord:
        return max(1, math.ceil(sweep / (math.pi / 2)))
    return max(1, min(1440, math.ceil(sweep / (2 * math.acos(1 - chord / radius)))))


class Reading:
    def __init__(self, deadline: float):
        self.paths: list[tuple[list, list]] = []       # (points, bulges); bulges[i] bends point i to i+1
        self.entities = self.points = 0
        self.ignored: dict[str, int] = {}
        self.units = "mm"
        self.deadline = deadline
        self._points: list | None = None
        self._bulges: list = []

    def tick(self) -> None:
        if time.monotonic() > self.deadline:
            raise Refusal("time")

    def entity(self) -> None:
        self.entities += 1
        if self.entities > MAX_ENTITIES:
            raise Refusal("entities")
        if not self.entities % 256:
            self.tick()

    def ignore(self, kind: str) -> None:
        if len(self.ignored) < 32 or kind in self.ignored:
            self.ignored[kind] = self.ignored.get(kind, 0) + 1

    def _count(self, point: tuple) -> None:
        if not (-LIMIT < point[0] < LIMIT and -LIMIT < point[1] < LIMIT):   # also refuses NaN
            raise Refusal("format")
        self.points += 1
        if self.points > MAX_POINTS:
            raise Refusal("points")
        if not self.points % 2048:
            self.tick()

    def begin(self, point: tuple) -> None:
        self.end()
        self._count(point)
        self._points, self._bulges = [point], []

    def here(self) -> tuple:
        return self._points[-1]

    def to(self, point: tuple, bulge: float = 0.0) -> None:
        self._count(point)
        if not math.isfinite(bulge) or abs(bulge) > 1e6:
            raise Refusal("format")
        self._points.append(point)
        self._bulges.append(bulge)

    def close(self) -> None:
        if self._points and len(self._points) > 1:
            first, last = self._points[0], self._points[-1]
            if math.hypot(first[0] - last[0], first[1] - last[1]) > 1e-9:
                self.to(first)

    def end(self) -> None:
        if self._points and len(self._points) > 1:
            self.paths.append((self._points, self._bulges))
        self._points = None

    # The shapes both readers draw. `m` carries the file's own coordinates to millimetres.

    def line(self, m: tuple, x0: float, y0: float, x1: float, y1: float) -> None:
        self.begin(_map(m, x0, y0))
        self.to(_map(m, x1, y1))
        self.end()

    def arc(self, m: tuple, cx: float, cy: float, r: float, start: float, sweep: float) -> None:
        """Carry the pen along a circular arc; `sweep` is signed, in the file's own sense of turning."""
        if not (r > 0 and math.isfinite(start) and math.isfinite(sweep)) or sweep == 0:
            return
        if _similar(m):
            pieces = max(1, math.ceil(abs(sweep) / math.pi - 1e-9))
            step = sweep / pieces
            for k in range(pieces):
                angle = start + k * step
                middle = _map(m, cx + r * math.cos(angle + step / 2), cy + r * math.sin(angle + step / 2))
                end = _map(m, cx + r * math.cos(angle + step), cy + r * math.sin(angle + step))
                self.to(end, _bulge3(self.here(), middle, end))
        else:
            self.curve(m, cx, cy, r, 0.0, 0.0, r, start, start + sweep)

    def circle(self, m: tuple, cx: float, cy: float, r: float) -> None:
        if r > 0:
            self.begin(_map(m, cx + r, cy))
            self.arc(m, cx, cy, r, 0.0, TAU)
            self.end()

    def curve(self, m: tuple, cx: float, cy: float, ux: float, uy: float, vx: float, vy: float,
              t0: float, t1: float) -> None:
        """Carry the pen along c + u cos t + v sin t, an ellipse drawn out in chords."""
        size = max(math.hypot(ux, uy), math.hypot(vx, vy)) * _scale(m)
        count = _steps(size, abs(t1 - t0))
        for k in range(1, count + 1):
            t = t0 + (t1 - t0) * k / count
            self.to(_map(m, cx + ux * math.cos(t) + vx * math.sin(t), cy + uy * math.cos(t) + vy * math.sin(t)))

    def bezier(self, m: tuple, points: list[tuple]) -> None:
        """Carry the pen along a quadratic or cubic Bezier from its first control point."""
        mapped = [_map(m, x, y) for x, y in points]
        degree = len(mapped) - 1
        bend = max(math.hypot(mapped[i][0] - 2 * mapped[i + 1][0] + mapped[i + 2][0],
                              mapped[i][1] - 2 * mapped[i + 1][1] + mapped[i + 2][1]) for i in range(degree - 1))
        count = max(1, min(400, math.ceil(math.sqrt(degree * (degree - 1) / 8 * bend / CHORD_MM))))
        for k in range(1, count + 1):
            t = k / count
            level = mapped
            while len(level) > 1:
                level = [(a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t) for a, b in zip(level, level[1:])]
            self.to(level[0])

    def polyline(self, m: tuple, vertices: list[tuple], closed: bool) -> None:
        """A run of (x, y, bulge) in the file's own coordinates; a bulge bends the step that follows it."""
        if len(vertices) < 2:
            return
        steps = list(zip(vertices, vertices[1:] + vertices[:1])) if closed else list(zip(vertices, vertices[1:]))
        self.begin(_map(m, vertices[0][0], vertices[0][1]))
        for (x0, y0, bulge), (x1, y1, _) in steps:
            end = _map(m, x1, y1)
            if bulge:
                middle = _map(m, (x0 + x1) / 2 + bulge / 2 * (y1 - y0), (y0 + y1) / 2 - bulge / 2 * (x1 - x0))
                self.to(end, _bulge3(self.here(), middle, end))
            else:
                self.to(end)
        self.end()


# ---------------------------------------------------------------------------------------------
# DXF

def _float(value: str) -> float:
    try:
        number = float(value)
    except ValueError:
        raise Refusal("format") from None
    if not math.isfinite(number):
        raise Refusal("format")
    return number


def _dxf_records(text: str, reading: Reading) -> tuple[dict, list]:
    """The header's variables, and the entities of the ENTITIES section as (type, [(code, value)])."""
    lines = text.lstrip("\ufeff").splitlines()
    header: dict[str, str] = {}
    records: list[tuple[str, list]] = []
    section = variable = current = None
    naming = False
    for index in range(0, len(lines) - 1, 2):
        try:
            code = int(lines[index])
        except ValueError:
            raise Refusal("format") from None
        value = lines[index + 1].strip()
        if not index % 8192:
            reading.tick()
        if code == 0:
            current = None
            if value == "SECTION":
                section, naming = None, True
            elif value == "ENDSEC":
                section = None
            elif value == "EOF":
                break
            elif section == "ENTITIES":
                current = []
                records.append((value, current))
                if len(records) > MAX_ENTITIES + MAX_POINTS:
                    raise Refusal("entities")
        elif naming and code == 2:
            section, naming = value, False
        elif section == "HEADER":
            if code == 9:
                variable = value
            elif variable is not None:
                header.setdefault(variable, value)
        elif current is not None:
            current.append((code, value))
    return header, records


def _first(pairs: list, code: int, default: float = 0.0) -> float:
    for key, value in pairs:
        if key == code:
            return _float(value)
    return default


def _spline(degree: int, knots: list, controls: list, weights: list, count: int) -> list[tuple]:
    """Points along a NURBS curve by de Boor's recurrence."""
    n = len(controls)
    low, high = knots[degree], knots[n]
    points = []
    for step in range(count + 1):
        u = low + (high - low) * step / count
        span = min(max(bisect_right(knots, u) - 1, degree), n - 1)
        level = [(controls[j][0] * weights[j], controls[j][1] * weights[j], weights[j])
                 for j in range(span - degree, span + 1)]
        for r in range(1, degree + 1):
            for j in range(degree, r - 1, -1):
                i = j + span - degree
                width = knots[i + degree - r + 1] - knots[i]
                a = (u - knots[i]) / width if width else 0.0
                level[j] = tuple((1 - a) * level[j - 1][t] + a * level[j][t] for t in range(3))
        x, y, w = level[degree]
        points.append((x / w, y / w) if w else (x, y))
    return points


def _read_dxf(text: str, reading: Reading) -> None:
    header, records = _dxf_records(text, reading)
    try:
        units = int(float(header.get("$INSUNITS", "0")))
    except ValueError:
        units = 0
    if units in DXF_UNITS:
        reading.units, scale = DXF_UNITS[units]
    elif header.get("$MEASUREMENT", "1").strip() == "0":
        reading.units, scale = "in", 25.4
    else:
        reading.units, scale = "mm", 1.0
    index, total = 0, len(records)
    while index < total:
        kind, pairs = records[index]
        index += 1
        if kind in ("VERTEX", "SEQEND"):
            continue                                   # met outside a POLYLINE: a damaged run
        reading.entity()
        if _first(pairs, 67):
            reading.ignore("PAPER SPACE")
            continue
        mirrored = _first(pairs, 230, 1.0) < 0         # drawn on the back of the sheet
        m = (-scale if mirrored else scale, 0.0, 0.0, scale, 0.0, 0.0)
        if kind == "LINE":
            reading.line(m, _first(pairs, 10), _first(pairs, 20), _first(pairs, 11), _first(pairs, 21))
        elif kind == "CIRCLE":
            reading.circle(m, _first(pairs, 10), _first(pairs, 20), _first(pairs, 40))
        elif kind == "ARC":
            cx, cy, r = _first(pairs, 10), _first(pairs, 20), _first(pairs, 40)
            start = math.radians(_first(pairs, 50))
            sweep = (math.radians(_first(pairs, 51, 360.0)) - start) % TAU or TAU
            if r > 0:
                reading.begin(_map(m, cx + r * math.cos(start), cy + r * math.sin(start)))
                reading.arc(m, cx, cy, r, start, sweep)
                reading.end()
        elif kind == "LWPOLYLINE":
            vertices: list[list] = []
            for code, value in pairs:
                if code == 10:
                    vertices.append([_float(value), 0.0, 0.0])
                elif vertices and code == 20:
                    vertices[-1][1] = _float(value)
                elif vertices and code == 42:
                    vertices[-1][2] = _float(value)
            reading.polyline(m, [tuple(v) for v in vertices], bool(int(_first(pairs, 70)) & 1))
        elif kind == "POLYLINE":
            flags = int(_first(pairs, 70))
            vertices = []
            while index < total and records[index][0] == "VERTEX":
                vertex = records[index][1]
                index += 1
                if not int(_first(vertex, 70)) & 16:   # 16 marks a spline frame's control point
                    vertices.append((_first(vertex, 10), _first(vertex, 20), _first(vertex, 42)))
            if index < total and records[index][0] == "SEQEND":
                index += 1
            if flags & (16 | 64):
                reading.ignore("MESH")
            else:
                reading.polyline(m, vertices, bool(flags & 1))
        elif kind == "ELLIPSE":
            cx, cy = _first(pairs, 10), _first(pairs, 20)
            ux, uy, ratio = _first(pairs, 11), _first(pairs, 21), _first(pairs, 40, 1.0)
            t0 = _first(pairs, 41)
            t1 = t0 + ((_first(pairs, 42, TAU) - t0) % TAU or TAU)        # one turn at most, like an arc
            m = (scale, 0.0, 0.0, scale, 0.0, 0.0)     # an ellipse is stored in world coordinates
            if mirrored:
                t0, t1 = -t0, -t1
            if math.hypot(ux, uy) > 0 and ratio > 0:
                vx, vy = -uy * ratio, ux * ratio
                reading.begin(_map(m, cx + ux * math.cos(t0) + vx * math.sin(t0),
                                   cy + uy * math.cos(t0) + vy * math.sin(t0)))
                reading.curve(m, cx, cy, ux, uy, vx, vy, t0, t1)
                reading.end()
        elif kind == "SPLINE":
            m = (scale, 0.0, 0.0, scale, 0.0, 0.0)
            degree = int(_first(pairs, 71, 3.0))
            knots = [_float(value) for code, value in pairs if code == 40]
            weights = [_float(value) for code, value in pairs if code == 41]
            xs = [_float(value) for code, value in pairs if code == 10]
            ys = [_float(value) for code, value in pairs if code == 20]
            controls = list(zip(xs, ys))
            fits = list(zip([_float(value) for code, value in pairs if code == 11],
                            [_float(value) for code, value in pairs if code == 21]))
            if len(weights) != len(controls):
                weights = [1.0] * len(controls)
            sound = (1 <= degree <= 9 and len(controls) > degree and len(knots) == len(controls) + degree + 1
                     and all(a <= b for a, b in zip(knots, knots[1:])) and knots[degree] < knots[len(controls)])
            if sound:
                drawn = _spline(degree, knots, controls, weights, max(16, min(2000, 8 * len(controls))))
            else:
                drawn = fits if len(fits) > 1 else controls
            if len(drawn) > 1:
                reading.polyline(m, [(x, y, 0.0) for x, y in drawn], bool(int(_first(pairs, 70)) & 1))
        else:
            reading.ignore(kind[:24])


# ---------------------------------------------------------------------------------------------
# SVG

def _local(tag: object) -> str:
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def _attr(element, name: str, default: float = 0.0) -> float:
    found = LENGTH.fullmatch(element.get(name) or "")
    if not found:
        return default
    return _float(found.group(1))


def _transform(text: str) -> tuple:
    m = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
    for name, inside in TRANSFORM.findall(text):
        v = [_float(number) for number in NUMBER.findall(inside)]
        if name == "matrix" and len(v) == 6:
            t = tuple(v)
        elif name == "translate" and v:
            t = (1.0, 0.0, 0.0, 1.0, v[0], v[1] if len(v) > 1 else 0.0)
        elif name == "scale" and v:
            t = (v[0], 0.0, 0.0, v[1] if len(v) > 1 else v[0], 0.0, 0.0)
        elif name == "rotate" and v:
            c, s = math.cos(math.radians(v[0])), math.sin(math.radians(v[0]))
            t = (c, s, -s, c, 0.0, 0.0)
            if len(v) == 3:
                t = _mul(_mul((1.0, 0.0, 0.0, 1.0, v[1], v[2]), t), (1.0, 0.0, 0.0, 1.0, -v[1], -v[2]))
        elif name == "skewX" and v:
            t = (1.0, 0.0, math.tan(math.radians(v[0])), 1.0, 0.0, 0.0)
        elif name == "skewY" and v:
            t = (1.0, math.tan(math.radians(v[0])), 0.0, 1.0, 0.0, 0.0)
        else:
            raise Refusal("format")
        m = _mul(m, t)
    return m


class _Scan:
    """Walks the numbers, flags and letters of a path's `d`."""

    def __init__(self, text: str):
        self.text, self.at, self.size = text, 0, len(text)

    def _skip(self) -> None:
        while self.at < self.size and self.text[self.at] in " \t\r\n,":
            self.at += 1

    def command(self) -> str | None:
        self._skip()
        if self.at < self.size and self.text[self.at].isalpha():
            self.at += 1
            return self.text[self.at - 1]
        return None

    def more(self) -> bool:
        self._skip()
        return self.at < self.size and (self.text[self.at] in "+-." or self.text[self.at].isdigit())

    def done(self) -> bool:
        self._skip()
        return self.at >= self.size

    def number(self) -> float:
        self._skip()
        found = NUMBER.match(self.text, self.at)
        if not found:
            raise Refusal("format")
        self.at = found.end()
        return _float(found.group())

    def flag(self) -> bool:
        self._skip()
        if self.at >= self.size or self.text[self.at] not in "01":
            raise Refusal("format")
        self.at += 1
        return self.text[self.at - 1] == "1"


def _svg_arc(reading: Reading, m: tuple, x1: float, y1: float, rx: float, ry: float, turn: float,
             large: bool, sweep: bool, x2: float, y2: float) -> None:
    """An elliptical arc from its two ends to its centre (SVG 1.1, F.6.5), then along it."""
    rx, ry = abs(rx), abs(ry)
    if (x1, y1) == (x2, y2):
        return
    if rx == 0 or ry == 0:
        return reading.to(_map(m, x2, y2))
    c, s = math.cos(turn), math.sin(turn)
    hx, hy = (x1 - x2) / 2, (y1 - y2) / 2
    px, py = c * hx + s * hy, -s * hx + c * hy
    spread = px * px / (rx * rx) + py * py / (ry * ry)
    if spread > 1:
        rx, ry = rx * math.sqrt(spread), ry * math.sqrt(spread)
    under = rx * rx * py * py + ry * ry * px * px
    factor = math.sqrt(max(0.0, (rx * rx * ry * ry - under) / under)) if under else 0.0
    if large == sweep:
        factor = -factor
    qx, qy = factor * rx * py / ry, -factor * ry * px / rx
    cx, cy = c * qx - s * qy + (x1 + x2) / 2, s * qx + c * qy + (y1 + y2) / 2
    start = math.atan2((py - qy) / ry, (px - qx) / rx)
    extent = (math.atan2((-py - qy) / ry, (-px - qx) / rx) - start) % TAU
    if not sweep:
        extent -= TAU
    if extent == 0:
        return reading.to(_map(m, x2, y2))
    if abs(rx - ry) <= 1e-9 * max(rx, ry):
        reading.arc(m, cx, cy, rx, start + turn, extent)
    else:
        reading.curve(m, cx, cy, rx * c, rx * s, -ry * s, ry * c, start, start + extent)


def _svg_path(reading: Reading, m: tuple, d: str) -> None:
    scan = _Scan(d)
    x = y = sx = sy = 0.0
    control: tuple | None = None                       # the last curve's second control point, for S and T
    command, drawing = None, False
    while not scan.done():
        letter = scan.command()
        if letter is None:
            if command is None or command in "Zz":
                raise Refusal("format")
            letter = "L" if command == "M" else "l" if command == "m" else command
        if letter not in "MmLlHhVvCcSsQqTtAaZz":
            raise Refusal("format")
        command, relative, kind = letter, letter.islower(), letter.upper()
        ox, oy = (x, y) if relative else (0.0, 0.0)
        if kind == "Z":
            if drawing:
                reading.close()
                reading.end()
            x, y, drawing, control = sx, sy, False, None
            continue
        if kind == "M":
            x, y = ox + scan.number(), oy + scan.number()
            sx, sy, drawing, control = x, y, False, None
            reading.end()
            continue
        if not drawing:
            reading.begin(_map(m, x, y))
            drawing = True
        previous = control
        control = None
        if kind == "L":
            x, y = ox + scan.number(), oy + scan.number()
            reading.to(_map(m, x, y))
        elif kind == "H":
            x = ox + scan.number()
            reading.to(_map(m, x, y))
        elif kind == "V":
            y = oy + scan.number()
            reading.to(_map(m, x, y))
        elif kind in "CS":
            if kind == "C":
                first = (ox + scan.number(), oy + scan.number())
            else:
                first = (2 * x - previous[0], 2 * y - previous[1]) if previous and previous[2] == "C" else (x, y)
            second = (ox + scan.number(), oy + scan.number())
            end = (ox + scan.number(), oy + scan.number())
            reading.bezier(m, [(x, y), first, second, end])
            control, (x, y) = (second[0], second[1], "C"), end
        elif kind in "QT":
            if kind == "Q":
                first = (ox + scan.number(), oy + scan.number())
            else:
                first = (2 * x - previous[0], 2 * y - previous[1]) if previous and previous[2] == "Q" else (x, y)
            end = (ox + scan.number(), oy + scan.number())
            reading.bezier(m, [(x, y), first, end])
            control, (x, y) = (first[0], first[1], "Q"), end
        else:
            rx, ry, turn = scan.number(), scan.number(), math.radians(scan.number())
            large, sweep = scan.flag(), scan.flag()
            end = (ox + scan.number(), oy + scan.number())
            _svg_arc(reading, m, x, y, rx, ry, turn, large, sweep, end[0], end[1])
            x, y = end
    reading.end()


def _svg_rect(reading: Reading, m: tuple, element) -> None:
    x, y, w, h = _attr(element, "x"), _attr(element, "y"), _attr(element, "width"), _attr(element, "height")
    if w <= 0 or h <= 0:
        return
    rx, ry = element.get("rx"), element.get("ry")
    rx = _attr(element, "rx") if rx is not None else (_attr(element, "ry") if ry is not None else 0.0)
    ry = _attr(element, "ry") if ry is not None else rx
    rx, ry = min(abs(rx), w / 2), min(abs(ry), h / 2)
    if rx == 0 or ry == 0:
        return reading.polyline(m, [(x, y, 0.0), (x + w, y, 0.0), (x + w, y + h, 0.0), (x, y + h, 0.0)], True)
    quarter = math.pi / 2
    reading.begin(_map(m, x + rx, y))
    for cx, cy, start, ex, ey in ((x + w - rx, y + ry, -quarter, x + w, y + h - ry),
                                  (x + w - rx, y + h - ry, 0.0, x + rx, y + h),
                                  (x + rx, y + h - ry, quarter, x, y + ry),
                                  (x + rx, y + ry, math.pi, x + rx, y)):
        reading.to(_map(m, cx + rx * math.cos(start), cy + ry * math.sin(start)))
        if rx == ry:
            reading.arc(m, cx, cy, rx, start, quarter)
        else:
            reading.curve(m, cx, cy, rx, 0.0, 0.0, ry, start, start + quarter)
        reading.to(_map(m, ex, ey) if (ex, ey) != (x + rx, y) else reading._points[0])
    reading.end()


def _read_svg(body: bytes, reading: Reading) -> None:
    if b"<!ENTITY" in body.upper():
        raise Refusal("format")
    try:
        root = ElementTree.fromstring(body)
    except (ElementTree.ParseError, ValueError, LookupError):   # LookupError: an encoding nobody knows
        raise Refusal("format") from None
    if _local(root.tag) != "svg":
        raise Refusal("format")
    box = [_float(number) for number in NUMBER.findall(root.get("viewBox") or "")]
    sizes = []
    for name in ("width", "height"):
        found = LENGTH.fullmatch(root.get(name) or "")
        unit = found.group(2).lower() if found else "%"
        sizes.append(_float(found.group(1)) * SVG_UNITS[unit] if found and unit in SVG_UNITS else None)
    if len(box) == 4 and box[2] > 0 and box[3] > 0:
        scale_x = sizes[0] / box[2] if sizes[0] else (sizes[1] / box[3] if sizes[1] else PX)
        scale_y = sizes[1] / box[3] if sizes[1] else scale_x
        left, top = box[0], box[1]
    else:
        scale_x = scale_y = PX
        left = top = 0.0
    if not (0 < scale_x < 1e6 and 0 < scale_y < 1e6):
        raise Refusal("format")
    reading.units = "mm" if abs(scale_x - 1) < 1e-6 else "px" if abs(scale_x - PX) < 1e-9 else "user"
    # SVG counts y downward; the reading counts it upward.
    stack = [(root, (scale_x, 0.0, 0.0, -scale_y, -scale_x * left, scale_y * top), 0)]
    while stack:
        element, m, depth = stack.pop()
        tag = _local(element.tag)
        if not tag or tag in SVG_SKIP or depth > 64:
            continue
        style = (element.get("style") or "").replace(" ", "")
        if element.get("display") == "none" or "display:none" in style:
            continue
        if element.get("transform"):
            m = _mul(m, _transform(element.get("transform")))
        if tag in SVG_GROUP:
            stack.extend((child, m, depth + 1) for child in reversed(list(element)))
            continue
        reading.entity()
        if tag == "line":
            reading.line(m, _attr(element, "x1"), _attr(element, "y1"), _attr(element, "x2"), _attr(element, "y2"))
        elif tag in ("polyline", "polygon"):
            numbers = [_float(number) for number in NUMBER.findall(element.get("points") or "")]
            reading.polyline(m, [(x, y, 0.0) for x, y in zip(numbers[::2], numbers[1::2])], tag == "polygon")
        elif tag == "circle":
            reading.circle(m, _attr(element, "cx"), _attr(element, "cy"), _attr(element, "r"))
        elif tag == "ellipse":
            cx, cy, rx, ry = (_attr(element, name) for name in ("cx", "cy", "rx", "ry"))
            if rx > 0 and ry > 0 and rx == ry:
                reading.circle(m, cx, cy, rx)
            elif rx > 0 and ry > 0:
                reading.begin(_map(m, cx + rx, cy))
                reading.curve(m, cx, cy, rx, 0.0, 0.0, ry, 0.0, TAU)
                reading.end()
        elif tag == "rect":
            _svg_rect(reading, m, element)
        elif tag == "path":
            _svg_path(reading, m, element.get("d") or "")
        else:
            reading.ignore(tag[:24])


# ---------------------------------------------------------------------------------------------
# Geometry of one step between two points, straight or bent by a bulge

def _length(p0: tuple, p1: tuple, bulge: float) -> float:
    chord = math.hypot(p1[0] - p0[0], p1[1] - p0[1])
    b = abs(bulge)
    return chord if b < 1e-12 else chord * (1 + b * b) * math.atan(b) / b


def _sector(p0: tuple, p1: tuple, bulge: float) -> float:
    """The area between the chord and its arc, signed like the bulge."""
    b = abs(bulge)
    if b < 1e-12:
        return 0.0
    chord = math.hypot(p1[0] - p0[0], p1[1] - p0[1])
    radius, angle = chord * (1 + b * b) / (4 * b), 4 * math.atan(b)
    area = radius * radius * (angle - math.sin(angle)) / 2
    return area if bulge > 0 else -area


def _centre(p0: tuple, p1: tuple, bulge: float) -> tuple[float, float, float]:
    dx, dy = p1[0] - p0[0], p1[1] - p0[1]
    k = (1 - bulge * bulge) / (4 * bulge)
    radius = math.hypot(dx, dy) * (1 + bulge * bulge) / (4 * abs(bulge))
    return (p0[0] + p1[0]) / 2 - dy * k, (p0[1] + p1[1]) / 2 + dx * k, radius


def _box(points: list, bulges: list, closed: bool) -> tuple[float, float, float, float]:
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    low_x, low_y, high_x, high_y = min(xs), min(ys), max(xs), max(ys)
    count = len(points)
    for i, bulge in enumerate(bulges):
        if abs(bulge) < 1e-12:
            continue
        p0, p1 = points[i], points[(i + 1) % count]
        cx, cy, radius = _centre(p0, p1, bulge)
        start, sweep = math.atan2(p0[1] - cy, p0[0] - cx), 4 * math.atan(bulge)
        for quarter in range(4):
            angle = quarter * math.pi / 2
            turned = (angle - start) % TAU if sweep > 0 else (start - angle) % TAU
            if turned < abs(sweep):
                x, y = cx + radius * math.cos(angle), cy + radius * math.sin(angle)
                low_x, low_y, high_x, high_y = min(low_x, x), min(low_y, y), max(high_x, x), max(high_y, y)
    return low_x, low_y, high_x, high_y


def _drawn(points: list, bulges: list, chord: float, room: int) -> list[tuple]:
    """The run with every arc drawn out in chords. A closed run leaves its first point unrepeated.

    `room` is how many points the drawing may still take; a run that passes it is refused.
    """
    count = len(points)
    out = [points[0]]
    for i, bulge in enumerate(bulges):
        if len(out) > room:
            raise Refusal("points")
        p0, p1 = points[i], points[(i + 1) % count]
        if abs(bulge) >= 1e-12:
            cx, cy, radius = _centre(p0, p1, bulge)
            start, sweep = math.atan2(p0[1] - cy, p0[0] - cx), 4 * math.atan(bulge)
            pieces = _steps(radius, abs(sweep), chord)
            for k in range(1, pieces):
                angle = start + sweep * k / pieces
                out.append((cx + radius * math.cos(angle), cy + radius * math.sin(angle)))
        out.append(p1)
    if len(bulges) == count:                           # closed: the last step returned to the start
        out.pop()
    return out


def _shoelace(points: list) -> float:
    total = 0.0
    for (x0, y0), (x1, y1) in zip(points, points[1:] + points[:1]):
        total += x0 * y1 - x1 * y0
    return total / 2


def _inside(point: tuple, polygon: list) -> bool:
    x, y = point
    inside = False
    x0, y0 = polygon[-1]
    for x1, y1 in polygon:
        if (y0 > y) != (y1 > y) and x < (x1 - x0) * (y - y0) / (y1 - y0) + x0:
            inside = not inside
        x0, y0 = x1, y1
    return inside


def _thin(points: list, tolerance: float, tick) -> list:
    """Douglas-Peucker on an open run: the points that keep the line within `tolerance`."""
    last = len(points) - 1
    if last < 2:
        return points
    keep = bytearray(last + 1)
    keep[0] = keep[last] = 1
    stack, limit = [(0, last)], tolerance * tolerance
    while stack:
        a, b = stack.pop()
        if b - a < 2:
            continue
        if b - a > 512:
            tick()
        ax, ay = points[a]
        dx, dy = points[b][0] - ax, points[b][1] - ay
        span = dx * dx + dy * dy
        worst, at = -1.0, a
        for i in range(a + 1, b):
            px, py = points[i][0] - ax, points[i][1] - ay
            if span:
                t = (px * dx + py * dy) / span
                t = 0.0 if t < 0 else 1.0 if t > 1 else t
                px, py = px - t * dx, py - t * dy
            distance = px * px + py * py
            if distance > worst:
                worst, at = distance, i
        if worst > limit:
            keep[at] = 1
            stack.append((a, at))
            stack.append((at, b))
    return [point for point, kept in zip(points, keep) if kept]


def _simplify(points: list, tolerance: float, closed: bool, tick) -> list:
    if not closed:
        return _thin(points, tolerance, tick)
    if len(points) <= 3:
        return points
    x0, y0 = points[0]
    far = max(range(1, len(points)), key=lambda i: (points[i][0] - x0) ** 2 + (points[i][1] - y0) ** 2)
    ring = _thin(points[:far + 1], tolerance, tick)[:-1] + _thin(points[far:] + [points[0]], tolerance, tick)[:-1]
    if len(ring) >= 3:
        return ring
    ax, ay = points[far][0] - x0, points[far][1] - y0                  # a sliver: keep its widest point too
    third = max((i for i in range(1, len(points)) if i != far),
                key=lambda i: abs(ax * (points[i][1] - y0) - ay * (points[i][0] - x0)))
    return [points[i] for i in sorted((0, far, third))]


# ---------------------------------------------------------------------------------------------
# From runs to contours

def _cluster(reading: Reading) -> tuple[list, list]:
    """One number per point of the drawing, ends within JOIN_MM sharing a number; and the steps between."""
    positions: list[tuple] = []
    exact: dict[tuple, int] = {}
    grid: dict[tuple, list] = {}
    scale, reach = 1 / JOIN_MM, JOIN_MM * JOIN_MM
    steps: list[tuple] = []                            # (node, node, bulge, path index)
    for number, (points, bulges) in enumerate(reading.paths):
        nodes = []
        for x, y in points:
            node = exact.get((x, y))
            if node is None:
                gx, gy = math.floor(x * scale), math.floor(y * scale)
                for cx in (gx - 1, gx, gx + 1):
                    for cy in (gy - 1, gy, gy + 1):
                        for other in grid.get((cx, cy), ()):
                            ox, oy = positions[other]
                            if (ox - x) ** 2 + (oy - y) ** 2 <= reach:
                                node = other
                                break
                        if node is not None:
                            break
                    if node is not None:
                        break
                if node is None:
                    node = len(positions)
                    positions.append((x, y))
                    grid.setdefault((gx, gy), []).append(node)
                exact[(x, y)] = node
            nodes.append(node)
        if not number % 512:
            reading.tick()
        for i, bulge in enumerate(bulges):
            if nodes[i] != nodes[i + 1]:
                steps.append((nodes[i], nodes[i + 1], bulge, number))
    return positions, steps


def _walk(steps: list, alive: list) -> tuple[list, dict]:
    """Chains of steps met end to end: (nodes, bulges, closed). And how many steps meet at each node."""
    links: dict[int, list] = {}
    for index, (a, b, _, _) in enumerate(steps):
        if alive[index]:
            links.setdefault(a, []).append(index)
            links.setdefault(b, []).append(index)
    used = bytearray(len(steps))
    chains = []

    def run(node: int, index: int) -> tuple:
        start, nodes, bulges = node, [node], []
        while True:
            used[index] = 1
            a, b, bulge, _ = steps[index]
            node, bulge = (b, bulge) if a == node else (a, -bulge)
            bulges.append(bulge)
            if node == start:
                return nodes, bulges, True
            nodes.append(node)
            around = links[node]
            if len(around) != 2:
                return nodes, bulges, False
            index = around[0] if not used[around[0]] else around[1]
            if used[index]:
                return nodes, bulges, False

    for node in sorted(node for node, around in links.items() if len(around) != 2):
        for index in links[node]:
            if not used[index]:
                chains.append(run(node, index))
    for index, (a, _, _, _) in enumerate(steps):
        if alive[index] and not used[index]:
            chains.append(run(a, index))
    return chains, {node: len(around) for node, around in links.items()}


def _chain_measure(positions: list, nodes: list, bulges: list) -> tuple[float, float]:
    """Length, and the signed area the chain would hold once its ends are joined."""
    points = [positions[node] for node in nodes]
    length, area = 0.0, _shoelace(points)
    count = len(points)
    for i, bulge in enumerate(bulges):
        p0, p1 = points[i], points[(i + 1) % count]
        length += _length(p0, p1, bulge)
        area += _sector(p0, p1, bulge)
    return length, area


def _contours(reading: Reading, gap: float) -> tuple[list, list, list]:
    """Join the drawing into contours. Returns (contours, issues, positions); issues hold raw positions."""
    positions, steps = _cluster(reading)
    if not steps:
        raise Refusal("empty")
    issues: list[dict] = []
    alive = [True] * len(steps)
    # A line drawn again over the same line: the same two points, the same bend.
    seen: dict[tuple, list] = {}
    removed: dict[int, list] = {}
    for index, (a, b, bulge, path) in enumerate(steps):
        key, bend = ((a, b), bulge) if a < b else ((b, a), -bulge)
        drawn = seen.setdefault(key, [])
        if any(abs(bend - other) <= 1e-6 for other in drawn):
            alive[index] = False
            removed.setdefault(path, []).append(index)
        else:
            drawn.append(bend)
    for indices in removed.values():
        a, b, bulge, _ = steps[indices[0]]
        p0, p1 = positions[a], positions[b]
        if abs(bulge) >= 1e-12:
            cx, cy, radius = _centre(p0, p1, bulge)
            angle = math.atan2(p0[1] - cy, p0[0] - cx) + 2 * math.atan(bulge)
            at = (cx + radius * math.cos(angle), cy + radius * math.sin(angle))
        else:
            at = ((p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2)
        length = sum(_length(positions[steps[i][0]], positions[steps[i][1]], steps[i][2]) for i in indices)
        issues.append({"kind": "duplicate", "at": at, "length": length, "fixed": True})
    reading.tick()

    chains, degree = _walk(steps, alive)
    ends = sorted(node for node, count in degree.items() if count == 1)
    if ends and gap > JOIN_MM:
        owner: dict[int, int] = {}
        for number, (nodes, _, closed) in enumerate(chains):
            if not closed:
                owner[nodes[0]] = owner[nodes[-1]] = number
        cells: dict[tuple, list] = {}
        for node in ends:
            x, y = positions[node]
            cells.setdefault((math.floor(x / gap), math.floor(y / gap)), []).append(node)
        pairs = []
        for count, node in enumerate(ends):
            if not count % 64:
                reading.tick()
            x, y = positions[node]
            gx, gy = math.floor(x / gap), math.floor(y / gap)
            for cx in (gx - 1, gx, gx + 1):
                for cy in (gy - 1, gy, gy + 1):
                    for other in cells.get((cx, cy), ()):
                        if other > node:
                            distance = math.hypot(positions[other][0] - x, positions[other][1] - y)
                            if distance <= gap:
                                pairs.append((distance, node, other))
        pairs.sort()
        joined: set[int] = set()
        for distance, a, b in pairs:
            if a in joined or b in joined:
                continue
            if owner.get(a) == owner.get(b):
                # Its own two ends: join them when the chain then holds a shape, never a line back on itself.
                nodes, bulges, _ = chains[owner[a]]
                length, area = _chain_measure(positions, nodes, bulges)
                if abs(area) <= JOIN_MM * length:
                    continue
            joined.update((a, b))
            steps.append((a, b, 0.0, -1))
            alive.append(True)
            issues.append({"kind": "open_contour", "gap": distance, "fixed": True,
                           "at": ((positions[a][0] + positions[b][0]) / 2, (positions[a][1] + positions[b][1]) / 2)})
        if joined:
            chains, degree = _walk(steps, alive)
            ends = sorted(node for node, count in degree.items() if count == 1)
    reading.tick()
    if len(chains) > MAX_CONTOURS:
        raise Refusal("entities")

    for nodes, _, closed in chains:
        loose = [node for node in (nodes[0], nodes[-1]) if not closed and degree[node] == 1]
        if not loose:
            continue
        reach = []
        for node in loose if len(ends) <= 400 else ():
            x, y = positions[node]
            others = [math.hypot(positions[other][0] - x, positions[other][1] - y) for other in ends if other != node]
            if others:
                reach.append((min(others), node))
        if reach:
            distance, node = min(reach)
        else:                                          # the one loose end, or a crowd of them: its own span
            node = loose[0]
            distance = math.hypot(positions[nodes[0]][0] - positions[nodes[-1]][0],
                                  positions[nodes[0]][1] - positions[nodes[-1]][1])
        issues.append({"kind": "open_contour", "at": positions[node], "gap": distance, "fixed": False})
    for node in sorted(node for node, count in degree.items() if count > 2):
        issues.append({"kind": "junction", "at": positions[node], "lines": degree[node], "fixed": False})

    contours = []
    for nodes, bulges, closed in chains:
        points = [positions[node] for node in nodes]
        length, area = _chain_measure(points, list(range(len(points))), bulges)
        if closed:
            if area < 0:                               # every closed contour runs anticlockwise
                points, bulges, area = [points[0]] + points[:0:-1], [-bulge for bulge in reversed(bulges)], -area
            first = min(range(len(points)), key=lambda i: (points[i][1], points[i][0]))
            points, bulges = points[first:] + points[:first], bulges[first:] + bulges[:first]
        elif (points[-1][1], points[-1][0]) < (points[0][1], points[0][0]):
            points, bulges = points[::-1], [-bulge for bulge in reversed(bulges)]
        contours.append({"points": points, "bulges": bulges, "closed": closed, "length": length,
                         "area": area if closed else 0.0, "box": _box(points, bulges, closed)})
    return contours, issues, positions


def _nest(reading: Reading, contours: list) -> None:
    """Depth of each closed contour inside the others; an odd depth is a hole."""
    total = 0
    for index, contour in enumerate(contours):
        if not index % 64:
            reading.tick()
        contour["drawn"] = _drawn(contour["points"], contour["bulges"], SHOW_MM, MAX_SAMPLES - total)
        total += len(contour["drawn"])
        if total > MAX_SAMPLES:
            raise Refusal("points")
    closed = sorted((c for c in contours if c["closed"]), key=lambda c: -c["area"])
    for index, contour in enumerate(closed):
        if not index % 64:
            reading.tick()
        low_x, low_y, high_x, high_y = contour["box"]
        probe = contour["drawn"][0]
        depth = 0
        for other in closed[:index]:
            box = other["box"]
            if (box[0] <= low_x and box[1] <= low_y and box[2] >= high_x and box[3] >= high_y
                    and other["area"] > contour["area"] and _inside(probe, other["drawn"])):
                depth += 1
        contour["depth"] = depth
    for contour in contours:
        contour.setdefault("depth", 0)


def _show(reading: Reading, contours: list) -> list[list]:
    """Each contour as at most CONTOUR_POINTS points, TOTAL_POINTS in all."""
    least = [3 if contour["closed"] else 2 for contour in contours]
    shown = [contour["drawn"] for contour in contours]
    tolerance = SHOW_MM
    for _ in range(64):
        reading.tick()
        over = sum(len(points) for points in shown) > TOTAL_POINTS
        wide = [i for i, points in enumerate(shown) if len(points) > (least[i] if over else CONTOUR_POINTS)]
        if not over and not wide:
            return shown
        for i in wide:
            shown[i] = _simplify(shown[i], tolerance, contours[i]["closed"], reading.tick)
        tolerance *= 1.5
    return [points[::max(1, len(points) // low)][:CONTOUR_POINTS] for points, low in zip(shown, least)]


def _dxf(contours: list, width: float, height: float) -> bytes:
    """The corrected drawing: one LWPOLYLINE per contour, in millimetres."""
    out = ["999", "Cut lines corrected for laser cutting: open contours joined, repeated lines removed.",
           "0", "SECTION", "2", "HEADER", "9", "$INSUNITS", "70", "4", "9", "$MEASUREMENT", "70", "1",
           "9", "$EXTMIN", "10", "0.0", "20", "0.0", "9", "$EXTMAX", "10", f"{width:.4f}", "20", f"{height:.4f}",
           "0", "ENDSEC", "0", "SECTION", "2", "ENTITIES"]
    for contour in contours:
        points, bulges = contour["shifted"], contour["bulges"]
        out += ["0", "LWPOLYLINE", "100", "AcDbEntity", "8", "CUT", "100", "AcDbPolyline",
                "90", str(len(points)), "70", "1" if contour["closed"] else "0"]
        for i, (x, y) in enumerate(points):
            out += ["10", f"{x:.4f}", "20", f"{y:.4f}"]
            if i < len(bulges) and abs(bulges[i]) >= 1e-12:
                out += ["42", f"{bulges[i]:.9f}"]
    out += ["0", "ENDSEC", "0", "EOF"]
    return ("\n".join(out) + "\n").encode("ascii")


def read(name: str, body: bytes, *, gap: float = 1.0, kerf: float = 0.2) -> tuple[dict, bytes | None]:
    """Read one drawing. Returns its facts and, when something was corrected, the corrected DXF."""
    if not isinstance(body, (bytes, bytearray)) or not body or len(body) > MAX_BYTES:
        raise Refusal("size")
    suffix = Path(name or "").suffix.lower()
    reading = Reading(time.monotonic() + MAX_SECONDS)
    try:
        if suffix == ".dxf":
            if b"\x00" in body[:4096]:
                raise Refusal("format")                # a binary DXF
            _read_dxf(body.decode("utf-8", errors="replace"), reading)
        elif suffix == ".svg":
            _read_svg(bytes(body), reading)
        else:
            raise Refusal("format")
        reading.end()
    except (OverflowError, ZeroDivisionError, IndexError, RecursionError):
        raise Refusal("format") from None
    if not reading.paths:
        raise Refusal("empty")
    contours, issues, _ = _contours(reading, gap)
    _nest(reading, contours)
    low_x = min(contour["box"][0] for contour in contours)
    low_y = min(contour["box"][1] for contour in contours)
    width = max(contour["box"][2] for contour in contours) - low_x
    height = max(contour["box"][3] for contour in contours) - low_y
    if not (width > 0 or height > 0):
        raise Refusal("empty")
    if not (width < LIMIT and height < LIMIT):         # moved to its own corner it would leave the page
        raise Refusal("format")

    def place(point: tuple) -> list:
        return [round(point[0] - low_x, 2), round(point[1] - low_y, 2)]

    contours.sort(key=lambda c: (not c["closed"], c["depth"], -c["area"], c["box"][1], c["box"][0]))
    narrow = 2 * kerf
    smallest = None
    for contour in contours:
        contour["shifted"] = [(x - low_x, y - low_y) for x, y in contour["points"]]
        if contour["closed"]:
            box = contour["box"]
            size = min(box[2] - box[0], box[3] - box[1])
            smallest = size if smallest is None else min(smallest, size)
            if size < narrow:
                issues.append({"kind": "small_feature", "size": size, "limit": narrow, "fixed": False,
                               "at": ((box[0] + box[2]) / 2, (box[1] + box[3]) / 2)})
    order = {"open_contour": 0, "duplicate": 1, "small_feature": 2, "junction": 3}
    issues.sort(key=lambda issue: (order[issue["kind"]], not issue["fixed"], issue["at"][1], issue["at"][0]))
    listed = []
    for issue in issues[:MAX_ISSUES]:
        entry = {"kind": issue["kind"], "at": place(issue["at"])}
        for key in ("gap", "length", "size", "limit"):
            if key in issue:
                entry[key] = round(issue[key], 2)
        if "lines" in issue:
            entry["lines"] = issue["lines"]
        entry["fixed"] = issue["fixed"]
        listed.append(entry)
    shown = _show(reading, contours)
    facts = {
        "name": name, "units": "mm", "source_units": reading.units,
        "bounds": {"w": round(width, 2), "h": round(height, 2)},
        "contours": [{"points": [place(point) for point in points], "closed": contour["closed"],
                      "hole": contour["closed"] and contour["depth"] % 2 == 1}
                     for contour, points in zip(contours, shown)],
        "issues": listed,
        "cut": {
            "length_mm": round(sum(contour["length"] for contour in contours), 2),
            "pierces": len(contours),
            "area_mm2": round(sum(-c["area"] if c["depth"] % 2 else c["area"] for c in contours), 2),
            "smallest_mm": None if smallest is None else round(smallest, 2),
        },
        "ignored": dict(sorted(reading.ignored.items())),
    }
    if len(issues) > MAX_ISSUES:
        facts["more_issues"] = len(issues) - MAX_ISSUES
    corrected = _dxf(contours, width, height) if any(issue["fixed"] for issue in issues) else None
    return facts, corrected


# ---------------------------------------------------------------------------------------------
# The service: one reading per uploaded file, kept beside the company's orders

def ensure_schema(store) -> None:
    store.db.executescript(SCHEMA)


def check_id(upload_id: str) -> str:
    return hashlib.sha256(("laser-check:" + upload_id).encode()).hexdigest()[:32]


def _answer(store, block: dict, row: dict) -> dict:
    facts = json.loads(row["result"])
    fixed = None
    if row["fixed_upload_id"]:
        staged = order_files.pending(store, row["fixed_upload_id"])
        kept = staged or store.one(
            "SELECT id,name,size FROM order_files WHERE id=? AND order_id IS NOT NULL", (row["fixed_upload_id"],))
        if kept is not None:
            fixed = {"upload": kept["id"], "name": kept["name"], "size": kept["size"],
                     "path": f"api/laser/{row['id']}/fixed.dxf"}
            if staged is not None:
                fixed["discard_token"] = staged["discard_token"]
    return {
        "ok": True, "id": row["id"], "name": facts["name"], "units": facts["units"],
        "source_units": facts["source_units"], "bounds": facts["bounds"], "contours": facts["contours"],
        "issues": facts["issues"], **({"more_issues": facts["more_issues"]} if "more_issues" in facts else {}),
        "fixed": fixed, "cut": facts["cut"], "ignored": facts["ignored"],
        "materials": block["materials"], "default": block["default"], "tariff": block["tariff"],
        "status": block["status"],
    }


def _row(store, identifier: str) -> dict | None:
    row = store.one("SELECT * FROM laser_checks WHERE id=?", (identifier,))
    if row is None or row["created_at"] < time.time() - CHECK_TTL_SECONDS:
        return None
    return row


def check(store, block: dict | None, upload_id: object) -> dict:
    """Read the drawing behind one staged upload, once, and answer the page."""
    if block is None:
        raise Refusal("off")
    staged = order_files.pending(store, upload_id) if isinstance(upload_id, str) else None
    if staged is None:
        raise Refusal("upload")
    ensure_schema(store)
    identifier = check_id(upload_id)
    row = _row(store, identifier)
    if row is None:
        try:
            body = order_files.read_pending(store, upload_id)
        except (OSError, ValueError, PermissionError):
            raise Refusal("upload") from None
        if not GATE.acquire(blocking=False):
            raise Refusal("busy")
        try:
            facts, corrected = read(staged["name"], body, gap=block["gap"], kerf=block["kerf"])
        except Refusal:
            raise
        except Exception:                              # noqa: BLE001 - a drawing this reader cannot follow
            raise Refusal("format") from None
        finally:
            GATE.release()
        fixed = None
        if corrected is not None:
            stem = Path(staged["name"]).stem[:100].rstrip(" .") or "drawing"
            try:
                fixed = order_files.stage(store, stem + "-corrected.dxf", corrected, "laser-" + identifier)["id"]
            except ValueError:
                raise Refusal("storage") from None
        store.db.execute("DELETE FROM laser_checks WHERE created_at<?", (time.time() - CHECK_TTL_SECONDS,))
        store.db.execute(
            "INSERT OR IGNORE INTO laser_checks(id,upload_id,fixed_upload_id,result,created_at) VALUES(?,?,?,?,?)",
            (identifier, upload_id, fixed, json.dumps(facts, ensure_ascii=False, separators=(",", ":")), time.time()),
        )
        row = _row(store, identifier)
    return _answer(store, block, row)


def reread(store, block: dict | None, identifier: str) -> dict:
    """The answer to an earlier check, with the company's tariff as it stands now."""
    if block is None:
        raise Refusal("off")
    ensure_schema(store)
    row = _row(store, identifier) if CHECK_ID.fullmatch(identifier or "") else None
    if row is None:
        raise Refusal("upload")
    return _answer(store, block, row)


def corrected_file(store, identifier: str) -> tuple[Path, dict]:
    """The corrected DXF of one check, for the customer who holds the check's id."""
    ensure_schema(store)
    row = _row(store, identifier) if CHECK_ID.fullmatch(identifier or "") else None
    if row is None or not row["fixed_upload_id"]:
        raise ValueError("Unknown order file.")
    return order_files.read_staged(store, row["fixed_upload_id"])


def order_line(store, block: dict | None, request: object, language: str = "bg", *,
               currency: str | None = None, vat: float | None = None) -> dict:
    """One laser line of an order, measured by the server and priced as an estimate.

    The page sends {"id", "material", "thickness", "quantity"}. The line is stored as custom work:
    the company confirms it before it is a price. It carries the corrected drawing when the check
    made one, with the customer's own drawing beside it. `currency` and `vat` are the catalogue's,
    whose totals the line joins.
    """
    if block is None:
        raise ValueError(MESSAGE["off"])
    if currency not in (None, block["tariff"]["currency"]) or (
            vat is not None and abs(vat - block["tariff"]["vat"]) > 1e-9):
        raise ValueError(MESSAGE["off"])
    if not isinstance(request, dict):
        raise ValueError("Choose the drawing again.")
    ensure_schema(store)
    identifier = request.get("id")
    row = _row(store, identifier) if isinstance(identifier, str) and CHECK_ID.fullmatch(identifier) else None
    if row is None or order_files.pending(store, row["upload_id"]) is None:
        raise ValueError("Choose the drawing again.")
    if row["fixed_upload_id"] and order_files.pending(store, row["fixed_upload_id"]) is None:
        raise ValueError("Choose the drawing again.")
    material = next((m for m in block["materials"] if m["id"] == request.get("material")), None)
    thickness, quantity = request.get("thickness"), request.get("quantity", 1)
    if material is None or isinstance(thickness, bool) or thickness not in material["thicknesses"]:
        raise ValueError("Choose a material and a thickness from the list.")
    facts = json.loads(row["result"])
    price = laser_quote.quote(facts, material, block["tariff"], thickness, quantity)
    if not price["ok"]:
        raise ValueError(f"Enter a quantity from 1 to {laser_quote.MAX_QUANTITY}.")
    title, unit = WORDS[language if language in WORDS else "en"]
    name = material[language if language in WORDS else "en"]
    description = f"{title} · {facts['name']} · {name} · {thickness:g} {unit}"
    chosen = {"id": identifier, "material": material["id"], "thickness": thickness, "quantity": price["quantity"]}
    line = {
        "item_id": None, "kind": "custom", "description": description, "quantity": 1,
        "requested_quantity": price["quantity"], "configuration": {"custom": description, "laser": chosen},
        "cuts": 0, "gross": price["gross"], "confirmation": True, "status": "estimate",
        "laser": {**chosen, "name": facts["name"], "bounds": facts["bounds"], "cut": facts["cut"],
                  "issues": len(facts["issues"]), "price": price, "tariff": block["status"]},
        "upload_id": row["fixed_upload_id"] or row["upload_id"],
    }
    if row["fixed_upload_id"]:
        line["source_upload_id"] = row["upload_id"]
    return line


def main(argv: list[str]) -> int:
    if len(argv) not in (2, 4) or (len(argv) == 4 and argv[2] != "--fixed"):
        print(__doc__.strip().splitlines()[2].strip())
        return 2
    path = Path(argv[1])
    try:
        facts, corrected = read(path.name, path.read_bytes())
    except Refusal as refusal:
        print(json.dumps(refusal.body()))
        return 1
    shown = {**facts, "contours": len(facts["contours"]), "points": sum(len(c["points"]) for c in facts["contours"])}
    print(json.dumps(shown, ensure_ascii=False, indent=1))
    if corrected is not None and len(argv) == 4:
        Path(argv[3]).write_bytes(corrected)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
