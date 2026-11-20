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
- `export_pcbs.py` — run with plain `python3`: exports every KiCad board
  with an outline to `pcb/<board>.glb` through `kicad-cli pcb export glb`
  (`pcb/` is ignored by Git). `--light` leaves out tracks, pads, zones,
  silkscreen and soldermask. Boards without Edge.Cuts are skipped.
- `pcbs.py` — `build_pcbs(placements)` imports each GLB once with the
  origin at the board's left-front-bottom corner and places one instance per
  entry of `harness.PLACEMENTS` (`(board, min_corner, axes)`; `axes` sends
  the board's local X, Y and component side Z to layout axes, so a board can
  be turned or stood on edge). Further instances share the meshes. Exported
  boards without a placement are parked beside the table; with no exports
  the stack builds without boards.
- `harness.py` — pure Python, no `bpy`: the planned board positions and the
  cable routes, built from the row and cover geometry that `layout.py`
  passes in. `finish()` adds lengths, slack and wire-1 orientation;
  `report()` prints the table `layout.py` shows on every build. Rules:
  - No cable is lengthened or shortened: 370 mm ribbons cut from 40-wire
    IDE cables and 440 mm LSM leads (both measured, about ±40 mm). A route
    longer than its cable raises an error; the rest is one folded pack on
    the route's longest straight run.
  - A turn towards the ribbon's own width is a flat 45° fold, any other
    turn a bend. Where wire 1 would land on the wrong side, the longest
    straight run gets a half or quarter twist.
  - Plan for 12 drives (three rows): three FDD modules, one per row, each
    centred on its row so the drive cables need no sideways jog. One IDE
    header serves the inner pair (drives 2 and 3, T arms 50.8 mm), the other
    the outer pair (drives 1 and 4, 152.4 mm); drive select stays firmware
    configuration. Module A lies on the table under trays B and C; modules
    B and C are stacked in the cavity under the shelf between the ATX cases.
    Rows A and B get a horizontal T under the next tray, row C a vertical T
    in the gap in front of the ATX cases, high enough that row B's cables
    and the FDD chain pass under it.
  - The mainboard stands on edge on the inner side of ATX 2, components
    facing the module stack, outside the metal cover for BLE. FDD branch:
    mainboard → C → B → A, each hop over the next board. Actuator branch:
    out of the cavity, up in front of the shelf, into the VCR cover.
  - The actuator module lies on the shelf inside the VCR cover, turned so
    its motor connectors face the rear. Each LSM lead runs down outside the
    side wall from the motor and through the ø4 foot hole just below it,
    then over the board to its slot; front-left, rear-left, rear-right and
    front-right go to M4, M3, M2 and M1. This needs the bare leads threaded
    before soldering and holes free of screws.
  - The panel lies on the table right of the frame; its ribbon is the
    tightest (20 mm slack). The proposed LED board is a placeholder
    perfboard inside the cover's front opening.
  - Not modelled: power wiring, strain relief, bend radii and ribbon
    stiffness; ribbon collisions were checked by sampling in the scene.
- `cables.py` — `build_cables(plan)` draws the routes: ribbons as flat
  strips with the red wire 1. A fold is the real flat fold: both runs end on
  the 45° crease (drawn as a dark line), the folded-over run lies one
  thickness higher, and a T split ends the stem in two creases. Bends are
  4 mm arcs and twists rotate continuously along their run. Also IDC sockets at both ends (the drive end on contacts
  10–29 of a 34-pin socket), JST-XH housings on the LSM leads, slack packs
  and the LED placeholder. Lead colours are assumed.
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

Export the boards first (again after KiCad changes):

```bash
python3 hardware/layout/export_pcbs.py
```

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

The model is real size, so `build_scene()` sets the near clip of every open
3D view to 0.1 mm (Blender's default of 10 mm cuts away anything closer and
blocks a view into the stack). To move inside, put the mouse over the spot
and zoom with Ctrl+scroll or use fly mode (Shift+`, WASD, scroll for speed);
View → Frame Selected (numpad .) centres the orbit on a selected part.
