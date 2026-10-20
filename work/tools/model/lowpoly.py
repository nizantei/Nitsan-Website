"""The page's character: a stylized low-poly model in the style of hand-made low-poly characters
(big planar facets, a beveled block head, features as separate blocks, warm solid colors with a
fine painted grain and baked ambient occlusion), built from scratch on top of the photo-fitted
guide body (build/character.blend) so it keeps your proportions, pose and face.

  head      box-modeled to your measurements: octagonal skull and face planes from the guide's
            cross-sections (brow ridge, cheeks, muzzle), wedge nose on your nose landmarks, slab
            brows, plate ears, small dark eyes, buzz-cut shell down to your hairline, a chunky
            short beard with a mustache bar, and the smile (teeth, lower lip)
  body      low-sided lofts sampled from the guide: tee with collar and cuff bands, crossed arms,
            chinos meeting in a center seam, belt with loops and buckle
  hands     blocks along the finger bones (posed)
  extras    sneakers, chain links, bead bracelet

Colors and sizes: character.json → lowpoly. Output: build/nitsan_lowpoly.glb, station heights in
build/lowpoly_stations.json (+ build/preview/lowpoly_*.png with --preview).
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

# ---------- head: box-modeled to your measurements ----------
#
# The style is a beveled block head, as in hand-made low-poly characters: an octagonal skull and
# face (flat face plane, angled cheeks, flat sides and back), and every feature a separate block:
# wedge nose, slab brows, plate ears, a buzz-cut shell, a chunky short beard with a mustache
# bar, the smile (teeth and lower lip), small dark eyes. Sizes and positions are measured on the
# photo-fitted guide head, so the proportions and the face are yours.

class HeadShape:
    """Octagonal cross-sections of the guide head, interpolated in height."""

    def __init__(self, g, cfg):
        H = g.verts('head')
        self.top = H[:, 2].max()
        lm = g.landmark
        self.eye_z = np.mean([e['center'][2] for e in g.meta['eyes'].values()])
        self.chin_z = lm(152)[2]
        zs = [self.top - 0.004, self.top - 0.03, lm(10)[2], lm(9)[2], self.eye_z - 0.004, (self.eye_z + lm(1)[2]) / 2 - 0.006,
              lm(61)[2], (lm(61)[2] + self.chin_z) / 2, self.chin_z + 0.004]
        rows = []
        for z in zs:
            s = np.abs(H[:, 2] - z) < 0.006
            P = H[s]
            cheek = (np.abs(P[:, 0]) > 0.02) & (np.abs(P[:, 0]) < 0.04)
            mid = np.abs(P[:, 0]) < 0.015
            yf = P[cheek, 1].min() if cheek.any() else P[:, 1].min()
            yb = P[mid, 1].max() if mid.any() else P[:, 1].max()
            ws = np.percentile(np.abs(P[np.abs(P[:, 0]) < 0.085, 0]), 92)
            rows.append([z, yf, yb, ws])
        R = np.array(rows)
        R[0, 3] = min(R[0, 3], R[1, 3] * 0.62)  # crown: a smaller top plane
        R[0, 1] = R[1, 1] + 0.025
        R[0, 2] = R[1, 2] - 0.02
        # Sculpted planes: brow ridge forward, eyes set in, cheekbones wide, muzzle forward.
        st = cfg['face_planes']
        R[:, 1] += np.array(st['front_offset'])
        R[:, 3] *= cfg['head_widen']
        self.R = R
        self.k = np.array(st['front_width'])  # front plane half width / side half width, per ring

    def params(self, z):
        R = self.R[::-1]  # increasing z for interp
        return [np.interp(z, R[:, 0], R[:, k]) for k in (1, 2, 3)]

    def octagon(self, z):
        """8 points: front-right, side-front-right, side-back-right, back-right, back-left, ..."""
        yf, yb, ws = self.params(z)
        kf = np.interp(z, self.R[::-1, 0], self.k[::-1])
        wf, wb = ws * kf, ws * 0.64
        c1, c2 = (ws - wf) * 1.05, (ws - wb) * 0.95
        pts = [(-wf, yf), (-ws, yf + c1), (-ws, yb - c2), (-wb, yb), (wb, yb), (ws, yb - c2), (ws, yf + c1), (wf, yf)]
        return np.array([[x, y, z] for x, y in pts])

    def surface(self, theta, z):
        """Point on the octagon at height z, in direction theta (0 = front, + = character's left),
        and the outward normal of the face it lies on."""
        O = self.octagon(z)
        c = np.array([0.0, (O[0, 1] + O[3, 1]) / 2, z])
        d = np.array([np.sin(theta), -np.cos(theta), 0.0])
        best = None
        for i in range(8):
            a, b = O[i], O[(i + 1) % 8]
            e = b - a
            M = np.array([[d[0], -e[0]], [d[1], -e[1]]])
            if abs(np.linalg.det(M)) < 1e-9:
                continue
            t, s = np.linalg.solve(M, (a - c)[:2])
            if t > 0 and -1e-6 <= s <= 1 + 1e-6 and (best is None or t < best[0]):
                n = unit(np.array([e[1], -e[0], 0.0]))
                if n @ d < 0:
                    n = -n
                best = (t, c + d * t, n)
        return best[1], best[2]


def head(g, parts, cfg):
    pal = cfg['palette']
    hs = HeadShape(g, cfg)
    lm = g.landmark
    out = []  # (verts, faces, color, material) in guide space; scaled together at the end

    def put(V, F, col, mat='skin'):
        out.append((np.asarray(V, float), F, col, mat))

    # Skull and face block.
    rings = [hs.octagon(z) for z in hs.R[:, 0]]
    V, F = loft(rings, cap_start=True, cap_end=True)
    put(V, F, pal['skin'])
    yface = lambda z: hs.params(z)[0]

    # Neck: an octagonal prism from inside the collar up into the head.
    nz = g.joint('joint-neck')[2]
    neck = []
    for z, sx, sy in ((nz - 0.07, 1.0, 1.0), (nz + 0.01, 0.97, 0.98), (hs.chin_z + 0.03, 0.95, 0.95)):
        hx, hy = cfg['neck'][0] * sx, cfg['neck'][1] * sy
        cy = -0.022
        neck.append(np.array([[x, cy + y, z] for x, y in ((-hx * 0.55, -hy), (-hx, -hy * 0.5), (-hx, hy * 0.5), (-hx * 0.55, hy),
                                                          (hx * 0.55, hy), (hx, hy * 0.5), (hx, -hy * 0.5), (hx * 0.55, -hy))]))
    V, F = loft(neck)
    put(V, F, pal['skin'], 'neck')

    # Nose: a block wedge from the root to the tip, on your nose landmarks.
    root, tip, tipu, base = lm(168), lm(1), lm(4), lm(2)
    ala = abs(lm(327)[0] - lm(98)[0]) / 2 * cfg['nose_scale']
    yr = yface(root[2])
    ztip = (tip[2] + tipu[2]) / 2
    ytip = yface(ztip) + (min(tip[1], tipu[1]) - yface(ztip)) * cfg['nose_scale']
    zb = base[2] - 0.003
    nv = np.array([[-0.0075, yr + 0.004, root[2] + 0.004], [0.0075, yr + 0.004, root[2] + 0.004],
                   [-0.011, ytip, ztip + 0.007], [0.011, ytip, ztip + 0.007],
                   [-0.012, ytip + 0.004, ztip - 0.008], [0.012, ytip + 0.004, ztip - 0.008],
                   [-ala, yface(zb) + 0.002, zb + 0.004], [ala, yface(zb) + 0.002, zb + 0.004],
                   [-ala * 0.8, yface(zb) + 0.004, ztip + 0.012], [ala * 0.8, yface(zb) + 0.004, ztip + 0.012]])
    nf = [[0, 1, 3, 2], [2, 3, 5, 4], [0, 2, 8], [1, 9, 3], [2, 4, 6, 8], [3, 9, 7, 5], [4, 5, 7, 6]]
    put(nv, orient(nv, nf, np.array([0, yr + 0.02, (root[2] + zb) / 2])), pal['skin'])

    # Eyes: small dark smiling almonds with a catchlight, just in front of the face plane.
    for side, iris_lm, (a, b) in (('r', 468, (33, 133)), ('l', 473, (263, 362))):
        c = (lm(a) + lm(b)) / 2
        w = abs(lm(a)[0] - lm(b)[0]) * cfg['eye_size'][0]
        h = cfg['eye_size'][1]
        sgn = -1 if side == 'r' else 1  # outer corner direction
        cz = c[2] - 0.0015
        y = min(yface(cz + h / 2), yface(cz - h / 2)) - 0.0012
        shape = [(-0.5, 0.0), (-0.3, 0.5), (0.3, 0.5), (0.5, 0.08), (0.32, -0.45), (-0.32, -0.45)]
        ev = np.array([[c[0] + sgn * u * w, y, cz + v * h] for u, v in shape])
        put(ev, orient(ev, [list(range(6))], ev.mean(0) + np.array([0, 0.01, 0])), pal['eyes'], 'eyes')
        gx, gz = c[0] + sgn * 0.18 * w, cz + 0.15 * h
        gv = np.array([[gx - 0.0011, y - 0.0004, gz - 0.0011], [gx + 0.0011, y - 0.0004, gz - 0.0011], [gx + 0.0011, y - 0.0004, gz + 0.0011], [gx - 0.0011, y - 0.0004, gz + 0.0011]])
        put(gv, orient(gv, [[0, 1, 2, 3]], gv.mean(0) + np.array([0, 0.01, 0])), pal['glint'], 'eyes')

    # Brows: two slabs each, following your brows, standing off the face.
    for ids in ((107, 105, 70), (336, 334, 300)):
        pts = [lm(i) for i in ids]
        lows = [lm(j) for j in ((55, 52, 46) if ids[0] == 107 else (285, 282, 276))]
        for k in range(2):
            p0 = (pts[k] + lows[k]) / 2
            p1 = (pts[k + 1] + lows[k + 1]) / 2
            zm = (p0[2] + p1[2]) / 2
            p0[2], p1[2] = zm + (p0[2] - zm) * 0.4 + (0.0015 if k == 0 else 0), zm + (p1[2] - zm) * 0.4
            mid = (p0 + p1) / 2
            ax0 = unit(np.array([p1[0] - p0[0], 0.0, p1[2] - p0[2]]))
            ax2 = np.array([0.0, -1.0, 0.0])
            ax1 = np.cross(ax2, ax0)
            hgt = cfg['brow'][0] * (1.15 if k == 0 else 0.95)
            mid[1] = yface(mid[2]) - cfg['brow'][1] / 2 - 0.001
            V, F = chamfer_box(mid, np.array([ax0, ax1, ax2]), [np.linalg.norm(p1 - p0) / 2 + (0.002 if k == 0 else -0.002), hgt / 2, cfg['brow'][1] / 2], k=0.25)
            put(V, F, pal['brows'], 'hair')

    # Ears: angled plates with an inset, on the sides of the head.
    for sgn, tr in ((-1, 234), (1, 454)):
        t = lm(tr)
        z = t[2] - 0.002
        yf, yb, ws = hs.params(z)
        a = np.radians(cfg['ear_angle'])
        n = np.array([sgn * np.cos(a), -np.sin(a), 0.0])  # facing out and a little forward
        u = np.array([sgn * np.sin(a), np.cos(a), 0.0])  # toward the back of the head
        v = np.array([0.0, 0.0, 1.0])
        o = np.array([sgn * (ws - 0.002), t[1] + 0.012, z])
        S = cfg['ear_size']
        outline = [(0.0, 0.5), (0.45, 0.62), (0.85, 0.48), (1.0, 0.12), (0.88, -0.3), (0.5, -0.55), (0.12, -0.5)]
        front = [o + u * px * S[0] + v * py * S[1] for px, py in outline]
        back = [p - n * 0.009 for p in front]
        V = np.array(front + back)
        m = len(outline)
        F = [list(range(m)), list(range(2 * m - 1, m - 1, -1))] + [[k, (k + 1) % m, m + (k + 1) % m, m + k] for k in range(m)]
        put(V, orient(V, F, V.mean(0)), pal['skin'])
        inner = [o + n * 0.0008 + u * (0.5 + (px - 0.5) * 0.55) * S[0] + v * (py * 0.55 - 0.03) * S[1] for px, py in outline]
        V = np.array(inner)
        put(V, orient(V, [list(range(m))], V.mean(0) - n), pal['ear'])

    # Buzz-cut hair: a shell over the skull down to your hairline, with a visible edge.
    hl = cfg['hairline']  # heights (m above the eyes) at the octagon's 8 corners, front-right first
    th = cfg['hair_thickness']
    O0, O1 = hs.octagon(hs.R[0, 0]), hs.octagon(hs.R[1, 0])
    centre = lambda z: np.array([0.0, sum(hs.params(z)[:2]) / 2, z])

    def offset(p, d):
        q = p - centre(p[2])
        q[2] = 0
        return p + unit(q) * d + np.array([0, 0, d * 0.4])

    hair_rings = [np.array([offset(p, th) for p in O0]), np.array([offset(p, th) for p in O1])]
    for t in (0.35, 0.7, 1.0):
        r = []
        for i in range(8):
            z = O1[i, 2] + (hs.eye_z + hl[i] - O1[i, 2]) * t
            r.append(offset(hs.octagon(z)[i], th))
        hair_rings.append(np.array(r))
    edge = np.array([offset(hs.octagon(hs.eye_z + hl[i])[i], 0.0007) for i in range(8)])
    hair_rings.append(edge)
    V, F = loft(hair_rings, cap_start=True)
    put(V, F, pal['hair'], 'hair')

    # Beard: a chunky band along the jaw, from the sideburns round the chin, with an under-chin.
    mz = lm(61)[2]
    top_c = lm(0)[2] + 0.006  # top of the mustache at the center
    chin_top = top_c - 0.0105 - cfg['teeth_height'] - 0.007  # beard starts under the lower lip
    secs = []
    for theta in np.radians(np.linspace(-cfg['beard_span'], cfg['beard_span'], 13)):
        at = abs(np.degrees(theta))
        top = np.interp(at, [0, 16, 30, 55, 80, 100], [chin_top, chin_top + 0.004, mz - 0.002, hs.eye_z - 0.052, hs.eye_z - 0.042, hs.eye_z - 0.036])
        bot = np.interp(at, [0, 35, 65, 100], [hs.chin_z - 0.004, hs.chin_z + 0.006, hs.chin_z + 0.03, hs.chin_z + 0.055])
        pt, nt = hs.surface(theta, top)
        pb, nb = hs.surface(theta, bot)
        thick = cfg['beard_thickness'] * np.interp(at, [0, 60, 100], [1.0, 0.8, 0.45])
        under = pb + nb * thick + np.array([0, 0.03, -0.006]) * np.interp(at, [0, 70, 100], [1.0, 0.6, 0.0])
        secs.append(np.array([pt + nt * 0.0005, pt + nt * thick, pb + nb * thick, under, under + np.array([0, 0.004, 0.004])]))
    V = np.vstack(secs)
    m = 5
    F = [[i * m + k, i * m + k + 1, (i + 1) * m + k + 1, (i + 1) * m + k] for i in range(len(secs) - 1) for k in range(m - 1)]
    F += [[0, 1, 2, 3, 4][::-1], [(len(secs) - 1) * m + k for k in range(m)]]
    F = orient(V, F, centre(hs.chin_z + 0.04) + np.array([0, -0.01, 0]))
    put(V, F, pal['beard'], 'hair')

    # Mustache: a thick bar over the smile, dropping at the corners into the beard.
    mw = abs(lm(291)[0] - lm(61)[0]) / 2
    pts = []
    for x, dz_top, dz_bot in ((-1.1, -0.004, -0.017), (-0.92, 0.0, -0.012), (-0.5, 0.001, -0.0105), (0.0, 0.002, -0.0105),
                              (0.5, 0.001, -0.0105), (0.92, 0.0, -0.012), (1.1, -0.004, -0.017)):
        X = x * mw
        zt, zb_ = top_c + dz_top, top_c + dz_bot
        y = min(yface(zt), yface(zb_))
        th_m = cfg['mustache_thickness']
        pts.append(np.array([[X, y + 0.001, zt], [X, y - th_m, zt - 0.001], [X, y - th_m, zb_], [X, y + 0.001, zb_]]))
    V = np.vstack(pts)
    F = [[i * 4 + k, i * 4 + (k + 1) % 4, (i + 1) * 4 + (k + 1) % 4, (i + 1) * 4 + k] for i in range(len(pts) - 1) for k in range(4)]
    F += [[0, 1, 2, 3], [(len(pts) - 1) * 4 + k for k in (3, 2, 1, 0)]]
    F = orient(V, F, V.mean(0) + np.array([0, 0.01, 0]))
    put(V, F, pal['mustache'], 'hair')

    # The smile: a curved band of teeth under the mustache, the lower lip below it.
    tw = mw * 0.9
    t_top = top_c - 0.0095
    rows_t, rows_l = [], []
    for x in np.linspace(-1, 1, 7):
        X = x * tw
        lift = 0.008 * x * x
        y = yface(t_top) + 0.0005 + 0.003 * x * x
        rows_t.append([[X, y, t_top + lift + 0.0005], [X, y, t_top - cfg['teeth_height'] + lift]])
        lb = t_top - cfg['teeth_height'] + lift
        rows_l.append([[X * 0.96, y - 0.0015, lb + 0.0006], [X * 0.92, y - 0.0025, lb - 0.0045 * (1 - 0.5 * x * x)]])
    for rows, col in ((rows_t, pal['teeth']), (rows_l, pal['lips'])):
        V = np.array(rows).reshape(-1, 3)
        F = [[i * 2, i * 2 + 1, (i + 1) * 2 + 1, (i + 1) * 2] for i in range(len(rows) - 1)]
        F = orient(V, F, V.mean(0) + np.array([0, 0.02, 0]))
        put(V, F, col, 'skin')

    # Bigger head (stylized), scaled about the top of the neck.
    s = cfg['head_scale']
    pivot = np.array([0.0, -0.035, hs.chin_z])
    for V, F, col, mat in out:
        if mat == 'neck':
            w = smoothstep(nz - 0.02, hs.chin_z + 0.02, V[:, 2])[:, None]
            V = pivot + (V - pivot) * (1 + (s - 1) * w)
            mat = 'skin'
        else:
            V = pivot + (V - pivot) * s
        parts.add(V, F, col, mat=mat, jitter=0)
    eyes_z = pivot[2] + (hs.eye_z - pivot[2]) * s
    return {'eyes_z': eyes_z}


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
        parts.add(V, F, pal['skin'], mat='skin')
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
            n = cfg['leg_sides']
            r = ring(pants_b, axis_pt, (0, 0, 1), n, reach=0.25)
            if z > crotch_z - 0.02:
                # Above the crotch the two tubes meet: the vertices facing the other leg sit on the
                # trousers' own front / back center line.
                ang = 2 * np.pi * (np.arange(n) + 0.5) / n
                dx = np.sin(ang)  # ring() directions: x component (ref = front, axis = up)
                fb = center_line(g, z) or (axis_pt[1] - 0.1, axis_pt[1] + 0.1)
                inner = (dx * sgn < -0.3) | (r[:, 0] * sgn < 0.0)
                r[inner, 0] = 0.0
                r[inner, 1] = np.where(np.cos(ang[inner]) > 0, fb[0], fb[1])
            leg.append(r)
        leg[-1] = leg[-1].mean(0) + (leg[-1] - leg[-1].mean(0)) * 1.05  # slight flare at the hem
        V, F = loft(leg)
        parts.add(V, F, pal['pants'], mat='cloth')
        sneaker(g, parts, cfg, side)

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
    V, F = chamfer_box(palm_c, np.array([along, across, nrm]), np.array([length / 2 + 0.006, width / 2, 0.016]) * s, k=0.25)
    parts.add(V, F, pal['skin'], mat='skin')
    for k in range(1, 6):
        chain = [g.bone(f'finger{k}-{j}.{side}') for j in (1, 2, 3)] + [g.bone(f'finger{k}-3.{side}', tail=True)]
        thick = (0.0115 if k > 1 else 0.013) * s
        for a, b in zip(chain[:-1], chain[1:]):
            ax0 = unit(b - a)
            ax1 = unit(np.cross(nrm, ax0))
            ax2 = np.cross(ax0, ax1)
            V, F = chamfer_box((a + b) / 2, np.array([ax0, ax1, ax2]), [np.linalg.norm(b - a) / 2 + 0.003, thick, thick * 0.92], k=0.22)
            parts.add(V, F, pal['skin'], mat='skin')


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

MATERIALS = {  # name: (roughness, metallic, coat, grain texture or None)
    'skin': (0.78, 0.0, 0.0, 'skin'), 'hair': (0.9, 0.0, 0.0, 'hair'), 'eyes': (0.25, 0.0, 0.8, None),
    'cloth': (0.92, 0.0, 0.0, 'cloth'), 'body': (0.7, 0.0, 0.0, 'cloth'), 'metal': (0.45, 1.0, 0.0, None),
    'beads': (0.3, 0.0, 0.6, None)}
GRAIN_TILE = 0.12  # meters per repeat of the grain textures


def grain_textures(out, size=512, seed=4):
    """Subtle, tileable 'painted' grain (values just under 1, multiplied with the facet colors)."""
    rng = np.random.default_rng(seed)
    f = np.fft.fftfreq(size)
    fx, fy = np.meshgrid(f, f)

    def noise(lo, hi, aspect=1.0):
        k = np.hypot(fx, fy * aspect) + 1e-9
        spec = (rng.normal(size=(size, size)) + 1j * rng.normal(size=(size, size))) * ((k > 1 / hi) & (k < 1 / lo)) / k
        n = np.real(np.fft.ifft2(spec))
        return (n - n.mean()) / (n.std() + 1e-9)

    paths = {}
    for name, amp, parts in (('skin', 0.035, ((2, 8, 1.0, 0.5), (12, 80, 1.0, 0.8))),
                             ('hair', 0.08, ((1.5, 5, 0.25, 0.8), (8, 40, 1.0, 0.5))),
                             ('cloth', 0.06, ((1.5, 4, 1.0, 0.7), (20, 120, 1.0, 0.6)))):
        v = sum(w * noise(lo, hi, asp) for lo, hi, asp, w in parts)
        v = np.clip(0.93 + amp * v / 2, 0.75, 1.0)
        img = (np.repeat(v[..., None], 3, -1) ** (1 / 2.2) * 255 + 0.5).astype(np.uint8)
        paths[name] = out / f'lowpoly_grain_{name}.png'
        Image.fromarray(img).save(paths[name])
    return paths


def box_uvs(me):
    """Per-face planar UVs along the face's dominant axis (fine for a uniform grain)."""
    co = np.array([v.co[:] for v in me.vertices])
    uv = me.uv_layers.new(name='UVMap')
    data = np.zeros((len(me.loops), 2))
    for poly in me.polygons:
        ax = int(np.argmax(np.abs(poly.normal)))
        keep = [i for i in range(3) if i != ax]
        for li in poly.loop_indices:
            data[li] = co[me.loops[li].vertex_index][keep] / GRAIN_TILE
    uv.data.foreach_set('uv', data.astype(np.float32).ravel())


def build_scene(parts, cfg):
    """Blender objects (one per material), flat-shaded, with per-corner colors = facet color ×
    baked ambient occlusion, a grain texture, and UVs for it."""
    bl.reset()
    scene = bpy.context.scene
    grains = grain_textures(BUILD)
    mats = {}
    for name, (rough, metal, coat, grain) in MATERIALS.items():
        m = bpy.data.materials.new(name)
        nt = m.node_tree
        b = nt.nodes['Principled BSDF']
        b.inputs['Roughness'].default_value = rough
        b.inputs['Metallic'].default_value = metal
        b.inputs['Coat Weight'].default_value = coat
        b.inputs['Specular IOR Level'].default_value = 0.3
        col = nt.nodes.new('ShaderNodeVertexColor')
        col.layer_name = 'Col'
        if grain:
            tex = nt.nodes.new('ShaderNodeTexImage')
            tex.image = bpy.data.images.load(str(grains[grain]))
            mix = nt.nodes.new('ShaderNodeMix')
            mix.data_type = 'RGBA'
            mix.blend_type = 'MULTIPLY'
            mix.inputs['Factor'].default_value = 1.0
            nt.links.new(tex.outputs['Color'], mix.inputs['A'])
            nt.links.new(col.outputs['Color'], mix.inputs['B'])
            nt.links.new(mix.outputs['Result'], b.inputs['Base Color'])
        else:
            nt.links.new(col.outputs['Color'], b.inputs['Base Color'])
        m.use_backface_culling = name != 'cloth'
        mats[name] = m
    objs = []
    face_cols = {}
    for name, gr in parts.groups.items():
        V = np.vstack(gr['v'])
        cols = np.vstack(gr['c'])
        me = bpy.data.meshes.new(name)
        me.from_pydata([tuple(map(float, v)) for v in V], [], gr['f'])
        me.update()
        me.shade_flat()
        box_uvs(me)
        ob = bpy.data.objects.new(name, me)
        scene.collection.objects.link(ob)
        me.materials.append(mats[name])
        objs.append(ob)
        face_cols[name] = cols
    # Ambient occlusion, baked per face corner (crevices, under the brows, nose and arms).
    scene.render.engine = 'CYCLES'
    scene.cycles.device = 'CPU'
    scene.cycles.samples = cfg['ao_samples']
    scene.world.light_settings.distance = cfg['ao_distance']
    for ob in objs:
        ao = ob.data.color_attributes.new('AO', 'FLOAT_COLOR', 'CORNER')
        ob.data.color_attributes.active_color = ao
    bpy.ops.object.select_all(action='DESELECT')
    for ob in objs:
        ob.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.object.bake(type='AO', target='VERTEX_COLORS')
    floor = cfg['ao_floor']
    for ob in objs:
        me = ob.data
        ao = np.empty(len(me.loops) * 4, np.float32)
        me.color_attributes['AO'].data.foreach_get('color', ao)
        ao = ao.reshape(-1, 4)[:, 0]
        per_face = face_cols[ob.name]
        corner = np.repeat(per_face, [len(p.vertices) for p in me.polygons], axis=0)
        shade = floor + (1 - floor) * np.clip(ao, 0, 1) ** cfg['ao_gamma']
        col = me.color_attributes.new('Col', 'FLOAT_COLOR', 'CORNER')
        col.data.foreach_set('color', np.c_[corner * shade[:, None], np.ones(len(corner))].astype(np.float32).ravel())
        me.color_attributes.remove(me.color_attributes['AO'])
        me.color_attributes.active_color = me.color_attributes['Col']
        me.color_attributes.render_color_index = me.color_attributes.active_color_index  # → COLOR_0
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
                              export_image_format='WEBP', export_image_quality=85,
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
