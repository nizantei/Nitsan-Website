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


def fill_crotch(P, used, V, crotch_y, drop=0.25):
    """Trouser fabric spans the gap between the thighs instead of following the body into it:
    lift the front (and back) centre up to the line between the thigh surfaces, and let the
    crotch seam hang a little lower than the body's."""
    out = P.copy()
    Vu = V[used]
    zc = np.median(Vu[np.abs(Vu[:, 1] - crotch_y) < 0.5, 2])
    band = (P[:, 1] > crotch_y - 1.2) & (P[:, 1] < crotch_y + 1.6)
    for sgn_z in (1, -1):
        side = band & (np.sign(P[:, 2] - zc) == sgn_z)
        for i in np.where(side & (np.abs(P[:, 0]) < 0.8))[0]:
            ref = side & (np.abs(P[:, 1] - P[i, 1]) < 0.1) & (np.abs(P[:, 0]) > 0.75) & (np.abs(P[:, 0]) < 1.2)
            if ref.sum() < 3:
                continue
            edge = np.percentile(P[ref, 2] * sgn_z, 70) * sgn_z
            w = 1 - abs(P[i, 0]) / 0.8
            if (P[i, 2] - edge) * sgn_z < 0:
                out[i, 2] = P[i, 2] + (edge - P[i, 2]) * (0.6 + 0.4 * w) - sgn_z * 0.04 * w
    d = np.hypot(P[:, 0] / 0.9, (P[:, 1] - crotch_y) / 1.4)
    out[:, 1] -= drop * np.clip(1 - d, 0, 1) ** 2
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


# ---------- tailoring (Blender axes: meters, Z up, front -Y; applied after subdivision) ----------

def pants_features(P, tl):
    """Per point of the trousers: displacement along the normal (m) and a 'seam' darkness 0..1.
    tl: leg axes, belt / crotch / hem heights and sizes from build_character (meta['tailor'])."""
    disp = np.zeros(len(P))
    seam = np.zeros(len(P))
    belt_z, crotch_z, hem_z = tl['belt_z'], tl['crotch_z'], tl['hem_z']
    z = P[:, 2]
    front = P[:, 1] < tl['center_y']
    for side, sgn in (('l', 1.0), ('r', -1.0)):
        on = np.sign(P[:, 0]) == sgn
        hip, ank = np.array(tl['legs'][side]['hip']), np.array(tl['legs'][side]['ankle'])
        a = (ank - hip) / np.linalg.norm(ank - hip)
        rel = P - hip
        radial = rel - np.outer(rel @ a, a)
        fwd = np.array([0.0, -1.0, 0.0]) - a[1] * -1 * a
        fwd /= np.linalg.norm(fwd)
        lat = np.cross(a, fwd) * sgn
        theta = np.arctan2(radial @ lat, radial @ fwd)  # 0 = front, ±π = back
        leg = on & (z < crotch_z + 0.02)
        below = smoothstep(crotch_z + 0.03, crotch_z - 0.1, z)
        # Pressed creases, front and back, soft in the geometry and crisp in the color map.
        cr = np.exp(-(theta / 0.13) ** 2) + 0.7 * np.exp(-((np.abs(theta) - np.pi) / 0.13) ** 2)
        disp += np.where(leg, tl['crease'] * cr * below, 0)
        seam += np.where(leg, 0.25 * (np.exp(-(theta / 0.03) ** 2)) * below, 0)
        # Side seams and inseams; the hem's stitch line.
        for th in (np.pi / 2, -np.pi / 2):
            seam += np.where(leg, np.exp(-((theta - th) / 0.025) ** 2) * below, 0)
        seam += np.where(leg, np.exp(-((z - (hem_z + 0.035)) / 0.0012) ** 2) * (np.abs(theta) < 2.9), 0)
        # A soft break where the hem rests on the shoe.
        brk = smoothstep(hem_z + 0.08, hem_z + 0.01, z) * np.exp(-(theta / 0.9) ** 2)
        disp += np.where(leg, tl['break'] * brk * (0.5 + 0.5 * np.sin((z - hem_z) / 0.028 * 2 * np.pi)), 0)
        # Two front pleats per side, folding down from the waistband into the crease.
        x_crease = hip[0] + fwd[0] * 0  # the crease line sits over the leg axis
        for k, off in enumerate((0.0, 0.045)):
            xp = x_crease + sgn * off - sgn * 0.012
            fade = smoothstep(belt_z - (0.2 if k == 0 else 0.13), belt_z - 0.03, z)
            ridge = np.exp(-((P[:, 0] - xp) / 0.006) ** 2) - 0.6 * np.exp(-((P[:, 0] - xp - sgn * 0.009) / 0.006) ** 2)
            disp += np.where(front & on, tl['pleat'] * ridge * fade, 0)
            seam += np.where(front & on, 0.35 * np.exp(-((P[:, 0] - xp - sgn * 0.004) / 0.0015) ** 2) * fade, 0)
        # Slanted side pockets.
        p0 = np.array([sgn * tl['hip_half'] * 0.62, belt_z - 0.02])
        p1 = np.array([sgn * tl['hip_half'] * 0.93, belt_z - 0.17])
        d = p1 - p0
        t = np.clip(((np.c_[P[:, 0], z] - p0) @ d) / (d @ d), 0, 1)
        dist = np.linalg.norm(np.c_[P[:, 0], z] - (p0 + t[:, None] * d), axis=1)
        pk = np.exp(-(dist / 0.0022) ** 2) * front * on
        disp -= 0.0012 * pk
        seam += pk
    # Fly: a stitched J from the waistband down to the crotch, left of center.
    fz = (z < belt_z - 0.02) & (z > crotch_z + 0.02) & front
    jx = 0.028 - 0.02 * smoothstep(crotch_z + 0.06, crotch_z + 0.02, z)
    seam += np.where(fz, np.exp(-((P[:, 0] - jx) / 0.0015) ** 2), 0)
    seam += np.where(front & (z < belt_z) & (z > crotch_z), np.exp(-(P[:, 0] / 0.0015) ** 2) * 0.6, 0)
    return disp, np.clip(seam, 0, 1)


def belt_solid(P_pants, cfg, belt_z_mh, n=160, thickness=0.035):
    """Belt as a closed band with thickness (MakeHuman units), plus its UVs and a buckle frame
    (rounded rectangle tube) and prong. Returns verts, faces, uvs, uv faces, buckle (v, f)."""
    band = P_pants[np.abs(P_pants[:, 1] - belt_z_mh) < cfg['height'] * 0.7]
    center = band.mean(0)
    ang = np.arctan2(band[:, 0] - center[0], band[:, 2] - center[2])
    rad = np.hypot(band[:, 0] - center[0], band[:, 2] - center[2])
    bins = np.linspace(-np.pi, np.pi, n + 1)
    r = np.full(n, np.nan)
    for i in range(n):
        sel = (ang >= bins[i]) & (ang < bins[i + 1])
        if sel.any():
            r[i] = rad[sel].max()
    ok = ~np.isnan(r)
    r = np.interp(np.arange(n), np.where(ok)[0], r[ok], period=n)
    r = np.convolve(np.r_[r[-3:], r, r[:3]], np.ones(7) / 7, 'valid') + cfg['offset']
    th = (bins[:-1] + bins[1:]) / 2
    h, t = cfg['height'], thickness
    # cross-section (radial offset, height), counter-clockwise with slightly rounded corners
    prof = [(0, -h / 2 + 0.01), (0, h / 2 - 0.01), (-0.008, h / 2), (-t + 0.008, h / 2), (-t, h / 2 - 0.01),
            (-t, -h / 2 + 0.01), (-t + 0.008, -h / 2), (-0.008, -h / 2)]
    m = len(prof)
    verts = [[center[0] + np.sin(a) * (ri + dr), belt_z_mh + dz, center[2] + np.cos(a) * (ri + dr)]
             for a, ri in zip(th, r) for dr, dz in prof]
    faces, uvs, uvf = [], [], []
    for i in range(n + 1):
        for j in range(m + 1):
            uvs.append([i / n, j / m])
    for i in range(n):
        i2 = (i + 1) % n
        for j in range(m):
            j2 = (j + 1) % m
            faces.append([i * m + j, i2 * m + j, i2 * m + j2, i * m + j2])
            uvf.append([i * (m + 1) + j, (i + 1) * (m + 1) + j, (i + 1) * (m + 1) + j + 1, i * (m + 1) + j + 1])
    front = int(np.argmin(np.abs(th)))
    fz = center[2] + r[front] + 0.01
    bw, bh, tube = 0.46, h * 1.12, 0.022
    path = []
    for cx, cy, a0 in ((bw / 2 - 0.06, bh / 2 - 0.06, 0), (-bw / 2 + 0.06, bh / 2 - 0.06, 90),
                       (-bw / 2 + 0.06, -bh / 2 + 0.06, 180), (bw / 2 - 0.06, -bh / 2 + 0.06, 270)):
        for k in range(7):
            a = np.radians(a0 + 90 * k / 6)
            path.append([center[0] + cx + 0.06 * np.cos(a), belt_z_mh + cy + 0.06 * np.sin(a)])
    path = np.array(path)
    bv, bf = [], []
    seg = 8
    N = len(path)
    for i in range(N):
        tng = path[(i + 1) % N] - path[i - 1]
        tng /= np.linalg.norm(tng)
        nrm = np.array([tng[1], -tng[0]])
        for k in range(seg):
            a = 2 * np.pi * k / seg
            off = nrm * np.cos(a) * tube
            bv.append([path[i, 0] + off[0], path[i, 1] + off[1], fz + np.sin(a) * tube])
    for i in range(N):
        for k in range(seg):
            i2, k2 = (i + 1) % N, (k + 1) % seg
            bf.append([i * seg + k, i2 * seg + k, i2 * seg + k2, i * seg + k2])
    # prong: a short bar across the middle of the frame
    base = len(bv)
    for x in (-bw / 2 + 0.06, bw / 2 - 0.06):
        for k in range(seg):
            a = 2 * np.pi * k / seg
            bv.append([center[0] + x, belt_z_mh + np.cos(a) * 0.012, fz + 0.012 + np.sin(a) * 0.012])
    for k in range(seg):
        k2 = (k + 1) % seg
        bf.append([base + k, base + k2, base + seg + k2, base + seg + k])
    return np.array(verts), np.array(faces), np.array(uvs), np.array(uvf), (np.array(bv), np.array(bf))


def belt_loops(P_pants, belt_z_mh, cfg, angles=(-2.4, -1.25, -0.42, 0.42, 1.25, 2.4, np.pi)):
    """Fabric loops standing over the belt (MakeHuman units)."""
    band = P_pants[np.abs(P_pants[:, 1] - belt_z_mh) < cfg['height'] * 0.7]
    center = band.mean(0)
    ang = np.arctan2(band[:, 0] - center[0], band[:, 2] - center[2])
    rad = np.hypot(band[:, 0] - center[0], band[:, 2] - center[2])
    verts, faces = [], []
    w, h, t = 0.09, cfg['height'] + 0.07, 0.015
    for a in angles:
        sel = np.abs(np.angle(np.exp(1j * (ang - a)))) < 0.08
        r = (rad[sel].max() if sel.any() else rad.max()) + cfg['offset'] + 0.006
        base = len(verts)
        for dx in (-w / 2, w / 2):
            for dz in (-h / 2, h / 2):
                for dr in (0, t):
                    aa = a + dx / r
                    verts.append([center[0] + np.sin(aa) * (r + dr - (0.035 if dr == 0 else 0)),
                                  belt_z_mh + dz, center[2] + np.cos(aa) * (r + dr)])
        faces += [[base + q for q in f] for f in ([0, 2, 6, 4], [1, 5, 7, 3], [0, 1, 3, 2], [4, 6, 7, 5], [0, 4, 5, 1], [2, 3, 7, 6])]
    return np.array(verts), np.array(faces)
