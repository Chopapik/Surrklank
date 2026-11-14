#!/usr/bin/env python3
"""Write the KF301 screw-terminal footprints (5.08 mm pitch, 2, 4 and 5 poles).

Usage: python3 -I gen_terminal_footprints.py
The footprints go to hardware/lib/surrklank.pretty/. Pin 1 is at the origin and
the pins run along +x. Wires enter from the +y side of the body; labels belong
on the -y side (they are placed by gen_module_pcb.py), never under the body.
Pad and body sizes are generic KF301 values: check them against the bought part.
"""
import os

PITCH = 5.08
HALF_W, HALF_D = 2.54, 4.0          # body extends 2.54 beyond the outer pins, 4 mm each side of the pin row
PAD, DRILL = 3.0, 1.4
PAD_4P = 2.6                      # the 4-pole terminal: two +5V pads must fit the 7.9 mm +5V band
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib", "surrklank.pretty")


def rect(x1, y1, x2, y2, layer, width):
    pts = [(x1, y1), (x2, y1), (x2, y2), (x1, y2), (x1, y1)]
    return "".join(f'\t(fp_line (start {a:.2f} {b:.2f}) (end {c:.2f} {d:.2f}) '
                   f'(stroke (width {width}) (type solid)) (layer "{layer}"))\n'
                   for (a, b), (c, d) in zip(pts, pts[1:]))


def footprint(n):
    name = f"TerminalBlock_KF301_1x{n:02d}_P5.08mm_Horizontal"
    x2 = (n - 1) * PITCH + HALF_W
    mid = (n - 1) * PITCH / 2
    s = f'(footprint "{name}"\n\t(version 20260206)\n\t(generator "surrklank_gen")\n\t(layer "F.Cu")\n'
    s += (f'\t(descr "KF301 screw terminal, {n} poles, 5.08 mm pitch, vertical pins. Pin 1 at the origin, '
          f'pins along +x, wires enter from the +y side (generic dimensions: check against the bought part).")\n')
    s += '\t(tags "KF301 screw terminal 5.08")\n'
    s += (f'\t(property "Reference" "REF**" (at {mid:.2f} {HALF_D + 2.2:.2f} 0) (layer "F.Fab") '
          '(effects (font (size 1 1) (thickness 0.15))))\n')
    s += (f'\t(property "Value" "KF301_{n}P" (at {mid:.2f} {HALF_D + 3.6:.2f} 0) (layer "F.Fab") '
          '(effects (font (size 1 1) (thickness 0.15))))\n')
    s += rect(-HALF_W, -HALF_D, x2, HALF_D, "F.SilkS", 0.15)
    s += rect(-HALF_W, -HALF_D, x2, HALF_D, "F.Fab", 0.1)
    s += rect(-HALF_W - 0.5, -HALF_D - 0.5, x2 + 0.5, HALF_D + 0.5, "F.CrtYd", 0.05)
    s += (f'\t(fp_text user "WIRES" (at {mid:.2f} {HALF_D - 1.0:.2f} 0) (layer "F.Fab") '
          '(effects (font (size 0.8 0.8) (thickness 0.1))))\n')
    pad = PAD_4P if n == 4 else PAD
    for i in range(n):
        shape = "rect" if i == 0 else "circle"
        s += (f'\t(pad "{i + 1}" thru_hole {shape} (at {i * PITCH:.2f} 0) (size {pad} {pad}) (drill {DRILL}) '
              '(layers "*.Cu" "*.Mask") (remove_unused_layers no))\n')
    s += ")\n"
    return name, s


if __name__ == "__main__":
    for n in (2, 4, 5):
        name, text = footprint(n)
        with open(os.path.join(OUT, name + ".kicad_mod"), "w", encoding="utf-8") as f:
            f.write(text)
        print("wrote", name)
