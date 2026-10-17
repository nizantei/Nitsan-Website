"""Debug renders of the fitted head: clay and photo-projected, front / three-quarter / profile.
Output: build/preview/head_*.png.  Run:  .venv/bin/python preview_head.py"""
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import bpy
import numpy as np
from PIL import Image

import bl
import mh

BUILD = HERE / 'build'


def main():
    d = np.load(BUILD / 'shape.npz')
    V, cam = d['verts'], d['head_cam']
    base = mh.base_mesh()
    keep = np.isin(base['face_group'], ['body', 'helper-l-eye', 'helper-r-eye', 'helper-upper-teeth', 'helper-lower-teeth'])
    faces = base['faces'][keep]
    photo = Image.open(BUILD / 'analysis' / 'photo.png')
    W, H = photo.size

    bl.reset()
    ob = bl.mesh_object('head', V, faces.tolist())
    me = ob.data
    uv = me.uv_layers.new(name='photo')
    proj = (cam @ np.c_[V, np.ones(len(V))].T).T
    loop_v = np.zeros(len(me.loops), np.int64)
    me.loops.foreach_get('vertex_index', loop_v)
    uvs = np.stack([proj[loop_v, 0] / W, 1 - proj[loop_v, 1] / H], 1)
    uv.data.foreach_set('uv', uvs.astype(np.float32).ravel())
    mod = ob.modifiers.new('sub', 'SUBSURF')
    mod.levels = mod.render_levels = 1

    clay = bpy.data.materials.new('clay')
    clay.node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value = (0.72, 0.55, 0.47, 1)
    tex = bpy.data.materials.new('photo')
    nt = tex.node_tree
    img = nt.nodes.new('ShaderNodeTexImage')
    img.image = bpy.data.images.load(str(BUILD / 'analysis' / 'photo.png'))
    uvn = nt.nodes.new('ShaderNodeUVMap')
    uvn.uv_map = 'photo'
    nt.links.new(uvn.outputs['UV'], img.inputs['Vector'])
    nt.links.new(img.outputs['Color'], nt.nodes['Principled BSDF'].inputs['Base Color'])
    nt.nodes['Principled BSDF'].inputs['Roughness'].default_value = 0.6
    me.materials.append(clay)

    groups = mh.vertex_groups()
    eye = (V[groups['helper-l-eye']].mean(0) + V[groups['helper-r-eye']].mean(0)) / 2
    target = (0, eye[1] - 0.2, 0)
    bl.area_light('key', (4, eye[1] + 5, 12), target, 2200)
    bl.area_light('fill', (-8, eye[1], 8), target, 800)
    bl.area_light('rim', (0, eye[1] + 4, -10), target, 900)
    camob = bl.ortho_camera((0, target[1]), 3.0)

    out = BUILD / 'preview'
    out.mkdir(exist_ok=True)
    shots = []
    for mat_name, mat in (('clay', clay), ('photo', tex)):
        me.materials[0] = mat
        for view, ang in (('front', 0), ('three-quarter', 35), ('profile', 85)):
            a = math.radians(ang)
            camob.location = (12 * math.sin(a), target[1], 12 * math.cos(a))
            camob.rotation_euler = (0, a, 0)
            path = out / f'head_{mat_name}_{view}.png'
            bl.render(path, 512, 512, samples=16)
            shots.append(path)
    tiles = [Image.open(p) for p in shots]
    sheet = Image.new('RGB', (512 * 3, 512 * 2))
    for i, t in enumerate(tiles):
        sheet.paste(t, ((i % 3) * 512, (i // 3) * 512))
    sheet.save(out / 'head_sheet.png')


if __name__ == '__main__':
    main()
