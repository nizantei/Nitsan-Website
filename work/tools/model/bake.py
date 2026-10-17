"""Part of step 4 (runs inside build_character.py's Blender session).

For each textured object: subdivide, pack UVs, then bake three maps that texture.py turns into
colors: world position, normal, and photo visibility (was this surface point in plain view of the
photo's camera, and how squarely). Output: build/bake/<object>.npz
"""
import math

import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

import cameras

TEXTURED = {'head': 2048, 'skin': 2048, 'tee': 1024, 'pants': 1024, 'belt': 512}
SUBDIVIDE = {'head': 1, 'skin': 1, 'tee': 1, 'pants': 1, 'shoe_l': 1, 'shoe_r': 1}


def apply_modifiers(ob):
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(ob.evaluated_get(dg), preserve_all_data_layers=True, depsgraph=dg)
    ob.modifiers.clear()
    old = ob.data
    ob.data = me
    bpy.data.meshes.remove(old)


def subdivide(objs):
    for name, levels in SUBDIVIDE.items():
        ob = objs[name]
        m = ob.modifiers.new('sub', 'SUBSURF')
        m.levels = m.render_levels = levels
        m.uv_smooth = 'PRESERVE_BOUNDARIES'
        apply_modifiers(ob)


def pack_uvs(ob, margin=0.004):
    bpy.ops.object.select_all(action='DESELECT')
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.uv.select_all(action='SELECT')
    bpy.ops.uv.average_islands_scale()
    bpy.ops.uv.pack_islands(rotate=True, margin=margin)
    bpy.ops.object.mode_set(mode='OBJECT')


def mesh_arrays(ob):
    me = ob.data
    n = len(me.vertices)
    co = np.empty(n * 3, np.float32)
    me.vertices.foreach_get('co', co)
    no = np.empty(n * 3, np.float32)
    me.vertices.foreach_get('normal', no)
    return co.reshape(-1, 3).astype(float), no.reshape(-1, 3).astype(float)


def visibility(objs, meta, to_bl, from_bl):
    """Per-vertex: R = unobstructed toward the photo camera, G = facing (cosine), for every
    textured object. The head uses the head camera (landmark fit), the rest the body camera."""
    all_v, all_t = [], []
    off = 0
    for ob in objs.values():
        co, _ = mesh_arrays(ob)
        me = ob.data
        me.calc_loop_triangles()
        tris = np.empty(len(me.loop_triangles) * 3, np.int64)
        me.loop_triangles.foreach_get('vertices', tris)
        all_v.append(co)
        all_t.append(tris.reshape(-1, 3) + off)
        off += len(co)
    bvh = BVHTree.FromPolygons([Vector(p) for p in np.vstack(all_v)], np.vstack(all_t).tolist())

    body_cam = cameras.Perspective.from_json(meta['body_cam'])
    head_cam = np.array(meta['head_cam'])
    a, b = head_cam[0, :3], head_cam[1, :3]
    head_dir_mh = np.cross(a, b)
    head_dir_mh /= np.linalg.norm(head_dir_mh)
    if head_dir_mh[2] < 0:
        head_dir_mh = -head_dir_mh
    head_dir = to_bl(head_dir_mh[None])[0]
    head_dir /= np.linalg.norm(head_dir)

    for name in TEXTURED:
        ob = objs[name]
        co, no = mesh_arrays(ob)
        if name == 'head':
            # Face: head camera direction; neck: blends to the body camera (matches texture.py).
            cam_bl = to_bl(body_cam.cam[None])[0]
            d = cam_bl - co
            body_dirs = d / np.linalg.norm(d, axis=1, keepdims=True)
            h = from_bl(co)[:, 1] - meta['eye_y']
            t = np.clip((h - -1.3) / (-1.85 - -1.3), 0, 1)
            t = (t * t * (3 - 2 * t))[:, None]
            dirs = np.tile(head_dir, (len(co), 1)) * (1 - t) + body_dirs * t
            dirs /= np.linalg.norm(dirs, axis=1, keepdims=True)
            far = np.where(t[:, 0] > 0.5, np.linalg.norm(d, axis=1), 50.0)
        else:
            cam_bl = to_bl(body_cam.cam[None])[0]
            d = cam_bl - co
            far = np.linalg.norm(d, axis=1)
            dirs = d / far[:, None]
        facing = np.clip((no * dirs).sum(1), 0, 1)
        vis = np.zeros(len(co))
        for i in np.where(facing > 0.05)[0]:
            hit = bvh.ray_cast(Vector(co[i] + no[i] * 0.002 + dirs[i] * 0.001), Vector(dirs[i]), far[i])
            vis[i] = 1.0 if hit[0] is None else 0.0
        force = np.zeros(len(co))
        if 'force_photo' in ob.data.attributes:
            ob.data.attributes['force_photo'].data.foreach_get('value', f := np.zeros(len(co), np.float32))
            force = (f > 0.5).astype(float)
        vis = np.maximum(vis, force)
        facing = np.minimum(facing, 1.0) + 2.0 * force  # >= 2 marks "always use the photo"
        attr = ob.data.color_attributes.new('vis', 'FLOAT_COLOR', 'POINT')
        attr.data.foreach_set('color', np.c_[vis, facing, np.ones_like(vis), np.ones_like(vis)].astype(np.float32).ravel())  # B = coverage


def bake_object(ob, size, outfile):
    """Bake position, normal and the 'vis' attribute into float images, save as npz."""
    mat = bpy.data.materials.new(f'bake_{ob.name}')
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new('ShaderNodeOutputMaterial')
    emit = nt.nodes.new('ShaderNodeEmission')
    geo = nt.nodes.new('ShaderNodeNewGeometry')
    attr = nt.nodes.new('ShaderNodeAttribute')
    attr.attribute_name = 'vis'
    tex = nt.nodes.new('ShaderNodeTexImage')
    nt.links.new(emit.outputs['Emission'], out.inputs['Surface'])
    ob.data.materials.clear()
    ob.data.materials.append(mat)

    bpy.ops.object.select_all(action='DESELECT')
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    scene = bpy.context.scene
    scene.render.engine = 'CYCLES'
    scene.cycles.device = 'CPU'
    scene.cycles.samples = 1
    scene.render.bake.margin = 8
    scene.render.bake.use_clear = True

    maps = {}
    for key, socket in (('pos', geo.outputs['Position']), ('nrm', geo.outputs['Normal']), ('vis', attr.outputs['Color'])):
        img = bpy.data.images.new(f'{ob.name}_{key}', size, size, alpha=True, float_buffer=True)
        img.generated_color = (0, 0, 0, 0)
        tex.image = img
        nt.nodes.active = tex
        nt.links.new(socket, emit.inputs['Color'])
        bpy.ops.object.bake(type='EMIT')
        px = np.empty(size * size * 4, np.float32)
        img.pixels.foreach_get(px)
        maps[key] = px.reshape(size, size, 4)[::-1]  # Blender stores bottom row first
        bpy.data.images.remove(img)
    np.savez_compressed(outfile, pos=maps['pos'][..., :3], nrm=maps['nrm'][..., :3], vis=maps['vis'][..., :2],
                        mask=(maps['vis'][..., 2] > 0.5))
    bpy.data.materials.remove(mat)


def run(objs, meta, build_dir, to_bl, from_bl):
    subdivide(objs)
    for name in TEXTURED:
        pack_uvs(objs[name])
    visibility(objs, meta, to_bl, from_bl)
    for name, size in TEXTURED.items():
        bake_object(objs[name], size, build_dir / 'bake' / f'{name}.npz')
        print('baked', name, size)
