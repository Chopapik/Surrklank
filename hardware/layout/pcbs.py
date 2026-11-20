"""Place the KiCad boards exported by export_pcbs.py in the Blender layout.

    build_pcbs(placements, park_origin=(x, y, z)) -> {instance: Empty}

Each hardware/layout/pcb/<board>.glb is imported once; its objects are
shifted so the board's left-front-bottom bounding-box corner (components
included) is the local origin, in millimetres like the rest of the layout.
placements maps an instance name to (board, min_corner, axes) as in
harness.PLACEMENTS: axes sends the board's local X, Y and Z (component side)
to layout axes, and min_corner is where the placed bounding box starts. A
second instance of a board shares the meshes of the first. Exported boards
without a placement are parked in a row at park_origin.
"""
from pathlib import Path

import bpy
from mathutils import Matrix, Vector

MM = 0.001
PCB_DIR = Path(__file__).resolve().parent / "pcb"
PARK_GAP = 20.0
AX = {"+X": (1, 0, 0), "-X": (-1, 0, 0), "+Y": (0, 1, 0), "-Y": (0, -1, 0),
      "+Z": (0, 0, 1), "-Z": (0, 0, -1)}


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


def _copy(src, name, coll):
    """Linked duplicate of a board hierarchy (meshes shared)."""
    root = bpy.data.objects.new(name, None)
    root.empty_display_size = src.empty_display_size
    coll.objects.link(root)
    mapping = {src: root}
    for o in src.children_recursive:
        c = o.copy()
        coll.objects.link(c)
        mapping[o] = c
    for o, c in mapping.items():
        if o is not src:
            c.parent = mapping[o.parent]
            c.matrix_parent_inverse = o.matrix_parent_inverse.copy()
    return root


def _place(root, size, min_corner, axes):
    a = [Vector(AX[s]) for s in axes]
    corners = [a[0] * x + a[1] * y + a[2] * z
               for x in (0, size[0]) for y in (0, size[1]) for z in (0, size[2])]
    lo = Vector([min(c[k] for c in corners) for k in range(3)])
    o = (Vector(min_corner) - lo) * MM
    m = Matrix.Identity(4)
    for i in range(3):
        for k in range(3):
            m[k][i] = a[i][k]
        m[i][3] = o[i]
    root.matrix_world = m


def build_pcbs(placements, park_origin=(0.0, 0.0, 0.0), pcb_dir=None, collection=None):
    pcb_dir = Path(pcb_dir) if pcb_dir else PCB_DIR
    if not pcb_dir.is_dir():
        print("pcbs: no exported boards; run export_pcbs.py")
        return {}
    coll = collection or bpy.context.scene.collection
    loaded, roots = {}, {}
    for inst, (board, mn, axes) in placements.items():
        glb = pcb_dir / f"{board}.glb"
        if not glb.is_file():
            print(f"pcbs: {glb.name} missing")
            continue
        if board in loaded:
            root, size = _copy(loaded[board][0], f"pcb_{inst}", coll), loaded[board][1]
        else:
            root, size = _import(glb, f"pcb_{inst}", coll)
            loaded[board] = (root, size)
        _place(root, size, mn, axes)
        roots[inst] = root
    y = park_origin[1]
    for glb in sorted(pcb_dir.glob("*.glb")):        # exported but not placed
        if glb.stem in loaded:
            continue
        root, size = _import(glb, f"pcb_{glb.stem}", coll)
        root.location = Vector((park_origin[0], y, park_origin[2])) * MM
        y += size.y + PARK_GAP
        roots[glb.stem] = root
    return roots
