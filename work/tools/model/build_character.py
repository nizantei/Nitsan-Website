"""Step 4: build the dressed, posed character in Blender.

  - skeleton from MPFB2's default rig (joint positions follow the fitted body)
  - crossed arms by IK, with wrist/elbow targets placed from the photo
  - tee / trousers / belt cut from the body surface, sneakers fitted to the feet (shoes.py), mouth fill
  - eyes with a procedural iris, necklace and bead bracelet traced from the photo (extras.py)
  - body faces hidden under clothes removed; head and arm skin split into separate objects
  - UVs packed per object; position / normal / visibility maps baked for texture.py

Output: build/character.blend, build/bake/*.npz, build/bake/meta.json, build/preview/pose_*.png
Run:  .venv/bin/python build_character.py [--preview-only | --guide]
  --guide  shapes only (for lowpoly.py): no UV packing, bakes or licensed shoe asset
"""
import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import bpy
import bmesh
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from PIL import Image

import bl
import cameras
import extras
import garments as G
import mh
import shape
import shoes

BUILD = HERE / 'build'
S = 0.1  # MakeHuman decimeters → meters
GUIDE = '--guide' in sys.argv  # build only the guide shapes for lowpoly.py (no textures)


def to_bl(P):
    P = np.asarray(P, float)
    return np.stack([P[..., 0], -P[..., 2], P[..., 1]], -1) * S


def from_bl(P):
    P = np.asarray(P, float) / S
    return np.stack([P[..., 0], P[..., 2], -P[..., 1]], -1)


# ---------- photo camera ----------

FACE_DIST_DM = 8.0  # lens → face surface; MediaPipe puts the head center ~86 cm from the lens


def body_camera(V, J, corr, photo_pose, photo_face, head_cam, image_size):
    """Pinhole camera for the body, fitted to shoulders, hips and the nose tip."""
    def surf(i):
        c = corr[i]
        return (V[c['tri']] * np.array(c['bary'])[:, None]).sum(0)
    nose = surf(1)
    model = [J['joint-l-shoulder'], J['joint-r-shoulder'], J['joint-l-upper-leg'], J['joint-r-upper-leg'], nose]
    photo = [photo_pose[11][:2], photo_pose[12][:2], photo_pose[23][:2], photo_pose[24][:2], photo_face[1][:2]]
    face_z = np.mean([surf(i)[2] for i in (1, 33, 263, 61, 291, 152)])
    s_head = np.linalg.norm(head_cam[0, :3])
    cam, err = cameras.fit_body(model, photo, [1, 1, 0.35, 0.35, 1.5], s_head, face_z, FACE_DIST_DM, image_size)
    return cam, {'reprojection_px': np.round(err, 1).tolist(), 'roll_deg': round(math.degrees(cam.roll), 2)}


# ---------- Blender helpers ----------

def make_object(name, P_mh, faces, uv=None, uv_faces=None, collection=None, recalc=False):
    ob = bl.mesh_object(name, to_bl(P_mh), np.asarray(faces).tolist(), collection=collection)
    me = ob.data
    if uv is not None:
        layer = me.uv_layers.new(name='UVMap')
        loops = []
        for f, fu in zip(np.asarray(faces).tolist(), np.asarray(uv_faces).tolist()):
            seen = []
            for vi, ui in zip(f, fu):
                if vi not in seen:
                    seen.append(vi)
                    loops.append(uv[ui])
        layer.data.foreach_set('uv', np.asarray(loops, np.float32).ravel())
    if recalc:
        fix_normals(ob)
    return ob


def fix_normals(ob, outward=True):
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    if outward:
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(ob.data)
    bm.free()


def add_groups(ob, used, weights):
    """Vertex groups from MakeHuman skin weights; `used` maps object vertex → base vertex."""
    inv = -np.ones(len(mh.base_mesh()['verts']), np.int64)
    inv[used] = np.arange(len(used))
    for bone, (idx, w) in weights.items():
        sel = inv[idx] >= 0
        if not sel.any():
            continue
        vg = ob.vertex_groups.new(name=bone)
        for vi, ww in zip(inv[idx][sel].tolist(), w[sel].tolist()):
            vg.add([vi], ww, 'REPLACE')


def build_armature(V):
    arm = bpy.data.armatures.new('rig')
    ob = bpy.data.objects.new('rig', arm)
    bpy.context.scene.collection.objects.link(ob)
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.mode_set(mode='EDIT')
    groups = mh.vertex_groups()

    def pos(spec):
        st = spec['strategy']
        if st == 'CUBE':
            p = V[groups[spec['cube_name']]].mean(0)
        elif st == 'VERTEX':
            p = V[spec['vertex_index']]
        else:
            p = V[spec['vertex_indices']].mean(0)
        return Vector(to_bl(p))

    rig = mh.rig()
    for name, b in rig.items():
        eb = arm.edit_bones.new(name)
        eb.head = pos(b['head'])
        eb.tail = pos(b['tail'])
        if (eb.tail - eb.head).length < 1e-4:
            eb.tail = eb.head + Vector((0, 0, 0.01))
        eb.roll = b['roll']
    for name, b in rig.items():
        if b.get('parent'):
            arm.edit_bones[name].parent = arm.edit_bones[b['parent']]
            arm.edit_bones[name].use_connect = b.get('use_connect', False)
    bpy.ops.object.mode_set(mode='OBJECT')
    return ob


def empty(name, p_mh):
    e = bpy.data.objects.new(name, None)
    e.location = Vector(to_bl(p_mh))
    bpy.context.scene.collection.objects.link(e)
    return e


def pose_arms(rig_ob, targets, cfg):
    for side in ('L', 'R'):
        t = empty(f'ik_{side}', targets[side]['wrist'])
        p = empty(f'pole_{side}', targets[side]['pole'])
        pb = rig_ob.pose.bones[f'lowerarm02.{side}']
        c = pb.constraints.new('IK')
        c.target = t
        c.pole_target = p
        c.pole_angle = math.radians(cfg['pole_angle'])
        c.chain_count = 4
        c.use_tail = True
        for twist in (f'upperarm02.{side}', f'lowerarm02.{side}'):
            b = rig_ob.pose.bones[twist]
            b.lock_ik_x = b.lock_ik_y = b.lock_ik_z = True
        for b in rig_ob.pose.bones:
            n = b.name
            if n.endswith('.' + side) and n.startswith('finger'):
                b.rotation_mode = 'XYZ'
                curl = cfg['thumb_curl'] if n.startswith('finger1') else cfg['finger_curl']
                b.rotation_euler = (math.radians(curl), 0, 0)
    bpy.context.view_layer.update()


def evaluated_coords(ob):
    dg = bpy.context.evaluated_depsgraph_get()
    ev = ob.evaluated_get(dg)
    me = ev.to_mesh()
    co = np.empty(len(me.vertices) * 3, np.float32)
    me.vertices.foreach_get('co', co)
    ev.to_mesh_clear()
    return co.reshape(-1, 3).astype(float)


# ---------- main ----------

def build(ch, preview_only=False):
    d = np.load(BUILD / 'shape.npz')
    V, head_cam = d['verts'], d['head_cam']
    corr = json.loads((BUILD / 'face_corr.json').read_text())
    photo_pose = json.loads((BUILD / 'analysis' / 'pose.json').read_text())['points']
    face_json = json.loads((BUILD / 'analysis' / 'face.json').read_text())
    base = mh.base_mesh()
    F, FU, UV, fg = base['faces'], base['face_uvs'], base['uvs'], base['face_group']
    reg = G.regions()
    J, floor, hip_y = G.body_frame(V)
    out = ch['outfit']
    belt_y = hip_y + out['pants']['waist_above_hip']
    ankle_y = (J['joint-l-ankle'][1] + J['joint-r-ankle'][1]) / 2
    body_fm = fg == 'body'
    FB, FUB = F[body_fm], FU[body_fm]

    # Garments (rest pose)
    tee_m = G.tee(V, FB, reg, out['tee'], belt_y)
    tee_used, tee_f, tee_P, tee_fm = G.shell(V, FB, tee_m, out['tee']['offset'])
    nb = G.neighbors(tee_f, len(tee_used))
    tee_P = G.smooth(tee_P, nb, np.arange(len(tee_used)), out['tee']['smooth'], 0.4, fixed=G.boundary_vertices(tee_f))
    tee_P = G.smooth_boundary(tee_P, tee_f, iters=8)
    tee_P = G.keep_clearance(tee_P, tee_used, V, FB, out['tee']['offset'] * 0.8)

    pants_m = G.pants(V, reg, out['pants'], belt_y, ankle_y)
    pants_used, pants_f, pants_P, pants_fm = G.shell(V, FB, pants_m, out['pants']['offset'])
    pants_P = G.shape_pants(pants_P, pants_used, V, reg, out['pants'])
    nb = G.neighbors(pants_f, len(pants_used))
    crotch_y = V[pants_used][np.abs(V[pants_used, 0]) < 0.15, 1].min()
    seat = np.where((V[pants_used, 1] < belt_y - 0.2) & (V[pants_used, 1] > crotch_y - 1.4)
                    & ((reg['leg'][pants_used] < 0.85) | (np.abs(V[pants_used, 0]) < 0.75)))[0]
    pants_P = G.smooth(pants_P, nb, seat, 30, 0.5)
    pants_P = G.flatten_fly(pants_P, pants_used, V, crotch_y)
    pants_P = G.fill_crotch(pants_P, pants_used, V, crotch_y)
    pants_P = G.smooth(pants_P, nb, seat, 6, 0.5)
    pants_P = G.smooth(pants_P, nb, np.arange(len(pants_used)), 3, 0.45, fixed=G.boundary_vertices(pants_f))
    hem = [k for k in G.boundary_loops_neighbors(pants_f) if pants_P[k, 1] < hip_y - 3]
    if hem:  # stretch the lower legs so the hem reaches its target height (over the shoe)
        knee_y = (J['joint-l-knee'][1] + J['joint-r-knee'][1]) / 2
        target = ankle_y + out['pants']['hem_above_ankle']
        cur = pants_P[hem, 1].min()
        if cur > target:
            low = pants_P[:, 1] < knee_y
            pants_P[low, 1] = knee_y + (pants_P[low, 1] - knee_y) * (knee_y - target) / (knee_y - cur)
    hem_y = pants_P[hem, 1].min() if hem else None
    if hem:
        pants_P[hem, 1] = hem_y
        pants_P = G.smooth_boundary(pants_P, pants_f, iters=6, select=lambda p: p[1] < hip_y - 3)
    pants_P = G.smooth_boundary(pants_P, pants_f, iters=6, select=lambda p: p[1] > belt_y - 0.5)
    pants_P = G.keep_clearance(pants_P, pants_used, V, FB, out['pants']['offset'] * 0.7)
    belt_v, belt_f, belt_uv, belt_uvf, (buckle_v, buckle_f) = G.belt_solid(pants_P, out['belt'], belt_y)
    loops_v, loops_f = G.belt_loops(pants_P, belt_y, out['belt'])

    # Body faces hidden by clothes: everything under the tee (except a margin at the collar and
    # sleeves), everything under the trousers, and the feet.
    hidden_v = G.erode(tee_m, FB, 4) | pants_m | (reg['foot'] > 0.2) | (V[:, 1] < ankle_y + 0.6)
    keep_f = ~hidden_v[FB].all(1)
    armish = (reg['upperarm'] + reg['lowerarm'] + reg['hand'])[FB].mean(1) > 0.5
    head_f = keep_f & ~armish  # head, neck and any torso skin that shows at the collar
    skin_f = keep_f & armish   # arms and hands

    # Pose: one skinned object with every base vertex (so indices stay put), plus the tee.
    bl.reset()
    rig_ob = build_armature(V)
    keep_all = np.isin(fg, ['body', 'helper-l-eye', 'helper-r-eye'])
    posebody = bl.mesh_object('posebody', to_bl(V), F[keep_all].tolist())
    add_groups(posebody, np.arange(len(V)), mh.skin_weights())
    tee_ob = bl.mesh_object('posetee', to_bl(tee_P), tee_f.tolist())
    add_groups(tee_ob, tee_used, mh.skin_weights())
    for ob in (posebody, tee_ob):
        ob.parent = rig_ob
        ob.modifiers.new('rig', 'ARMATURE').object = rig_ob

    cam_body, cam_info = body_camera(V, J, corr, photo_pose, face_json['points'], head_cam, face_json['size'])
    pc = ch['pose']
    torso_front = V[(reg['torso'] > 0.5)]
    def front_z(p):
        near = torso_front[np.hypot(torso_front[:, 0] - p[0], torso_front[:, 1] - p[1]) < 0.45]
        return near[:, 2].max() if len(near) else J['joint-neck'][2] + 1.0
    targets = {}
    for side, s_name, sgn in (('R', 'right', -1), ('L', 'left', 1)):
        guess = cam_body.unproject(pc[f'{s_name}_wrist_px'], J['joint-neck'][2] + 1.0)
        wrist = cam_body.unproject(pc[f'{s_name}_wrist_px'], front_z(guess) + pc[f'{s_name}_wrist_depth'])
        sh = J[f'joint-{side.lower()}-shoulder']
        elbow = cam_body.unproject(pc[f'{s_name}_elbow_px'], sh[2] + pc['elbow_forward'])
        pole = elbow + np.array([sgn * 2.0, -0.5, 0.8])
        targets[side] = {'wrist': wrist, 'elbow': elbow, 'pole': pole}
    pose_arms(rig_ob, targets, pc)

    Vp = from_bl(evaluated_coords(posebody))
    teeP = from_bl(evaluated_coords(tee_ob))
    for ob in (posebody, tee_ob):
        bpy.data.objects.remove(ob)
    rig_ob.hide_render = True

    # Final objects (posed, MakeHuman units → Blender meters)
    col = bpy.data.collections.new('character')
    bpy.context.scene.collection.children.link(col)
    objs = {}
    hf, hfu = FB[head_f], FUB[head_f]
    used, hf_local = G.submesh(hf, np.ones(len(hf), bool))
    mf_v, mf_f = G.mouth_fill(Vp, corr)
    head_P = np.vstack([Vp[used], mf_v])
    xy = mf_v[:, :2]
    mf_uv = 0.02 + 0.08 * (xy - xy.min(0)) / np.ptp(xy, 0).max()  # planar UV (needs real area for packing)
    head_faces = np.vstack([hf_local, mf_f + len(used)])
    uv_all = np.vstack([UV, mf_uv])
    head_uvf = np.vstack([hfu, np.arange(len(mf_v))[mf_f] + len(UV)])
    objs['head'] = make_object('head', head_P, head_faces, uv_all, head_uvf, col)
    # The mouth fill always takes the photo (the lips would block visibility rays).
    force = np.r_[np.zeros(len(used), np.float32), np.ones(len(mf_v), np.float32)]
    attr = objs['head'].data.attributes.new('force_photo', 'FLOAT', 'POINT')
    attr.data.foreach_set('value', force)

    used, f_local = G.submesh(FB[skin_f], np.ones(skin_f.sum(), bool))
    objs['skin'] = make_object('skin', Vp[used], f_local, UV, FUB[skin_f], col)
    objs['tee'] = make_object('tee', teeP, tee_f, UV, FUB[tee_fm], col)
    objs['pants'] = make_object('pants', pants_P, pants_f, UV, FUB[pants_fm], col)
    objs['belt'] = make_object('belt', belt_v, belt_f, belt_uv, belt_uvf, col, recalc=True)
    objs['buckle'] = make_object('buckle', buckle_v, buckle_f, collection=col, recalc=True)
    objs['loops'] = make_object('loops', loops_v, loops_f, collection=col, recalc=True)
    if not GUIDE:  # the low-poly model builds its own sneakers
        for side in ('l', 'r'):
            frame = shoes.foot_frame(V, reg, side, J, floor)
            frame['floor'] = floor
            objs[f'shoe_{side}'] = shoes.place(side, frame, out['sneakers'], to_bl, col)

    # Eyes: the posed MakeHuman eyeballs, UVs aimed where the photo shows each iris.
    eyes = {}
    for side, iris_lm in (('l', 473), ('r', 468)):
        idx = mh.vertex_groups()[f'helper-{side}-eye']
        efm = fg == f'helper-{side}-eye'
        e_used, e_f = G.submesh(F, efm)
        ob = make_object(f'eye_{side}', Vp[e_used], e_f, collection=col)
        c_mh = Vp[idx].mean(0)
        r_mh = float(np.median(np.linalg.norm(Vp[idx] - c_mh, axis=1)))
        g_mh = extras.gaze_from_photo(c_mh, r_mh, np.asarray(head_cam), face_json['points'][iris_lm])
        c = to_bl(c_mh[None])[0]
        radius = r_mh * S
        gaze = to_bl(g_mh[None])[0]
        iris_uv = extras.aim_eye_uvs(ob, c, gaze, radius)
        objs[f'eye_{side}'] = ob
        eyes[side] = {'center': c.tolist(), 'radius': radius, 'iris_uv': iris_uv}

    # Necklace over the neck and tee; bead bracelet on the left forearm.
    acc = ch['accessories']
    surf = extras.bvh_of([objs['head'], objs['tee']])
    def cam_ray(px):
        a, b = cam_body.unproject(px, 0.0), cam_body.unproject(px, -2.0)
        o = to_bl(cam_body.cam[None])[0]
        d = to_bl(b[None])[0] - to_bl(a[None])[0]
        return o, d / np.linalg.norm(d)
    neck_c = to_bl(J['joint-neck'][None])[0]
    path = extras.chain_path(acc['necklace_px'], cam_ray, surf, (neck_c, None), lift=0.0011)
    clasp = None
    o, dvec = cam_ray(acc['clasp_px'])
    hit = surf.ray_cast(Vector(o), Vector(dvec), 10.0)[0]
    if hit is not None:
        clasp = np.array(hit)
    cv, cf = extras.cable_chain(path, clasp_at=clasp)
    objs['necklace'] = extras.make('necklace', cv, cf, col)

    arm_bvh = extras.bvh_of([objs['skin']])
    rig_mw = np.array(rig_ob.matrix_world)
    def bone_pt(name, tail=False):
        b = rig_ob.pose.bones[name]
        p = np.array((b.tail if tail else b.head)[:] + (1.0,))
        return (rig_mw @ p)[:3]
    elbow, wrist = bone_pt('lowerarm01.L'), bone_pt('lowerarm02.L', tail=True)
    o, dvec = cam_ray(acc['bracelet_px'])
    axis = wrist - elbow
    # point on the forearm axis closest to the photo ray through the beads
    w0 = elbow - o
    a_, b_, c_ = axis @ axis, axis @ dvec, dvec @ dvec
    t = np.clip((b_ * (dvec @ w0) - c_ * (axis @ w0)) / (a_ * c_ - b_ * b_), 0.55, 0.97)
    center = elbow + t * axis
    br = acc['bead_radius']
    ring_r = extras.surface_radius(arm_bvh, center, axis) + br * 0.9
    bv, bf = extras.bead_ring(center, axis, ring_r, br)
    objs['bracelet'] = extras.make('bracelet', bv, bf, col)

    meta = {
        'body_cam': cam_body.to_json(), 'head_cam': np.asarray(head_cam).tolist(), 'cam_info': cam_info,
        'belt_y': belt_y, 'floor': floor,
        'eye_y': float((V[mh.vertex_groups()['helper-l-eye']].mean(0)[1] + V[mh.vertex_groups()['helper-r-eye']].mean(0)[1]) / 2),
        'eyes_bl': [to_bl(Vp[mh.vertex_groups()[f'helper-{s}-eye']].mean(0)).tolist() for s in ('l', 'r')],
        'eye_radius_bl': float(np.linalg.norm(Vp[mh.vertex_groups()['helper-l-eye']] - Vp[mh.vertex_groups()['helper-l-eye']].mean(0), axis=1).max() * S), 'targets': {k: {kk: vv.tolist() for kk, vv in v.items()} for k, v in targets.items()},
        'eyes': eyes,
        'tailor': {
            'legs': {sd: {'hip': to_bl(J[f'joint-{sd}-upper-leg'][None])[0].tolist(), 'ankle': to_bl(J[f'joint-{sd}-ankle'][None])[0].tolist()} for sd in ('l', 'r')},
            'belt_z': belt_y * S, 'crotch_z': crotch_y * S, 'hem_z': (hem_y if hem_y is not None else ankle_y) * S,
            'center_y': float(to_bl(((J['joint-l-upper-leg'] + J['joint-r-upper-leg']) / 2)[None])[0, 1]),
            'hip_half': float(np.abs(pants_P[np.abs(pants_P[:, 1] - hip_y) < 0.3, 0]).max() * S),
            **out['pants'].get('tailor', {'crease': 0.0025, 'pleat': 0.004, 'break': 0.004}),
        },
    }
    return objs, meta, rig_ob


def preview(objs, meta, tag):
    """Clay renders: front / three-quarter / profile, and a front render aligned to the photo."""
    colors = {'head': (0.75, 0.55, 0.47), 'skin': (0.75, 0.55, 0.47), 'tee': (0.05, 0.05, 0.07), 'pants': (0.6, 0.55, 0.45),
              'belt': (0.05, 0.05, 0.05), 'buckle': (0.8, 0.8, 0.8)}
    for name, ob in objs.items():
        mat = bpy.data.materials.new('clay_' + name)
        c = colors.get(name, (0.93, 0.93, 0.9))
        mat.node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value = (*c, 1)
        ob.data.materials.clear()
        ob.data.materials.append(mat)
        mod = ob.modifiers.new('sub', 'SUBSURF')
        mod.levels = mod.render_levels = 1 if name in ('head', 'skin', 'tee', 'pants', 'shoe_l', 'shoe_r') else 0
    out = BUILD / 'preview'
    target = (0, 0, 0.1)
    bl.area_light('key', (2.5, -4, 3), target, 900, 3)
    bl.area_light('fill', (-4, -2, 1.5), target, 350, 3)
    bl.area_light('rim', (0, 4, 3), target, 500, 3)
    cam = bpy.data.cameras.new('cam')
    cam.type = 'ORTHO'
    cam.ortho_scale = 2.0
    co = bpy.data.objects.new('cam', cam)
    bpy.context.scene.collection.objects.link(co)
    bpy.context.scene.camera = co
    shots = []
    for view, ang in (('front', 0), ('three-quarter', 40), ('profile', 90), ('back', 180)):
        a = math.radians(ang)
        co.location = (8 * math.sin(a), -8 * math.cos(a), 0.1)
        co.rotation_euler = (math.pi / 2, 0, a)
        p = out / f'pose_{tag}_{view}.png'
        bl.render(p, 420, 840, samples=12)
        shots.append(p)
    sheet = Image.new('RGB', (420 * 4, 840))
    for i, p in enumerate(shots):
        sheet.paste(Image.open(p), (i * 420, 0))
    sheet.save(out / f'pose_{tag}_sheet.png')

    # Front view through the photo's body camera, blended over the photo.
    cb = cameras.Perspective.from_json(meta['body_cam'])
    photo = Image.open(BUILD / 'analysis' / 'photo.png').convert('RGB')
    W, H = photo.size
    cam.type = 'PERSP'
    cam.sensor_fit = 'HORIZONTAL'
    cam.sensor_width = 36
    cam.lens = cb.f * 36 / W
    cam.clip_start = 0.05
    co.location = tuple(to_bl(cb.cam))
    co.rotation_euler = (math.pi / 2, cb.roll, 0)
    p = out / f'pose_{tag}_photo_match.png'
    bl.render(p, W // 2, H // 2, samples=8)
    Image.blend(photo.resize((W // 2, H // 2)), Image.open(p).convert('RGB'), 0.55).save(out / f'pose_{tag}_overlay.png')


def main():
    ch = shape.character()
    objs, meta, rig_ob = build(ch)
    (BUILD / 'bake').mkdir(exist_ok=True)
    (BUILD / 'bake' / 'meta.json').write_text(json.dumps(meta, indent=1))
    print('body camera:', meta['cam_info'])
    if '--preview-only' in sys.argv:
        preview(objs, meta, 'v1')
        return
    import bake
    if GUIDE:  # the low-poly model only needs the shapes: smooth them, skip UVs and bakes
        bake.subdivide(objs)
        bake.tailor(objs['pants'], meta['tailor'])
    else:
        bake.run(objs, meta, BUILD, to_bl, from_bl)
    bpy.ops.wm.save_as_mainfile(filepath=str(BUILD / 'character.blend'))


if __name__ == '__main__':
    main()
