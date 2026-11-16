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
- `layout.py` — the stack: IKEA table 550x550x50, row 1 of four drives on the
  table from the origin (left-front corner of the table top), two vertical
  rolls (height 50, assumed diameter 70) carrying a 73x400x28 board (top at
  z = 78), row 2 of four drives on the board, rear-aligned to its back edge.
  The LED rims of row 1 stick out 0.35 mm past the table front edge.
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
