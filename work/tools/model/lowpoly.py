"""The page's character: a stylized low-poly model (flat-shaded facets, solid colors per region),
built from scratch on top of the photo-fitted guide body (build/character.blend) so that it keeps
your proportions, your pose (crossed arms) and your face.

  head      triangulated over your fitted face landmarks plus sparse skull points (spherical
            Delaunay), colored by region from the photo: hair, stubble, mustache, brows, eyes,
            teeth, lips, skin. Hair, mustache, beard and brows are raised a few millimeters so
            they read as faceted shells; eyes and mouth are set in.
  body      low-sided lofts sampled from the guide surfaces: tee with collar and cuff bands,
            arms, chinos, belt with loops and buckle
  hands     blocks along the finger bones (posed)
  extras    sneakers, chain links, bead bracelet

Colors and sizes: character.json → lowpoly. Output: build/nitsan_lowpoly.glb
(+ build/preview/lowpoly_*.png with --preview).
Run:  .venv/bin/python lowpoly.py [--preview]
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
from scipy.spatial import ConvexHull

import bl
import garments as G
import mh
import shape
import shoes

BUILD = HERE / 'build'
S = 0.1  # MakeHuman decimeters → meters


def to_bl(P):
    P = np.asarray(P, float)
    return np.stack([P[..., 0], -P[..., 2], P[..., 1]], -1) * S


def from_bl(P):
    P = np.asarray(P, float) / S
    return np.stack([P[..., 0], P[..., 2], -P[..., 1]], -1)


def unit(v):
    v = np.asarray(v, float)
    return v / (np.linalg.norm(v, axis=-1, keepdims=True) + 1e-12)


def smoothstep(a, b, x):
    t = np.clip((np.asarray(x, float) - a) / (b - a), 0, 1)
    return t * t * (3 - 2 * t)


def srgb(hexstr):
    h = hexstr.lstrip('#')
    c = np.array([int(h[i:i + 2], 16) for i in (0, 2, 4)]) / 255.0
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def inside(poly, pts):
    """Even-odd point-in-polygon, vectorized over pts (N, 2)."""
    poly = np.asarray(poly, float)
    x, y = pts[:, 0], pts[:, 1]
    res = np.zeros(len(pts), bool)
    j = len(poly) - 1
    for i in range(len(poly)):
        xi, yi = poly[i]
        xj, yj = poly[j]
        cross = ((yi > y) != (yj > y)) & (x < (xj - xi) * (y - yi) / (yj - yi + 1e-12) + xi)
        res ^= cross
        j = i
    return res


# ---------- guide ----------

class Guide:
    def __init__(self):
        bpy.ops.wm.open_mainfile(filepath=str(BUILD / 'character.blend'))
        self.obj = {o.name: o for o in bpy.data.objects}
        self.rig = self.obj['rig']
        self._bvh, self._verts = {}, {}
        self.meta = json.loads((BUILD / 'bake' / 'meta.json').read_text())
        d = np.load(BUILD / 'shape.npz')
        self.V, self.cam = d['verts'], d['head_cam']
        self.corr = json.loads((BUILD / 'face_corr.json').read_text())
        self.photo_pts = np.array(json.loads((BUILD / 'analysis' / 'face.json').read_text())['points'])
        self.J, self.floor, self.hip_y = G.body_frame(self.V)
        self.toward = self.cam[2, :3] / np.linalg.norm(self.cam[2, :3])  # MakeHuman axes

    def verts(self, name):
        if name not in self._verts:
            ob = self.obj[name]
            co = np.empty(len(ob.data.vertices) * 3, np.float32)
            ob.data.vertices.foreach_get('co', co)
            M = np.array(ob.matrix_world)
            co = co.reshape(-1, 3).astype(float) @ M[:3, :3].T + M[:3, 3]
            self._verts[name] = co
        return self._verts[name]

    def bvh(self, *names):
        key = names
        if key not in self._bvh:
            vs, ts, off = [], [], 0
            for n in names:
                me = self.obj[n].data
                me.calc_loop_triangles()
                t = np.empty(len(me.loop_triangles) * 3, np.int64)
                me.loop_triangles.foreach_get('vertices', t)
                vs.append(self.verts(n))
                ts.append(t.reshape(-1, 3) + off)
                off += len(vs[-1])
            V = np.vstack(vs)
            self._bvh[key] = BVHTree.FromPolygons([Vector(p) for p in V], np.vstack(ts).tolist())
        return self._bvh[key]

    def bone(self, name, tail=False):
        b = self.rig.pose.bones[name]
        p = np.array(list(b.tail if tail else b.head) + [1.0])
        return (np.array(self.rig.matrix_world) @ p)[:3]

    def joint(self, name):
        return to_bl(self.J[name][None])[0]

    def landmark(self, i):
        c = self.corr[i]
        if not c:  # no correspondence on the 3D head: take it from the photo instead
            return self.unproject(self.photo_pts[i, :2])
        p = to_bl((self.V[c['tri']] * np.array(c['bary'])[:, None]).sum(0)[None])[0]
        loc = self.bvh('head').find_nearest(Vector(p))[0]
        return np.array(loc) if loc is not None else p

    def photo_px(self, P_bl):
        X = from_bl(np.atleast_2d(P_bl))
        return (self.cam[:2] @ np.c_[X, np.ones(len(X))].T).T

    def unproject(self, px, names=('head',)):
        """Point on the guide surface seen at photo pixel px (head camera)."""
        A, t = self.cam[:2, :3], self.cam[:2, 3]
        X0 = np.linalg.pinv(A) @ (np.asarray(px, float) - t)
        o = to_bl((X0 + self.toward * 4.0)[None])[0]
        d = unit(to_bl((-self.toward)[None])[0])
        hit = self.bvh(*names).ray_cast(Vector(o), Vector(d), 2.0)
        return np.array(hit[0]) if hit[0] is not None else None


# ---------- mesh accumulation ----------

class Parts:
    """Collects faceted parts: vertices, polygons and one color per polygon, by material."""

    def __init__(self, cfg, seed=7):
        self.groups = {}
        self.cfg = cfg
        self.rng = np.random.default_rng(seed)

    def add(self, verts, faces, color, mat='body', jitter=None):
        verts = np.asarray(verts, float)
        faces = [list(f) for f in faces]
        if isinstance(color, str):
            cols = np.tile(srgb(color), (len(faces), 1))
        else:
            cols = np.asarray(color, float)
        j = self.cfg['jitter'] if jitter is None else jitter
        cols = cols * (1 + self.rng.uniform(-j, j, (len(faces), 1)))
        g = self.groups.setdefault(mat, {'v': [], 'f': [], 'c': [], 'n': 0})
        g['v'].append(verts)
        g['f'] += [[i + g['n'] for i in f] for f in faces]
        g['c'].append(cols)
        g['n'] += len(verts)


def ring(bvh, center, axis, n, ref=(0.0, -1.0, 0.0), phase=0.5, reach=0.3, scale=1.0, pad=0.0, fallback=None):
    """n points around an axis, on the surface around it (rays cast outward from the axis)."""
    a = unit(axis)
    r0 = unit(np.asarray(ref, float) - (np.asarray(ref, float) @ a) * a)
    r1 = np.cross(a, r0)
    ang = 2 * np.pi * (np.arange(n) + phase) / n
    dirs = np.cos(ang)[:, None] * r0 + np.sin(ang)[:, None] * r1
    rad = np.full(n, np.nan)
    for k, d in enumerate(dirs):
        hit = bvh.ray_cast(Vector(center), Vector(d), reach)
        if hit[0] is not None:
            rad[k] = hit[3]
    if np.isnan(rad).all():
        rad[:] = fallback if fallback is not None else 0.05
    rad[np.isnan(rad)] = np.nanmedian(rad)
    return center + (rad * scale + pad)[:, None] * dirs


def loft(rings, cap_start=False, cap_end=False):
    rings = [np.asarray(r, float) for r in rings]
    n = len(rings[0])
    V = np.vstack(rings)
    F = []
    for i in range(len(rings) - 1):
        for k in range(n):
            F.append([i * n + k, i * n + (k + 1) % n, (i + 1) * n + (k + 1) % n, (i + 1) * n + k])
    # Outward orientation: the first face's normal should point away from the first ring's center.
    a, b, c = V[F[0][0]], V[F[0][1]], V[F[0][2]]
    if np.cross(b - a, c - a) @ (a - rings[0].mean(0)) < 0:
        F = [f[::-1] for f in F]
        flip = True
    else:
        flip = False
    V = list(V)
    for idx, cap in ((0, cap_start), (len(rings) - 1, cap_end)):
        if not cap:
            continue
        ci = len(V)
        V.append(rings[idx].mean(0))
        for k in range(n):
            f = [idx * n + k, idx * n + (k + 1) % n, ci]
            if (idx == 0) != flip:
                f = f[::-1]
            F.append(f)
    return np.array(V), F


def box(center, axes, half):
    """Oriented box: axes (3, 3) rows = unit directions, half = half sizes."""
    c = np.asarray(center, float)
    V = [c + sx * half[0] * axes[0] + sy * half[1] * axes[1] + sz * half[2] * axes[2]
         for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)]
    F = [[0, 1, 3, 2], [4, 6, 7, 5], [0, 4, 5, 1], [2, 3, 7, 6], [0, 2, 6, 4], [1, 5, 7, 3]]
    return np.array(V), F


def chamfer_box(center, axes, half, k=0.25):
    """Box with its edges cut (a low-poly 'rounded' block): 24 verts, 26 faces."""
    c = np.asarray(center, float)
    V, idx = [], {}
    for sx in (-1, 1):
        for sy in (-1, 1):
            for sz in (-1, 1):
                for axis in range(3):
                    s = np.array([sx, sy, sz], float)
                    p = s.copy()
                    for o in range(3):
                        if o != axis:
                            p[o] = s[o] * (1 - k)
                    idx[(sx, sy, sz, axis)] = len(V)
                    V.append(c + p[0] * half[0] * axes[0] + p[1] * half[1] * axes[1] + p[2] * half[2] * axes[2])
    F = []
    for axis in range(3):
        for s in (-1, 1):
            o1, o2 = [o for o in range(3) if o != axis]
            quad = []
            for a1, a2 in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
                key = [0, 0, 0]
                key[axis], key[o1], key[o2] = s, a1, a2
                quad.append(idx[(*key, axis)])
            F.append(quad)
    for sx in (-1, 1):  # corner triangles
        for sy in (-1, 1):
            for sz in (-1, 1):
                F.append([idx[(sx, sy, sz, 0)], idx[(sx, sy, sz, 1)], idx[(sx, sy, sz, 2)]])
    for axis in range(3):  # edge strips
        o1, o2 = [o for o in range(3) if o != axis]
        for s1 in (-1, 1):
            for s2 in (-1, 1):
                k1, k2 = [0, 0, 0], [0, 0, 0]
                for kk in (k1, k2):
                    kk[o1], kk[o2] = s1, s2
                k1[axis], k2[axis] = -1, 1
                F.append([idx[(*k1, o1)], idx[(*k2, o1)], idx[(*k2, o2)], idx[(*k1, o2)]])
    V = np.array(V)
    return V, orient(V, F, c)


def orient(V, F, center):
    """Flip faces that point toward the center (for convex-ish shapes)."""
    out = []
    for f in F:
        p = V[f]
        n = np.cross(p[1] - p[0], p[2] - p[0])
        out.append(f if n @ (p.mean(0) - center) >= 0 else f[::-1])
    return out


def icosahedron(r):
    t = (1 + 5 ** 0.5) / 2
    V = np.array([[-1, t, 0], [1, t, 0], [-1, -t, 0], [1, -t, 0], [0, -1, t], [0, 1, t], [0, -1, -t], [0, 1, -t],
                  [t, 0, -1], [t, 0, 1], [-t, 0, -1], [-t, 0, 1]], float)
    V = unit(V) * r
    F = [[0, 11, 5], [0, 5, 1], [0, 1, 7], [0, 7, 10], [0, 10, 11], [1, 5, 9], [5, 11, 4], [11, 10, 2], [10, 7, 6], [7, 1, 8],
         [3, 9, 4], [3, 4, 2], [3, 2, 6], [3, 6, 8], [3, 8, 9], [4, 9, 5], [2, 4, 11], [6, 2, 10], [8, 6, 7], [9, 8, 1]]
    return V, F


# ---------- head ----------

OVAL = [10, 338, 297, 332, 284, 251, 389, 356, 454, 323, 361, 288, 397, 365, 379, 378, 400, 377, 152, 148, 176, 149, 150, 136, 172, 58, 132, 93, 234, 127, 162, 21, 54, 103, 67, 109]
EYE_R = [33, 7, 163, 144, 145, 153, 154, 155, 133, 173, 157, 158, 159, 160, 161, 246]
EYE_L = [263, 249, 390, 373, 374, 380, 381, 382, 362, 398, 384, 385, 386, 387, 388, 466]
BROW_R = [70, 63, 105, 66, 107, 55, 65, 52, 53, 46]
BROW_L = [300, 293, 334, 296, 336, 285, 295, 282, 283, 276]
LIPS_OUT = [61, 146, 91, 181, 84, 17, 314, 405, 321, 375, 291, 409, 270, 269, 267, 0, 37, 39, 40, 185]
LIPS_IN = [78, 95, 88, 178, 87, 14, 317, 402, 318, 324, 308, 415, 310, 311, 312, 13, 82, 81, 80, 191]
NOSE = [168, 6, 195, 4, 1, 2, 98, 327, 64, 294, 129, 358, 49, 279, 48, 278]
CHEEKS = [50, 280, 123, 352, 205, 425, 187, 411, 147, 376, 116, 345, 118, 347, 36, 266, 101, 330, 207, 427]
FOREHEAD = [151, 9, 108, 337, 69, 299, 104, 333, 67, 297]
CHIN = [175, 199, 200, 18, 83, 313, 32, 262, 211, 431, 204, 424]


def head(g, parts, cfg):
    pal = cfg['palette']
    meta = g.meta
    eyes_c = np.array([e['center'] for e in meta['eyes'].values()])
    eye_mid = eyes_c.mean(0)
    c = eye_mid + np.array([0.0, 0.085, 0.015])  # skull center, behind the eyes
    hb = g.bvh('head')
    P, kind = [], []

    def add(p, k):
        if p is not None:
            P.append(np.asarray(p, float))
            kind.append(k)

    lower_lip = [61, 146, 91, 181, 84, 17, 314, 405, 321, 375, 291]  # the upper lip is under the mustache
    face_ids = (OVAL[::2] + EYE_R + EYE_L + BROW_R + BROW_L + lower_lip + LIPS_IN + NOSE + CHEEKS + FOREHEAD + CHIN)
    seen = set()
    ids_of = {}
    for i in face_ids:
        if i in seen:
            continue
        seen.add(i)
        k = 'eye' if i in EYE_R + EYE_L else 'brow' if i in BROW_R + BROW_L else 'inner' if i in LIPS_IN else 'lip' if i in LIPS_OUT else 'face'
        # Lip contours come straight from the photo (the fitted mouth opening is a little small).
        q = g.unproject(g.photo_pts[i, :2]) if k in ('inner', 'lip') else g.landmark(i)
        if q is not None:
            ids_of[i] = len(P)
        add(q, k)

    for contour in (EYE_R, EYE_L):
        idx = [ids_of[i] for i in contour if i in ids_of]
        E = np.array([P[k] for k in idx])
        ec = E.mean(0)
        for k in idx:
            d = P[k] - ec
            P[k] = ec + np.array([d[0] * cfg['eye_scale'][0], d[1], d[2] * cfg['eye_scale'][1]])
    iris_ids = []
    for contour, iris_lm in ((EYE_R, 468), (EYE_L, 473)):
        idx = [ids_of[i] for i in contour if i in ids_of]
        q = g.unproject(g.photo_pts[iris_lm, :2])
        if q is not None and idx:
            ec = np.mean([P[k] for k in idx], 0)
            iris_ids.append(len(P))
            add(ec + (q - ec) * np.array([1, 0, 1]) * 0.6, 'iris')  # on the eye plane, near the photo's iris
    pp = g.photo_pts[:, :2]
    poly = lambda ids: pp[ids]
    oval_poly = poly(OVAL)

    # Mustache and beard regions (photo pixels), with a few interior points so they can be raised.
    m_corner_r = pp[61] + [-7, 7]
    m_corner_l = pp[291] + [7, 7]
    must_poly = np.vstack([m_corner_r, pp[[185, 40, 39, 37, 0, 267, 269, 270, 409]], m_corner_l,
                           pp[327] + [9, 1], pp[[326, 2, 97]], pp[98] + [-9, 1]])
    beard_poly = np.vstack([pp[[127, 116, 50, 205]], m_corner_r + [0, 4], pp[[146, 91, 181, 84, 17, 314, 405, 321, 375]],
                            m_corner_l + [0, 4], pp[[425, 280, 345, 356, 454, 323, 361, 288, 397, 365, 379, 378, 400, 377, 152,
                                                     148, 176, 149, 150, 136, 172, 58, 132, 93, 234]]])
    for poly_, step, k in ((must_poly, 13, 'must'), (beard_poly, 30, 'beard')):
        lo, hi = poly_.min(0), poly_.max(0)
        xs, ys = np.meshgrid(np.arange(lo[0] + step / 2, hi[0], step), np.arange(lo[1] + step / 2, hi[1], step))
        cand = np.c_[xs.ravel(), ys.ravel()]
        for px in cand[inside(poly_, cand)]:
            add(g.unproject(px), k)

    # Denser lip contours (midpoints from the photo), so triangle edges follow them.
    for contour, k, closed in ((LIPS_IN, 'inner', True), (lower_lip, 'lip', False)):
        pts = g.photo_pts[contour, :2]
        nxt = np.roll(pts, -1, 0) if closed else pts[1:]
        for a, b in zip(pts if closed else pts[:-1], nxt):
            for t in (1 / 3, 2 / 3):
                add(g.unproject(a * (1 - t) + b * t), k)

    # Teeth: a row of points along the middle of the mouth opening, so the opening gets its own
    # triangles (the lips are thin; without these the triangulation zigzags across them).
    up_in = pp[[78, 191, 80, 81, 82, 13, 312, 311, 310, 415, 308]]
    lo_in = pp[[78, 95, 88, 178, 87, 14, 317, 402, 318, 324, 308]]
    for x in np.linspace(up_in[0, 0], up_in[-1, 0], 9)[1:-1]:
        yu = np.interp(x, up_in[:, 0], up_in[:, 1])
        yl = np.interp(x, lo_in[:, 0], lo_in[:, 1])
        add(g.unproject([x, yu * 0.55 + yl * 0.45]), 'teeth')

    # Skull, sides and back: Fibonacci directions outside the face, plus the ears.
    N = cfg['skull_points']
    i = np.arange(N) + 0.5
    phi = np.arccos(1 - 2 * i / N)
    th = np.pi * (1 + 5 ** 0.5) * i
    dirs = np.c_[np.cos(th) * np.sin(phi), np.sin(th) * np.sin(phi), np.cos(phi)]  # Blender axes, z up
    toward_bl = unit(to_bl(g.toward[None])[0])
    for d in dirs:
        if d[2] < -0.55:
            continue  # the neck is sampled separately
        hit = hb.ray_cast(Vector(c + d * 0.35), Vector(-d), 0.35)
        if hit[0] is None:
            continue
        p = np.array(hit[0])
        if d @ toward_bl > 0.25 and inside(oval_poly, g.photo_px(p))[0]:
            continue  # covered by the landmarks
        add(p, 'skull')
    for sx in (-1, 1):  # ears: a small fan of directions toward each ear
        ear_dir = unit(np.array([sx, 0.15, -0.05]))
        for a in np.linspace(-0.35, 0.35, 4):
            for b in np.linspace(-0.4, 0.3, 4):
                d = unit(ear_dir + np.array([0, a, 0]) + np.array([0, 0, b]))
                hit = hb.ray_cast(Vector(c + d * 0.35), Vector(-d), 0.35)
                if hit[0] is not None:
                    add(np.array(hit[0]), 'ear')

    # Hairline: a ring of points just at the hair edge, so the hair shell gets a clean border.
    fr = hairline_frame(g, eye_mid, c)
    for az in np.linspace(-np.pi, np.pi, 28, endpoint=False):
        h = np.interp(abs(az), fr['phi'], fr['hl']) * S + eye_mid[2]
        d = unit(np.array([np.sin(az), -np.cos(az), 0.0]) * 0.1 + np.array([0, 0, h - c[2]]))
        hit = hb.ray_cast(Vector(c + d * 0.35), Vector(-d), 0.35)
        if hit[0] is not None:
            add(np.array(hit[0]), 'hairline')

    # Neck: two rings, down into the collar.
    neck_top = g.joint('joint-neck') + np.array([0, 0, 0.02])
    for z, n in ((neck_top[2] + 0.03, 10), (neck_top[2] - 0.035, 10)):
        cen = np.array([0.0, neck_top[1] + 0.005, z])
        for p in ring(hb, cen, (0, 0, 1), n, phase=0.0, reach=0.15, scale=cfg['neck_scale']):
            add(p, 'neck')

    P = np.array(P)
    kind = np.array(kind)
    # Spherical Delaunay: the convex hull of the directions from the skull center.
    D = unit(P - c)
    hull = ConvexHull(D)
    F = hull.simplices.copy()
    for f in F:
        a, b, cc = P[f]
        if np.cross(b - a, cc - a) @ ((a + b + cc) / 3 - c) < 0:
            f[[1, 2]] = f[[2, 1]]

    # Per-vertex classes for offsets.
    az = np.arctan2(P[:, 0] - c[0], -(P[:, 1] - c[1]))
    hrel = (P[:, 2] - eye_mid[2]) / S
    hl = np.interp(np.abs(az), fr['phi'], fr['hl'])
    is_hair = (hrel > hl + 0.05) & (kind != 'neck')
    nrm = unit(P - c)
    off = np.zeros(len(P))
    off[is_hair] = cfg['hair_raise']
    off[kind == 'hairline'] = cfg['hair_raise'] * 0.35
    off[kind == 'must'] = cfg['mustache_raise']
    off[kind == 'beard'] = cfg['beard_raise']
    off[kind == 'brow'] = cfg['brow_raise']
    off[kind == 'eye'] = -cfg['eye_sink']
    off[kind == 'iris'] = -cfg['eye_sink'] * 0.3
    off[kind == 'inner'] = -cfg['mouth_sink']
    off[kind == 'teeth'] = -cfg['mouth_sink'] * 1.5
    P = P + nrm * off[:, None]

    # Per-face colors.
    cen = P[F].mean(1)
    fn = unit(np.cross(P[F[:, 1]] - P[F[:, 0]], P[F[:, 2]] - P[F[:, 0]]))
    px = g.photo_px(cen)
    front = (fn @ toward_bl > 0.05) & ((cen - c) @ toward_bl > 0)
    col = np.tile(srgb(pal['skin']), (len(F), 1))
    face_hrel = (cen[:, 2] - eye_mid[2]) / S
    face_az = np.arctan2(cen[:, 0] - c[0], -(cen[:, 1] - c[1]))
    hair_f = face_hrel > np.interp(np.abs(face_az), fr['phi'], fr['hl'])
    # Stubble: below a cheek line from the sideburns down to the mouth corners, front of the ears,
    # down to just under the jaw.
    chin_z = g.landmark(152)[2]
    mc = (g.landmark(61) + g.landmark(291)) / 2
    mouth_hw = abs(g.landmark(61)[0] - g.landmark(291)[0]) / 2
    ear_x = 0.075
    cheek_line = np.interp(np.abs(cen[:, 0]), [mouth_hw + 0.006, ear_x], [mc[2] + 0.012, eye_mid[2] - 0.03])
    ahead = (cen[:, 1] - c[1]) < 0.0
    beard_f = ahead & (cen[:, 2] < cheek_line) & (cen[:, 2] > chin_z - 0.03) & ~np.isin(kind[F], ['neck']).all(1)
    beard_f |= front & inside(beard_poly, px) & (cen[:, 2] < cheek_line)
    must_f = front & inside(must_poly, px)
    # Mouth: the opening as the 3D inner-lip vertices project (so it matches the triangles exactly).
    vpx = g.photo_px(P)
    order_in = [ids_of[i] for i in LIPS_IN if i in ids_of]
    order_low = [ids_of[i] for i in lower_lip if i in ids_of]
    opening = vpx[order_in]
    lower_band = np.vstack([vpx[[ids_of[i] for i in [78, 95, 88, 178, 87, 14, 317, 402, 318, 324, 308] if i in ids_of]],
                            vpx[order_low][::-1]])
    teeth_f = front & inside(opening, px)
    lips_f = front & inside(lower_band, px) & ~teeth_f
    upper_lip = np.zeros(len(F), bool)
    eye_f = front & (inside(vpx[[ids_of[i] for i in EYE_R if i in ids_of]], px) | inside(vpx[[ids_of[i] for i in EYE_L if i in ids_of]], px))
    brow_f = front & (inside(pp[BROW_R], px) | inside(pp[BROW_L], px))
    ear_f = (np.isin(kind[F], ['ear']).sum(1) >= 2) & ~hair_f
    col[ear_f] = srgb(pal['ear'])
    col[beard_f] = srgb(pal['beard'])
    col[lips_f] = srgb(pal['lips'])
    col[must_f | upper_lip] = srgb(pal['mustache'])
    col[teeth_f] = srgb(pal['teeth'])
    col[hair_f] = srgb(pal['hair'])
    col[brow_f] = srgb(pal['brows'])
    col[eye_f] = srgb(pal['sclera'])
    iris_f = eye_f & np.isin(F, iris_ids).any(1)
    for k in iris_ids:  # iris: the triangles around the iris point, within the iris radius
        d = np.linalg.norm(cen - P[k], axis=1)
        iris_f |= eye_f & (d < cfg['iris_radius'])
    col[iris_f] = srgb(pal['eyes'])

    debug_face(g, P, F, col, pp)
    if '--debug-mouth' in sys.argv:
        mpx = g.photo_px(cen)
        sel = np.where(inside(pp[LIPS_OUT], mpx))[0]
        for i in sel:
            print(i, kind[F[i]].tolist(), 'teeth', teeth_f[i], 'lips', lips_f[i], 'must', must_f[i], 'front', front[i], round(float(fn[i] @ toward_bl), 2))

    # Stylize: a slightly larger head (scaled about the neck, fading out down the neck).
    s = cfg['head_scale']
    pivot = neck_top.copy()
    w = smoothstep(neck_top[2] - 0.03, neck_top[2] + 0.06, P[:, 2])[:, None]
    P = pivot + (P - pivot) * (1 + (s - 1) * w)
    parts.add(P, F.tolist(), col, jitter=cfg['jitter'] * 0.6)
    return {'center': c, 'scale_pivot': pivot, 'scale': s, 'P': P, 'F': F, 'eyes_z': float(P[iris_ids, 2].mean()) if iris_ids else None}


def debug_face(g, P, F, col, pp):
    """build/preview/lowpoly_face_debug.png: the head's triangles projected onto the photo."""
    from PIL import ImageDraw
    im = Image.open(BUILD / 'analysis' / 'photo.png').convert('RGB')
    x0, y0, x1, y1 = (pp.min(0) - 40).astype(int).tolist() + (pp.max(0) + 40).astype(int).tolist()
    im = im.crop((x0, y0, x1, y1)).resize(((x1 - x0) * 3, (y1 - y0) * 3))
    d = ImageDraw.Draw(im, 'RGBA')
    px = g.photo_px(P)
    toward_bl = unit(to_bl(g.toward[None])[0])
    fn = unit(np.cross(P[F[:, 1]] - P[F[:, 0]], P[F[:, 2]] - P[F[:, 0]]))
    order = np.argsort((P[F].mean(1) @ toward_bl))
    for i in order:
        if fn[i] @ toward_bl < 0.05:
            continue
        q = [((px[v, 0] - x0) * 3, (px[v, 1] - y0) * 3) for v in F[i]]
        c = tuple(int(255 * (min(max(v, 0), 1) ** (1 / 2.2))) for v in col[i]) + (210,)
        d.polygon(q, fill=c, outline=(0, 0, 0, 90))
    im.save(BUILD / 'preview' / 'lowpoly_face_debug.png')


def hairline_frame(g, eye_mid, c):
    """Hairline height (dm above the eyes) by azimuth (0 = front, π = back); same curve the
    realistic texture used, which was matched to the photo."""
    return {'phi': [0, 0.5, 0.9, 1.3, 1.6, 1.9, 2.3, np.pi], 'hl': [0.68, 0.66, 0.55, 0.38, 0.22, -0.3, -0.75, -0.85]}


# ---------- body ----------

def neckline(g, n):
    """The tee's neck opening (its boundary loop near the neck), resampled to n points at the
    same angles as the torso rings."""
    T = g.verts('tee')
    me = g.obj['tee'].data
    edges = {}
    for poly in me.polygons:
        vs = list(poly.vertices)
        for i in range(len(vs)):
            e = tuple(sorted((vs[i], vs[(i + 1) % len(vs)])))
            edges[e] = edges.get(e, 0) + 1
    bverts = np.unique([v for e, c in edges.items() if c == 1 for v in e])
    nz = g.joint('joint-neck')
    loop = bverts[(np.abs(T[bverts, 0]) < 0.14) & (T[bverts, 2] > nz[2] - 0.09)]
    P = T[loop]
    c = np.array([0.0, P[:, 1].mean(), 0.0])
    ang = np.arctan2(P[:, 0] - c[0], -(P[:, 1] - c[1]))  # 0 = front, matching ring(ref=(0, -1, 0))
    order = np.argsort(ang)
    ang, P = ang[order], P[order]
    targets = 2 * np.pi * (np.arange(n) + 0.5) / n
    targets = np.where(targets > np.pi, targets - 2 * np.pi, targets)
    out = []
    for t in targets:
        k = np.argmin(np.abs(np.angle(np.exp(1j * (ang - t)))))
        out.append(P[k])
    return np.array(out)


def neckline_z(g):
    T = g.verts('tee')
    front = T[(np.abs(T[:, 0]) < 0.03) & (T[:, 1] < -0.02)]
    return front[:, 2].max()


def center_line(g, z):
    """Front and back of the trousers on the center plane at height z (or None)."""
    V = g.verts('pants')
    sel = (np.abs(V[:, 2] - z) < 0.012) & (np.abs(V[:, 0]) < 0.02)
    if sel.sum() < 2:
        return None
    return V[sel, 1].min(), V[sel, 1].max()


def torso_center(g, z, name='tee', half=0.13):
    V = g.verts(name)
    sel = (np.abs(V[:, 2] - z) < 0.015) & (np.abs(V[:, 0]) < half)
    if sel.sum() < 4:
        return np.array([0.0, -0.01, z])
    return np.array([0.0, (V[sel, 1].min() + V[sel, 1].max()) / 2, z])


def body(g, parts, cfg):
    pal = cfg['palette']
    meta = g.meta
    belt_z, crotch_z, hem_z = meta['tailor']['belt_z'], meta['tailor']['crotch_z'], meta['tailor']['hem_z']
    tee_b, skin_b, pants_b, belt_b = g.bvh('tee'), g.bvh('skin'), g.bvh('pants'), g.bvh('belt')
    sh_l, sh_r = g.bone('upperarm01.L'), g.bone('upperarm01.R')
    sh_z = (sh_l[2] + sh_r[2]) / 2
    collar_z = g.verts('tee')[np.abs(g.verts('tee')[:, 0]) < 0.05, 2].max()

    # Tee: torso rings up to the shoulders, then a sloped ring and the tee's own neckline.
    n = cfg['torso_sides']
    neck_lo = neckline_z(g)
    zs = [belt_z - 0.05, belt_z + 0.05, belt_z + 0.15, belt_z + 0.26, sh_z - 0.12, sh_z - 0.04, neck_lo - 0.01]
    rings = [ring(tee_b, torso_center(g, z), (0, 0, 1), n, reach=0.3) for z in zs]
    neck = neckline(g, n)
    slope = []
    for a, b in zip(rings[-1], neck):
        m = (a * 0.45 + b * 0.55) + [0, 0, 0.012]
        hit = tee_b.find_nearest(Vector(m))[0]
        slope.append(np.array(hit) if hit is not None else m)
    rings += [np.array(slope), neck]
    V, F = loft(rings)
    parts.add(V, F, pal['tee'], mat='cloth')
    # collar band: a ribbed ring standing on the neckline
    cen = neck.mean(0)
    band = [cen + (neck - cen) * 0.99 - [0, 0, 0.004], cen + (neck - cen) * 1.07 + [0, 0, 0.004], cen + (neck - cen) * 1.0 + [0, 0, 0.016],
            cen + (neck - cen) * 0.94 + [0, 0, 0.012]]
    V, F = loft(band)
    parts.add(V, F, pal['tee_trim'], mat='cloth')

    # Sleeves, arms
    for side in ('L', 'R'):
        sh, el = g.bone(f'upperarm01.{side}'), g.bone(f'lowerarm01.{side}')
        wr = g.bone(f'lowerarm02.{side}', tail=True)
        up = el - sh
        sleeve_end = sh + up * cfg['sleeve_t']
        srings = [ring(tee_b, sh + up * t, up, cfg['sleeve_sides'], ref=(0, -1, 0), reach=0.15, pad=0.002)
                  for t in (0.12, 0.3, cfg['sleeve_t'])]
        V, F = loft(srings)
        parts.add(V, F, pal['tee'], mat='cloth')
        last = srings[-1]
        cen = last.mean(0)
        cuff = [cen + (last - cen) * 1.02 - unit(up) * 0.004, cen + (last - cen) * 1.08 + unit(up) * 0.004,
                cen + (last - cen) * 1.08 + unit(up) * 0.022, cen + (last - cen) * 1.0 + unit(up) * 0.026]
        V, F = loft(cuff)
        parts.add(V, F, pal['tee_trim'], mat='cloth')
        # skin: upper arm below the sleeve → elbow → forearm → wrist
        fo = wr - el
        pts = [(sh + up * (cfg['sleeve_t'] - 0.06), up), (sh + up * 0.75, up), (el, unit(up) + unit(fo)),
               (el + fo * 0.3, fo), (el + fo * 0.62, fo), (el + fo * 0.92, fo)]
        arings = [ring(skin_b, p, a, cfg['arm_sides'], ref=(0, -1, 0), reach=0.12) for p, a in pts]
        V, F = loft(arings)
        parts.add(V, F, pal['skin'], mat='body')
        hand(g, parts, cfg, side)

    # Chinos: one tube per leg from the belt down; above the crotch the inner side is flattened
    # onto the center plane, so the two tubes meet in a clean front seam.
    for side, sgn in (('l', 1.0), ('r', -1.0)):
        hip, knee, ank = (g.joint(f'joint-{side}-upper-leg'), g.joint(f'joint-{side}-knee'), g.joint(f'joint-{side}-ankle'))
        leg = []
        for z in (belt_z + 0.012, belt_z - 0.05, crotch_z + 0.07, crotch_z + 0.01, crotch_z - 0.06, (crotch_z + knee[2]) / 2,
                  knee[2] + 0.03, knee[2] - 0.1, (knee[2] + hem_z) / 2, hem_z + 0.05, hem_z + 0.004):
            t = np.clip((hip[2] - z) / (hip[2] - ank[2]), 0, 1)
            axis_pt = hip + (ank - hip) * t
            if z > hip[2]:
                axis_pt = hip.copy()
            axis_pt[1] = torso_center(g, z, 'pants', 0.1)[1] if z > crotch_z else axis_pt[1]
            axis_pt[2] = z
            r = ring(pants_b, axis_pt, (0, 0, 1), cfg['leg_sides'], reach=0.25)
            if z > crotch_z - 0.02:
                fb = center_line(g, z)
                inner = r[:, 0] * sgn < 0.0
                r[inner, 0] = 0.0
                if fb is not None:
                    r[inner, 1] = np.clip(r[inner, 1], fb[0], fb[1])
                    k_front, k_back = np.argmin(r[:, 1]), np.argmax(r[:, 1])
                    r[k_front, 1] = min(r[k_front, 1], fb[0]) if inner[k_front] else r[k_front, 1]
                    r[k_back, 1] = max(r[k_back, 1], fb[1]) if inner[k_back] else r[k_back, 1]
            leg.append(r)
        leg[-1] = leg[-1].mean(0) + (leg[-1] - leg[-1].mean(0)) * 1.05  # slight flare at the hem
        V, F = loft(leg)
        parts.add(V, F, pal['pants'], mat='cloth')
        sneaker(g, parts, cfg, side)

    # Seam panels where the leg tubes meet (front fly and back seam).
    for side_y in (0, 1):
        rows = []
        for z in (belt_z + 0.012, belt_z - 0.05, crotch_z + 0.07, crotch_z + 0.015):
            fb = center_line(g, z)
            if fb is None:
                continue
            y = fb[side_y] + (-0.0015 if side_y == 0 else 0.0015)
            rows.append(np.array([[-0.03, y + (0.004 if side_y == 0 else -0.004), z], [0.0, y, z], [0.03, y + (0.004 if side_y == 0 else -0.004), z]]))
        if len(rows) >= 2:
            V = np.vstack(rows)
            F = [[i * 3 + k, i * 3 + k + 1, (i + 1) * 3 + k + 1, (i + 1) * 3 + k] for i in range(len(rows) - 1) for k in range(2)]
            F = orient(V, F, V.mean(0) + np.array([0, 0.05 if side_y == 0 else -0.05, 0]))
            parts.add(V, F, pal['pants'], mat='cloth')

    # Belt: a band with thickness, buckle, loops.
    h = cfg['belt_height']
    cen = torso_center(g, belt_z, 'pants', 0.1)
    outer = [ring(belt_b, cen + [0, 0, dz], (0, 0, 1), cfg['belt_sides'], reach=0.35, pad=0.002) for dz in (-h / 2, h / 2)]
    inner = [cen + [0, 0, dz] + (r - (cen + [0, 0, dz])) * 0.97 for r, dz in zip(outer[::-1], (h / 2, -h / 2))]
    rings_ = outer + inner + [outer[0]]
    V, F = loft(rings_)
    parts.add(V, F, pal['belt'], mat='body')
    front = outer[0][np.argmin(outer[0][:, 1])]
    fy = min(outer[0][:, 1].min(), outer[1][:, 1].min())
    bx = np.array([[1.0, 0, 0], [0, 0, 1.0], [0, -1.0, 0]])
    for x0, z0, hw, hh in ((-0.021, 0, 0.0035, 0.019), (0.021, 0, 0.0035, 0.019), (0, 0.0165, 0.024, 0.0035), (0, -0.0165, 0.024, 0.0035)):
        V, F = chamfer_box([x0, fy - 0.004, belt_z + z0], bx, [hw, hh, 0.003], k=0.3)
        parts.add(V, F, pal['metal'], mat='metal', jitter=0)
    for a in cfg['loop_angles']:
        d = np.array([np.sin(a), -np.cos(a), 0.0])
        p = ring(belt_b, cen, (0, 0, 1), 1, ref=d, phase=0, reach=0.35)[0]
        ax = np.array([np.cross([0, 0, 1], d), [0, 0, 1], d])
        V, F = chamfer_box(p + d * 0.004, ax, [0.006, h / 2 + 0.006, 0.0028], k=0.3)
        parts.add(V, F, pal['pants'], mat='cloth')


def hand(g, parts, cfg, side):
    pal = cfg['palette']
    s = cfg['hand_scale']
    wr = g.bone(f'wrist.{side}')
    mets = [g.bone(f'metacarpal{k}.{side}') for k in range(1, 5)]
    knuck = [g.bone(f'finger{k}-1.{side}') for k in range(2, 6)]
    palm_c = (wr + np.mean(knuck, 0)) / 2
    along = unit(np.mean(knuck, 0) - wr)
    across = unit(knuck[0] - knuck[-1])
    nrm = unit(np.cross(along, across))
    across = unit(np.cross(nrm, along))
    length = np.linalg.norm(np.mean(knuck, 0) - wr)
    width = np.linalg.norm(knuck[0] - knuck[-1]) + 0.022
    V, F = chamfer_box(palm_c, np.array([along, across, nrm]), np.array([length / 2 + 0.006, width / 2, 0.015]) * s, k=0.3)
    parts.add(V, F, pal['skin'], mat='body')
    for k in range(1, 6):
        chain = [g.bone(f'finger{k}-{j}.{side}') for j in (1, 2, 3)] + [g.bone(f'finger{k}-3.{side}', tail=True)]
        thick = (0.0105 if k > 1 else 0.012) * s
        for a, b in zip(chain[:-1], chain[1:]):
            ax0 = unit(b - a)
            ax1 = unit(np.cross(nrm, ax0))
            ax2 = np.cross(ax0, ax1)
            V, F = chamfer_box((a + b) / 2, np.array([ax0, ax1, ax2]), [np.linalg.norm(b - a) / 2 + 0.003, thick, thick * 0.92], k=0.3)
            parts.add(V, F, pal['skin'], mat='body')


def sneaker(g, parts, cfg, side):
    """A clean low-poly sneaker: sole slab, upper with a raised collar, laces, a side stripe."""
    pal = cfg['palette']
    reg = G.regions()
    fr = shoes.foot_frame(g.V, reg, side, g.J, g.floor)
    heel = to_bl(fr['heel'][None])[0]
    d = to_bl(fr['dir'][None])[0]
    d[2] = 0
    d = unit(d)
    lat = unit(np.cross(d, [0, 0, 1])) * (-1 if side == 'l' else 1)  # toward the outside of the foot
    L = fr['length'] * S + cfg['shoe_extra'][0]
    W = fr['width'] * S + cfg['shoe_extra'][1]
    floor_z = g.floor * S
    sole_t = cfg['sole']
    base = heel - d * 0.012
    base[2] = floor_z - sole_t
    # footprint outline (fraction along, half-width fraction): rounded heel, wider forefoot, round toe
    prof = [(0.0, 0.0), (0.02, 0.62), (0.12, 0.86), (0.35, 0.82), (0.62, 1.0), (0.82, 0.95), (0.94, 0.72), (1.0, 0.0)]
    outline = []
    for t, w in prof:
        outline.append(base + d * t * L + lat * w * W / 2)
    for t, w in prof[-2:0:-1]:
        outline.append(base + d * t * L - lat * w * W / 2 * (0.92 if 0.3 < t < 0.7 else 1.0))  # arch side
    outline = np.array(outline)
    n = len(outline)
    up = np.array([0, 0, 1.0])
    ctr = outline.mean(0)
    sole = [outline, outline + up * sole_t * 0.55, ctr + (outline - ctr) * 0.985 + up * sole_t]
    V, F = loft(sole, cap_start=True, cap_end=True)
    cols = [srgb(pal['sole_bottom']) if i < n else srgb(pal['sole']) for i in range(len(F))]
    parts.add(V, F, np.array(cols), mat='body')
    # upper: rings across the shoe from heel to toe (height profile), on top of the sole
    top = ctr + up * sole_t
    hts = [(0.02, 0.085), (0.16, 0.1), (0.3, 0.092), (0.46, 0.08), (0.62, 0.064), (0.8, 0.052), (0.94, 0.038)]
    rings_ = []
    for t, h in hts:
        p = base + d * t * L
        p[2] = floor_z
        w = np.interp(t, [q[0] for q in prof], [q[1] for q in prof]) * W / 2 * 0.97
        r = [p - lat * w, p - lat * w + up * h * 0.55, p - lat * w * 0.7 + up * h * 0.95, p + up * h,
             p + lat * w * 0.7 + up * h * 0.95, p + lat * w + up * h * 0.55, p + lat * w]
        rings_.append(np.array(r))
    V = np.vstack(rings_)
    m = 7
    F = []
    for i in range(len(rings_) - 1):
        for k in range(m - 1):
            F.append([i * m + k, i * m + k + 1, (i + 1) * m + k + 1, (i + 1) * m + k])
    F = orient(V, F, (rings_[0].mean(0) + rings_[-1].mean(0)) / 2 - up * 0.02)
    tip = base + d * L * 0.995
    tip[2] = floor_z + 0.015
    ti = len(V)
    V = np.vstack([V, tip])
    last = (len(rings_) - 1) * m
    F += orient(V, [[last + k, last + k + 1, ti] for k in range(m - 1)], tip - d * 0.03 + up * 0.01)
    hb = base + d * 0.005
    hb[2] = floor_z + 0.03
    hi = len(V)
    V = np.vstack([V, hb])
    F += orient(V, [[k, k + 1, hi] for k in range(m - 1)], hb + d * 0.04)
    parts.add(V, F, pal['shoe'], mat='body')
    # collar (dark lining) and tongue, laces
    col_p = base + d * 0.2 * L
    col_p[2] = floor_z + 0.09
    V, F = chamfer_box(col_p, np.array([d, lat, up]), [0.045, W * 0.3, 0.006], k=0.35)
    parts.add(V, F, pal['shoe_lining'], mat='body')
    for k, t in enumerate((0.36, 0.45, 0.54)):
        p = base + d * t * L
        p[2] = floor_z + np.interp(t, [q[0] for q in hts], [q[1] for q in hts]) + 0.003
        V, F = box(p, np.array([d, lat, up]), [0.004, W * 0.22, 0.003])
        parts.add(V, F, pal['laces'], mat='body')
    # side stripe on both faces, heel tab
    for sgn in (1, -1):
        p = base + d * 0.42 * L + lat * sgn * (np.interp(0.42, [q[0] for q in prof], [q[1] for q in prof]) * W / 2 * 0.97 + 0.0015)
        p[2] = floor_z + 0.032
        V, F = box(p, np.array([d, lat * sgn, up]), [0.04, 0.0015, 0.009])
        parts.add(V, F, pal['shoe_accent'], mat='body')
    tab = base + d * 0.004
    tab[2] = floor_z + 0.07
    V, F = chamfer_box(tab, np.array([d, lat, up]), [0.006, 0.014, 0.022], k=0.3)
    parts.add(V, F, pal['shoe_accent'], mat='body')


def accessories(g, parts, cfg, head_info):
    pal = cfg['palette']
    # Chain: links along the guide necklace's center line (binned around the neck).
    N = g.verts('necklace')
    c = g.joint('joint-neck')
    ang = np.arctan2(N[:, 1] - c[1], N[:, 0] - c[0])
    bins = np.linspace(-np.pi, np.pi, 61)
    path = []
    for a0, a1 in zip(bins[:-1], bins[1:]):
        sel = (ang >= a0) & (ang < a1)
        if sel.sum() > 5:
            path.append(N[sel].mean(0))
    path = np.array(path)
    radial = path - np.array([c[0], c[1], path[:, 2].mean()])
    radial[:, 2] = 0
    path = path + unit(radial) * cfg['chain_lift'] + np.array([0, 0, 0.002])
    seg = np.linalg.norm(np.roll(path, -1, 0) - path, axis=1)
    s = np.r_[0, np.cumsum(seg)]
    pitch = cfg['chain_link']
    closed = np.vstack([path, path[:1]])
    for k, t in enumerate(np.arange(0, s[-1], pitch)):
        p = np.array([np.interp(t, s, closed[:, j]) for j in range(3)])
        q = np.array([np.interp(t + pitch * 0.5, s, closed[:, j]) for j in range(3)])
        ax0 = unit(q - p)
        ax1 = unit(np.cross(ax0, [0, 0, 1]) if abs(ax0[2]) < 0.9 else np.cross(ax0, [1, 0, 0]))
        if k % 2:
            ax1 = unit(np.cross(ax0, ax1))
        ax2 = np.cross(ax0, ax1)
        V = np.array([p - ax0 * pitch * 0.5, p + ax0 * pitch * 0.5, p + ax1 * 0.0022, p - ax1 * 0.0022, p + ax2 * 0.0015, p - ax2 * 0.0015])
        F = orient(V, [[0, 2, 4], [0, 4, 3], [0, 3, 5], [0, 5, 2], [1, 4, 2], [1, 3, 4], [1, 5, 3], [1, 2, 5]], p)
        parts.add(V, F, pal['metal'], mat='metal', jitter=0)
    # Bracelet: beads around the guide bracelet's ring.
    B = g.verts('bracelet')
    bc = B.mean(0)
    _, _, vt = np.linalg.svd(B - bc)
    axis = vt[2]
    r = np.median(np.linalg.norm((B - bc) - np.outer((B - bc) @ axis, axis), axis=1)) + cfg['bead'] * 0.3
    e1 = unit(np.cross(axis, [0, 0, 1]))
    e2 = np.cross(axis, e1)
    br = cfg['bead']
    n = max(int(2 * np.pi * r / (2.05 * br)), 8)
    for k in range(n):
        a = 2 * np.pi * k / n
        p = bc + r * (np.cos(a) * e1 + np.sin(a) * e2)
        V, F = icosahedron(br)
        parts.add(V + p, F, pal['beads'], mat='beads', jitter=0.08)


# ---------- output ----------

def build_scene(parts, cfg):
    bl.reset()
    mats = {}
    for name, (rough, metal, coat) in {'body': (0.72, 0.0, 0.0), 'cloth': (0.86, 0.0, 0.0), 'metal': (0.4, 1.0, 0.0), 'beads': (0.25, 0.0, 0.6)}.items():
        m = bpy.data.materials.new(name)
        b = m.node_tree.nodes['Principled BSDF']
        b.inputs['Roughness'].default_value = rough
        b.inputs['Metallic'].default_value = metal
        b.inputs['Coat Weight'].default_value = coat
        b.inputs['Specular IOR Level'].default_value = 0.35
        attr = m.node_tree.nodes.new('ShaderNodeVertexColor')
        attr.layer_name = 'Col'
        m.node_tree.links.new(attr.outputs['Color'], b.inputs['Base Color'])
        m.use_backface_culling = name != 'cloth'
        mats[name] = m
    objs = []
    for name, gr in parts.groups.items():
        V = np.vstack(gr['v'])
        cols = np.vstack(gr['c'])
        me = bpy.data.meshes.new(name)
        me.from_pydata([tuple(map(float, v)) for v in V], [], gr['f'])
        me.update()
        me.shade_flat()
        attr = me.color_attributes.new('Col', 'FLOAT_COLOR', 'CORNER')
        corner = np.repeat(np.c_[cols, np.ones(len(cols))], [len(p.vertices) for p in me.polygons], axis=0)
        attr.data.foreach_set('color', corner.astype(np.float32).ravel())
        me.color_attributes.active_color = attr
        ob = bpy.data.objects.new(name, me)
        bpy.context.scene.collection.objects.link(ob)
        me.materials.append(mats[name])
        objs.append(ob)
    return objs


def preview(tag='lowpoly'):
    scene = bpy.context.scene
    scene.view_settings.view_transform = 'Standard'
    scene.world.color = (0.05, 0.055, 0.07)
    target = (0, 0, 0.1)
    bl.area_light('key', (2.2, -3.6, 2.8), target, 380, 3)
    bl.area_light('fill', (-3.5, -2.0, 1.4), target, 140, 3)
    bl.area_light('rim', (0.5, 3.5, 2.6), target, 260, 3)
    cam = bpy.data.cameras.new('cam')
    cam.type = 'ORTHO'
    co = bpy.data.objects.new('cam', cam)
    scene.collection.objects.link(co)
    scene.camera = co
    out = BUILD / 'preview'
    tiles = []
    zs = [(o.matrix_world @ Vector(c)).z for o in bpy.data.objects if o.type == 'MESH' for c in o.bound_box]
    zmin, zmax = min(zs), max(zs)
    mid = (zmin + zmax) / 2
    for view, ang, scale, z, w, h in (('front', 0, 2.05, mid, 420, 840), ('three-quarter', 35, 2.05, mid, 420, 840),
                                      ('profile', 90, 2.05, mid, 420, 840), ('back', 180, 2.05, mid, 420, 840),
                                      ('face', 0, 0.34, zmax - 0.14, 420, 420), ('face34', 32, 0.34, zmax - 0.14, 420, 420),
                                      ('chest', 0, 0.8, zmax - 0.52, 420, 420), ('feet', 25, 0.6, zmin + 0.2, 420, 420)):
        a = math.radians(ang)
        cam.ortho_scale = scale
        co.location = (8 * math.sin(a), -8 * math.cos(a), z)
        co.rotation_euler = (math.pi / 2, 0, a)
        p = out / f'{tag}_{view}.png'
        bl.render(p, w, h, samples=16)
        tiles.append(p)
    sheet = Image.new('RGB', (420 * 4, 840 + 420), (30, 30, 34))
    for i, p in enumerate(tiles):
        sheet.paste(Image.open(p), ((i % 4) * 420, 0 if i < 4 else 840))
    sheet.save(out / f'{tag}_sheet.png')


def main():
    ch = shape.character()
    cfg = ch['lowpoly']
    g = Guide()
    parts = Parts(cfg)
    info = head(g, parts, cfg)
    body(g, parts, cfg)
    accessories(g, parts, cfg, info)
    marks = {'eyes': info['eyes_z'],
             'arms': (g.bone('lowerarm02.L', tail=True)[2] + g.bone('lowerarm02.R', tail=True)[2]) / 2,
             'belt': g.meta['tailor']['belt_z'],
             'knees': (g.joint('joint-l-knee')[2] + g.joint('joint-r-knee')[2]) / 2,
             'ankles': g.joint('joint-l-ankle')[2]}
    objs = build_scene(parts, cfg)
    tris = sum(sum(len(p.vertices) - 2 for p in o.data.polygons) for o in objs)
    out = BUILD / 'nitsan_lowpoly.glb'
    bpy.ops.export_scene.gltf(filepath=str(out), export_format='GLB', export_yup=True, export_apply=True,
                              export_normals=True, export_materials='EXPORT', export_vertex_color='ACTIVE',
                              export_animations=False, export_skins=False)
    print('exported', out.name, round(out.stat().st_size / 1e3), 'KB,', tris, 'triangles')
    # Heights of the page's stations, as fractions of the figure (js/config.js → stations.*.y).
    zs = np.vstack([np.array([v.co[:] for v in o.data.vertices]) for o in objs])[:, 2]
    zmin, H = zs.min(), zs.max() - zs.min()
    frac = lambda z: round(float((z - zmin) / H), 3)
    stations = {k: frac(z) for k, z in marks.items()}
    stations['height_m'] = round(float(H), 3)
    (BUILD / 'lowpoly_stations.json').write_text(json.dumps(stations, indent=1))
    print('stations', stations)
    if '--preview' in sys.argv:
        preview()


if __name__ == '__main__':
    main()
