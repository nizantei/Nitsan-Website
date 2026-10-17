"""Geometry built in plain numpy, in MakeHuman units (dm, Y up, front +Z):
body regions from the rig's skin weights, the tee / pants / belt as shells offset from the body
surface, procedural sneakers, and a fill for the open mouth. No Blender needed here."""
import numpy as np

import mh


# ---------- mesh utilities ----------

def vertex_normals(V, faces):
    a, b, c, d = faces.T
    fn = np.cross(V[c] - V[a], V[d] - V[b])  # quad normal from diagonals (works for degenerate quads)
    tri = c == d
    fn[tri] = np.cross(V[b[tri]] - V[a[tri]], V[c[tri]] - V[a[tri]])
    n = np.zeros_like(V)
    for k in (a, b, c, d):
        np.add.at(n, k, fn)
    return n / (np.linalg.norm(n, axis=1, keepdims=True) + 1e-12)


def neighbors(faces, n):
    nb = [set() for _ in range(n)]
    for f in faces.tolist():
        f = list(dict.fromkeys(f))
        for i in range(len(f)):
            a, b = f[i], f[(i + 1) % len(f)]
            nb[a].add(b)
            nb[b].add(a)
    return nb


def smooth(P, nb, idx, iters, lam=0.5, fixed=None):
    """Laplacian smoothing of the vertices in idx (others stay put)."""
    P = P.copy()
    idx = np.asarray(idx)
    nbl = [np.fromiter(nb[i], int) for i in idx]
    fixed = set() if fixed is None else set(fixed)
    move = np.array([i not in fixed and len(nbl[k]) > 0 for k, i in enumerate(idx)])
    for _ in range(iters):
        avg = np.array([P[n].mean(0) if len(n) else P[i] for i, n in zip(idx, nbl)])
        P[idx[move]] += lam * (avg[move] - P[idx[move]])
    return P


def submesh(faces, face_mask):
    """Faces → (vertex ids used, faces re-indexed into that list)."""
    f = faces[face_mask]
    used = np.unique(f)
    remap = -np.ones(faces.max() + 1, np.int64)
    remap[used] = np.arange(len(used))
    return used, remap[f]


def boundary_vertices(faces):
    edges = {}
    for f in faces.tolist():
        f = list(dict.fromkeys(f))
        for i in range(len(f)):
            e = tuple(sorted((f[i], f[(i + 1) % len(f)])))
            edges[e] = edges.get(e, 0) + 1
    return np.unique([v for e, c in edges.items() if c == 1 for v in e])


def boundary_loops_neighbors(faces):
    """For boundary vertices: their neighbors along the boundary."""
    edges = {}
    for f in faces.tolist():
        f = list(dict.fromkeys(f))
        for i in range(len(f)):
            e = tuple(sorted((f[i], f[(i + 1) % len(f)])))
            edges[e] = edges.get(e, 0) + 1
    nb = {}
    for (a, b), c in edges.items():
        if c == 1:
            nb.setdefault(a, []).append(b)
            nb.setdefault(b, []).append(a)
    return nb


def smooth_boundary(P, faces, iters=6, lam=0.5, select=None):
    """Smooth open edges (collars, hems) along themselves, so cut lines read as clean seams."""
    nb = boundary_loops_neighbors(faces)
    keys = [k for k in nb if select is None or select(P[k])]
    P = P.copy()
    for _ in range(iters):
        avg = {k: P[nb[k]].mean(0) for k in keys}
        for k in keys:
            P[k] += lam * (avg[k] - P[k])
    return P


def erode(mask, faces, rings):
    """Shrink a vertex mask by `rings` edge rings."""
    m = mask.copy()
    for _ in range(rings):
        bad = np.zeros_like(m)
        for f in faces:
            vals = m[f]
            if vals.any() and not vals.all():
                bad[f] = True
        m &= ~bad
    return m


# ---------- body regions and joints ----------

def regions():
    R = mh.rig()
    pick = lambda *pre: [b for b in R if b.split('.')[0].startswith(pre)]
    rw = mh.region_weight
    return {
        'head': rw(mh.descendants('head')),
        'neck': rw(pick('neck')),
        'torso': rw(pick('spine', 'clavicle', 'shoulder', 'breast')),
        'upperarm': rw(pick('upperarm')),
        'lowerarm': rw(pick('lowerarm')),
        'hand': rw(pick('wrist', 'finger', 'metacarpal')),
        'pelvis': rw(pick('pelvis', 'root')),
        'leg': rw(pick('upperleg', 'lowerleg')),
        'foot': rw(pick('foot', 'toe')),
    }


def joint(V, name):
    return V[mh.vertex_groups()[name]].mean(0)


def along(P, a, b):
    d = b - a
    return ((P - a) @ d) / (d @ d)


def body_frame(V):
    g = mh.vertex_groups()
    body = g['body']
    J = {n: joint(V, n) for n in g if n.startswith('joint-')}
    floor = V[body, 1].min()
    hip_y = (J['joint-l-upper-leg'][1] + J['joint-r-upper-leg'][1]) / 2
    return J, floor, hip_y


# ---------- garments ----------

def tee(V, faces_body, reg, cfg, belt_y):
    J, _, _ = body_frame(V)
    side_l = V[:, 0] > 0
    t_l = along(V, J['joint-l-shoulder'], J['joint-l-elbow'])
    t_r = along(V, J['joint-r-shoulder'], J['joint-r-elbow'])
    t_arm = np.where(side_l, t_l, t_r)
    sleeve = reg['upperarm'] * (t_arm < cfg['sleeve_length'])
    torso = reg['torso'] + reg['pelvis'] + reg['upperarm'] * (t_arm < 0.05)
    neckish = reg['neck'] + reg['head']
    arms_low = reg['lowerarm'] + reg['hand']
    m = (torso + sleeve > 0.5) & (neckish < cfg['collar']) & (arms_low < 0.3) & (V[:, 1] > belt_y - 0.35)
    m &= reg['leg'] < 0.3
    return m


def pants(V, reg, cfg, belt_y, ankle_y):
    arms = reg['upperarm'] + reg['lowerarm'] + reg['hand']
    return (V[:, 1] < belt_y + 0.25) & (V[:, 1] > ankle_y + cfg['hem_above_ankle']) & (reg['foot'] < 0.5) & (arms < 0.2) & (reg['torso'] + reg['pelvis'] + reg['leg'] > 0.5)


def shell(V, faces, mask, offset):
    """Copy the faces whose vertices are all in mask; offset along normals."""
    fm = mask[faces].all(1)
    used, f = submesh(faces, fm)
    N = vertex_normals(V, faces)
    P = V[used] + N[used] * offset
    return used, f, P, fm


def keep_clearance(P, used, V, faces, min_offset):
    """After smoothing, push shell vertices back out to at least min_offset above the body,
    so skin never pokes through the fabric."""
    N = vertex_normals(V, faces)[used]
    d = ((P - V[used]) * N).sum(1)
    short = d < min_offset
    P = P.copy()
    P[short] += (min_offset - d[short])[:, None] * N[short]
    return P


def flatten_fly(P, used, V, crotch_y):
    """Trouser fronts span from thigh to thigh: cap anything at the front of the crotch that
    sticks out past the thigh fronts at the same height."""
    Vu = V[used]
    out = P.copy()
    band = (Vu[:, 1] > crotch_y - 0.5) & (Vu[:, 1] < crotch_y + 1.4) & (P[:, 2] > 0)
    center = band & (np.abs(Vu[:, 0]) < 0.75)
    thighs = band & (np.abs(Vu[:, 0]) > 0.55) & (np.abs(Vu[:, 0]) < 1.1)
    for i in np.where(center)[0]:
        ref = thighs & (np.abs(P[:, 1] - P[i, 1]) < 0.12)
        if ref.sum() < 3:
            continue
        cap = np.percentile(P[ref, 2], 85) + 0.06 * (1 - abs(Vu[i, 0]) / 0.75)
        out[i, 2] = min(out[i, 2], cap)
    return out


def shape_pants(P, used, V, reg, cfg):
    """Turn leg shells into straight trouser legs (minimum radius around the leg axis)."""
    J, _, _ = body_frame(V)
    out = P.copy()
    for side, sgn in (('l', 1), ('r', -1)):
        a, k, b = J[f'joint-{side}-upper-leg'], J[f'joint-{side}-knee'], J[f'joint-{side}-ankle']
        sel = np.where((np.sign(V[used, 0]) == sgn) & (reg['leg'][used] > 0.5))[0]
        for i in sel:
            p = P[i]
            best = None
            for s0, s1, t0 in ((a, k, 0.0), (k, b, 0.5)):
                d = s1 - s0
                t = np.clip((p - s0) @ d / (d @ d), 0, 1)
                c = s0 + t * d
                dist = np.linalg.norm(p - c)
                if best is None or dist < best[0]:
                    best = (dist, c, t0 + 0.5 * t)
            r, c, t = best
            radial = (p - c) / (r + 1e-9)
            r_min = cfg['thigh_radius'] + (cfg['hem_radius'] - cfg['thigh_radius']) * smoothstep(0.0, 0.6, t)
            inner = radial[0] * sgn < -0.5 and t < 0.3
            new_r = r + 0.6 * cfg['offset'] if inner else max(r + cfg['offset'] * 0.3, r_min)
            out[i] = c + radial * new_r
    return out


def smoothstep(a, b, x):
    t = np.clip((x - a) / (b - a), 0, 1)
    return t * t * (3 - 2 * t)


def belt(P_pants, cfg, belt_y, n=128):
    """A band hugging the trousers at belt height. Returns verts, quads, buckle box verts/faces."""
    band = P_pants[np.abs(P_pants[:, 1] - belt_y) < cfg['height'] * 0.7]
    center = band.mean(0)
    ang = np.arctan2(band[:, 0] - center[0], band[:, 2] - center[2])
    rad = np.hypot(band[:, 0] - center[0], band[:, 2] - center[2])
    bins = np.linspace(-np.pi, np.pi, n + 1)
    r = np.zeros(n)
    for i in range(n):
        sel = (ang >= bins[i]) & (ang < bins[i + 1])
        r[i] = rad[sel].max() if sel.any() else np.nan
    r = np.interp(np.arange(n), np.where(~np.isnan(r))[0], r[~np.isnan(r)], period=n)
    r = np.convolve(np.r_[r[-2:], r, r[:2]], np.ones(5) / 5, 'valid') + cfg['offset']
    th = (bins[:-1] + bins[1:]) / 2
    verts, quads = [], []
    for y in (belt_y - cfg['height'] / 2, belt_y + cfg['height'] / 2):
        verts += [[center[0] + np.sin(t) * ri, y, center[2] + np.cos(t) * ri] for t, ri in zip(th, r)]
    for i in range(n):
        j = (i + 1) % n
        quads.append([i, j, n + j, n + i])
    front = int(np.argmin(np.abs(th)))
    fz = center[2] + r[front]
    bw, bh, bd = 0.55, cfg['height'] * 1.15, 0.07
    bx = [[center[0] + sx * bw / 2, belt_y + sy * bh / 2, fz + sz * bd] for sx in (-1, 1) for sy in (-1, 1) for sz in (0, 1)]
    bf = [[0, 1, 3, 2], [4, 6, 7, 5], [0, 4, 5, 1], [2, 3, 7, 6], [0, 2, 6, 4], [1, 5, 7, 3]]
    return np.array(verts), np.array(quads), np.array(bx), np.array(bf)


def sneaker(V, reg, side, cfg, slices=40, ring=28):
    """Procedural low-top sneaker around one foot: upper (closed, rounded) + sole slab + laces."""
    g = mh.vertex_groups()
    J, floor, _ = body_frame(V)
    sgn = 1 if side == 'l' else -1
    body = np.zeros(len(V), bool)
    body[g['body']] = True
    foot = body & (reg['foot'] > 0.4) & (np.sign(V[:, 0]) == sgn)
    P = V[foot]
    m = cfg['margin']
    z0, z1 = P[:, 2].min() - m, P[:, 2].max() + m * 1.4
    zs = np.linspace(z0, z1, slices)
    win = (z1 - z0) / slices * 1.5
    xmin, xmax, ytop = [], [], []
    for z in zs:
        sel = np.abs(P[:, 2] - z) < win
        low = sel & (P[:, 1] < floor + 0.45)
        q = P[low] if low.sum() > 3 else P[sel] if sel.sum() > 3 else None
        if q is None:
            xmin.append(np.nan); xmax.append(np.nan); ytop.append(np.nan)
        else:
            xmin.append(q[:, 0].min()); xmax.append(q[:, 0].max()); ytop.append(P[sel, 1].max() if sel.any() else np.nan)
    def fill(a):
        a = np.array(a)
        ok = ~np.isnan(a)
        return np.interp(np.arange(len(a)), np.where(ok)[0], a[ok])
    xmin, xmax, ytop = fill(xmin), fill(xmax), fill(ytop)
    k = np.ones(5) / 5
    pad = lambda a: np.convolve(np.r_[a[:1], a[:1], a, a[-1:], a[-1:]], k, 'valid')
    xmin, xmax, ytop = pad(xmin) - m, pad(xmax) + m, pad(ytop)
    ankle_cap = J[f'joint-{side}-ankle'][1] - 0.15
    ytop = np.minimum(ytop + m, ankle_cap)
    # Sneaker silhouette: heel collar, raised throat over the instep, low rounded toe box.
    sp = np.linspace(0, 1, slices)  # 0 heel → 1 toe
    profile = np.interp(sp, [0.0, 0.12, 0.3, 0.55, 0.75, 0.9, 1.0], [0.6, 0.74, 0.76, 0.66, 0.5, 0.42, 0.34])
    ytop = np.maximum(ytop, floor + profile)

    s = np.linspace(0, 1, slices)
    edge = np.minimum(s, 1 - s)
    cap = np.where(edge < 0.14, np.sqrt(np.clip(1 - (1 - edge / 0.14) ** 2, 0, 1)), 1.0)
    cap_h = np.where(edge < 0.14, np.sqrt(np.clip(1 - (1 - edge / 0.14) ** 2, 0, 1)) * 0.6 + 0.4, 1.0)
    cap_h[0] = cap_h[-1] = 0.35
    xc = (xmin + xmax) / 2
    a = (xmax - xmin) / 2 * cap
    sole_top = floor + 0.06
    b = (ytop - sole_top) * cap_h
    n = 3.0  # superellipse exponent: rounder at 2, boxier above
    th = np.linspace(0, np.pi, ring)
    cx = np.sign(np.cos(th)) * np.abs(np.cos(th)) ** (2 / n)
    cy = np.abs(np.sin(th)) ** (2 / n)
    verts = []
    for i in range(slices):
        for j in range(ring):
            verts.append([xc[i] + a[i] * cx[j], sole_top - 0.05 + (b[i] + 0.05) * cy[j], zs[i]])
    faces = [[i * ring + j, i * ring + j + 1, (i + 1) * ring + j + 1, (i + 1) * ring + j] for i in range(slices - 1) for j in range(ring - 1)]
    upper = (np.array(verts), np.array(faces))

    # Sole: footprint outline extruded downward, with toe spring.
    t = cfg['sole_thickness']
    outline = [[xc[i] - a[i] - 0.03, zs[i]] for i in range(slices)] + [[xc[i] + a[i] + 0.03, zs[i]] for i in range(slices - 1, -1, -1)]
    outline = np.array(outline)
    spring = lambda z: cfg.get('toe_spring', 0.06) * smoothstep(0.8, 1.0, (z - z0) / (z1 - z0))
    top = [[x, sole_top + 0.02 + spring(z), z] for x, z in outline]
    cen = outline.mean(0)
    bot = [[cen[0] + (x - cen[0]) * 0.985, floor - t + spring(z) * 1.6, cen[1] + (z - cen[1]) * 0.995] for x, z in outline]
    sv = np.array(top + bot + [[cen[0], sole_top + 0.02, cen[1]], [cen[0], floor - t, cen[1]]])
    N = len(outline)
    sf = [[i, (i + 1) % N, N + (i + 1) % N, N + i] for i in range(N)]
    sf += [[2 * N, (i + 1) % N, i, i] for i in range(N)]
    sf += [[2 * N + 1, N + i, N + (i + 1) % N, N + (i + 1) % N] for i in range(N)]
    sole = (sv, np.array(sf))

    # Laces: thin bars across the instep.
    lv, lf = [], []
    for li, sl in enumerate(np.linspace(0.48, 0.68, 5)):
        i = int(sl * (slices - 1))
        y = sole_top - 0.05 + b[i] + 0.05 + 0.012
        w = a[i] * 0.42
        base = len(lv)
        for sx in (-1, 1):
            for sz in (-1, 1):
                for sy in (0, 1):
                    lv.append([xc[i] + sx * w, y + sy * 0.03, zs[i] + sz * 0.035])
        lf += [[base + q for q in f] for f in ([0, 2, 6, 4], [1, 5, 7, 3], [0, 1, 3, 2], [4, 6, 7, 5], [0, 4, 5, 1], [2, 3, 7, 6])]
    laces = (np.array(lv), np.array(lf))
    return upper, sole, laces


# ---------- mouth fill ----------

UPPER_INNER = [78, 191, 80, 81, 82, 13, 312, 311, 310, 415, 308]
LOWER_INNER = [324, 318, 402, 317, 14, 87, 178, 88, 95]


def mouth_fill(V, corr, depth=0.02):
    """A shallow curved surface spanning the open lips, set just behind them, for the teeth."""
    def point(i):
        c = corr[i]
        return (V[c['tri']] * np.array(c['bary'])[:, None]).sum(0)
    loop = np.array([point(i) for i in UPPER_INNER + LOWER_INNER])
    center = loop.mean(0)
    rim = center + (loop - center) * 0.97
    rim[:, 2] -= depth
    inner = center + (loop - center) * 0.55
    inner[:, 2] -= depth * 2.2
    c = center.copy()
    c[2] -= depth * 2.8
    verts = np.vstack([rim, inner, c[None]])
    n = len(loop)
    faces = [[i, (i + 1) % n, n + (i + 1) % n, n + i] for i in range(n)]
    faces += [[n + i, n + (i + 1) % n, 2 * n, 2 * n] for i in range(n)]
    faces = np.array(faces)
    a, b, c = verts[faces[0, 0]], verts[faces[0, 1]], verts[faces[0, 2]]
    if np.cross(b - a, c - a)[2] < 0:  # face the viewer (+Z)
        faces = faces[:, ::-1]
        faces[n:] = faces[n:][:, [1, 2, 3, 0]]  # keep the fan's repeated center vertex last
    return verts, faces
