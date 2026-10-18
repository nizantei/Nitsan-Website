"""Sneakers: "Materials Variants Shoe" © 2021 Shopify, CC BY 4.0 (Khronos glTF-Sample-Assets),
recolored to an off-white knit with tonal stripes, logo removed (the license excludes logos),
then fitted to each foot. Attribution is required wherever the model is shown: see README.

  prep_textures()   build/shoe/{color,normal,orm}.png from the downloaded asset
  place(...)        (inside Blender) imports the shoe and fits it to one foot
"""
import json
import math
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

HERE = Path(__file__).resolve().parent
CACHE = HERE / 'cache' / 'shoe'
OUT = HERE / 'build' / 'shoe'
URL = 'https://raw.githubusercontent.com/KhronosGroup/glTF-Sample-Assets/main/Models/MaterialsVariantsShoe/glTF-Binary/MaterialsVariantsShoe.glb'
LOGO_BOX = (540, 600, 650, 730)  # x0, y0, x1, y1 in the 2048 texture: the mark on the tongue tab


def _load(name):
    return np.asarray(Image.open(CACHE / name).convert('RGB'), np.float32) / 255.0


def _inpaint(img, mask, iters=200):
    """Fill masked pixels by repeated averaging of their neighbors (keeps the surroundings)."""
    out = img.copy()
    ys, xs = np.where(mask)
    if not len(ys):
        return out
    y0, y1 = max(ys.min() - 4, 0), ys.max() + 5
    x0, x1 = max(xs.min() - 4, 0), xs.max() + 5
    sub, m = out[y0:y1, x0:x1], mask[y0:y1, x0:x1]
    idx = ndimage.distance_transform_edt(m, return_distances=False, return_indices=True)
    sub[m] = sub[idx[0][m], idx[1][m]]
    k = np.ones((3, 3), np.float32) / 9
    for _ in range(iters):
        blur = np.stack([ndimage.convolve(sub[..., c], k, mode='nearest') for c in range(sub.shape[-1])], -1)
        sub[m] = blur[m]
    return out


def prep_textures(cfg):
    OUT.mkdir(parents=True, exist_ok=True)
    street, beach = _load('diffuseStreet.jpg'), _load('diffuseBeach.jpg')
    red = (street[..., 0] - street[..., 1:].max(-1)) > 0.12
    x0, y0, x1, y1 = LOGO_BOX
    logo = np.zeros(red.shape, bool)
    logo[y0:y1, x0:x1] = red[y0:y1, x0:x1]
    logo = ndimage.binary_dilation(logo, iterations=6)
    accent = red & ~logo

    color = street.copy()
    # Knit upper: the regions that are pink in the "Beach" variant, recolored with their knit pattern.
    lum = beach @ np.array([0.299, 0.587, 0.114], np.float32)
    upper = (beach[..., 0] - beach[..., 2] > 0.03) & (lum > 0.45) & (lum < 0.92)
    upper = ndimage.binary_opening(upper, iterations=1)
    rel = lum / np.median(lum[upper])
    color[upper] = np.array(cfg['upper_rgb'], np.float32)[None] * np.clip(0.55 + 0.45 * rel[upper], 0.6, 1.1)[:, None]
    stripe = np.array(cfg['stripe_rgb'], np.float32)
    shade = (street @ np.array([0.299, 0.587, 0.114], np.float32)) / max(np.median((street @ np.array([0.299, 0.587, 0.114]))[accent]), 1e-3)
    color[accent] = stripe[None] * np.clip(shade[accent], 0.8, 1.15)[:, None]
    color = _inpaint(color, logo)
    Image.fromarray((np.clip(color, 0, 1) * 255 + 0.5).astype(np.uint8)).save(OUT / 'color.png')
    for name, out in (('normal.jpg', 'normal.png'), ('occlusionRougnessMetalness.jpg', 'orm.png')):
        img = _inpaint(_load(name), logo)
        Image.fromarray((img * 255 + 0.5).astype(np.uint8)).save(OUT / out)
    return OUT


def foot_frame(V, reg, side, J, floor):
    """Heel point, toe direction and length of one foot (MakeHuman units, dm)."""
    import mh
    g = mh.vertex_groups()
    body = np.zeros(len(V), bool)
    body[g['body']] = True
    sgn = 1 if side == 'l' else -1
    P = V[body & (reg['foot'] > 0.4) & (np.sign(V[:, 0]) == sgn)]
    low = P[P[:, 1] < floor + 0.5]
    heel = low[np.argmin(low[:, 2])]
    toe = low[np.argmax(low[:, 2])]
    d = toe - heel
    d[1] = 0
    length = np.linalg.norm(d)
    width = np.ptp(low[:, 0])
    return {'heel': heel, 'toe': toe, 'dir': d / length, 'length': length, 'width': width,
            'ankle': J[f'joint-{side}-ankle']}


def place(side, frame, cfg, to_bl, collection):
    """Import the shoe (a left shoe: toe +X, medial -Y, sole at z=0) and fit it to one foot.
    The right shoe is the mirror image. Returns the Blender object, named shoe_<side>."""
    import bpy
    if not (CACHE / 'MaterialsVariantsShoe.glb').exists():
        raise SystemExit(f'missing {CACHE}/MaterialsVariantsShoe.glb: run fetch_assets.sh')
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(CACHE / 'MaterialsVariantsShoe.glb'))
    new = [o for o in bpy.data.objects if o not in before]
    src = next(o for o in new if o.type == 'MESH')
    me = src.data.copy()
    me.transform(src.matrix_world)
    for o in new:
        bpy.data.objects.remove(o)
    co = np.array([v.co[:] for v in me.vertices])
    heel_x, toe_x = co[:, 0].min(), co[:, 0].max()
    y_mid = (co[:, 1].min() + co[:, 1].max()) / 2
    s = (frame['length'] * 0.1 + cfg['allowance']) / (toe_x - heel_x)
    d = to_bl(frame['dir'][None])[0]
    d[2] = 0
    d /= np.linalg.norm(d)
    up = np.array([0.0, 0.0, 1.0])
    R = np.stack([d, np.cross(up, d), up], 1)  # shoe x → toe direction, y → lateral axis, z → up
    S = np.diag([s, -s if side == 'r' else s, s])  # the right shoe is the mirror image
    heel = to_bl(frame['heel'][None])[0]
    floor_z = to_bl(np.array([[0.0, frame['floor'], 0.0]]))[0, 2]
    offset = np.r_[(heel - d * cfg['heel_gap'])[:2], floor_z - cfg['insole']]
    M = np.eye(4)
    M[:3, :3] = R @ S
    M[:3, 3] = offset - R @ S @ np.array([heel_x, y_mid, 0.0])
    ob = bpy.data.objects.new(f'shoe_{side}', me)
    collection.objects.link(ob)
    from mathutils import Matrix
    ob.matrix_world = Matrix(M.tolist())
    bpy.ops.object.select_all(action='DESELECT')
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)  # also flips the mirrored faces
    me.materials.clear()
    return ob
