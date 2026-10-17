"""Neutral body shape from character.json (macros + extra body targets), in MakeHuman units."""
import json
from pathlib import Path

import numpy as np

import mh

HERE = Path(__file__).resolve().parent
BUILD = HERE / 'build'


def character():
    return json.loads((HERE / 'character.json').read_text())


def sided(name):
    """'arms/upperarm-muscle-incr' → existing target names (unsided, or l- and r- variants)."""
    if mh.exists(name):
        return [name]
    folder, base = name.split('/', 1)
    both = [f'{folder}/{s}-{base}' for s in ('l', 'r')]
    if all(mh.exists(n) for n in both):
        return both
    raise KeyError(f'unknown target: {name}')


def body_targets(ch):
    out = mh.macro_targets(ch['macros'])
    for name, w in ch.get('body', {}).items():
        if name.startswith('_'):
            continue
        out += [(n, w) for n in sided(name)]
    return out


def neutral(ch=None):
    ch = ch or character()
    return mh.apply(mh.base_mesh()['verts'], body_targets(ch))


def triangles(faces):
    """MakeHuman quads (triangles stored as degenerate quads) → triangles + source face index."""
    tris, src = [], []
    for i, (a, b, c, d) in enumerate(faces.tolist()):
        tris.append((a, b, c)); src.append(i)
        if d != c:
            tris.append((a, c, d)); src.append(i)
    return np.array(tris, np.int64), np.array(src, np.int64)


if __name__ == '__main__':
    v = neutral()
    body = mh.vertex_groups()['body']
    print('height (dm):', round(v[body, 1].max() - v[body, 1].min(), 3))
