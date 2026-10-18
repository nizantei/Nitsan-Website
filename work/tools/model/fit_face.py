"""Step 3: fit the MakeHuman face to the photo.

Unknowns: how the head sits in the photo (rotation, scale, offset; weak perspective) and the
weights of MakeHuman face-shape targets and expression units (smile, squint, ...). Solved by
alternating a 3D similarity fit and a bounded linear least squares over the target weights,
then a smooth residual warp moves the face the rest of the way onto the landmarks.

Output: build/shape.npz
  verts        final rest-pose vertices (MakeHuman units)
  head_cam     3x4 matrix mapping MakeHuman points to photo pixels (x right, y down) for the head
  weights      fitted target weights (also written to build/face_fit.json for reading)
Plus build/face_fit_overlay.png (green: photo landmarks, red: fitted model landmarks).

Run:  .venv/bin/python fit_face.py
"""
import json
from collections import defaultdict
from pathlib import Path

import bpy  # noqa: F401  (mathutils needs bpy imported first)
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from PIL import Image, ImageDraw
from scipy.interpolate import RBFInterpolator
from scipy.optimize import lsq_linear

import mh
import shape

HERE = Path(__file__).resolve().parent
BUILD = HERE / 'build'

# MediaPipe face mesh index groups
OVAL = [10, 338, 297, 332, 284, 251, 389, 356, 454, 323, 361, 288, 397, 365, 379, 378, 400, 377, 152, 148, 176, 149, 150, 136, 172, 58, 132, 93, 234, 127, 162, 21, 54, 103, 67, 109]
LIPS = [61, 146, 91, 181, 84, 17, 314, 405, 321, 375, 291, 185, 40, 39, 37, 0, 267, 269, 270, 409, 78, 95, 88, 178, 87, 14, 317, 402, 318, 324, 308, 191, 80, 81, 82, 13, 312, 311, 310, 415]
EYES = [263, 249, 390, 373, 374, 380, 381, 382, 362, 466, 388, 387, 386, 385, 384, 398, 33, 7, 163, 144, 145, 153, 154, 155, 133, 246, 161, 160, 159, 158, 157, 173]
BROWS = [276, 283, 282, 295, 285, 300, 293, 334, 296, 336, 46, 53, 52, 65, 55, 70, 63, 105, 66, 107]
NOSE = [1, 2, 98, 327, 4, 5, 195, 197, 6, 168, 129, 358, 49, 279, 102, 331, 64, 294]
IRIS = list(range(468, 478))


def landmark_weights():
    w = np.full(478, 0.5)
    w[OVAL] = 0.8
    w[BROWS] = 1.0
    w[NOSE] = 1.5
    w[EYES] = 2.0
    w[LIPS] = 2.0
    w[IRIS] = 0.0
    return w


def basis(ch):
    """Columns of the fit: name → dense delta (N,3). Left/right shape targets are paired so
    the face stays symmetric; expression units stay per side."""
    cols = defaultdict(lambda: np.zeros_like(mh.base_mesh()['verts']))
    for group in ch['face']['groups']:
        for f in sorted((mh.TARGETS / group).glob('*.target.gz')):
            name = f'{group}/{f.name[:-10]}'
            key = name.replace('/l-', '/').replace('/r-', '/')
            cols['shape:' + key] += mh.dense(name)
    for unit in ch['face']['expression_units']:
        cols['expr:' + unit] = mh.dense(f'expression/units/caucasian/{unit}')
    return dict(cols)


def landmark_matrix(corr, n_verts):
    """Sparse-ish (478, N) matrix mapping vertices → landmark positions (barycentric)."""
    M = np.zeros((len(corr), n_verts))
    ok = np.zeros(len(corr), bool)
    for i, c in enumerate(corr):
        if c:
            M[i, c['tri']] = c['bary']
            ok[i] = True
    return M, ok


def similarity(X, Q, w):
    """Weighted similarity (s, R, t) with Q ≈ s R X + t (Umeyama)."""
    w = w / w.sum()
    mx, mq = w @ X, w @ Q
    Xc, Qc = X - mx, Q - mq
    C = (Qc * w[:, None]).T @ Xc
    U, S, Vt = np.linalg.svd(C)
    D = np.eye(3)
    D[2, 2] = np.sign(np.linalg.det(U @ Vt))
    R = U @ D @ Vt
    s = (S * np.diag(D)).sum() / (w @ (Xc ** 2).sum(1))
    return s, R, mq - s * R @ mx


# Photo eye contours (MediaPipe): corners, upper lid, lower lid; MakeHuman side names.
LIDS = {
    'r': {'corners': (33, 133), 'upper': [246, 161, 160, 159, 158, 157, 173], 'lower': [7, 163, 144, 145, 153, 154, 155]},
    'l': {'corners': (263, 362), 'upper': [466, 388, 387, 386, 385, 384, 398], 'lower': [249, 390, 373, 374, 380, 381, 382]},
}


def snap_lids(V, cam, P, iters=3, reach=0.22, cover=0.006):
    """Make the eye openings match the photo. Many lid landmarks land on the eyeball when
    correspondences are found, so the fit moves the eyeball instead of the lids and the eyes stay
    too open. Here the 3D opening, as the photo camera sees it, is ray-cast column by column and
    the lids are moved (in the camera's image plane, along the eyeball) by the difference."""
    base = mh.base_mesh()
    F, fg = base['faces'], base['face_group']
    groups = mh.vertex_groups()
    A = cam[:2, :3]
    A_pinv = np.linalg.pinv(A)
    toward = cam[2, :3] / np.linalg.norm(cam[2, :3])  # model-space direction toward the camera
    body_f = F[fg == 'body']
    for _ in range(iters):
        tris = shape.triangles(np.vstack([body_f, F[np.isin(fg, ['helper-l-eye', 'helper-r-eye'])]]))[0]
        n_body = len(shape.triangles(body_f)[0])
        bvh = BVHTree.FromPolygons([Vector(v) for v in V], tris.tolist())
        moved = np.zeros(len(V), bool)
        for side, lid in LIDS.items():
            eye = groups[f'helper-{side}-eye']
            c = V[eye].mean(0)
            R = np.median(np.linalg.norm(V[eye] - c, axis=1))
            c0, c1 = P[lid['corners'][0], :2], P[lid['corners'][1], :2]
            xs = np.linspace(min(c0[0], c1[0]) + 1, max(c0[0], c1[0]) - 1, 24)
            def contour(ids):
                pts = np.array([c0] + [P[i, :2] for i in ids] + [c1])
                pts = pts[np.argsort(pts[:, 0])]
                return np.interp(xs, pts[:, 0], pts[:, 1])
            top_photo, bot_photo = contour(lid['upper']), contour(lid['lower'])
            top3d, bot3d = np.full(len(xs), np.nan), np.full(len(xs), np.nan)
            for k, x in enumerate(xs):
                ys = np.arange(min(top_photo[k], bot_photo[k]) - 25, max(top_photo[k], bot_photo[k]) + 25, 0.5)
                on_eye = []
                for y in ys:
                    X = A_pinv @ (np.array([x, y]) - cam[:2, 3])
                    X = X + toward * ((c - X) @ toward)  # the eye's depth
                    hit = bvh.ray_cast(Vector(X + toward * 3), Vector(-toward), 6)
                    on_eye.append(hit[0] is not None and hit[2] >= n_body)
                on_eye = np.array(on_eye)
                if on_eye.any():
                    top3d[k], bot3d[k] = ys[on_eye].min(), ys[on_eye].max()
            ok = ~np.isnan(top3d)
            if ok.sum() < 3:
                continue
            d_top = np.interp(xs, xs[ok], (top_photo - top3d)[ok])  # + = lid moves down (image y)
            d_bot = np.interp(xs, xs[ok], (bot_photo - bot3d)[ok])
            near = np.where(np.linalg.norm(V - c, axis=1) < R + reach)[0]
            near = near[~np.isin(near, eye)]
            near = near[(V[near] - c) @ toward > 0.2 * R]
            px = (A @ V[near].T).T + cam[:2, 3]
            mid_y = np.interp(px[:, 0], [c0[0], c1[0]] if c0[0] < c1[0] else [c1[0], c0[0]],
                              [c0[1], c1[1]] if c0[0] < c1[0] else [c1[1], c0[1]])
            upper = px[:, 1] < mid_y
            dy = np.where(upper, np.interp(px[:, 0], xs, d_top, left=0, right=0), np.interp(px[:, 0], xs, d_bot, left=0, right=0))
            dist = np.linalg.norm(V[near] - c, axis=1) - R
            w = np.clip(1 - dist / reach, 0, 1) ** 2
            V[near] += (A_pinv @ np.c_[np.zeros(len(near)), dy * w].T).T
            # Keep the lids on the eyeball, not inside it.
            rel = V[near] - c
            r = np.linalg.norm(rel, axis=1)
            inside = r < R + cover
            V[near[inside]] = c + rel[inside] / r[inside, None] * (R + cover)
            moved[near] = True
            err = np.nanmean(np.abs(np.r_[(top_photo - top3d)[ok], (bot_photo - bot3d)[ok]]))
            print(f'  lids {side}: mean opening error {err:.1f} px')
    return V


def main():
    ch = shape.character()
    cfg = ch['face']
    face = json.loads((BUILD / 'analysis' / 'face.json').read_text())
    corr = json.loads((BUILD / 'face_corr.json').read_text())
    P = np.array(face['points'])
    Q = np.stack([P[:, 0], -P[:, 1], -P[:, 2]], 1)  # pixels; x right, y up, z toward camera

    V0 = shape.neutral(ch)
    M, ok = landmark_matrix(corr, len(V0))
    lw = landmark_weights() * ok
    zw = 0.25  # MediaPipe depth is only relative: trust it less than x/y

    cols = basis(ch)
    names = list(cols)
    J = np.stack([M @ cols[n] for n in names], 2)  # (478, 3, K)
    L0 = M @ V0
    reg = np.array([cfg['expression_regularization'] if n.startswith('expr:') else cfg['regularization'] for n in names])

    w = np.zeros(len(names))
    for _ in range(4):
        X = L0 + J @ w
        s, R, t = similarity(X, Q, lw)
        # Linear solve for target weights in model units (divide the photo side by s).
        target = (np.einsum('ij,nj->ni', R.T, (Q - t) / s))  # photo landmarks in model frame
        resid0 = target - L0
        axis_w = np.array([1.0, 1.0, zw])
        sw = np.sqrt(lw)[:, None] * axis_w[None, :]
        A = (J * sw[:, :, None]).reshape(-1, len(names))
        b = (resid0 * sw).reshape(-1)
        A = np.vstack([A, np.diag(np.sqrt(reg))])
        b = np.concatenate([b, np.zeros(len(names))])
        w = lsq_linear(A, b, bounds=(0, 1), lsmr_tol='auto').x

    V = V0.copy()
    for n, wi in zip(names, w):
        if wi > 1e-4:
            V += wi * cols[n]

    # Residual warp, limited to the face (falls off toward scalp, ears and neck).
    X = M @ V
    s, R, t = similarity(X, Q, lw)
    target = np.einsum('ij,nj->ni', R.T, (Q - t) / s)
    resid = (target - X)
    resid[:, 2] *= zw
    use = lw > 0
    rbf = RBFInterpolator(X[use], resid[use] * cfg['residual'], kernel='thin_plate_spline', smoothing=0.5)
    head = mh.region_weight(mh.descendants('head'))
    groups = mh.vertex_groups()
    eye_c = (V[groups['helper-l-eye']].mean(0) + V[groups['helper-r-eye']].mean(0)) / 2
    mouth_c = X[[13, 14]].mean(0)
    face_c = (eye_c + mouth_c) / 2
    radius = np.linalg.norm(X[use] - face_c, axis=1).max()
    dist = np.linalg.norm(V - face_c, axis=1)
    falloff = np.clip(1.2 - dist / radius, 0, 1) ** 1.5 * head
    falloff[V[:, 2] < face_c[2] - 0.6] = 0  # nothing behind the ears
    region = falloff > 0
    disp = np.zeros_like(V)
    disp[region] = rbf(V[region]) * falloff[region, None]
    # Eyeballs and teeth move rigidly with their surroundings.
    for g in ('helper-l-eye', 'helper-r-eye', 'helper-upper-teeth', 'helper-lower-teeth', 'helper-tongue'):
        idx = groups[g]
        disp[idx] = disp[idx].mean(0)
    V = V + disp

    # Eye openings: match the photo exactly (see snap_lids).
    X = M @ V
    s_, R_, t_ = similarity(X, Q, lw)
    cam0 = np.hstack([s_ * R_, t_[:, None]])
    cam0[1] *= -1
    V = snap_lids(V, cam0, P)

    # Final head camera: photo pixel = cam @ [x, y, z, 1], with y flipped to image-down.
    X = M @ V
    s, R, t = similarity(X, Q, lw)
    cam = np.vstack([np.hstack([s * R, t[:, None]])])
    cam[1] *= -1
    proj = (cam @ np.c_[X, np.ones(len(X))].T).T
    err = np.linalg.norm(proj[:, :2] - P[:, :2], axis=1)[ok & (lw > 0)]

    np.savez(BUILD / 'shape.npz', verts=V, head_cam=cam, weights=w, names=np.array(names))
    fitted = {n: round(float(x), 3) for n, x in zip(names, w) if x > 0.02}
    report = {'pixel_error_mean': round(float(err.mean()), 2), 'pixel_error_max': round(float(err.max()), 2),
              'head_scale_px_per_dm': round(float(s), 2), 'weights': dict(sorted(fitted.items(), key=lambda kv: -kv[1]))}
    (BUILD / 'face_fit.json').write_text(json.dumps(report, indent=1))

    img = Image.open(BUILD / 'analysis' / 'photo.png').convert('RGB')
    d = ImageDraw.Draw(img)
    for (x, y, _), (u, v, _) in zip(P, proj):
        d.ellipse((x - 2, y - 2, x + 2, y + 2), fill=(0, 255, 0))
        d.ellipse((u - 2, v - 2, u + 2, v + 2), outline=(255, 0, 0))
    xs, ys = P[:, 0], P[:, 1]
    pad = 60
    img.crop((int(xs.min()) - pad, int(ys.min()) - pad, int(xs.max()) + pad, int(ys.max()) + pad)).save(BUILD / 'face_fit_overlay.png')
    print(json.dumps({k: v for k, v in report.items() if k != 'weights'}), 'targets used:', len(fitted))


if __name__ == '__main__':
    main()
