#!/usr/bin/env python3
"""Export an ink-saving 1:1 dry-fit sheet with all four boards on one A4 page.

Run with KiCad's Python (it needs pcbnew):

  KIPY=/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3
  $KIPY hardware/tools/export_dryfit.py [output.pdf]

Writes hardware/fabrication/review/surrklank-dryfit-a4-1to1.pdf by default: A4
landscape, boards drawn at true size with black outlines (board edge, footprint
silkscreen outlines, mounting holes) and red through-hole pads with their drill
circles. Tracks, zones, SMD parts and fills are left out to save ink. A 10 cm
ruler along both axes lets you check that the printer did not rescale: print at
"actual size" / 100 %, never "fit to page". The PDF page is A4 portrait with
the drawing rotated 90 degrees, so the printer needs no orientation setting;
turn the printed sheet to read it.
"""
import math
import sys
from pathlib import Path

import pcbnew

HARDWARE = Path(__file__).resolve().parent.parent
DEFAULT_OUT = HARDWARE / "fabrication" / "review" / "surrklank-dryfit-a4-1to1.pdf"
PAGE_W_MM, PAGE_H_MM = 297.0, 210.0
K = 72.0 / 25.4                      # points per millimetre
RED, BLACK = (0.85, 0.0, 0.0), (0.0, 0.0, 0.0)
LAYOUT = [                           # board, title, x, y of the board's top-left corner (mm)
    ("mainboard", "MAINBOARD 100 x 80 mm", 10.0, 12.0),
    ("fdd-module", "FDD MODULE 100 x 80 mm", 122.0, 12.0),
    ("lsm-hdd-module", "LSM/HDD MODULE 120 x 80 mm", 10.0, 106.0),
    ("panel", "PANEL 100 x 59 mm", 140.0, 106.0),
]
# Back side of a double-sided print: same boards, other places, so the holes pushed through
# the paper from one side do not fall on the other side's parts.
LAYOUT_BACK = [
    ("fdd-module", "FDD MODULE 100 x 80 mm", 10.0, 12.0),
    ("mainboard", "MAINBOARD 100 x 80 mm", 122.0, 12.0),
    ("panel", "PANEL 100 x 59 mm", 10.0, 106.0),
    ("lsm-hdd-module", "LSM/HDD MODULE 120 x 80 mm", 138.0, 106.0),
]
LABELLED = ("J", "A", "M", "SW", "D", "C8")


class Page:
    def __init__(self):
        self.ops = []

    def color(self, rgb):
        self.ops.append("%.3f %.3f %.3f RG %.3f %.3f %.3f rg" % (*rgb, *rgb))

    def width(self, mm_width):
        self.ops.append("%.3f w" % (mm_width * K))

    @staticmethod
    def p(x, y):
        return x * K, (PAGE_H_MM - y) * K

    def line(self, a, b):
        (x1, y1), (x2, y2) = self.p(*a), self.p(*b)
        self.ops.append("%.2f %.2f m %.2f %.2f l S" % (x1, y1, x2, y2))

    def poly(self, pts, close=True):
        if len(pts) < 2:
            return
        parts = ["%.2f %.2f m" % self.p(*pts[0])]
        parts += ["%.2f %.2f l" % self.p(*q) for q in pts[1:]]
        parts.append("s" if close else "S")
        self.ops.append(" ".join(parts))

    def circle(self, c, r):
        k = 0.5522847498 * r
        x, y = c
        pts = [(x + r, y), (x + r, y + k, x + k, y + r, x, y + r),
               (x - k, y + r, x - r, y + k, x - r, y),
               (x - r, y - k, x - k, y - r, x, y - r),
               (x + k, y - r, x + r, y - k, x + r, y)]
        parts = ["%.2f %.2f m" % self.p(*pts[0])]
        for seg in pts[1:]:
            q = [self.p(seg[i], seg[i + 1]) for i in (0, 2, 4)]
            parts.append("%.2f %.2f %.2f %.2f %.2f %.2f c" % (*q[0], *q[1], *q[2]))
        parts.append("S")
        self.ops.append(" ".join(parts))

    def text(self, x, y, s, size_pt=7.0):
        s = s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        px, py = self.p(x, y)
        self.ops.append("BT /F1 %.1f Tf %.2f %.2f Td (%s) Tj ET" % (size_pt, px, py, s))


def write_pdf(pages, path):
    """Write one A4 portrait PDF page per Page. The drawing is landscape (w x h) and is
    rotated 90 degrees on the portrait page: a printer does not rotate a landscape
    page when scaling is off and would crop it. Turn the printed sheet to read it."""
    w, h = PAGE_W_MM * K, PAGE_H_MM * K
    n = len(pages)
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>",
            ("<< /Type /Pages /Kids [%s] /Count %d >>"
             % (" ".join("%d 0 R" % (3 + 2 * i) for i in range(n)), n)).encode()]
    font_id = 3 + 2 * n
    for i, pg in enumerate(pages):
        stream = "\n".join(["q 0 1 -1 0 %.3f 0 cm" % h] + pg.ops + ["Q"]).encode("latin-1", "replace")
        objs.append(("<< /Type /Page /Parent 2 0 R /MediaBox [0 0 %.3f %.3f] /Contents %d 0 R "
                     "/Resources << /Font << /F1 %d 0 R >> >> >>" % (h, w, 4 + 2 * i, font_id)).encode())
        objs.append(b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream")
    objs.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, body in enumerate(objs, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    for off in offsets:
        out += b"%010d 00000 n \n" % off
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref)
    Path(path).write_bytes(bytes(out))


def mm(v):
    return pcbnew.ToMM(v)


def stadium(a, b, r, n=10):
    """Outline of a segment a-b with radius r (a slot; a circle when a == b)."""
    ang = math.atan2(b[1] - a[1], b[0] - a[0]) if a != b else 0.0
    pts = []
    for c, start in ((b, -math.pi / 2), (a, math.pi / 2)):
        for i in range(n + 1):
            t = ang + start + math.pi * i / n
            pts.append((c[0] + r * math.cos(t), c[1] + r * math.sin(t)))
    return pts


def arc_points(start, mid, end, n=16):
    ax, ay = start
    bx, by = mid
    cx, cy = end
    d = 2 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by))
    if abs(d) < 1e-9:
        return [start, end]
    ux = ((ax**2 + ay**2) * (by - cy) + (bx**2 + by**2) * (cy - ay) + (cx**2 + cy**2) * (ay - by)) / d
    uy = ((ax**2 + ay**2) * (cx - bx) + (bx**2 + by**2) * (ax - cx) + (cx**2 + cy**2) * (bx - ax)) / d
    r = math.hypot(ax - ux, ay - uy)
    a0, am, a1 = (math.atan2(y - uy, x - ux) for x, y in (start, mid, end))
    sweep = (a1 - a0) % (2 * math.pi)
    if (am - a0) % (2 * math.pi) > sweep:
        sweep -= 2 * math.pi
    return [(ux + r * math.cos(a0 + sweep * i / n), uy + r * math.sin(a0 + sweep * i / n))
            for i in range(n + 1)]


def xy(pt):
    return mm(pt.x), mm(pt.y)


def shape_paths(shape):
    """Polylines (list of points, closed flag) of a PCB_SHAPE in board millimetres."""
    kind = shape.GetShape()
    if kind == pcbnew.SHAPE_T_SEGMENT:
        return [([xy(shape.GetStart()), xy(shape.GetEnd())], False)]
    if kind == pcbnew.SHAPE_T_RECT:
        (x1, y1), (x2, y2) = xy(shape.GetStart()), xy(shape.GetEnd())
        return [([(x1, y1), (x2, y1), (x2, y2), (x1, y2)], True)]
    if kind == pcbnew.SHAPE_T_CIRCLE:
        c, r = xy(shape.GetCenter()), mm(shape.GetRadius())
        return [([(c[0] + r * math.cos(t * math.pi / 12), c[1] + r * math.sin(t * math.pi / 12))
                  for t in range(24)], True)]
    if kind == pcbnew.SHAPE_T_ARC:
        return [(arc_points(xy(shape.GetStart()), xy(shape.GetArcMid()), xy(shape.GetEnd())), False)]
    if kind == pcbnew.SHAPE_T_POLY:
        out = []
        poly = shape.GetPolyShape()
        for i in range(poly.OutlineCount()):
            ol = poly.Outline(i)
            out.append(([xy(ol.CPoint(j)) for j in range(ol.PointCount())], True))
        return out
    return []


def draw_board(page, name, title, ox, oy):
    board = pcbnew.LoadBoard(str(HARDWARE / name / f"surrklank-{name}.kicad_pcb"))
    edges = [d for d in board.GetDrawings()
             if d.GetLayer() == pcbnew.Edge_Cuts and d.GetClass() == "PCB_SHAPE"]
    bb = board.GetBoardEdgesBoundingBox()
    bx, by = mm(bb.GetX()), mm(bb.GetY())

    def t(pt):
        return pt[0] - bx + ox, pt[1] - by + oy

    page.color(BLACK)
    page.width(0.25)
    for e in edges:
        for pts, closed in shape_paths(e):
            page.poly([t(p) for p in pts], closed)
    page.text(ox, oy - 4.0, title, 8.0)

    for fp in board.GetFootprints():
        ref = fp.GetReference()
        pads = [p for p in fp.Pads()
                if p.GetAttribute() in (pcbnew.PAD_ATTRIB_PTH, pcbnew.PAD_ATTRIB_NPTH)]
        if not pads or ref.startswith("LOGO"):
            continue
        outline = [g for g in fp.GraphicalItems()
                   if g.GetClass() == "PCB_SHAPE" and g.GetLayer() == pcbnew.F_SilkS]
        fab = [g for g in fp.GraphicalItems()
               if g.GetClass() == "PCB_SHAPE" and g.GetLayer() == pcbnew.F_Fab]
        if not outline or len(outline) > 40:     # hatched polarity marks cost ink
            outline = fab
        elif ref == "A1":                        # add the ESP32 board body (fab layer)
            outline = outline + fab
        page.color(BLACK)
        page.width(0.15)
        for g in outline:
            for pts, closed in shape_paths(g):
                page.poly([t(p) for p in pts], closed)
        for pad in pads:
            copper = pad.GetAttribute() == pcbnew.PAD_ATTRIB_PTH
            hole = pad.GetEffectiveHoleShape()
            seg = hole.GetSeg()
            a, b = t(xy(seg.A)), t(xy(seg.B))
            r = mm(hole.GetWidth()) / 2
            page.color(RED if copper else BLACK)
            page.width(0.15)
            if copper:
                if pad.GetShape() == pcbnew.PAD_SHAPE_CIRCLE:
                    page.circle(t(xy(pad.GetPosition())), mm(pad.GetSizeX()) / 2)
                else:
                    poly = pad.GetEffectivePolygon(pcbnew.F_Cu)
                    for i in range(poly.OutlineCount()):
                        ol = poly.Outline(i)
                        page.poly([t(xy(ol.CPoint(j))) for j in range(ol.PointCount())])
            page.poly(stadium(a, b, r), True) if a != b else page.circle(a, r)
        if ref.startswith(LABELLED):
            box = fp.GetBoundingBox(False)
            page.color(BLACK)
            page.text(*t((mm(box.GetX()), mm(box.GetY()) - 0.8)), ref, 6.0)


def ruler(page, x0, y0, horizontal):
    page.color(BLACK)
    page.width(0.2)
    end = (x0 + 100, y0) if horizontal else (x0, y0 + 100)
    page.line((x0, y0), end)
    for i in range(101):
        length = 4.0 if i % 10 == 0 else 2.5 if i % 5 == 0 else 1.5
        if horizontal:
            page.line((x0 + i, y0), (x0 + i, y0 + length))
            if i % 10 == 0:
                page.text(x0 + i - 1.0, y0 + 8.0, str(i // 10), 7.0)
        else:
            page.line((x0, y0 + i), (x0 + length, y0 + i))
            if i % 10 == 0:
                page.text(x0 + 6.0, y0 + i + 1.0, str(i // 10), 7.0)
    label = "cm: the ruler must measure exactly 10 cm"
    if horizontal:
        page.text(x0 + 12.0, y0 + 13.0, label, 7.0)
    else:
        page.text(x0 - 12.0, y0 - 2.0, "10 cm vertical", 7.0)


def sheet(layout, ruler_h, note_x):
    page = Page()
    for name, title, x, y in layout:
        draw_board(page, name, title, x, y)
    ruler(page, ruler_h[0], ruler_h[1], True)
    ruler(page, 262.0, 20.0, False)
    page.color(BLACK)
    page.text(note_x, 201.0, "Print at 100 % / actual size (not fit to page). Black: board and part outlines. "
                             "Red: through-hole pads.", 6.5)
    return page


def main():
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUT
    out.parent.mkdir(parents=True, exist_ok=True)
    pages = [sheet(LAYOUT, (140.0, 178.0), 140.0), sheet(LAYOUT_BACK, (10.0, 178.0), 10.0)]
    write_pdf(pages, out)
    print(f"wrote {out} ({len(pages)} pages: front, back)")


if __name__ == "__main__":
    main()
