"""Boil the resort glb down to one geometry per material.

The export has 1044 meshes, no node transforms, no normals and no UVs -- so
every triangle is already in world space and the only thing that separates
one surface from another is which of the fourteen materials it uses. Merging
by material turns a thousand draw calls into fourteen, and lets the page
carry the model as a few compact arrays instead of a 650KB glb and a loader.
"""
import base64
import json
import struct
import sys

SRC = sys.argv[1]
OUT = sys.argv[2]

with open(SRC, "rb") as fh:
    magic, ver, total = struct.unpack("<III", fh.read(12))
    assert magic == 0x46546C67, "not a glb"
    chunks = {}
    while fh.tell() < total:
        ln, kind = struct.unpack("<II", fh.read(8))
        chunks.setdefault(kind, fh.read(ln))
gltf = json.loads(chunks[0x4E4F534A].decode("utf-8"))
BIN = chunks[0x004E4942]

COMP = {5120: ("b", 1), 5121: ("B", 1), 5122: ("h", 2),
        5123: ("H", 2), 5125: ("I", 4), 5126: ("f", 4)}
NUM = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}


def read(ix):
    """One accessor, as a flat list. Sparse and interleaved are not used here."""
    acc = gltf["accessors"][ix]
    bv = gltf["bufferViews"][acc["bufferView"]]
    fmt, size = COMP[acc["componentType"]]
    n = NUM[acc["type"]]
    stride = bv.get("byteStride") or size * n
    base = bv.get("byteOffset", 0) + acc.get("byteOffset", 0)
    out = []
    for i in range(acc["count"]):
        off = base + i * stride
        out.extend(struct.unpack_from("<" + fmt * n, BIN, off))
    return out


groups = {}
ground = -1e30          # the top of the terrain plate, so the page can carry
                        # the snowfield out past the edge of the model
for node in gltf["nodes"]:
    assert not any(k in node for k in ("matrix", "translation", "rotation",
                                       "scale")), "a node carries a transform"
for mesh in gltf["meshes"]:
    for prim in mesh["primitives"]:
        assert prim.get("mode", 4) == 4, "not triangles"
        mi = prim.get("material", 0)
        g = groups.setdefault(mi, {"pos": [], "idx": []})
        pos = read(prim["attributes"]["POSITION"])
        idx = (read(prim["indices"]) if "indices" in prim
               else list(range(len(pos) // 3)))
        off = len(g["pos"]) // 3
        g["pos"].extend(pos)
        g["idx"].extend(i + off for i in idx)
        if mesh.get("name", "").startswith(("terrain", "plaza", "ski_slope")):
            ground = max(ground, max(pos[2::3]))

out = {"materials": [], "groups": []}
for mi in sorted(groups):
    m = gltf["materials"][mi]
    pbr = m.get("pbrMetallicRoughness", {})
    col = pbr.get("baseColorFactor", [0.8, 0.8, 0.8, 1.0])
    g = groups[mi]
    nverts = len(g["pos"]) // 3
    wide = nverts > 65535
    pos = struct.pack("<%df" % len(g["pos"]), *g["pos"])
    idx = struct.pack("<%d%s" % (len(g["idx"]), "I" if wide else "H"), *g["idx"])
    out["materials"].append({
        "name": m.get("name", "material %d" % mi),
        # trimesh writes the authored sRGB bytes straight into baseColorFactor
        # as 0..1, with no gamma applied, so none is undone here.
        "color": "#%02x%02x%02x" % tuple(
            max(0, min(255, round(c * 255))) for c in col[:3]),
        "opacity": round(col[3], 3)})
    out["groups"].append({
        "verts": nverts, "tris": len(g["idx"]) // 3, "wide": wide,
        "pos": base64.b64encode(pos).decode("ascii"),
        "idx": base64.b64encode(idx).decode("ascii")})

lo = [1e30] * 3
hi = [-1e30] * 3
for mi in sorted(groups):
    p = groups[mi]["pos"]
    for k in range(3):
        vals = p[k::3]
        lo[k] = min(lo[k], min(vals))
        hi[k] = max(hi[k], max(vals))
out["bounds"] = {"min": [round(v, 4) for v in lo],
                 "max": [round(v, 4) for v in hi]}
out["up"] = "z"          # trimesh writes Z-up; three.js is Y-up
out["ground"] = round(ground, 4)

with open(OUT, "w", encoding="utf-8") as fh:
    json.dump(out, fh, separators=(",", ":"))

import os
print("wrote %s  %.0f KB" % (OUT, os.path.getsize(OUT) / 1024))
for m, g in zip(out["materials"], out["groups"]):
    print("  %-16s %-8s verts=%-6d tris=%-6d" %
          (m["name"], m["color"], g["verts"], g["tris"]))
print("bounds", out["bounds"], " ground z", out["ground"])
