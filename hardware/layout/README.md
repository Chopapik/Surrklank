# Surrklank physical layout (Blender)

Procedural Blender (`bpy`) models used to plan the floppy-drive stack, purchases
and 3D-printed parts. Blender units are metres; all dimensions are written in
millimetres and converted with `MM = 0.001`.

- `fdd_model.py` — `build_fdd(name, origin=(0, 0, 0), open_top=True, track=40,
  bezel="beige", collection=None)` creates one 3.5" drive as an Empty with
  child objects and returns the Empty. Origin is the left-front-bottom corner
  of the body; X = width, Y = depth (bezel face at Y = 0), Z = height.
  `track` (0..79) positions the head carriage, `bezel` is `"beige"` or
  `"black"`, `open_top=False` adds the top cover with a label.
  - Bezel, from a front photo of an orchestra drive: a large stepped recess
    with sloped walls, a finger ramp below and a shallow lobe above the closed
    disk door, a dark groove around the door, an eject button lower right and
    an LED with a raised rim and ribbed lens lower left.
  - The rest follows a Teac FD-235HF-class drive: steel chassis with M3 holes
    cut in the side walls and floor; PCB on the underside with clearance
    cut-outs; flat spindle motor with turntable, magnetic chuck and drive pin;
    guide rod, lead screw and can-stack stepper; head carriage with both heads
    and a track-0 flag; disk holder, eject slider and spring; write-protect,
    density and track-0 sensors; 2x17 pin header, drive-select jumper and
    4-pin mini power connector at the rear.
  - Meshes, including the boolean cut-outs, are built once per module load
    and shared by all drives, so eight drives build quickly.
- `vcr_cover.py` — `build_vcr_cover(name, origin)`: the Samsung VCR top cover
  used as a resonance box for stepper motors. An inverted U, 398x284 top
  plate, two 290x90 side walls on the short sides, 0.5 mm sheet (all
  measured); front and back open. A lip along the rear long edge (none at
  the front) with three deeper screw tabs and screw holes near the wall feet are read from
  photos (`[PHOTO]`). Four linear steppers sit at its corners. In the layout it
  stands centred on the shelf.
- `linear_stepper.py` — `build_linear_stepper(name, origin, facing)`: a 15 mm
  can-stack linear stepper (CHIHAI SM15xx class, M3 x 0.5 brass lead screw)
  on a bent steel bracket, 61 mm from motor face to end flange, screwed flat
  to the cover with two screws; no carriage. On the cover each bracket starts
  at a short edge and runs inward, the can overhangs the edge; screw axes
  25 mm from the rear edge (measured) and 20 mm from the front (photo).
- `layout.py` — the stack: IKEA table 550x550x50, row 1 of four drives on the
  table from the origin (left-front corner of the table top), two vertical
  rolls (height 50, assumed diameter 70) carrying a 73x400x28 board (top at
  z = 78), row 2 of four drives on the board, centred on it in depth.
  Two ATX PSU cases (140x85x149, standing upright: 85 wide, 149 deep, 140
  high; plain black boxes) stand in the left-rear corner and at the mirrored
  position under the right end of a black 455x285x15 shelf that rests on
  them with its front and left edges flush with the left one (top at
  z = 155); the shelf overhangs the table's rear edge by 136 mm. Row 3 of
  four drives stands on an identical board on double rolls (two stacked,
  board top at z = 128), centred on it, set back from row 2 by the same
  109.5 mm as row 2 from row 1 (drives at y = 219..365; the rolls just clear
  row 2's rear at y = 255.5; 36 mm left to the ATX fronts).
  `SUPPORT` selects how rows 2 and 3 are raised: `"rolls"` is the current
  real setup (tape rolls under 400 mm boards); `"cheeks"` (default) is the
  proposed replacement: two stepped 12 mm plywood side plates outside the
  rows, built for maintenance. The rows rise in equal `STEP_Z` = 64 mm steps
  (drives at z = 0, 64, 128); all rows shift right by the plate thickness.
  - Frame (permanent): each plate is a lower and an upper part joined by two
    flat plates with four 3.5x10 screws each; an 18x30 rear stretcher,
    screwed through the plates (3.5x30), keeps the frame square.
  - Trays (lift-off): each full-width board carries its row and lies on the
    plates, located by two 6x20 dowels per end; no screws. Lift tray C,
    then tray B. Row 1 stands loose on the table.
  - Table: two 6x20 dowels under each plate go 10 mm into the table top;
    they only stop sliding (an IKEA LACK top is honeycomb-filled).
  Nothing stands behind the rear connectors.
  The table is black. The LED rims of row 1 stick out 0.35 mm past the table front edge.
- `live_server.py` / `send.py` — optional live view (see below).

## Dimensions

Every constant in `fdd_model.py` is tagged:

- `[STD]` — published: 101.6 x 25.4 mm form factor, 2.54 mm header pitch,
  90 x 94 x 3.3 mm disk, 0.1875 mm track pitch (track radii recalled).
- `[PHOTO]` — bezel features read from the photo, scaled from the 101.6 mm
  bezel width; about ±0.5 mm. Depths of the relief cannot be read from a
  front photo and are `[ASSUMED]`.
- `[SFF-8301]` — side and bottom M3 holes follow the 3.5" HDD pattern as
  recalled; not checked on a floppy drive.
- `[TYP]` — typical values (146 mm depth, 1.6 mm PCB, connector outlines).
- `[ASSUMED]` — everything else, including the whole mechanism layout.

No drive was measured. Check hole positions and bezel features with calipers
before ordering or printing parts.

## Run headless

```bash
/Applications/Blender.app/Contents/MacOS/Blender -b --python hardware/layout/layout.py -- <out_dir>
```

Writes `iso.png`, `top.png`, `front.png` (Workbench) and `layout.blend`.

## Run live

`live_server.py` listens on 127.0.0.1:8765 inside a GUI Blender and **executes
arbitrary Python it receives** — run it only on a machine you trust.

1. In Blender's Scripting workspace open and run `live_server.py`.
2. Send a script from a terminal. `send.py` prepends `__file__`, so a sent
   script can import its sibling modules. For the stack layout send code that
   calls `build_scene()` (it removes every object in the open file first):

```bash
echo 'exec(open("/abs/path/hardware/layout/layout.py").read()); build_scene()' > /tmp/go.py
python3 hardware/layout/send.py /tmp/go.py
```
