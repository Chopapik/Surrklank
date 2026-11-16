"""Place the KiCad boards exported by export_pcbs.py in the Blender layout.

    build_pcbs(placements=PLACEMENTS, default_origin=(x, y, z)) -> [Empty]

Each hardware/layout/pcb/<board>.glb is imported under an Empty named
pcb_<board>. The import is shifted so the Empty's origin is the board's
left-front-bottom bounding-box corner (components included), in millimetres
like the rest of the layout. PLACEMENTS maps a board name (the .kicad_pcb
stem) to (x, y, z, rot_z_deg); boards without an entry are lined up next to
the table at default_origin until their real positions are known.
"""
import math
from pathlib import Path

import bpy
from mathutils import Vector

MM = 0.001
PCB_DIR = Path(__file__).resolve().parent / "pcb"

# Real positions are not known yet; fill in as (x, y, z, rot_z_deg) in mm.
PLACEMENTS = {}
PARK_GAP = 20.0     # gap between parked boards along Y


def _import(glb, name, coll):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(glb))
    new = [o for o in bpy.data.objects if o not in before]
    root = bpy.data.objects.new(name, None)
    root.empty_display_size = 0.01
    coll.objects.link(root)
    meshes = [o for o in new if o.type == "MESH"]
    bpy.context.view_layer.update()
    pts = [o.matrix_world @ Vector(c) for o in meshes for c in o.bound_box]
    lo = Vector([min(p[i] for p in pts) for i in range(3)])
    hi = Vector([max(p[i] for p in pts) for i in range(3)])
    for o in new:
        if o.parent is None:
            o.location -= lo
            o.parent = root
    for o in new:                      # keep them in the target collection only
        for c in list(o.users_collection):
            if c is not coll:
                c.objects.unlink(o)
        if coll not in o.users_collection:
            coll.objects.link(o)
    return root, (hi - lo) / MM


def build_pcbs(placements=None, default_origin=(0.0, 0.0, 0.0), pcb_dir=None, collection=None):
    placements = PLACEMENTS if placements is None else placements
    pcb_dir = Path(pcb_dir) if pcb_dir else PCB_DIR
    if pcb_dir is None or not pcb_dir.is_dir():
        print("pcbs: no exported boards; run export_pcbs.py")
        return []
    coll = collection or bpy.context.scene.collection
    roots, park_y = [], default_origin[1]
    for glb in sorted(pcb_dir.glob("*.glb")):
        board = glb.stem
        root, size = _import(glb, f"pcb_{board}", coll)
        if board in placements:
            x, y, z, rot = placements[board]
        else:                          # parked beside the table
            x, y, z, rot = default_origin[0], park_y, default_origin[2], 0.0
            park_y += size.y + PARK_GAP
        root.location = (x * MM, y * MM, z * MM)
        root.rotation_euler.z = math.radians(rot)
        roots.append(root)
    return roots
