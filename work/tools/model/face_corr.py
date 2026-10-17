"""Step 2: find where each of MediaPipe's 478 face landmarks sits on the MakeHuman head.

Renders the neutral head from the front, runs the same face landmarker used on the photo, and
ray-casts every landmark back onto the mesh. Result: one surface point per landmark (triangle +
barycentric weights), which moves with any shape target. Output: build/face_corr.json

Run:  .venv/bin/python face_corr.py
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import bpy  # noqa: F401  (must load before mathutils)
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from PIL import Image, ImageDraw
import mediapipe as mp
from mediapipe.tasks import python as mpt
from mediapipe.tasks.python import vision

import bl
import mh
import shape
from analyze_photo import model_path

BUILD = HERE / 'build'
RES = 1024


def main():
    BUILD.mkdir(exist_ok=True)
    verts = shape.neutral()
    base = mh.base_mesh()
    groups = mh.vertex_groups()
    keep = np.isin(base['face_group'], ['body', 'helper-l-eye', 'helper-r-eye'])
    faces = base['faces'][keep]

    # Vertex colors: skin, eyes with iris and pupil (MediaPipe needs readable eyes).
    colors = np.tile([0.78, 0.56, 0.47, 1.0], (len(verts), 1))
    for side in ('l', 'r'):
        idx = groups[f'helper-{side}-eye']
        center = verts[idx].mean(0)
        d = verts[idx] - center
        d /= np.linalg.norm(d, axis=1, keepdims=True)
        cos = d[:, 2]
        colors[idx] = [0.92, 0.9, 0.88, 1]
        colors[idx[cos > 0.9]] = [0.25, 0.15, 0.08, 1]
        colors[idx[cos > 0.985]] = [0.02, 0.02, 0.02, 1]

    eyes = (verts[groups['helper-l-eye']].mean(0) + verts[groups['helper-r-eye']].mean(0)) / 2
    cx, cy = 0.0, eyes[1] - 0.25
    scale = 3.0  # decimeters across the frame

    bl.reset()
    ob = bl.mesh_object('head', verts, faces.tolist())
    bl.set_point_colors(ob, colors)
    ob.data.materials.append(bl.attribute_material('skin'))
    bl.area_light('key', (3, eyes[1] + 4, 12), (0, eyes[1], 0), 2500)
    bl.area_light('fill', (-6, eyes[1], 10), (0, eyes[1], 0), 900)
    bl.ortho_camera((cx, cy), scale)
    out = BUILD / 'face_corr_render.png'
    bl.render(out, RES, RES, samples=24)

    img = np.asarray(Image.open(out).convert('RGB'))
    opts = vision.FaceLandmarkerOptions(base_options=mpt.BaseOptions(model_asset_path=model_path('face')), num_faces=1)
    with vision.FaceLandmarker.create_from_options(opts) as fl:
        res = fl.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=np.ascontiguousarray(img)))
    if not res.face_landmarks:
        raise SystemExit('MediaPipe found no face in the render')
    lm = np.array([[p.x * RES, p.y * RES] for p in res.face_landmarks[0]])

    tris, _ = shape.triangles(faces)
    bvh = BVHTree.FromPolygons([Vector(v) for v in verts], tris.tolist())
    corr = []
    for px, py in lm:
        wx = cx + (px / RES - 0.5) * scale
        wy = cy - (py / RES - 0.5) * scale
        hit, _, ti, _ = bvh.ray_cast(Vector((wx, wy, 50.0)), Vector((0, 0, -1)))
        if hit is None:
            corr.append(None)
            continue
        a, b, c = (verts[i] for i in tris[ti])
        bary = barycentric(np.array(hit), a, b, c)
        corr.append({'tri': tris[ti].tolist(), 'bary': bary.round(5).tolist()})

    (BUILD / 'face_corr.json').write_text(json.dumps(corr))
    dbg = Image.open(out).convert('RGB')
    d = ImageDraw.Draw(dbg)
    for x, y in lm:
        d.point((x, y), fill=(0, 255, 0))
    dbg.save(BUILD / 'face_corr_debug.png')
    print(f'{sum(c is not None for c in corr)}/{len(corr)} landmarks mapped onto the mesh')


def barycentric(p, a, b, c):
    v0, v1, v2 = b - a, c - a, p - a
    d00, d01, d11 = v0 @ v0, v0 @ v1, v1 @ v1
    d20, d21 = v2 @ v0, v2 @ v1
    den = d00 * d11 - d01 * d01
    v = (d11 * d20 - d01 * d21) / den
    w = (d00 * d21 - d01 * d20) / den
    return np.array([1 - v - w, v, w])


if __name__ == '__main__':
    main()
