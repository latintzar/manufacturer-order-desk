"""Studio renders of metal stock with Cycles (offline path tracing), built parametrically.

Run headless, one frame per call:

    blender -b --factory-startup -P scene.py -- --shape sq_tube --dims 50,50,5 --length 320 \
        --mat hr --rig grey --cam hero --out /path/p1.jpg --res 1600x1200 --samples 160

Everything is real scale in metres. The section is built from its standard (corner radii, root radii, flange
slopes), extruded along Y, and every vertex carries its analytic normal, so a 0.3 mm end bevel and a 12 mm root
radius shade equally cleanly. Materials are procedural Principled BSDF graphs in object space (metres), so a
texture has the same physical size on every product. The rig scales with the piece, so a 20 mm bar and a 1 m
plate are lit by the same solid angles.

Only bpy, mathutils and the standard library are used.
"""
import argparse
import math
import os
import sys
import time

import bpy
from mathutils import Vector
from mathutils.geometry import tessellate_polygon

MM = 0.001
PI = math.pi

# ---------------------------------------------------------------------------------------------------------
# Section standards (mm). h -> [b, tw, tf, root radius]
# ---------------------------------------------------------------------------------------------------------
IPE = {80: [46, 3.8, 5.2, 5], 100: [55, 4.1, 5.7, 7], 120: [64, 4.4, 6.3, 7], 140: [73, 4.7, 6.9, 7],
       160: [82, 5, 7.4, 9], 180: [91, 5.3, 8, 9], 200: [100, 5.6, 8.5, 12], 220: [110, 5.9, 9.2, 12],
       240: [120, 6.2, 9.8, 15], 270: [135, 6.6, 10.2, 15], 300: [150, 7.1, 10.7, 15], 330: [160, 7.5, 11.5, 18],
       360: [170, 8, 12.7, 18], 400: [180, 8.6, 13.5, 21], 450: [190, 9.4, 14.6, 21], 500: [200, 10.2, 16, 21],
       550: [210, 11.1, 17.2, 24], 600: [220, 12, 19, 24]}
# nominal -> [b, tw, tf, real height, root radius]
HEA = {100: [100, 5, 8, 96, 12], 120: [120, 5, 8, 114, 12], 140: [140, 5.5, 8.5, 133, 12],
       160: [160, 6, 9, 152, 15], 180: [180, 6, 9.5, 171, 15], 200: [200, 6.5, 10, 190, 18],
       220: [220, 7, 11, 210, 18], 240: [240, 7.5, 12, 230, 21], 260: [260, 7.5, 12.5, 250, 24],
       280: [280, 8, 13, 270, 24], 300: [300, 8.5, 14, 290, 27], 320: [300, 9, 15.5, 310, 27],
       340: [300, 9.5, 16.5, 330, 27], 360: [300, 10, 17.5, 350, 27], 400: [300, 11, 19, 390, 27],
       450: [300, 11.5, 21, 440, 27]}
HEB = {100: [100, 6, 10, 100, 12], 120: [120, 6.5, 11, 120, 12], 140: [140, 7, 12, 140, 12],
       160: [160, 8, 13, 160, 15], 180: [180, 8.5, 14, 180, 15], 200: [200, 9, 15, 200, 18],
       220: [220, 9.5, 16, 220, 18], 240: [240, 10, 17, 240, 21], 260: [260, 10, 17.5, 260, 24],
       280: [280, 10.5, 18, 280, 24], 300: [300, 11, 19, 300, 27], 320: [300, 11.5, 20.5, 320, 27],
       340: [300, 12, 21.5, 340, 27], 360: [300, 12.5, 22.5, 360, 27], 400: [300, 13.5, 24, 400, 27]}
# h -> [b, tw, tf]; root radius = tf, toe radius = tf / 2, flange slope 8 %
UPN = {30: [15, 4, 4.5], 40: [20, 5, 5.5], 50: [25, 5, 6], 65: [42, 5.5, 7.5], 80: [45, 6, 8], 100: [50, 6, 8.5],
       120: [55, 7, 9], 140: [60, 7, 10], 160: [65, 7.5, 10.5], 180: [70, 8, 11], 200: [75, 8.5, 11.5],
       220: [80, 9, 12.5], 240: [85, 9.5, 13], 260: [90, 10, 14], 280: [95, 10, 15], 300: [100, 10, 16],
       400: [110, 14, 18]}

WELDED = {'hr', 'cr', 'galv', 'wrought', 'inox'}      # hollow sections of these are roll-formed and welded


# ---------------------------------------------------------------------------------------------------------
# 2D profiles. A loop is a list of (x, z, nx, nz): position in mm and the unit normal pointing away from the
# metal. Outer loops run counter-clockwise, holes clockwise, so the metal is always on the left of travel.
# ---------------------------------------------------------------------------------------------------------
def fillet_loop(pts, radii):
    """Polygon (list of (x, z)) with a radius per corner -> dense loop with analytic normals."""
    n = len(pts)
    out = []
    # clamp each radius so two neighbouring tangent lengths never overlap on an edge
    tl = []
    geo = []
    for i in range(n):
        p0, p1, p2 = Vector(pts[i - 1]), Vector(pts[i]), Vector(pts[(i + 1) % n])
        u, v = (p1 - p0), (p2 - p1)
        lu, lv = u.length, v.length
        u, v = u / lu, v / lv
        cross = u.x * v.y - u.y * v.x
        phi = math.atan2(cross, u.dot(v))
        geo.append((p1, u, v, phi, lu, lv))
        tl.append(radii[i] * math.tan(abs(phi) / 2))
    scale = [1.0] * n
    for i in range(n):
        j = (i + 1) % n
        edge = geo[i][5]
        if tl[i] + tl[j] > edge * 0.98 and tl[i] + tl[j] > 0:
            k = edge * 0.98 / (tl[i] + tl[j])
            scale[i] = min(scale[i], k)
            scale[j] = min(scale[j], k)
    for i in range(n):
        p1, u, v, phi, lu, lv = geo[i]
        r = max(radii[i] * scale[i], 0.02)
        t = r * math.tan(abs(phi) / 2)
        a = p1 - u * t
        sgn = 1.0 if phi > 0 else -1.0
        c = a + Vector((-u.y, u.x)) * r * sgn
        seg = max(3, int(math.ceil(abs(phi) / (PI / 2) * (6 + min(26, r * 2.2)))))
        a0 = math.atan2(a.y - c.y, a.x - c.x)
        for k in range(seg + 1):
            ang = a0 + phi * k / seg
            d = Vector((math.cos(ang), math.sin(ang)))
            p = c + d * r
            nn = d * sgn
            out.append((p.x, p.y, nn.x, nn.y))
    # drop coincident neighbours (a tangent point shared by two arcs)
    clean = []
    for q in out:
        if clean and (abs(q[0] - clean[-1][0]) + abs(q[1] - clean[-1][1])) < 1e-6:
            continue
        clean.append(q)
    if (abs(clean[0][0] - clean[-1][0]) + abs(clean[0][1] - clean[-1][1])) < 1e-6:
        clean.pop()
    return clean


def circle_loop(r, n, hole=False, bead=None):
    """Circle of radius r. bead = (angle, half width in mm, height in mm): a weld bead on a hole."""
    out = []
    for k in range(n):
        a = 2 * PI * k / n
        if hole:
            a = -a
        rr = r
        if bead:
            d = (a - bead[0] + PI) % (2 * PI) - PI
            s = d * r / bead[1]
            if abs(s) < 1:
                rr = r - bead[2] * math.cos(s * PI / 2) ** 2
        out.append([rr * math.cos(a), rr * math.sin(a)])
    res = []
    for k in range(n):
        p0, p2 = out[k - 1], out[(k + 1) % n]
        tx, tz = p2[0] - p0[0], p2[1] - p0[1]
        ln = math.hypot(tx, tz)
        res.append((out[k][0], out[k][1], tz / ln, -tx / ln))
    return res


def dense_loop(pts):
    """Closed dense polyline (x, z) -> loop with normals taken from its neighbours. Counter-clockwise gives
    an outer loop, clockwise a hole: the normal is always the right-hand one, away from the metal."""
    n = len(pts)
    res = []
    for k in range(n):
        p0, p2 = pts[k - 1], pts[(k + 1) % n]
        tx, tz = p2[0] - p0[0], p2[1] - p0[1]
        ln = math.hypot(tx, tz) or 1.0
        res.append((pts[k][0], pts[k][1], tz / ln, -tx / ln))
    return res


def offset_hole(loop, t):
    """The bore of a formed section: the outer loop moved in by the wall t, run clockwise."""
    inner = [(x - nx * t, z - nz * t) for (x, z, nx, nz) in loop]
    inner.reverse()
    return dense_loop(inner)


def smooth_loop(half, W, H, rounds=3):
    """A formed section drawn by its right half (control points from the base to the crown, x >= 0),
    mirrored, rounded by corner cutting, then set to exactly W x H."""
    pts = list(half) + [(-x, z) for (x, z) in reversed(half)]
    for _ in range(rounds):
        nxt = []
        for k in range(len(pts)):
            a, b = pts[k], pts[(k + 1) % len(pts)]
            if math.hypot(b[0] - a[0], b[1] - a[1]) < 1e-9:
                continue
            nxt.append((0.75 * a[0] + 0.25 * b[0], 0.75 * a[1] + 0.25 * b[1]))
            nxt.append((0.25 * a[0] + 0.75 * b[0], 0.25 * a[1] + 0.75 * b[1]))
        pts = nxt
    xs, zs = [q[0] for q in pts], [q[1] for q in pts]
    sx, sz = W / (max(xs) - min(xs)), H / (max(zs) - min(zs))
    z0 = min(zs)
    return dense_loop([(x * sx, (z - z0) * sz) for (x, z) in pts])


def rect_pts(w, h):
    return [(-w / 2, -h / 2), (w / 2, -h / 2), (w / 2, h / 2), (-w / 2, h / 2)]


def build_profile(shape, d, mat, weld_mode=None):
    """-> dict(loops, w, h, minT, seam, info). Loops in mm, lowest point at z = 0, centred on x."""
    d = [float(x) for x in (d or [])]
    seam = None
    info = {}
    e_hr = 0.9            # the rolled edge of a hot-rolled section
    if shape in ('sq_tube', 'rect_tube'):
        a = d[0]
        b = d[1] if len(d) > 1 else a
        t = d[2] if len(d) > 2 else max(1.5, a * 0.06)
        extruded = mat in ('alu', 'copper', 'brass', 'bronze')
        ro = (0.6 if extruded else (2.0 if t <= 6 else 2.5 if t <= 10 else 3.0) * t)
        ri = (0.4 if extruded else max(ro - t, 0.5 * t))
        ro = min(ro, min(a, b) * 0.45)
        outer = fillet_loop(rect_pts(a, b), [ro] * 4)
        wi, hi = a - 2 * t, b - 2 * t
        if mat in WELDED and weld_mode not in ('seamless', 'spiral'):
            zb = hi * 0.14
            bw, bh = min(3.2, hi * 0.3) if t >= 2.5 else 2.2, min(0.9, t * 0.28)
            x = wi / 2
            pts = [(-x, -hi / 2), (x, -hi / 2), (x, zb - bw / 2), (x - bh, zb - bw / 5), (x - bh, zb + bw / 5),
                   (x, zb + bw / 2), (x, hi / 2), (-x, hi / 2)]
            rad = [ri, ri, 0.5, 0.35, 0.35, 0.5, ri, ri]
            seam = (a / 2, zb + b / 2, max(2.4, min(4.0, t * 0.8)))
        else:
            pts, rad = rect_pts(wi, hi), [ri] * 4
        inner = fillet_loop(pts[::-1], rad[::-1])
        loops, w, h, mt = [outer, inner], a, b, t
        info = dict(ro=ro, ri=ri)
    elif shape == 'round_tube':
        dia = d[0]
        t = d[1] if len(d) > 1 else max(1.5, dia * 0.06)
        n = 192 if dia < 120 else 288
        bead = None
        if mat in WELDED and weld_mode not in ('seamless', 'spiral'):
            ang = math.radians(28)
            bead = (-ang, 1.6, min(0.8, t * 0.28))          # hole loop runs clockwise: angle is negated
            seam = (dia / 2 * math.cos(ang), dia / 2 * math.sin(ang) + dia / 2, max(2.4, min(4.0, t * 0.8)))
        loops = [circle_loop(dia / 2, n), circle_loop(dia / 2 - t, n, hole=True, bead=bead)]
        w, h, mt = dia, dia, t
    elif shape == 'round':
        dia = d[0]
        loops, w, h, mt = [circle_loop(dia / 2, 224)], dia, dia, dia
    elif shape == 'square':
        a = d[0]
        r = max(0.5, a * 0.045) if mat in ('hr', 'wrought') else 0.4
        loops, w, h, mt = [fillet_loop(rect_pts(a, a), [r] * 4)], a, a, a
    elif shape == 'hex':
        s = d[0]
        c = s / math.sqrt(3)
        pts = [(c * math.cos(PI / 6 + k * PI / 3), c * math.sin(PI / 6 + k * PI / 3)) for k in range(6)]
        loops, w, h, mt = [fillet_loop(pts, [0.35] * 6)], 2 * c * math.cos(PI / 6), 2 * c, s
        w, h = s, 2 * c
        pts = [(c * math.cos(k * PI / 3), c * math.sin(k * PI / 3)) for k in range(6)]     # rests on a flat
        loops, w, h = [fillet_loop(pts, [0.35] * 6)], 2 * c, s
    elif shape == 'flat':
        w, t = d[0], d[1]
        r = min(1.2, t * 0.22) if mat in ('hr', 'wrought') else min(0.6, t * 0.14)
        loops, h, mt = [fillet_loop(rect_pts(w, t), [r] * 4)], t, t
    elif shape in ('sheet', 'chequer'):
        t, w = d[0], (d[1] if len(d) > 1 else 1000)
        r = min(0.22, t * 0.2)
        loops, h, mt = [fillet_loop(rect_pts(w, t), [r] * 4)], t, t
    elif shape in ('angle', 'angle_u'):
        a = d[0]
        b = d[1] if len(d) > 1 else a
        t = d[2] if len(d) > 2 else max(3, a * 0.1)
        lo, hi = max(a, b), min(a, b)                 # long leg lies on the floor
        if mat in ('hr', 'wrought'):
            r1 = min(0.6 * t + 5, (hi - t) * 0.6)
            r2, e = r1 / 2, e_hr
        else:
            r1, r2, e = min(t, 2.0), 0.4, 0.4
        pts = [(0, 0), (lo, 0), (lo, t), (t, t), (t, hi), (0, hi)]
        loops = [fillet_loop(pts, [e, e, min(r2, t * 0.6), r1, min(r2, t * 0.6), e])]
        w, h, mt = lo, hi, t
        info = dict(t=t, r1=r1)
    elif shape == 'tee':
        a = d[0]
        b = d[1] if len(d) > 1 else a
        t = d[2] if len(d) > 2 else max(3, a * 0.1)
        pts = [(-a / 2, 0), (a / 2, 0), (a / 2, t), (t / 2, t), (t / 2, b), (-t / 2, b), (-t / 2, t), (-a / 2, t)]
        loops = [fillet_loop(pts, [e_hr, e_hr, t / 2, t, t / 4, t / 4, t, t / 2])]
        w, h, mt = a, b, t
    elif shape == 'channel':
        hh, b = d[0], d[1]
        t = d[2] if len(d) > 2 else 3
        pts = [(-hh / 2, 0), (hh / 2, 0), (hh / 2, b), (hh / 2 - t, b), (hh / 2 - t, t), (-hh / 2 + t, t),
               (-hh / 2 + t, b), (-hh / 2, b)]
        loops = [fillet_loop(pts, [2 * t, 2 * t, 0.3, 0.3, t, t, 0.3, 0.3])]
        w, h, mt = hh, b, t
    elif shape == 'upn':
        hh = d[0]
        T = UPN.get(int(hh)) or [d[1] if len(d) > 1 else hh * 0.45, max(4, hh * 0.05), max(5, hh * 0.07)]
        b = d[1] if len(d) > 1 else T[0]
        tw, tf = T[1], T[2]
        s = 0.08 if hh <= 300 else 0.05
        zi = tf + s * (b / 2 - tw)                    # flange thickness at the web
        zo = max(tf - s * (b / 2), tf * 0.45)         # and at the toe
        pts = [(0, 0), (b, 0), (b, zo), (tw, zi), (tw, hh - zi), (b, hh - zo), (b, hh), (0, hh)]
        pts = [(x - b / 2, z) for x, z in pts]
        loops = [fillet_loop(pts, [e_hr, e_hr, tf / 2, tf, tf, tf / 2, e_hr, e_hr])]
        w, h, mt = b, hh, min(tw, zo)
    elif shape in ('ipe', 'hea', 'heb'):
        n = int(d[0])
        if shape == 'ipe':
            T = IPE.get(n) or [n * 0.5, n * 0.03 + 2, n * 0.045 + 2, max(5, n * 0.05)]
            hh, b, tw, tf, r = n, T[0], T[1], T[2], T[3]
        else:
            tab = HEA if shape == 'hea' else HEB
            T = tab.get(n) or [n, n * 0.04 + 2, n * 0.06 + 3, n, 18]
            b, tw, tf, hh, r = T[0], T[1], T[2], T[3], T[4]
        x, wb = b / 2, tw / 2
        pts = [(-x, 0), (x, 0), (x, tf), (wb, tf), (wb, hh - tf), (x, hh - tf), (x, hh), (-x, hh), (-x, hh - tf),
               (-wb, hh - tf), (-wb, tf), (-x, tf)]
        e = min(1.6, tf * 0.16)
        loops = [fillet_loop(pts, [e, e, e, r, r, e, e, e, e, r, r, e])]
        w, h, mt = b, hh, min(tw, tf)
        info = dict(b=b, tw=tw, tf=tf, r=r)
    elif shape == 'handrail':
        # roll-formed handrail tube: a flat base under an arch (the company's photo of 50 and 60)
        W = d[0]
        t = d[1] if len(d) > 1 else 1.5
        H = d[2] if len(d) > 2 else (25.0 if W <= 50 else 33.0)
        a = W / 2
        half = [(a - 9.0, 0), (a, 0), (a, 9.0), (a * 0.985, H * 0.5), (a * 0.84, H * 0.80), (a * 0.52, H * 0.975),
                (a * 0.18, H)]
        outer = smooth_loop(half, W, H)
        loops, w, h, mt = [outer, offset_hole(outer, t)], W, H, t
    elif shape == 'mushroom':
        # embossed handrail tube: a rounded cap W wide on a narrower flat base B (the maker's section sketch)
        W, H = d[0], d[1]
        t = d[2] if len(d) > 2 else 1.5
        B = d[3] if len(d) > 3 else round(W * 0.64)
        a, b = W / 2, B / 2
        if H / W > 0.8:
            half = [(b - 7.0, 0), (b, 0), (b, H * 0.13), (b * 0.93, H * 0.34), (b, H * 0.46), (a, H * 0.60),
                    (a, H * 0.78), (a * 0.86, H * 0.93), (a * 0.5, H), (a * 0.18, H)]
        else:
            half = [(b - 7.0, 0), (b, 0), (b + (a - b) * 0.2, H * 0.14), (a, H * 0.40), (a, H * 0.62),
                    (a * 0.85, H * 0.88), (a * 0.5, H), (a * 0.18, H)]
        outer = smooth_loop(half, W, H)
        loops, w, h, mt = [outer, offset_hole(outer, t)], W, H, t
    elif shape == 'moulded':
        # solid moulded handrail bar: a low dome between two shoulder beads on a flat back
        W, H = d[0], d[1]
        a = W / 2
        half = [(a - 2.5, 0), (a, 0), (a, 2.5), (a, H * 0.34), (a * 0.94, H * 0.52), (a * 0.82, H * 0.54),
                (a * 0.72, H * 0.44), (a * 0.63, H * 0.56), (a * 0.50, H * 0.80), (a * 0.30, H * 0.95),
                (a * 0.10, H)]
        loops, w, h, mt = [smooth_loop(half, W, H)], W, H, H
    elif shape in ('window1', 'window2'):
        # steel window section: a square box with one or two rebate fins (the strip folded back on itself)
        a = d[0]
        t = d[1] if len(d) > 1 else 1.5
        f = round(a * 0.44)
        ro = 2.0 * t
        x = a / 2
        if shape == 'window1':
            pts = [(-x, 0), (x + f, 0), (x + f, 2 * t), (x, 2 * t), (x, a), (-x, a)]
            rad = [ro, 0.6 * t, 0.9 * t, 1.5 * t, ro, ro]
        else:
            pts = [(-x - f, 0), (x + f, 0), (x + f, 2 * t), (x, 2 * t), (x, a), (-x, a), (-x, 2 * t),
                   (-x - f, 2 * t)]
            rad = [0.6 * t, 0.6 * t, 0.9 * t, 1.5 * t, ro, ro, 1.5 * t, 0.9 * t]
        ih = [(px, pz + a / 2) for (px, pz) in rect_pts(a - 2 * t, a - 2 * t)]
        loops = [fillet_loop(pts, rad), fillet_loop(ih[::-1], [max(ro - t, 0.5 * t)] * 4)]
        w, h, mt = a + (f if shape == 'window1' else 2 * f), a, t
    elif shape == 'trapezoid':
        # trapezoidal roofing sheet LT20: ribs 20 mm high at 145 mm (six to the 870 mm cover width)
        t = d[0]
        wd = d[1] if len(d) > 1 else 450.0
        rib, pitch, top, bot = 20.0, 145.0, 36.0, 72.0
        fl = (pitch - top - bot) / 2
        low = [(-wd / 2, 0.0)]
        k = -int((wd / 2 - top / 2 - fl - 4) // pitch)
        while k * pitch + top / 2 + fl < wd / 2 - 4:
            c = k * pitch
            low += [(c - top / 2 - fl, 0.0), (c - top / 2, rib), (c + top / 2, rib), (c + top / 2 + fl, 0.0)]
            k += 1
        low.append((wd / 2, 0.0))

        def left(a_, b_):
            dx, dz = b_[0] - a_[0], b_[1] - a_[1]
            ln = math.hypot(dx, dz)
            return (-dz / ln, dx / ln)
        up = []
        for i, q in enumerate(low):
            if i == 0:
                n1 = n2 = left(low[0], low[1])
            elif i == len(low) - 1:
                n1 = n2 = left(low[-2], low[-1])
            else:
                n1, n2 = left(low[i - 1], q), left(q, low[i + 1])
            k2 = t / (1 + n1[0] * n2[0] + n1[1] * n2[1])
            up.append((q[0] + (n1[0] + n2[0]) * k2, q[1] + (n1[1] + n2[1]) * k2))
        pts = low + up[::-1]
        rad = []
        for i in range(len(pts)):
            p0, p1, p2 = pts[i - 1], pts[i], pts[(i + 1) % len(pts)]
            cr = (p1[0] - p0[0]) * (p2[1] - p1[1]) - (p1[1] - p0[1]) * (p2[0] - p1[0])
            end = i in (0, len(low) - 1, len(low), len(pts) - 1)
            rad.append(0.25 * t if end else (2.0 + t if cr > 0 else 2.0))
        loops, w, h, mt = [fillet_loop(pts, rad)], wd, rib + t, t
    else:
        raise SystemExit('unknown shape ' + shape)
    # rest on the floor, centred on x
    zmin = min(p[1] for p in loops[0])
    xs = [p[0] for p in loops[0]]
    xc = (min(xs) + max(xs)) / 2
    loops = [[(p[0] - xc, p[1] - zmin, p[2], p[3]) for p in lp] for lp in loops]
    if seam:
        seam = (seam[0] - xc, seam[1] - b / 2 - zmin if shape in ('sq_tube', 'rect_tube') else seam[1], seam[2])
    return dict(loops=loops, w=w, h=h, minT=mt, seam=seam, info=info)


# ---------------------------------------------------------------------------------------------------------
# Mesh: the profile extruded along +Y from 0 to L, with a rounded bevel at both sawn ends.
# Material slots: 0 = the rolled / drawn surface, 1 = the cut (end face and its bevel).
# ---------------------------------------------------------------------------------------------------------
def build_bar(name, prof, length_mm, bevel_mm=0.3, bevel_seg=3, cut_sides=False):
    L = length_mm
    bv = min(bevel_mm, prof['minT'] * 0.22)
    edge_x = prof['w'] / 2 - 2.5 * max(prof['minT'], 0.3)
    rings = []                                   # (inset, y, weight of the profile normal, y normal)
    for k in range(bevel_seg + 1):
        th = (PI / 2) * k / bevel_seg
        rings.append((bv * (1 - math.sin(th)), bv * (1 - math.cos(th)), math.sin(th), -math.cos(th)))
    for k in range(bevel_seg, -1, -1):
        th = (PI / 2) * k / bevel_seg
        rings.append((bv * (1 - math.sin(th)), L - bv * (1 - math.cos(th)), math.sin(th), math.cos(th)))
    verts, norms, faces, fmat = [], [], [], []
    nr = len(rings)
    base = 0
    cap_a, cap_b = [], []
    for li, lp in enumerate(prof['loops']):
        n = len(lp)
        hole = li > 0
        for (ins, y, wn, yn) in rings:
            for (x, z, nx, nz) in lp:
                verts.append(((x - nx * ins) * MM, y * MM, (z - nz * ins) * MM))
                norms.append((nx * wn, yn, nz * wn))
        for j in range(nr - 1):
            side = (j == bevel_seg)
            for i in range(n):
                i2 = (i + 1) % n
                a, b = base + j * n + i, base + j * n + i2
                c, dd = base + (j + 1) * n + i2, base + (j + 1) * n + i
                faces.append((a, dd, c, b))
                m = (2 if hole else 0) if side else 1
                if (side and cut_sides and abs(lp[i][2]) > 0.5 and abs(lp[i2][2]) > 0.5
                        and abs(lp[i][0]) > edge_x):
                    m = 1                        # the sheared long edges of a sheet
                fmat.append(m)
        cap_a.append([base + i for i in range(n)])
        cap_b.append([base + (nr - 1) * n + i for i in range(n)])
        base += nr * n
    for cap, ysign in ((cap_a, -1.0), (cap_b, 1.0)):
        flat = [i for lp in cap for i in lp]
        polys = [[Vector((verts[i][0], verts[i][2], 0.0)) for i in lp] for lp in cap]
        for tri in tessellate_polygon(polys):
            a, b, c = (flat[t] for t in tri)
            va, vb, vc = Vector(verts[a]), Vector(verts[b]), Vector(verts[c])
            if ((vb - va).cross(vc - va)).y * ysign < 0:
                b, c = c, b
            faces.append((a, b, c))
            fmat.append(1)
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.polygons.foreach_set('use_smooth', [True] * len(faces))
    me.polygons.foreach_set('material_index', fmat)
    me.update()
    me.normals_split_custom_set_from_vertices(norms)
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def build_pattern(name, kind, w_mm, l_mm, top_mm):
    """Raised chequer pattern as real geometry on the top of a plate: 'tear' (single lentils, alternating
    +-45 degrees) or 'bars' (five parallel bars, alternating)."""
    import bmesh
    if kind == 'bars':
        pitch, a, b, H = 30.0, 11.0, 1.6, 1.0
        offs = [(-2, 0.62), (-1, 0.86), (0, 1.0), (1, 0.86), (2, 0.62)]
        gap = 4.6
    else:
        pitch, a, b, H = 26.0, 12.5, 3.9, 1.5
        offs = [(0, 1.0)]
        gap = 0.0
    nu, nv = 26, 11
    tmpl_v, tmpl_f = [], []
    for iu in range(nu):
        s = -math.cos(PI * iu / (nu - 1))
        prof_s = max(0.0, 1 - s * s)
        hw = b * (prof_s ** (0.75 if kind != 'bars' else 0.35)) + 0.02
        hh = H * (prof_s ** (0.55 if kind != 'bars' else 0.3))
        for iv in range(nv):
            t = -1 + 2 * iv / (nv - 1)
            c = math.cos(t * PI / 2)
            tmpl_v.append((s * a, t * hw * 1.25, hh * (c ** 1.35) - 0.03))
    for iu in range(nu - 1):
        for iv in range(nv - 1):
            p = iu * nv + iv
            tmpl_f.append((p, p + nv, p + nv + 1, p + 1))
    verts, faces = [], []
    nx_, ny_ = int(w_mm / pitch) + 2, int(l_mm / pitch) + 2
    x0, y0 = -(nx_ - 1) * pitch / 2, l_mm / 2 - (ny_ - 1) * pitch / 2
    for i in range(nx_):
        for j in range(ny_):
            ang = PI / 4 if (i + j) % 2 == 0 else -PI / 4
            ca, sa = math.cos(ang), math.sin(ang)
            cx, cy = x0 + i * pitch, y0 + j * pitch
            reach = (a + 2 * gap) * 0.72 + 1.0            # a whole figure fits, or it is left out
            if abs(cx) > w_mm / 2 - reach or cy < reach or cy > l_mm - reach:
                continue
            for (o, lf) in offs:
                ox, oy = -sa * o * gap, ca * o * gap
                base = len(verts)
                for (u, v, hgt) in tmpl_v:
                    u2 = u * lf
                    verts.append(((cx + ox + u2 * ca - v * sa) * MM, (cy + oy + u2 * sa + v * ca) * MM,
                                  (top_mm + hgt) * MM))
                faces.extend([tuple(base + q for q in f) for f in tmpl_f])
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    bm = bmesh.new()
    bm.from_mesh(me)
    edge = 0.05
    for co, no in (((-(w_mm / 2 - edge) * MM, 0, 0), (-1, 0, 0)), (((w_mm / 2 - edge) * MM, 0, 0), (1, 0, 0)),
                   ((0, edge * MM, 0), (0, -1, 0)), ((0, (l_mm - edge) * MM, 0), (0, 1, 0))):
        geom = bm.verts[:] + bm.edges[:] + bm.faces[:]
        bmesh.ops.bisect_plane(bm, geom=geom, plane_co=co, plane_no=no, clear_outer=True)
    bm.to_mesh(me)
    bm.free()
    me.polygons.foreach_set('use_smooth', [True] * len(me.polygons))
    me.update()
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


# ---------------------------------------------------------------------------------------------------------
# Node graph helper
# ---------------------------------------------------------------------------------------------------------
VARY = False        # set by a stack builder: textures shift per object, so no two bars are twins


class G:
    def __init__(self, name):
        self.mat = bpy.data.materials.new(name)
        self.mat.use_nodes = True
        self.t = self.mat.node_tree
        self.t.nodes.clear()
        self.out = self.t.nodes.new('ShaderNodeOutputMaterial')
        tc = self.t.nodes.new('ShaderNodeTexCoord')
        self.Pobj = tc.outputs['Object']         # metres, Y along the bar
        self.P = self.Pobj
        if VARY:                                  # each copy in a stack gets its own stretch of the textures
            oi = self.t.nodes.new('ShaderNodeObjectInfo')
            sc = self.t.nodes.new('ShaderNodeVectorMath')
            sc.operation = 'SCALE'
            sc.inputs[0].default_value = (0.37, 1.13, 0.59)
            self.t.links.new(oi.outputs['Random'], sc.inputs['Scale'])
            ad = self.t.nodes.new('ShaderNodeVectorMath')
            ad.operation = 'ADD'
            self.t.links.new(self.Pobj, ad.inputs[0])
            self.t.links.new(sc.outputs[0], ad.inputs[1])
            self.P = ad.outputs[0]
        self.UV = tc.outputs['Generated']
        geo = self.t.nodes.new('ShaderNodeNewGeometry')
        self.N = geo.outputs['Normal']
        self._xyz = None

    def node(self, kind, props=None, **ins):
        nd = self.t.nodes.new(kind)
        for k, v in (props or {}).items():
            setattr(nd, k, v)
        for k, v in ins.items():
            self.set(nd, k.replace('_', ' ') if k.replace('_', ' ') in nd.inputs else k, v)
        return nd

    def set(self, nd, key, val):
        sock = nd.inputs[key]
        if isinstance(val, bpy.types.NodeSocket):
            self.t.links.new(val, sock)
        else:
            sock.default_value = val

    def math(self, op, a, b=None, c=None, clamp=False):
        nd = self.t.nodes.new('ShaderNodeMath')
        nd.operation = op
        nd.use_clamp = clamp
        for i, v in enumerate((a, b, c)):
            if v is not None:
                self.set(nd, i, v)
        return nd.outputs[0]

    def add(self, a, b): return self.math('ADD', a, b)
    def mul(self, a, b): return self.math('MULTIPLY', a, b)
    def sub(self, a, b): return self.math('SUBTRACT', a, b)

    def remap(self, x, a, b, c=0.0, d=1.0, smooth=False):
        nd = self.t.nodes.new('ShaderNodeMapRange')
        nd.interpolation_type = 'SMOOTHSTEP' if smooth else 'LINEAR'
        nd.clamp = True
        self.set(nd, 'Value', x)
        for k, v in (('From Min', a), ('From Max', b), ('To Min', c), ('To Max', d)):
            self.set(nd, k, v)
        return nd.outputs['Result']

    def mixf(self, f, a, b):
        nd = self.t.nodes.new('ShaderNodeMix')
        nd.data_type = 'FLOAT'
        self.set(nd, 0, f)
        self.set(nd, 2, a)
        self.set(nd, 3, b)
        return nd.outputs[0]

    def mixc(self, f, a, b, blend='MIX'):
        nd = self.t.nodes.new('ShaderNodeMix')
        nd.data_type = 'RGBA'
        nd.blend_type = blend
        self.set(nd, 0, f)
        self.set(nd, 6, a if isinstance(a, bpy.types.NodeSocket) else (*a, 1.0))
        self.set(nd, 7, b if isinstance(b, bpy.types.NodeSocket) else (*b, 1.0))
        return nd.outputs[2]

    def stretch(self, vec, scale, loc=(0, 0, 0), rot=(0, 0, 0)):
        nd = self.t.nodes.new('ShaderNodeMapping')
        self.set(nd, 'Vector', vec)
        nd.inputs['Scale'].default_value = scale
        nd.inputs['Location'].default_value = loc
        nd.inputs['Rotation'].default_value = rot
        return nd.outputs[0]

    def noise(self, vec, scale, detail=2.0, rough=0.5, dim='3D', w=None, lac=2.0, dist=0.0):
        nd = self.t.nodes.new('ShaderNodeTexNoise')
        nd.noise_dimensions = dim
        if dim != '1D':
            self.set(nd, 'Vector', vec)
        if w is not None:
            self.set(nd, 'W', w)
        for k, v in (('Scale', scale), ('Detail', detail), ('Roughness', rough), ('Lacunarity', lac),
                     ('Distortion', dist)):
            self.set(nd, k, v)
        return nd.outputs['Fac']

    def voronoi(self, vec, scale, feature='F1', rand=1.0):
        nd = self.t.nodes.new('ShaderNodeTexVoronoi')
        nd.feature = feature
        self.set(nd, 'Vector', vec)
        self.set(nd, 'Scale', scale)
        self.set(nd, 'Randomness', rand)
        return nd

    def xyz(self):
        if self._xyz is None:
            self._xyz = self.t.nodes.new('ShaderNodeSeparateXYZ')
            self.t.links.new(self.Pobj, self._xyz.inputs[0])
        return self._xyz.outputs

    def bump(self, height, dist, strength=1.0, normal=None):
        nd = self.t.nodes.new('ShaderNodeBump')
        self.set(nd, 'Height', height)
        nd.inputs['Distance'].default_value = dist
        nd.inputs['Strength'].default_value = strength
        if normal is not None:
            self.set(nd, 'Normal', normal)
        return nd.outputs['Normal']

    def axis_tangent(self, v=(0, 1, 0)):
        nd = self.t.nodes.new('ShaderNodeVectorTransform')
        nd.vector_type = 'VECTOR'
        nd.convert_from, nd.convert_to = 'OBJECT', 'WORLD'
        nd.inputs[0].default_value = v
        return nd.outputs[0]

    def principled(self, **ins):
        nd = self.t.nodes.new('ShaderNodeBsdfPrincipled')
        nd.distribution = 'MULTI_GGX'
        for k, v in ins.items():
            key = k.replace('_', ' ')
            if isinstance(v, (tuple, list)) and len(v) == 3 and nd.inputs[key].type == 'RGBA':
                v = (*v, 1.0)
            self.set(nd, key, v)
        self.t.links.new(nd.outputs[0], self.out.inputs['Surface'])
        return nd


def seam_mask(g, seam, width_scale=1.0):
    """1 on a band along Y through the object-space point (x, z) of the weld seam, 0 elsewhere."""
    if not seam:
        return None, None
    x, y, z = g.xyz()
    dx = g.sub(x, seam[0] * MM)
    dz = g.sub(z, seam[1] * MM)
    dist = g.math('SQRT', g.add(g.mul(dx, dx), g.mul(dz, dz)))
    half = seam[2] * MM * 0.5 * width_scale
    band = g.remap(dist, half * 0.72, half, 1.0, 0.0, smooth=True)
    rim = g.mul(g.remap(dist, half * 0.55, half * 0.9, 0.0, 1.0, smooth=True),
                g.remap(dist, half * 0.9, half * 1.5, 1.0, 0.0, smooth=True))
    return band, rim


# ---------------------------------------------------------------------------------------------------------
# Materials. Colours are linear reflectance at normal incidence.
# ---------------------------------------------------------------------------------------------------------
def mat_cut(base=(0.56, 0.57, 0.585), center=(0.09, 0.16), rough=0.26, straight=False):
    """A sawn end: bare bright metal with the arcs of a circular saw (centre of the blade off the piece)."""
    g = G('cut')
    x, y, z = g.xyz()
    if straight:                                  # a sheared sheet edge: fine vertical drag lines
        r = g.add(x, g.mul(y, 1.0))
        tangent = g.axis_tangent((0, 0, 1))
    else:
        dx, dz = g.sub(x, center[0]), g.sub(z, center[1])
        r = g.math('SQRT', g.add(g.mul(dx, dx), g.mul(dz, dz)))
        tv = g.node('ShaderNodeCombineXYZ', X=g.mul(dz, -1.0), Y=0.0, Z=dx).outputs[0]
        tn = g.node('ShaderNodeVectorTransform', dict(vector_type='VECTOR', convert_from='OBJECT',
                                                      convert_to='WORLD'), Vector=tv).outputs[0]
        tangent = tn
    fine = g.noise(None, 2600.0, 3.0, 0.65, dim='1D', w=r)
    feed = g.noise(None, 420.0, 2.0, 0.5, dim='1D', w=r)
    grit = g.noise(g.P, 9000.0, 2.0, 0.6)
    arcs = g.add(g.mul(fine, 0.6), g.mul(feed, 0.4))
    rgh = g.add(g.remap(arcs, 0.25, 0.75, rough - 0.08, rough + 0.2), g.mul(g.sub(grit, 0.5), 0.06))
    col = g.mixc(g.remap(arcs, 0.3, 0.7, 0.0, 1.0), tuple(c * 0.72 for c in base), base)
    h = g.add(g.mul(fine, 0.7), g.mul(grit, 0.3))
    nrm = g.bump(g.add(h, g.mul(feed, 1.6)), 1.4e-5, 1.0)
    g.principled(Base_Color=col, Metallic=1.0, Roughness=rgh, Anisotropic=0.55, Anisotropic_Rotation=0.0,
                 Tangent=tangent, Normal=nrm)
    return g.mat


def mat_hr(seam=None, hammered=False, inner=False, crest=None, relief=''):
    """Hot-rolled steel with mill scale: blue-black oxide, semi-matte, rolling streaks along the length,
    a fine grain, a few breaks in the scale, a thin oil sheen."""
    g = G('hr')
    streak = g.noise(g.stretch(g.P, (1.0, 0.010, 1.0)), 1500.0, 2.0, 0.6)
    wide = g.noise(g.stretch(g.P, (1.0, 0.008, 1.0), loc=(3.1, 0.7, 1.3)), 260.0, 2.0, 0.5)
    mottle = g.noise(g.stretch(g.P, (1.0, 0.4, 1.0), loc=(0.3, 2.0, 5.0)), 24.0, 3.0, 0.6)
    grain = g.noise(g.P, 3400.0, 2.0, 0.65)
    speck_n = g.noise(g.stretch(g.P, (1.0, 0.5, 1.0), loc=(5.0, 3.0, 1.0)), 1100.0, 1.0, 0.5)
    speck = g.remap(speck_n, 0.66, 0.72, 0.0, 1.0, smooth=True)
    brk_n = g.noise(g.stretch(g.P, (1.0, 0.3, 1.0), loc=(7.0, 1.0, 2.0)), 70.0, 4.0, 0.62)
    brk = g.remap(brk_n, 0.705, 0.725, 0.0, 1.0, smooth=True)
    tone = g.add(g.mul(mottle, 0.6), g.add(g.mul(wide, 0.25), g.mul(streak, 0.15)))
    tone = g.remap(tone, 0.34, 0.66, 0.0, 1.0, smooth=True)
    col = g.mixc(tone, (0.040, 0.044, 0.052), (0.076, 0.081, 0.092))
    col = g.mixc(g.mul(speck, 0.35), col, (0.026, 0.028, 0.033))
    col = g.mixc(g.mul(brk, 0.85), col, (0.17, 0.155, 0.14))
    rgh = g.add(0.29, g.add(g.mul(streak, 0.05), g.add(g.mul(wide, 0.04), g.add(g.mul(mottle, 0.07),
                                                                                  g.mul(grain, 0.06)))))
    rgh = g.add(rgh, g.mul(speck, 0.06))
    rgh = g.mixf(brk, rgh, 0.58)
    coat = g.mixf(brk, 0.5, 0.05)
    h = g.add(g.add(g.mul(grain, 1.0), g.mul(speck, -0.3)), g.add(g.mul(streak, 0.22), g.mul(wide, 0.35)))
    h = g.sub(h, g.mul(brk, 2.2))
    band_m, rim_m = seam_mask(g, seam)
    if band_m is not None:                        # scarfed weld: a smooth, slightly blue strip
        col = g.mixc(g.mul(band_m, 0.35), col, (0.045, 0.055, 0.080))
        col = g.mixc(g.mul(rim_m, 0.22), col, (0.11, 0.098, 0.084))
        rgh = g.sub(rgh, g.mul(band_m, 0.05))
        h = g.mixf(g.mul(band_m, 0.6), h, 0.5)
    if crest:                                     # the tops of a chequer pattern: scale worn thin, brighter
        x, y, z = g.xyz()
        cm = g.remap(z, crest[0], crest[1], 0.0, 1.0, smooth=True)
        col = g.mixc(g.mul(cm, 0.8), col, (0.15, 0.155, 0.165))
        rgh = g.sub(rgh, g.mul(cm, 0.07))
    if hammered:
        v = g.voronoi(g.P, 85.0, 'SMOOTH_F1')
        h = g.add(h, g.mul(g.remap(v.outputs['Distance'], 0.0, 0.75, 0.0, 1.0, smooth=True), 30.0))
    if relief:                                    # an embossed pattern rolled into the tube: raised lines
        x, y, z = g.xyz()
        if relief == 'wood':                      # nested long arches, like the grain of a plank
            ym = g.sub(g.math('MODULO', g.add(y, 0.05), 0.26), 0.13)
            wob = g.sub(g.noise(g.stretch(g.P, (1.0, 0.15, 1.0)), 45.0, 2.0, 0.5), 0.5)
            ys = g.mul(ym, 0.10)
            e = g.add(g.math('SQRT', g.add(g.mul(x, x), g.mul(ys, ys))), g.mul(wob, 0.010))
            ph = g.math('FRACT', g.mul(e, 230.0))
            ridge = g.remap(g.math('ABSOLUTE', g.sub(ph, 0.5)), 0.0, 0.12, 1.0, 0.0, smooth=True)
        else:                                     # 'flower': five-petal rosettes between two wavy vines
            pit = 0.075
            ym = g.sub(g.math('MODULO', g.add(y, 0.02), pit), pit / 2)
            r = g.math('SQRT', g.add(g.mul(x, x), g.mul(ym, ym)))
            th = g.math('ARCTAN2', ym, x)
            pet = g.math('POWER', g.math('ABSOLUTE', g.math('COSINE', g.mul(th, 2.5))), 0.7)
            rp = g.mul(g.add(0.5, g.mul(pet, 0.5)), 0.0150)
            outline = g.remap(g.math('ABSOLUTE', g.sub(r, rp)), 0.0, 0.0011, 1.0, 0.0, smooth=True)
            eye = g.remap(g.math('ABSOLUTE', g.sub(r, 0.0034)), 0.0, 0.0009, 1.0, 0.0, smooth=True)
            wave = g.add(0.0185, g.mul(g.math('SINE', g.mul(y, 2 * PI / pit)), 0.0028))
            vine = g.remap(g.math('ABSOLUTE', g.sub(g.math('ABSOLUTE', x), wave)), 0.0, 0.0008, 1.0, 0.0,
                           smooth=True)
            ridge = g.math('MAXIMUM', g.math('MAXIMUM', outline, eye), vine)
        h = g.add(h, g.mul(ridge, 20.0))
        rgh = g.sub(rgh, g.mul(ridge, 0.05))
        col = g.mixc(g.mul(ridge, 0.5), col, (0.12, 0.125, 0.135))
    nrm = g.bump(h, 1.6e-5, 1.0)
    # mill scale is an iron oxide, a dark conductor with a trace of diffuse: mostly metal, so the faces are
    # drawn by what they mirror, and a little dielectric, so shaded faces keep their form
    if inner:                                     # the bore: no oil, rougher scale, more of a dull oxide
        dull = g.mixc(0.5, col, (0.20, 0.185, 0.17))
        g.principled(Base_Color=dull, Metallic=0.0, Roughness=g.add(rgh, 0.35), Specular_IOR_Level=0.3,
                     Normal=nrm)
        return g.mat
    g.principled(Base_Color=col, Metallic=0.9, Roughness=rgh, Coat_Weight=coat, Coat_Roughness=0.13,
                 Coat_IOR=1.5, Normal=nrm)
    return g.mat


def mat_drawn(name, base, rough, aniso=0.0, line=0.1, lines='drawn', coat=0.0, seam=None, tone=0.0,
              tone_col=None, bump=4e-6):
    """A drawn, ground, brushed or extruded metal: fine lines along the length.
    lines = 'drawn' (long random lines), 'die' (constant along the length, an extrusion) or 'none'."""
    g = G(name)
    if lines == 'die':
        fine = g.noise(g.stretch(g.P, (1.0, 0.0, 1.0)), 2400.0, 2.0, 0.6)
        wide = g.noise(g.stretch(g.P, (1.0, 0.0006, 1.0), loc=(1, 0, 2)), 380.0, 2.0, 0.5)
    else:
        fine = g.noise(g.stretch(g.P, (1.0, 0.004, 1.0)), 3400.0, 3.0, 0.7)
        wide = g.noise(g.stretch(g.P, (1.0, 0.003, 1.0), loc=(1, 0, 2)), 520.0, 2.0, 0.5)
    hair = g.noise(g.stretch(g.P, (1.0, 0.02, 1.0), loc=(4, 1, 0)), 9000.0, 2.0, 0.6)
    ln = g.add(g.mul(fine, 0.5), g.add(g.mul(wide, 0.3), g.mul(hair, 0.2)))
    k = 0.0 if lines == 'none' else 1.0
    rgh = g.add(rough, g.mul(g.sub(ln, 0.5), line * 2.0 * k))
    col = base
    if tone > 0:
        tn = g.noise(g.stretch(g.P, (1.0, 0.25, 1.0), loc=(2, 5, 1)), 22.0, 4.0, 0.6)
        col = g.mixc(g.mul(g.remap(tn, 0.35, 0.7, 0.0, 1.0, smooth=True), tone), base,
                     tone_col or tuple(c * 0.8 for c in base))
    band_m, rim_m = seam_mask(g, seam)
    if band_m is not None:                        # polished weld line on a welded stainless tube
        rgh = g.mixf(band_m, rgh, rough * 0.7)
        col = g.mixc(g.mul(rim_m, 0.25), col, tuple(c * 0.75 for c in base))
    nrm = g.bump(g.add(g.mul(fine, 0.6), g.mul(hair, 0.4)), bump * k if k else 1e-9, 1.0)
    ins = dict(Base_Color=col, Metallic=1.0, Roughness=rgh, Normal=nrm)
    if aniso > 0:
        ins.update(Anisotropic=aniso, Anisotropic_Rotation=0.0, Tangent=g.axis_tangent((0, 1, 0)))
    if coat > 0:
        ins.update(Coat_Weight=coat, Coat_Roughness=0.1, Coat_IOR=1.45)
    g.principled(**ins)
    return g.mat


def mat_galv(seam=None):
    """Hot-dip galvanised: zinc spangle. Each crystal reflects a little differently (its own anisotropy angle,
    a slightly tilted normal, a slightly different roughness); the colour stays one zinc grey, so the
    spangle shows in the reflections and never as blotches of brightness."""
    g = G('galv')
    warp = g.node('ShaderNodeTexNoise', dict(noise_dimensions='3D'), Vector=g.P, Scale=260.0, Detail=2.0,
                  Roughness=0.55).outputs['Color']
    pw = g.node('ShaderNodeVectorMath', dict(operation='ADD'), Vector=g.stretch(g.P, (1.0, 0.7, 1.0)),
                Vector_001=g.node('ShaderNodeVectorMath', dict(operation='SCALE'), Vector=warp,
                                  Scale=0.0045).outputs[0]).outputs[0]
    vor = g.voronoi(pw, 125.0, 'F1')
    cellc = vor.outputs['Color']
    sep = g.node('ShaderNodeSeparateColor', Color=cellc)
    r1, r2, r3 = sep.outputs[0], sep.outputs[1], sep.outputs[2]
    edge = g.voronoi(pw, 125.0, 'DISTANCE_TO_EDGE').outputs['Distance']
    edge_m = g.remap(edge, 0.0, 0.03, 1.0, 0.0, smooth=True)
    micro = g.noise(g.P, 3000.0, 2.0, 0.6)
    fern = g.noise(g.stretch(g.P, (1.0, 0.25, 1.0)), 900.0, 2.0, 0.6)
    drip = g.noise(g.stretch(g.P, (1.0, 0.05, 1.0), loc=(2, 1, 4)), 140.0, 2.0, 0.5)
    rgh = g.add(g.add(0.30, g.mul(r2, 0.07)), g.add(g.mul(edge_m, 0.04), g.mul(g.sub(fern, 0.5), 0.06)))
    col = g.mixc(g.mul(r3, 0.35), (0.60, 0.625, 0.65), (0.66, 0.68, 0.70))
    tilt = g.node('ShaderNodeVectorMath', dict(operation='SCALE'),
                  Vector=g.node('ShaderNodeVectorMath', dict(operation='SUBTRACT'), Vector=cellc,
                                Vector_001=(0.5, 0.5, 0.5)).outputs[0], Scale=0.03).outputs[0]
    base_n = g.bump(g.add(g.add(g.mul(micro, 0.5), g.mul(fern, 0.5)), g.mul(drip, 4.0)), 4e-6, 1.0)
    nrm = g.node('ShaderNodeVectorMath', dict(operation='NORMALIZE'),
                 Vector=g.node('ShaderNodeVectorMath', dict(operation='ADD'), Vector=base_n,
                               Vector_001=tilt).outputs[0]).outputs[0]
    aniso = 0.3
    band_m, rim_m = seam_mask(g, seam, 2.2)
    if band_m is not None:                        # re-metallised weld: a dull grey stripe without spangle
        rgh = g.mixf(band_m, rgh, 0.46)
        col = g.mixc(g.mul(band_m, 0.5), col, (0.50, 0.52, 0.54))
        aniso = g.mixf(band_m, 0.3, 0.0)
    g.principled(Base_Color=col, Metallic=1.0, Roughness=rgh, Anisotropic=aniso, Anisotropic_Rotation=r1,
                 Tangent=g.axis_tangent((0, 1, 0)), Normal=nrm)
    return g.mat


def mat_lead():
    g = G('lead')
    mottle = g.noise(g.P, 30.0, 4.0, 0.65)
    micro = g.noise(g.P, 2500.0, 3.0, 0.7)
    dent = g.noise(g.P, 120.0, 2.0, 0.5)
    col = g.mixc(g.remap(mottle, 0.3, 0.7, 0.0, 1.0, smooth=True), (0.30, 0.31, 0.335), (0.40, 0.41, 0.43))
    rgh = g.add(0.5, g.mul(mottle, 0.14))
    nrm = g.bump(g.add(g.mul(micro, 0.3), g.mul(dent, 6.0)), 1.5e-5, 1.0)
    g.principled(Base_Color=col, Metallic=1.0, Roughness=rgh, Normal=nrm)
    return g.mat


def mat_pvc():
    """Pre-painted (PVC or polyester coated) sheet: an off-white satin paint."""
    g = G('pvc')
    peel = g.noise(g.P, 1800.0, 2.0, 0.5)
    nrm = g.bump(peel, 6e-6, 1.0)
    g.principled(Base_Color=(0.80, 0.79, 0.74), Metallic=0.0, Roughness=0.42, Coat_Weight=0.3,
                 Coat_Roughness=0.25, Normal=nrm)
    return g.mat


BARE = {'hr': (0.56, 0.57, 0.585), 'cr': (0.58, 0.59, 0.60), 'galv': (0.56, 0.57, 0.585),
        'wrought': (0.56, 0.57, 0.585), 'inox': (0.63, 0.63, 0.63), 'alu': (0.90, 0.91, 0.92),
        'copper': (0.945, 0.560, 0.430), 'brass': (0.887, 0.745, 0.380), 'bronze': (0.78, 0.545, 0.32),
        'lead': (0.62, 0.63, 0.66)}


# how much harder the lights that draw the rolled surface work for a dark metal (the cut end keeps its own)
RIG_GAIN = {'hr': 1.0, 'wrought': 1.0, 'lead': 1.0, 'copper': 0.7, 'brass': 0.7, 'bronze': 0.8}
# the light from the camera: strong enough to open the bore of a dark tube, weak on a bright mirror
EYE_GAIN = {'hr': 1.0, 'wrought': 1.0, 'lead': 0.6}


def make_materials(mat, finish, seam, sheet=False, relief=''):
    """-> (surface material, cut material, material of the bore)"""
    inner = None
    if mat == 'hr':
        side = mat_hr(seam, relief=relief)
        inner = mat_hr(inner=True)
    elif mat == 'wrought':
        side = mat_hr(seam, hammered=not relief, relief=relief)
        inner = mat_hr(inner=True)
    elif mat == 'cr':
        side = mat_drawn('cr', (0.50, 0.51, 0.525), 0.30, aniso=0.25, line=0.05, coat=0.2, seam=seam, tone=0.25)
    elif mat == 'galv':
        side = mat_galv(seam)
    elif mat == 'inox':
        if finish == 'polished':
            side = mat_drawn('inox_polished', (0.66, 0.66, 0.655), 0.035, lines='none', seam=seam)
        else:
            side = mat_drawn('inox_brushed', (0.62, 0.62, 0.615), 0.20, aniso=0.82, line=0.07, seam=seam,
                             bump=5e-6)
    elif mat == 'alu':
        side = mat_drawn('alu', (0.90, 0.91, 0.92), 0.34, aniso=0.4, line=0.06, lines='die', bump=3e-6)
    elif mat == 'copper':
        side = mat_drawn('copper', BARE['copper'], 0.16, aniso=0.35, line=0.045, tone=0.3,
                         tone_col=(0.88, 0.45, 0.33), bump=2.5e-6)
    elif mat == 'brass':
        side = mat_drawn('brass', BARE['brass'], 0.17, aniso=0.35, line=0.045, tone=0.2,
                         tone_col=(0.84, 0.70, 0.36), bump=2.5e-6)
    elif mat == 'bronze':
        side = mat_drawn('bronze', BARE['bronze'], 0.24, aniso=0.3, line=0.06, tone=0.3,
                         tone_col=(0.70, 0.48, 0.28), bump=3e-6)
    elif mat == 'lead':
        side = mat_lead()
    elif mat == 'pvc':
        side = mat_pvc()
    else:
        raise SystemExit('unknown material ' + mat)
    soft = mat in ('alu', 'copper', 'brass', 'bronze', 'lead')
    cut = mat_cut(BARE.get(mat, BARE['hr']), rough=0.24 if soft else 0.31, straight=sheet)
    return side, cut, inner or side


# ---------------------------------------------------------------------------------------------------------
# Rigs. Every size and position is in units of S (the radius of the piece's bounding sphere) around C.
# ---------------------------------------------------------------------------------------------------------
def emitter(name, size, pos, target, strength, color=(1, 1, 1), hot=0.0, camera=False, roll=0.0, only=None):
    """A softbox: a plane that emits. hot > 0 gives it a brighter centre, like a real diffuser."""
    me = bpy.data.meshes.new(name)
    sx, sy = size[0] / 2, size[1] / 2
    me.from_pydata([(-sx, -sy, 0), (sx, -sy, 0), (sx, sy, 0), (-sx, sy, 0)], [], [(0, 1, 2, 3)])
    me.uv_layers.new(name='uv')
    for loop, uv in zip(me.uv_layers[0].data, ((0, 0), (1, 0), (1, 1), (0, 1))):
        loop.uv = uv
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    ob.location = pos
    d = (Vector(target) - Vector(pos)).normalized()
    ob.rotation_euler = d.to_track_quat('Z', 'Y').to_euler()
    if roll:
        ob.rotation_euler.rotate_axis('Z', roll)
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    t = m.node_tree
    t.nodes.clear()
    out = t.nodes.new('ShaderNodeOutputMaterial')
    em = t.nodes.new('ShaderNodeEmission')
    em.inputs['Color'].default_value = (*color, 1)
    em.inputs['Strength'].default_value = strength
    if hot > 0:
        tc = t.nodes.new('ShaderNodeTexCoord')
        mp = t.nodes.new('ShaderNodeMapping')
        mp.inputs['Location'].default_value = (-0.5, -0.5, 0)
        t.links.new(tc.outputs['UV'], mp.inputs['Vector'])
        ln = t.nodes.new('ShaderNodeVectorMath')
        ln.operation = 'LENGTH'
        t.links.new(mp.outputs[0], ln.inputs[0])
        mr = t.nodes.new('ShaderNodeMapRange')
        mr.interpolation_type = 'SMOOTHERSTEP'
        mr.inputs['From Min'].default_value = 0.0
        mr.inputs['From Max'].default_value = 0.72
        mr.inputs['To Min'].default_value = strength
        mr.inputs['To Max'].default_value = strength * (1 - hot)
        t.links.new(ln.outputs['Value'], mr.inputs['Value'])
        t.links.new(mr.outputs[0], em.inputs['Strength'])
    geo = t.nodes.new('ShaderNodeNewGeometry')          # light leaves the front only
    mix = t.nodes.new('ShaderNodeMixShader')
    tr = t.nodes.new('ShaderNodeBsdfTransparent')
    t.links.new(geo.outputs['Backfacing'], mix.inputs[0])
    t.links.new(em.outputs[0], mix.inputs[1])
    t.links.new(tr.outputs[0], mix.inputs[2])
    t.links.new(mix.outputs[0], out.inputs['Surface'])
    me.materials.append(m)
    ob.visible_camera = camera
    ob.visible_shadow = False
    if only is not None:                          # a flagged light: it reaches the piece and nothing else
        ob.light_linking.receiver_collection = only
    return ob


def flag(name, size, pos, target):
    """A black card: takes light away, draws the dark side of a reflection."""
    ob = emitter(name, size, pos, target, 0.0)
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes['Principled BSDF']
    b.inputs['Base Color'].default_value = (0.004, 0.004, 0.004, 1)
    b.inputs['Roughness'].default_value = 0.9
    ob.data.materials.clear()
    ob.data.materials.append(m)
    ob.visible_shadow = True
    return ob


def plain(name, color, rough=0.8, spec=0.3):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes['Principled BSDF']
    b.inputs['Base Color'].default_value = (*color, 1)
    b.inputs['Roughness'].default_value = rough
    b.inputs['Specular IOR Level'].default_value = spec
    return m


def cyclorama(S, C, color, rough=0.85, spec=0.25, wall=True, half=60.0, back=22.0, sweep=9.0, name='cyc'):
    """Seamless floor that sweeps up into a back wall (the sweep runs along X, the wall stands at +Y)."""
    prof = [(-half, 0.0)]
    y0 = back
    if wall:
        n = 24
        prof.append((y0, 0.0))
        for k in range(1, n + 1):
            a = (PI / 2) * k / n
            prof.append((y0 + sweep * math.sin(a), sweep * (1 - math.cos(a))))
        prof.append((y0 + sweep, half))
    else:
        prof.append((half, 0.0))
    verts, faces = [], []
    for (y, z) in prof:
        verts.append((C.x - half * S, C.y + y * S, z * S))
        verts.append((C.x + half * S, C.y + y * S, z * S))
    for k in range(len(prof) - 1):
        faces.append((2 * k, 2 * k + 1, 2 * k + 3, 2 * k + 2))
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.polygons.foreach_set('use_smooth', [True] * len(faces))
    me.update()
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    me.materials.append(plain(name, color, rough, spec))
    return ob


def set_world(color, strength):
    w = bpy.data.worlds.new('world')
    w.use_nodes = True
    bg = w.node_tree.nodes['Background']
    bg.inputs['Color'].default_value = (*color, 1)
    bg.inputs['Strength'].default_value = strength
    bpy.context.scene.world = w


def build_rig(rig, S, C, view, pieces, box, gain=1.0, eye_gain=1.0, top_gain=1.0, top_wide=0.0):
    """S: radius of the lit part of the piece, C: its centre, view: unit vector from the piece to the camera,
    box: (w, L, h) of the piece in metres. Strips run parallel to the bar. Lights marked `only` are flagged
    off the floor (light linking): they draw the metal and leave the contact shadow to the key.

    A flat face mirrors one direction, so the lights that draw the faces are placed by the mirror rule:
    the top face mirrors a strip that sits as far to the left as the camera sits to the right; the side face
    and the cut end mirror the floor next to them, which is where their bounce cards lie."""
    w, _, h = box

    def P(x, y, z):                               # a point in units of S around the piece
        return (C.x + x * S, C.y + y * S, C.z + z * S)

    def L(*a, **k):
        return emitter(a[0], (a[1][0] * S, a[1][1] * S), P(*a[2]), P(*a[3]), *a[4:], **k)

    def flat(name, size, x, y, strength, **k):    # a card lying on the floor, facing up (metres)
        return emitter(name, size, (x, y, 0.004 * S), (x, y, 1.0), strength, **k)

    only = bpy.data.collections.new('piece_only')
    for ob in pieces:
        only.objects.link(ob)
    eye = (view.x * 7.0, view.y * 7.0, view.z * 7.0 + 0.8)
    hn = math.hypot(view.x, view.y) or 1.0
    hx, hy = view.x / hn, view.y / hn             # horizontal part of the view direction
    slope = hn / max(view.z, 0.15)                # how far a face mirrors, per unit of its height
    # the strip the top face mirrors: zs above the top, as far left as the camera is right
    zs = 3.4 * S
    top_x = -(view.x / max(view.z, 0.15)) * zs
    tw = max(0.95 * w, 0.12 * S) + top_wide       # about 40 % of the face is the line, the rest stays dark
    top_off = -0.12 * w
    top_pos = (top_x + top_off, C.y + 1.2 * S, h + zs)
    # the floor the cut end mirrors (in front of it) and the floor the side face mirrors (beside it)
    # (its centre is where the top left of the end looks, so the end runs from bright to dark across itself)
    ce = (-hx * slope * h * 1.05 + hy * 0.3 * w, hy * slope * h * 1.05 + hx * 0.3 * w)
    end_r = max(slope * h * 0.95, 0.75 * w)
    side_x = w / 2 + (view.x / max(view.z, 0.15)) * h * 0.95
    side_r = (view.x / max(view.z, 0.15)) * h * 1.2
    if rig in ('grey', 'paper', 'stage'):
        paper = rig in ('paper', 'stage')         # paper: page #f7f7f4; stage: the viewer's #f4f4f1
        floor_col = {'paper': (0.925, 0.925, 0.902), 'stage': (0.905, 0.905, 0.880)}.get(rig, (0.60, 0.60, 0.61))
        fl = cyclorama(S, Vector((C.x, C.y, 0)), floor_col, wall=not paper, name='floor')
        if paper:
            fl.is_shadow_catcher = True
            wall = cyclorama(S, Vector((C.x, C.y, 0)), (0.60, 0.60, 0.61), wall=True, name='wall')
            wall.location.z = -0.002 * S
            wall.visible_camera = False
            wall.visible_shadow = False
            wall.visible_diffuse = False
        set_world((0.55, 0.56, 0.58), 0.12)
        # large overhead softbox, behind and to the left: the top faces, the sweep and the contact shadow,
        # which falls toward the camera
        L('key', (6.0, 6.0), (-2.6, 4.6, 6.0), (0.0, 0.3, 0.0), 16.0, hot=0.55)
        # one long strip, parallel to the bar, high on the camera side: the line along the near top edge
        L('strip', (0.22, 11.0), (2.9, 1.0, 5.0), (0.0, 1.0, 0.0), 110.0 * gain, only=only)
        # and the strip the top face mirrors: a soft line of light along the top
        emitter('top_line', (tw, 14.0 * S), top_pos, (top_off, C.y + 1.2 * S, h), 5.0 * gain * top_gain, only=only)
        # soft fill from the front left for the cut end, and a weak one from the camera into the bore
        L('fill', (5.0, 3.0), (-4.5, -6.5, 2.2), (0.0, 0.0, 0.0), 1.3, hot=0.5)
        L('eye', (2.5, 2.5), eye, (0.0, 0.0, 0.0), 4.0 * eye_gain, hot=0.6, only=only)
    elif rig == 'dark':
        cyclorama(S, Vector((C.x, C.y, 0)), (0.010, 0.010, 0.011), rough=0.16, spec=0.5, wall=False, name='floor')
        set_world((0.0, 0.0, 0.0), 0.0)
        # a softbox low behind the piece, where the top faces mirror it: a faint sheet of light on top
        bx, by, bz = -hx * 6.5, -hy * 6.5, max(view.z, 0.2) * 6.5 + 0.6
        L('back', (4.6, 2.4), (bx, by, bz), (0.0, 0.0, 0.0), 0.4 * gain, hot=1.0, only=only)
        # strips parallel to the bar: the lines along the edges and along the top
        emitter('top_line', (tw, 14.0 * S), top_pos, (top_off, C.y + 1.2 * S, h), 6.0 * gain * top_gain, only=only)
        L('edge', (0.30, 12.0), (3.4, 1.0, 2.6), (0.0, 1.0, 0.0), 45.0 * gain, only=only)
        L('top', (0.5, 12.0), (-0.6, 1.5, 5.2), (0.0, 1.5, 0.0), 20.0 * gain, only=only)
        L('rim', (0.4, 12.0), (-3.8, 2.0, 1.4), (0.0, 2.0, 0.3), 20.0 * gain, only=only)
        # bounce cards on the floor: in front, where the cut end mirrors it, and beside, for the side face
        flat('card_end', (2 * end_r, 2 * end_r), ce[0], ce[1], 1.9, hot=1.0, only=only)
        flat('card_side', (2 * side_r, 16.0 * S), side_x, C.y, 0.3 * gain, hot=1.0, only=only)
        L('eye', (2.5, 2.5), eye, (0.0, 0.0, 0.0), 1.2 * eye_gain, hot=0.6, only=only)
        # the floor sees one soft light, so the piece stands on something
        L('floor_light', (5.0, 5.0), (-1.5, 2.0, 7.0), (0.0, 0.5, 0.0), 1.0, hot=0.6)
    else:
        raise SystemExit('unknown rig ' + rig)


# ---------------------------------------------------------------------------------------------------------
# Camera
# ---------------------------------------------------------------------------------------------------------
def fstop_for(focal_mm, focus_m, far_m, blur_frac, sensor_mm=36.0):
    """Aperture that gives a blur circle of blur_frac x frame width at distance far_m (the Cycles lens:
    an aperture of diameter f / N focused at focus_m)."""
    f = focal_mm * MM
    if abs(far_m - focus_m) < 1e-6:
        return 16.0
    n = f * f * abs(far_m - focus_m) / (blur_frac * sensor_mm * MM * focus_m * far_m)
    return max(1.4, min(128.0, n))


def build_camera(preset, dims, res, lens=None, az_deg=None, el_deg=None, sheet=False):
    """dims = (w, L, h) of the piece in metres; the piece spans x -w/2..w/2, y 0..L, z 0..h."""
    w, L, h = dims
    scene = bpy.context.scene
    cam_d = bpy.data.cameras.new('cam')
    cam = bpy.data.objects.new('cam', cam_d)
    scene.collection.objects.link(cam)
    scene.camera = cam
    cam_d.sensor_width = 36.0
    cam_d.sensor_fit = 'HORIZONTAL'
    sec = max(w, h)
    P = dict(hero=dict(lens=100, az=38, el=19, margin=1.12, blur=0.0055),
             macro=dict(lens=100, az=33, el=22, margin=1.0, blur=0.016),
             poster=dict(lens=85, az=40, el=24, margin=1.16, blur=0.0022),
             stage=dict(lens=85, az=40, el=24, margin=1.48, blur=0.0016),
             ref=dict(lens=100, az=38, el=22, margin=1.42, blur=0.0016),
             refclose=dict(lens=100, az=33, el=22, margin=1.0, blur=0.009))[preset]
    if sheet and preset == 'hero':                # a plate: the near corner, the rest runs out of the frame
        P = dict(P, az=40, el=27, margin=1.0, blur=0.0075)
    cam_d.lens = lens or P['lens']
    az, el = math.radians(az_deg if az_deg is not None else P['az']), math.radians(
        el_deg if el_deg is not None else P['el'])
    view = Vector((math.sin(az) * math.cos(el), -math.cos(az) * math.cos(el), math.sin(el)))   # piece -> camera
    cam.rotation_euler = (-view).to_track_quat('-Z', 'Y').to_euler()
    cam_d.clip_start, cam_d.clip_end = 0.01, 500.0
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    if preset in ('macro', 'refclose'):
        # the near end fills the frame and runs out of it: frame a box around the end and the first stretch
        k = 0.62
        pts = []
        for x in (-w / 2 * k, w / 2):
            for z in (h * (1 - k) if h > w * 0.5 else 0.0, h):
                for y in (0.0, sec * 0.55):
                    pts.append((x, y, z))
        focus_pt = Vector((w / 2 * 0.55, 0.0, h * 0.8))
        far_pt = Vector((w / 2, sec * 3.0, h))
    elif sheet and preset == 'hero':
        pts = [(-w * 0.22, 0.0, 0.0), (w / 2, 0.0, 0.0), (w / 2, L * 0.36, h), (-w * 0.22, L * 0.36, h)]
        focus_pt = Vector((w * 0.25, L * 0.06, h))
        far_pt = Vector((0.0, L * 0.45, h))
    else:
        pts = [(x, y, z) for x in (-w / 2, w / 2) for y in (0.0, L) for z in (0.0, h)]
        focus_pt = Vector((w / 2 * 0.6, 0.0 if preset == 'hero' else L * (0.12 if preset == 'stage' else 0.3),
                           h * 0.75))
        far_pt = Vector((0.0, L, h))
    flat = [c for p in pts for c in p]
    loc, _ = cam.camera_fit_coords(dg, flat)
    loc = Vector(loc)
    # back off along the view axis for the margin
    ctr = Vector((sum(p[0] for p in pts), sum(p[1] for p in pts), sum(p[2] for p in pts))) / len(pts)
    dist = (loc - ctr).dot(view)
    cam.location = loc + view * dist * (P['margin'] - 1.0)
    bpy.context.view_layer.update()
    fwd = -view
    focus = (focus_pt - cam.location).dot(fwd)
    far = (far_pt - cam.location).dot(fwd)
    cam_d.dof.use_dof = True
    cam_d.dof.focus_distance = focus
    cam_d.dof.aperture_fstop = fstop_for(cam_d.lens, focus, far, P['blur'])
    cam_d.dof.aperture_blades = 0
    return cam, view, dict(focus=focus, fstop=cam_d.dof.aperture_fstop, dist=(cam.location - ctr).length)


# ---------------------------------------------------------------------------------------------------------
# Render settings, grade
# ---------------------------------------------------------------------------------------------------------
def setup_render(args, res, alpha):
    sc = bpy.context.scene
    sc.render.engine = 'CYCLES'
    cy = sc.cycles
    cy.device = 'CPU'
    cy.samples = args.samples
    cy.use_adaptive_sampling = True
    cy.adaptive_threshold = args.noise
    cy.adaptive_min_samples = max(16, args.samples // 5)
    cy.time_limit = args.time_limit
    cy.use_denoising = True
    cy.denoiser = 'OPENIMAGEDENOISE'
    cy.denoising_input_passes = 'RGB_ALBEDO_NORMAL'
    cy.denoising_prefilter = 'ACCURATE'
    try:
        cy.denoising_quality = 'HIGH'
    except Exception:
        pass
    cy.max_bounces = 6
    cy.diffuse_bounces = 2
    cy.glossy_bounces = 5
    cy.transmission_bounces = 2
    cy.transparent_max_bounces = 6
    cy.caustics_reflective = False
    cy.caustics_refractive = False
    cy.blur_glossy = 0.4
    cy.sample_clamp_indirect = 10.0
    cy.pixel_filter_type = 'BLACKMAN_HARRIS'
    cy.filter_width = 1.5
    cy.use_light_tree = True
    cy.seed = args.seed
    sc.render.threads_mode = 'FIXED'
    sc.render.threads = args.threads
    sc.render.resolution_x, sc.render.resolution_y = res
    sc.render.resolution_percentage = 100
    sc.render.film_transparent = alpha
    sc.render.use_persistent_data = False
    sc.display_settings.display_device = 'sRGB'
    sc.view_settings.view_transform = 'AgX'
    sc.view_settings.look = args.look
    sc.view_settings.exposure = args.exposure
    sc.view_settings.gamma = 1.0
    sc.render.dither_intensity = 1.0
    ext = os.path.splitext(args.out)[1].lower()
    im = sc.render.image_settings
    if ext in ('.jpg', '.jpeg'):
        im.file_format = 'JPEG'
        im.quality = 90
        im.color_mode = 'RGB'
    elif ext == '.webp':
        im.file_format = 'WEBP'
        im.quality = 82
        im.color_mode = 'RGBA' if alpha else 'RGB'
    else:
        im.file_format = 'PNG'
        im.color_mode = 'RGBA' if alpha else 'RGB'
        im.color_depth = '8'
        im.compression = 60
    sc.render.filepath = args.out
    sc.render.use_file_extension = False


def setup_grain(amount, glare):
    """A trace of film grain (multiplicative, so blacks stay clean) and a little bloom on the highlights."""
    sc = bpy.context.scene
    sc.use_nodes = True
    t = sc.node_tree
    t.nodes.clear()
    rl = t.nodes.new('CompositorNodeRLayers')
    comp = t.nodes.new('CompositorNodeComposite')
    last = rl.outputs['Image']
    if glare > 0:
        gl = t.nodes.new('CompositorNodeGlare')
        try:
            gl.glare_type = 'BLOOM'
            gl.quality = 'HIGH'
            gl.inputs['Threshold'].default_value = 3.0
            gl.inputs['Strength'].default_value = glare
            gl.inputs['Size'].default_value = 0.35
        except Exception:
            pass
        t.links.new(last, gl.inputs['Image'])
        last = gl.outputs['Image']
    if amount > 0:
        tex = bpy.data.textures.new('grain', 'NOISE')
        tn = t.nodes.new('CompositorNodeTexture')
        tn.texture = tex
        mr = t.nodes.new('CompositorNodeMapRange')
        mr.inputs['From Min'].default_value = 0.0
        mr.inputs['From Max'].default_value = 1.0
        mr.inputs['To Min'].default_value = 1.0 - amount
        mr.inputs['To Max'].default_value = 1.0 + amount
        t.links.new(tn.outputs['Value'], mr.inputs['Value'])
        mx = t.nodes.new('CompositorNodeMixRGB')
        mx.blend_type = 'MULTIPLY'
        mx.inputs[0].default_value = 1.0
        t.links.new(last, mx.inputs[1])
        t.links.new(mr.outputs[0], mx.inputs[2])
        last = mx.outputs[0]
    t.links.new(last, comp.inputs['Image'])


# ---------------------------------------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------------------------------------
SHEETS = ('sheet', 'chequer', 'trapezoid', 'cupal')


def default_length(shape, prof, cam):
    sec = max(prof['w'], prof['h'])
    if shape in SHEETS:
        return prof['w'] * 0.7
    return sec * (2.3 if cam in ('poster', 'stage') else 6.0)


def make_piece(shape, dims, length, mat, finish='brushed', pattern='', bevel=0.3, relief='', cam='hero', weld_mode=None):
    """Build one product at the origin: x centred, y from 0 (the near end) to L, resting on z = 0.
    -> (objects, (w, L, h) in metres, the section's profile)."""
    sheet = shape in SHEETS
    if shape == 'cupal':                          # copper-clad aluminium: 30 % copper on 70 % aluminium
        t, wd = dims[0], (dims[1] if len(dims) > 1 else 100.0)
        tc = t * 0.3
        length = length or wd * 0.7
        pieces = []
        for name, m, th, z0 in (('piece_alu', 'alu', t - tc, 0.0), ('piece_cu', 'copper', tc, t - tc)):
            pr = build_profile('sheet', [th, wd], m)
            ob = build_bar(name, pr, length, bevel_mm=bevel, cut_sides=True)
            ob.location.z = z0 * MM
            for mm_ in make_materials(m, finish, None, sheet=True):
                ob.data.materials.append(mm_)
            pieces.append(ob)
        prof = dict(w=wd, h=t, minT=t, seam=None, info={})
        return pieces, (wd * MM, length * MM, t * MM), prof
    prof = build_profile(shape, dims, mat, weld_mode=weld_mode)
    length = length or default_length(shape, prof, cam)
    ob = build_bar('piece', prof, length, bevel_mm=bevel, cut_sides=sheet)
    side, cut, inner = make_materials(mat, finish, prof['seam'], sheet=sheet, relief=relief)
    for m in (side, cut, inner):
        ob.data.materials.append(m)
    pieces = [ob]
    if shape == 'round_tube' and weld_mode == 'spiral':
        # Representative helical weld, pitch not supplied by catalogue; own photo is final authority.
        radius = float(dims[0]) / 2
        pitch = radius * 3.6
        cu = bpy.data.curves.new('helical_weld', 'CURVE')
        cu.dimensions = '3D'
        cu.bevel_depth = min(float(dims[1]) * .12, .7) * MM
        cu.bevel_resolution = 2
        spline = cu.splines.new('POLY')
        n = max(80, int(length / pitch * 160))
        spline.points.add(n)
        for i,p in enumerate(spline.points):
            y = length * i/n
            a = 2*PI*y/pitch + PI/5
            p.co = (radius*math.cos(a)*MM, y*MM, (radius+radius*math.sin(a))*MM, 1)
        ridge = bpy.data.objects.new('helical_weld', cu)
        bpy.context.scene.collection.objects.link(ridge)
        ridge.data.materials.append(side)
        pieces.append(ridge)
    if shape == 'chequer':
        pat = build_pattern('pattern', pattern or 'tear', prof['w'], length, prof['h'])
        top = prof['h'] * MM
        pat.data.materials.append(mat_hr(crest=(top + 0.0005, top + 0.0013)) if mat in ('hr', 'wrought')
                                  else side)
        pieces.append(pat)
    return pieces, (prof['w'] * MM, length * MM, prof['h'] * MM), prof


def parse(argv):
    p = argparse.ArgumentParser(prog='scene.py')
    p.add_argument('--shape', required=True)
    p.add_argument('--dims', required=True, help='section dimensions in mm, comma separated, as in catalog.json d')
    p.add_argument('--length', type=float, default=0.0, help='length in mm (0 = a sample length for the preset)')
    p.add_argument('--mat', default='hr')
    p.add_argument('--finish', default='brushed', help='inox: brushed or polished')
    p.add_argument('--pattern', default='', help='chequer: tear or bars')
    p.add_argument('--rig', default='grey', choices=['grey', 'dark', 'paper', 'stage'])
    p.add_argument('--cam', default='hero', choices=['hero', 'macro', 'poster', 'stage'])
    p.add_argument('--relief', default='', help='embossed handrail tubes: wood or flower')
    p.add_argument('--out', required=True)
    p.add_argument('--res', default='1600x1200')
    p.add_argument('--samples', type=int, default=160)
    p.add_argument('--noise', type=float, default=0.03, help='adaptive sampling noise threshold')
    p.add_argument('--time-limit', type=float, default=0.0, help='seconds, 0 = none')
    p.add_argument('--threads', type=int, default=4)
    p.add_argument('--seed', type=int, default=7)
    p.add_argument('--exposure', type=float, default=None)
    p.add_argument('--look', default='AgX - High Contrast')
    p.add_argument('--grain', type=float, default=0.035)
    p.add_argument('--glare', type=float, default=0.0)
    p.add_argument('--lens', type=float, default=None)
    p.add_argument('--az', type=float, default=None)
    p.add_argument('--el', type=float, default=None)
    p.add_argument('--bevel', type=float, default=0.3, help='end bevel in mm')
    p.add_argument('--weld-mode', default='', choices=['', 'seamless', 'spiral'])
    p.add_argument('--save-blend', default='')
    return p.parse_args(argv)


def main():
    argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    args = parse(argv)
    t0 = time.time()
    bpy.ops.wm.read_factory_settings(use_empty=True)
    dims = [float(x) for x in args.dims.replace('x', ',').split(',') if x]
    res = tuple(int(x) for x in args.res.lower().split('x'))
    sheet = args.shape in SHEETS
    if sheet and args.cam in ('poster', 'stage') and not args.length:
        # a poster of a sheet shows a sample, not the whole sheet
        dims = [dims[0], {'trapezoid': 450.0, 'cupal': 150.0}.get(args.shape, 180.0)]
        args.length = {'trapezoid': 280.0, 'cupal': 100.0}.get(args.shape, 125.0)
        if args.el is None:
            args.el = 31.0
    pieces, (w, L, h), prof = make_piece(
        args.shape,
        dims,
        args.length,
        args.mat,
        args.finish,
        args.pattern,
        args.bevel,
        args.relief,
        args.cam,
        weld_mode=args.weld_mode or None,
    )
    length = L / MM
    C = Vector((0.0, L / 2, h / 2))
    S = 0.5 * math.sqrt(w * w + L * L + h * h)
    alpha = args.rig in ('paper', 'stage')
    cam, view, info = build_camera(args.cam, (w, L, h), res, args.lens, args.az, args.el, sheet=sheet)
    if args.cam == 'macro':                       # light the end, not the whole bar
        sec = max(w, h)
        S = 0.5 * math.sqrt(w * w + h * h + (sec * 2.0) ** 2)
        C = Vector((0.0, sec * 0.9, h / 2))
    build_rig(args.rig, S, C, view, pieces, (w, L, h), RIG_GAIN.get(args.mat, 1.0), EYE_GAIN.get(args.mat, 0.12),
              top_gain=0.3 if sheet else 1.0)
    if args.exposure is None:
        args.exposure = 0.0
    setup_render(args, res, alpha)
    if not alpha and (args.grain > 0 or args.glare > 0):
        setup_grain(args.grain, args.glare)
    if args.save_blend:
        bpy.ops.wm.save_as_mainfile(filepath=args.save_blend)
    t1 = time.time()
    bpy.ops.render.render(write_still=True)
    t2 = time.time()
    print('ROCOTO_RENDER out=%s shape=%s dims=%s length=%.0f mat=%s rig=%s cam=%s res=%dx%d samples=%d '
          'fstop=%.1f focus=%.3f build_s=%.1f render_s=%.1f' % (
              args.out, args.shape, args.dims, length, args.mat, args.rig, args.cam, res[0], res[1],
              args.samples, info['fstop'], info['focus'], t1 - t0, t2 - t1))


if __name__ == '__main__':
    main()
