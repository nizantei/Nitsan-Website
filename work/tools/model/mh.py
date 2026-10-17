"""MakeHuman base mesh + targets, in plain numpy (no MakeHuman/MPFB runtime needed).

Data: cache/mpfb2 (CC0 assets from MPFB2, fetched by fetch_mpfb.sh).
Units: MakeHuman decimeters, Y up, the figure faces +Z (same axes as glTF).
"""
import gzip
import json
from functools import lru_cache
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
DATA = HERE / 'cache' / 'mpfb2' / 'src' / 'mpfb' / 'data'
TARGETS = DATA / 'targets'
CACHE = HERE / 'cache' / 'targets-npz'


@lru_cache(None)
def base_mesh():
    """Returns dict: verts (N,3), uvs (M,2), faces (F,4) vertex indices, face_uvs (F,4), face_group (F,) names."""
    verts, uvs, faces, fuvs, groups = [], [], [], [], []
    group = None
    for line in (DATA / '3dobjs' / 'base.obj').read_text().splitlines():
        if line.startswith('v '):
            verts.append([float(x) for x in line.split()[1:4]])
        elif line.startswith('vt '):
            uvs.append([float(x) for x in line.split()[1:3]])
        elif line.startswith('g '):
            group = line[2:].strip()
        elif line.startswith('f '):
            parts = [p.split('/') for p in line.split()[1:]]
            if len(parts) == 3:
                parts.append(parts[2])  # triangles stored as degenerate quads
            faces.append([int(p[0]) - 1 for p in parts])
            fuvs.append([int(p[1]) - 1 for p in parts])
            groups.append(group)
    return {
        'verts': np.array(verts, np.float64),
        'uvs': np.array(uvs, np.float64),
        'faces': np.array(faces, np.int64),
        'face_uvs': np.array(fuvs, np.int64),
        'face_group': np.array(groups),
    }


@lru_cache(None)
def vertex_groups():
    raw = json.loads((DATA / 'mesh_metadata' / 'basemesh_vertex_groups.json').read_text())
    return {k: np.concatenate([np.arange(a, b + 1) for a, b in v]) for k, v in raw.items()}


@lru_cache(None)
def mirror_table():
    """Index of the mirrored vertex for every base mesh vertex."""
    pairs = np.loadtxt(DATA / 'mesh_metadata' / 'hm08.mirror', dtype=np.int64, usecols=(0, 1))
    n = len(base_mesh()['verts'])
    table = np.arange(n)
    table[pairs[:, 0]] = pairs[:, 1]
    return table


def target(name):
    """Sparse target as (indices, deltas). `name` is relative to targets/, without .target.gz."""
    CACHE.mkdir(parents=True, exist_ok=True)
    npz = CACHE / (name.replace('/', '__') + '.npz')
    if npz.exists():
        d = np.load(npz)
        return d['idx'], d['delta']
    rows = [l.split() for l in gzip.open(TARGETS / f'{name}.target.gz', 'rt') if l.strip() and not l.startswith('#')]
    idx = np.array([int(r[0]) for r in rows], np.int64)
    delta = np.array([[float(x) for x in r[1:4]] for r in rows], np.float64).reshape(-1, 3)
    np.savez(npz, idx=idx, delta=delta)
    return idx, delta


def dense(name):
    out = np.zeros_like(base_mesh()['verts'])
    idx, delta = target(name)
    out[idx] = delta
    return out


def exists(name):
    return (TARGETS / f'{name}.target.gz').exists()


# ---- Macro modifiers (same interpolation scheme MakeHuman uses) ----

def _split3(v, names):
    """0..0.5..1 → weights for (min, average, max)."""
    lo, mid, hi = names
    if v < 0.5:
        return {lo: 1 - v / 0.5, mid: v / 0.5}
    return {mid: 1 - (v - 0.5) / 0.5, hi: (v - 0.5) / 0.5}


def _age(a):
    if a < 0.1875:
        return {'baby': 1 - a / 0.1875, 'child': a / 0.1875}
    if a < 0.5:
        t = (a - 0.1875) / (0.5 - 0.1875)
        return {'child': 1 - t, 'young': t}
    return {'young': 1 - (a - 0.5) / 0.5, 'old': (a - 0.5) / 0.5}


def macro_targets(m):
    """Weighted list of macrodetail targets for macro values in 0..1 (MakeHuman semantics):
    gender (0 female, 1 male), age (0.5 = 25 years, 1 = 90), muscle, weight, height, proportions,
    and ethnicity weights african/asian/caucasian (normalized)."""
    gender = {'female': 1 - m['gender'], 'male': m['gender']}
    age = _age(m['age'])
    muscle = _split3(m['muscle'], ('minmuscle', 'averagemuscle', 'maxmuscle'))
    weight = _split3(m['weight'], ('minweight', 'averageweight', 'maxweight'))
    height = {'minheight': max(0, 0.5 - m['height']) * 2, 'maxheight': max(0, m['height'] - 0.5) * 2}
    prop = {'uncommonproportions': max(0, 0.5 - m['proportions']) * 2, 'idealproportions': max(0, m['proportions'] - 0.5) * 2}
    eth = {k: m[k] for k in ('african', 'asian', 'caucasian')}
    s = sum(eth.values()) or 1
    eth = {k: v / s for k, v in eth.items()}

    out = []
    for g, gw in gender.items():
        for a, aw in age.items():
            for e, ew in eth.items():
                out.append((f'macrodetails/{e}-{g}-{a}', gw * aw * ew))
            for mu, muw in muscle.items():
                for we, wew in weight.items():
                    base = gw * aw * muw * wew
                    out.append((f'macrodetails/universal-{g}-{a}-{mu}-{we}', base))
                    for h, hw in height.items():
                        out.append((f'macrodetails/height/{g}-{a}-{mu}-{we}-{h}', base * hw))
                    for p, pw in prop.items():
                        out.append((f'macrodetails/proportions/{g}-{a}-{mu}-{we}-{p}', base * pw))
    return [(n, w) for n, w in out if w > 1e-6 and exists(n)]


def apply(verts, weighted):
    v = verts.copy()
    for name, w in weighted:
        idx, delta = target(name)
        v[idx] += w * delta
    return v


# ---- Rig (MPFB2 "default" skeleton) ----

@lru_cache(None)
def rig():
    return json.loads((DATA / 'rigs' / 'standard' / 'rig.default.json').read_text())


@lru_cache(None)
def skin_weights():
    """bone name → (vertex indices, weights) for the default rig."""
    raw = json.loads((DATA / 'rigs' / 'standard' / 'weights.default.json').read_text())['weights']
    return {b: (np.array([p[0] for p in pairs], np.int64), np.array([p[1] for p in pairs], np.float64)) for b, pairs in raw.items()}


def descendants(bone):
    r = rig()
    out, todo = [], [bone]
    while todo:
        b = todo.pop()
        out.append(b)
        todo += [k for k, v in r.items() if v.get('parent') == b]
    return out


def region_weight(bones):
    """Per-vertex summed skin weight of the given bones (0..1)."""
    w = np.zeros(len(base_mesh()['verts']))
    for b in bones:
        if b in skin_weights():
            idx, ww = skin_weights()[b]
            w[idx] += ww
    return np.clip(w, 0, 1)
