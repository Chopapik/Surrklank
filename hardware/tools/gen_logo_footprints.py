#!/usr/bin/env python3
"""Write the Surrklank mark footprint: a 10 mm square frame with the beamed-notes glyph.

Usage: python3 -I gen_logo_footprints.py
Writes hardware/lib/surrklank.pretty/Surrklank_Mark_10mm.kicad_mod (front silkscreen, origin at the
centre). The note is one filled polygon whose height is 55 % of the frame (design choice B of the
ui-design brand set); the frame is a 0.7 mm outline. The author ring is Surrklank_Logo_8mm.
"""
import os

NOTE_PATH = "M13.441 2.0L13.441 11.409L13.44 11.409L13.44 11.469L13.433 11.598L13.418 11.729L13.395 11.86L13.364 11.992L13.326 12.124L13.281 12.255L13.228 12.386L13.168 12.515L13.102 12.644L13.028 12.77L12.948 12.894L12.861 13.016L12.768 13.135L12.67 13.251L12.566 13.364L12.456 13.473L12.341 13.577L12.222 13.678L12.098 13.774L11.97 13.865L11.839 13.951L11.704 14.031L11.566 14.106L11.426 14.175L11.283 14.238L11.139 14.296L10.993 14.346L10.846 14.391L10.699 14.428L10.551 14.46L10.404 14.484L10.257 14.502L10.111 14.512L9.966 14.516L9.824 14.513L9.683 14.503L9.545 14.487L9.41 14.463L9.278 14.433L9.15 14.396L9.026 14.352L8.907 14.302L8.792 14.246L8.682 14.183L8.577 14.115L8.478 14.04L8.385 13.961L8.298 13.875L8.217 13.785L8.143 13.69L8.076 13.59L8.016 13.485L7.963 13.377L7.917 13.265L7.878 13.149L7.847 13.031L7.824 12.909L7.808 12.785L7.8 12.659L7.8 12.531L7.807 12.402L7.823 12.271L7.846 12.14L7.876 12.008L7.914 11.876L7.959 11.745L8.012 11.614L8.072 11.485L8.139 11.356L8.212 11.23L8.293 11.106L8.379 10.984L8.472 10.865L8.571 10.749L8.675 10.636L8.784 10.527L8.899 10.423L9.018 10.322L9.142 10.226L9.27 10.135L9.401 10.049L9.536 9.969L9.674 9.894L9.814 9.825L9.957 9.762L10.101 9.704L10.247 9.654L10.394 9.609L10.542 9.572L10.689 9.54L10.837 9.516L10.984 9.498L11.13 9.488L11.274 9.484L11.417 9.487L11.557 9.497L11.695 9.513L11.83 9.537L11.962 9.567L12.041 9.59L12.041 3.796L5.641 5.604L5.641 13.409L5.64 13.409L5.64 13.469L5.633 13.598L5.618 13.729L5.595 13.86L5.564 13.992L5.526 14.124L5.481 14.255L5.428 14.386L5.368 14.515L5.302 14.644L5.228 14.77L5.148 14.894L5.061 15.016L4.968 15.135L4.87 15.251L4.766 15.364L4.656 15.473L4.541 15.577L4.422 15.678L4.298 15.774L4.17 15.865L4.039 15.951L3.904 16.031L3.766 16.106L3.626 16.175L3.483 16.238L3.339 16.296L3.193 16.346L3.046 16.391L2.899 16.428L2.751 16.46L2.604 16.484L2.457 16.502L2.311 16.512L2.166 16.516L2.024 16.513L1.883 16.503L1.745 16.487L1.61 16.463L1.478 16.433L1.35 16.396L1.226 16.352L1.107 16.302L0.992 16.246L0.882 16.183L0.777 16.115L0.678 16.04L0.585 15.961L0.498 15.875L0.417 15.785L0.343 15.69L0.276 15.59L0.216 15.485L0.163 15.377L0.117 15.265L0.078 15.149L0.047 15.031L0.024 14.909L0.008 14.785L0.0 14.659L0.0 14.531L0.007 14.402L0.023 14.271L0.046 14.14L0.076 14.008L0.114 13.876L0.159 13.745L0.212 13.614L0.272 13.485L0.339 13.356L0.412 13.23L0.493 13.106L0.579 12.984L0.672 12.865L0.771 12.749L0.875 12.636L0.984 12.527L1.099 12.423L1.218 12.322L1.342 12.226L1.47 12.135L1.601 12.049L1.736 11.969L1.874 11.894L2.014 11.825L2.157 11.762L2.301 11.704L2.447 11.654L2.594 11.609L2.742 11.572L2.889 11.54L3.037 11.516L3.184 11.498L3.33 11.488L3.474 11.484L3.617 11.487L3.757 11.497L3.895 11.513L4.03 11.537L4.162 11.567L4.241 11.59L4.241 2.6L13.441 0.0Z"
NOTE_W, NOTE_H = 13.441, 16.516
FRAME, STROKE, RATIO = 10.0, 0.7, 0.55
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib", "surrklank.pretty")


def points():
    pts = []
    for pair in NOTE_PATH.strip("MZ").split("L"):
        x, y = (float(v) for v in pair.split())
        pts.append((x, y))
    s = FRAME * RATIO / NOTE_H
    return [((x - NOTE_W / 2) * s, (y - NOTE_H / 2) * s) for x, y in pts]


def main():
    half = FRAME / 2 - STROKE / 2
    xy = " ".join(f"(xy {x:.3f} {y:.3f})" for x, y in points())
    text = (
        '(footprint "Surrklank_Mark_10mm"\n\t(version 20260206)\n\t(generator "surrklank_gen")\n\t(layer "F.Cu")\n'
        '\t(descr "Surrklank mark: 10 mm square frame with the beamed-notes glyph (55 % of the frame height), front silkscreen.")\n'
        '\t(property "Reference" "LOGO**" (at 0 0 0) (layer "F.SilkS") (hide yes) (effects (font (size 1 1) (thickness 0.15))))\n'
        '\t(property "Value" "Surrklank_Mark" (at 0 0 0) (layer "F.Fab") (hide yes) (effects (font (size 1 1) (thickness 0.15))))\n'
        '\t(attr board_only exclude_from_pos_files exclude_from_bom)\n'
        f'\t(fp_rect (start {-half:.3f} {-half:.3f}) (end {half:.3f} {half:.3f}) (stroke (width {STROKE}) (type solid)) (fill no) (layer "F.SilkS"))\n'
        f'\t(fp_poly (pts {xy}) (stroke (width 0.01) (type solid)) (fill yes) (layer "F.SilkS"))\n'
        ")\n"
    )
    with open(os.path.join(OUT, "Surrklank_Mark_10mm.kicad_mod"), "w", encoding="utf-8") as f:
        f.write(text)
    print("wrote Surrklank_Mark_10mm")


if __name__ == "__main__":
    main()
