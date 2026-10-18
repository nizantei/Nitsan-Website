"""Small parts built inside Blender (Blender axes: meters, Z up, front -Y):

  eyes      the posed MakeHuman eyeballs with a planar UV aimed along the gaze, plus a
            procedural iris / sclera texture tinted from the photo (the photo's own eyes are too
            small and too shaded to project well at close range)
  necklace  a cable chain traced over the neck and tee from points picked on the photo
  bracelet  black beads around the left forearm, where the photo shows them
"""
import math

import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from PIL import Image
from scipy import ndimage

import bl


def _unit(v):
    v = np.asarray(v, float)
    return v / (np.linalg.norm(v, axis=-1, keepdims=True) + 1e-12)


def bvh_of(objs):
    verts, tris, off = [], [], 0
    for ob in objs:
        me = ob.data
        me.calc_loop_triangles()
        co = np.empty(len(me.vertices) * 3, np.float32)
        me.vertices.foreach_get('co', co)
        t = np.empty(len(me.loop_triangles) * 3, np.int64)
        me.loop_triangles.foreach_get('vertices', t)
        verts.append(co.reshape(-1, 3))
        tris.append(t.reshape(-1, 3) + off)
        off += len(co) // 3
    V = np.vstack(verts).astype(float)
    return BVHTree.FromPolygons([Vector(p) for p in V], np.vstack(tris).tolist())


# ---------- eyes ----------

def eye_texture(path, iris_rgb, iris_uv, size=1024, seed=3):
    """Sclera, iris with radial fibers and a dark limbal ring, pupil. UV center = gaze, +v = up.
    The page has no ambient occlusion, so the lid shadow and the darker corners are painted in."""
    rng = np.random.default_rng(seed)
    y, x = (np.mgrid[0:size, 0:size] + 0.5) / size - 0.5
    y = -y  # image rows go down; +v (up on the eyeball) is the top of the image
    r = np.hypot(x, y) / 0.48  # 1 = sphere rim
    a = np.arctan2(y, x)
    ri = iris_uv / 0.48
    t = r / ri  # 1 = iris edge
    sclera = srgb_lin([0.80, 0.74, 0.70])
    noise = ndimage.gaussian_filter(rng.random((size, size)), 6)
    veins = ndimage.gaussian_filter(rng.random((size, size)), 1.2)
    veins = np.clip((veins - 0.55) * 6, 0, 1) * np.clip((r - 0.5) / 0.4, 0, 1) * 0.4
    col = sclera[None, None] * (0.94 + 0.12 * noise[..., None])
    col = col * (1 - veins[..., None]) + srgb_lin([0.72, 0.42, 0.40]) * veins[..., None]
    col *= (1 - 0.35 * np.clip((r - 0.35) / 0.5, 0, 1))[..., None]  # corners in shadow
    # Iris: radial fibers (fine in angle, smooth in radius), lighter collarette, dark limbus.
    fib = np.zeros((size, size))
    for k, amp in ((90, 0.5), (230, 0.35), (510, 0.15)):
        ph = rng.random(k) * 2 * np.pi
        idx = ((a + np.pi) / (2 * np.pi) * k).astype(int) % k
        fib += amp * np.sin(ph[idx] + t * 6)
    iris = np.asarray(iris_rgb, float)[None, None] * (1 + 0.35 * fib[..., None])
    iris *= (1 + 0.6 * np.exp(-((t - 0.52) / 0.1) ** 2))[..., None]
    iris *= (1 - 0.7 * np.clip((t - 0.8) / 0.2, 0, 1))[..., None]
    w = np.clip((1.04 - t) / 0.08, 0, 1)[..., None]
    col = col * (1 - w) + iris * w
    p = np.clip((0.36 - t) / 0.04, 0, 1)[..., None]
    col = col * (1 - p) + np.array([0.008, 0.007, 0.007]) * p
    col *= (1 - 0.5 * np.clip((y / 0.48 + 0.05) / 0.45, 0, 1))[..., None]  # under the upper lid
    Image.fromarray((np.clip(col, 0, 1) ** (1 / 2.2) * 255 + 0.5).astype(np.uint8)).save(path)
    return path


def srgb_lin(c):
    return np.asarray(c, float) ** 2.2


def gaze_from_photo(center_mh, radius_mh, cam, px):
    """Direction (MakeHuman axes) from the eye center to where the photo shows the iris: the
    camera ray through that pixel, intersected with the eyeball."""
    A, t = cam[:2, :3], cam[:2, 3]
    toward = cam[2, :3] / np.linalg.norm(cam[2, :3])
    X0 = np.linalg.pinv(A) @ (np.asarray(px[:2], float) - t)
    X0 = X0 + toward * ((center_mh - X0) @ toward)  # on the ray, at the eye's depth
    off = X0 - center_mh
    d2 = radius_mh ** 2 - off @ off
    front = X0 + toward * np.sqrt(max(d2, 0.0))
    g = front - center_mh
    return g / np.linalg.norm(g)


def aim_eye_uvs(ob, center, gaze, radius, iris_mm=6.4):
    """Planar UVs along the gaze; the back of the ball maps to the sclera at the rim."""
    gaze = _unit(gaze)
    e1 = _unit(np.cross(gaze, [0, 0, 1]))
    e2 = np.cross(e1, gaze)
    me = ob.data
    uv = me.uv_layers.new(name='UVMap')
    co = np.array([v.co[:] for v in me.vertices])
    L = co - center
    u, v, f = L @ e1 / radius, L @ e2 / radius, L @ gaze / radius
    r = np.hypot(u, v)
    back = f < 0
    u[back], v[back] = u[back] / np.maximum(r[back], 1e-6), v[back] / np.maximum(r[back], 1e-6)
    per_vert = np.c_[0.5 + 0.48 * u, 0.5 + 0.48 * v]
    loops = np.array([l.vertex_index for l in me.loops])
    uv.data.foreach_set('uv', per_vert[loops].astype(np.float32).ravel())
    return 0.48 * iris_mm / (radius * 1000)


# ---------- necklace ----------

def _resample(P, step, closed=True):
    P = np.vstack([P, P[:1]]) if closed else P
    seg = np.linalg.norm(np.diff(P, axis=0), axis=1)
    s = np.r_[0, np.cumsum(seg)]
    n = max(int(s[-1] / step), 8)
    t = np.linspace(0, s[-1], n, endpoint=not closed)
    return np.stack([np.interp(t, s, P[:, k]) for k in range(3)], 1)


def _smooth_closed(P, iters=20, lam=0.5, fixed=None):
    P = P.copy()
    for _ in range(iters):
        avg = (np.roll(P, 1, 0) + np.roll(P, -1, 0)) / 2
        d = lam * (avg - P)
        if fixed is not None:
            d[fixed] = 0
        P += d
    return P


def chain_path(px_points, cam_ray, bvh, neck_axis, lift):
    """Front from the photo (ray-cast onto neck/tee), back as an arc around the neck."""
    front = []
    for px in px_points:
        o, d = cam_ray(px)
        hit, nrm, _, _ = bvh.ray_cast(Vector(o), Vector(d), 10.0)
        if hit is not None:
            front.append(np.array(hit) + np.array(nrm) * lift)
    front = np.array(front)
    # Back half: from the last front point around the back of the neck to the first one,
    # at heights blended between the two ends, pushed out onto the surface from the neck axis.
    c, up = neck_axis
    a0 = math.atan2(*(front[-1] - c)[[0, 1]][::-1])  # angle of the end points around the axis
    a1 = math.atan2(*(front[0] - c)[[0, 1]][::-1])
    if a1 < a0:
        a1 += 2 * math.pi
    # the back is +Y (front is -Y): go the way that passes through +Y
    mid = (a0 + a1) / 2
    if math.sin(mid) < 0:
        a1 -= 2 * math.pi
    back = []
    for k in range(1, 40):
        s = k / 40
        ang = a0 + (a1 - a0) * s
        z = front[-1][2] * (1 - s) + front[0][2] * s + 0.012 * math.sin(math.pi * s)
        d = np.array([math.cos(ang), math.sin(ang), 0.0])
        o = np.array([c[0], c[1], z]) + d * 0.2
        hit, nrm, _, _ = bvh.ray_cast(Vector(o), Vector(-d), 0.3)
        if hit is not None:
            back.append(np.array(hit) + np.array(nrm) * lift)
    return np.vstack([front, np.array(back)])


def torus(major, minor, nu=12, nv=6):
    verts, faces = [], []
    for i in range(nu):
        a = 2 * math.pi * i / nu
        for j in range(nv):
            b = 2 * math.pi * j / nv
            verts.append([(major + minor * math.cos(b)) * math.cos(a), (major + minor * math.cos(b)) * math.sin(a), minor * math.sin(b)])
    for i in range(nu):
        for j in range(nv):
            faces.append([i * nv + j, ((i + 1) % nu) * nv + j, ((i + 1) % nu) * nv + (j + 1) % nv, i * nv + (j + 1) % nv])
    return np.array(verts), np.array(faces)


def cable_chain(path, link=0.0026, wire=0.00034, clasp_at=None):
    """Links along a closed path, alternating 90°: elongated tori."""
    P = _resample(path, link * 0.78)
    T = _unit(np.roll(P, -1, 0) - np.roll(P, 1, 0))
    tv, tf = torus(link * 0.36, wire)
    tv[:, 0] *= 1.45  # elongate along the chain
    verts, faces = [], []
    for k, (p, t) in enumerate(zip(P, T)):
        n = _unit(np.cross(t, [0, 0, 1]) if abs(t[2]) < 0.9 else np.cross(t, [1, 0, 0]))
        b = np.cross(t, n)
        if k % 2:
            n, b = b, -n
        R = np.stack([t, n, b], 1)
        verts.append(tv @ R.T + p)
        faces.append(tf + k * len(tv))
    if clasp_at is not None:
        i = int(np.argmin(np.linalg.norm(P - clasp_at, axis=1)))
        cv, cf = torus(0.0028, 0.0006, 16, 8)
        t = T[i]
        n = _unit(np.cross(t, [0, 0, 1]))
        R = np.stack([t, n, np.cross(t, n)], 1)
        verts.append(cv @ R.T + P[i])
        faces.append(cf + sum(len(v) for v in verts[:-1]))
    return np.vstack(verts), np.vstack(faces)


# ---------- bracelet ----------

def uv_sphere(r, nu=16, nv=10):
    verts, faces = [[0, 0, -r]], []
    for j in range(1, nv):
        b = -math.pi / 2 + math.pi * j / nv
        for i in range(nu):
            a = 2 * math.pi * i / nu
            verts.append([r * math.cos(b) * math.cos(a), r * math.cos(b) * math.sin(a), r * math.sin(b)])
    verts.append([0, 0, r])
    top = len(verts) - 1
    for i in range(nu):
        faces.append([0, 1 + (i + 1) % nu, 1 + i, 1 + i])
    for j in range(nv - 2):
        for i in range(nu):
            a, b = 1 + j * nu + i, 1 + j * nu + (i + 1) % nu
            faces.append([a, b, b + nu, a + nu])
    base = 1 + (nv - 2) * nu
    for i in range(nu):
        faces.append([base + i, base + (i + 1) % nu, top, top])
    return np.array(verts, float), np.array(faces)


def bead_ring(center, axis, ring_r, bead_r, seed=5):
    axis = _unit(axis)
    e1 = _unit(np.cross(axis, [0, 0, 1]) if abs(axis[2]) < 0.9 else np.cross(axis, [1, 0, 0]))
    e2 = np.cross(axis, e1)
    n = max(int(2 * math.pi * ring_r / (2 * bead_r * 1.02)), 8)
    rng = np.random.default_rng(seed)
    sv, sf = uv_sphere(bead_r)
    verts, faces = [], []
    for k in range(n):
        a = 2 * math.pi * k / n
        p = center + ring_r * (math.cos(a) * e1 + math.sin(a) * e2)
        s = 1 + rng.uniform(-0.05, 0.05)
        verts.append(sv * s + p)
        faces.append(sf + k * len(sv))
    return np.vstack(verts), np.vstack(faces)


def surface_radius(bvh, center, axis, samples=24, limit=0.06):
    """Typical distance from an axis point to the surrounding surface: rays cast outward from
    inside, so the nearest wall (this limb, not a neighboring one) is what counts."""
    axis = _unit(axis)
    e1 = _unit(np.cross(axis, [0, 0, 1]))
    e2 = np.cross(axis, e1)
    dists = []
    for k in range(samples):
        a = 2 * math.pi * k / samples
        d = math.cos(a) * e1 + math.sin(a) * e2
        hit, _, _, dist = bvh.ray_cast(Vector(center), Vector(d), limit)
        if hit is not None:
            dists.append(dist)
    return float(np.percentile(dists, 80)) if dists else 0.032


def make(name, verts, faces, collection, smooth=True):
    return bl.mesh_object(name, verts, faces, smooth=smooth, collection=collection)
