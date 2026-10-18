"""Step 5: color every texel.

Where the photo saw a surface point clearly (unobstructed, facing the lens, and the photo's
segmentation agrees it's skin / hair / tee / khaki / belt), the color is sampled from the photo.
Everywhere else it is synthesized: skin, stubble along the jaw, buzz-cut hair above a hairline
that wraps around the head, black tee fabric, khaki twill, leather. Synthesized base colors are
measured from the photo texels next to them, so the two blend without a visible seam.

Output: build/textures/<object>.png (+ <object>_weight.png debug maps)
Run:  .venv/bin/python texture.py
"""
import json
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

import cameras
import mh
import shape

HERE = Path(__file__).resolve().parent
BUILD = HERE / 'build'
OUT = BUILD / 'textures'

# photo segmentation classes
BG, HAIR, BODY_SKIN, FACE_SKIN, CLOTHES, OTHER = range(6)


def from_bl_points(P):
    return np.stack([P[..., 0], P[..., 2], -P[..., 1]], -1) * 10.0


def from_bl_dirs(N):
    return np.stack([N[..., 0], N[..., 2], -N[..., 1]], -1)


def smoothstep(a, b, x):
    t = np.clip((x - a) / (b - a), 0, 1)
    return t * t * (3 - 2 * t)


def srgb(hexstr):
    h = hexstr.lstrip('#')
    return np.array([int(h[i:i + 2], 16) for i in (0, 2, 4)]) / 255.0


# ---------- procedural noise (value noise on a 3D lattice) ----------

def _hash(ix, iy, iz):
    n = (ix * 73856093) ^ (iy * 19349663) ^ (iz * 83492791)
    n = (n ^ (n >> 13)) * 1274126177
    return ((n ^ (n >> 16)) & 0xFFFF) / 65535.0


def vnoise(P, freq):
    p = P * freq
    i = np.floor(p).astype(np.int64)
    f = p - i
    f = f * f * (3 - 2 * f)
    out = 0.0
    for dx in (0, 1):
        for dy in (0, 1):
            for dz in (0, 1):
                w = (f[:, 0] if dx else 1 - f[:, 0]) * (f[:, 1] if dy else 1 - f[:, 1]) * (f[:, 2] if dz else 1 - f[:, 2])
                out = out + w * _hash(i[:, 0] + dx, i[:, 1] + dy, i[:, 2] + dz)
    return out


def fbm(P, freq, octaves=3):
    total, amp, norm = 0.0, 1.0, 0.0
    for o in range(octaves):
        total = total + amp * vnoise(P + o * 17.3, freq * 2 ** o)
        norm += amp
        amp *= 0.5
    return total / norm


# ---------- photo sampling ----------

class Photo:
    def __init__(self):
        a = BUILD / 'analysis'
        self.seg = np.asarray(Image.open(a / 'segments.png'))
        self.H, self.W = self.seg.shape
        self.colors = json.loads((a / 'colors.json').read_text())
        # Colors come from the 4x enhanced photo (enhance_photo.py); coordinates stay in photo pixels.
        hd = a / 'photo_hd.png'
        self.rgb = np.asarray(Image.open(hd if hd.exists() else a / 'photo.png').convert('RGB'), np.float32) / 255.0
        self.k = self.rgb.shape[1] / self.W
        hair = (self.seg == HAIR)
        small = np.asarray(Image.open(a / 'photo.png').convert('RGB'), np.float32) / 255.0
        luma = small @ np.array([0.299, 0.587, 0.114], np.float32)
        h = hair & (luma < np.percentile(luma[hair], 40))
        self.hair_rgb = np.median(small[h], 0)  # the strands, not the scalp showing through

    def sample(self, px):
        H, W = self.rgb.shape[:2]
        x = np.clip(px[:, 0] * self.k + (self.k - 1) / 2, 0, W - 1.001)
        y = np.clip(px[:, 1] * self.k + (self.k - 1) / 2, 0, H - 1.001)
        x0, y0 = np.floor(x).astype(int), np.floor(y).astype(int)
        fx, fy = (x - x0)[:, None], (y - y0)[:, None]
        r = self.rgb
        return (r[y0, x0] * (1 - fx) * (1 - fy) + r[y0, x0 + 1] * fx * (1 - fy)
                + r[y0 + 1, x0] * (1 - fx) * fy + r[y0 + 1, x0 + 1] * fx * fy)

    def inside(self, px, margin=2):
        return (px[:, 0] > margin) & (px[:, 0] < self.W - margin) & (px[:, 1] > margin) & (px[:, 1] < self.H - margin)

    def class_mask(self, classes, erode=3):
        m = np.isin(self.seg, classes)
        return ndimage.binary_erosion(m, iterations=erode) if erode else m

    def class_soft(self, classes, erode=3, blur=6.0):
        """0..1 gate that fades out smoothly toward the class boundary."""
        m = self.class_mask(classes, erode).astype(np.float32)
        return smoothstep(0.5, 0.95, ndimage.gaussian_filter(m, blur))

    def lookup_soft(self, field, px):
        x = np.clip(px[:, 0], 0, self.W - 1.001)
        y = np.clip(px[:, 1], 0, self.H - 1.001)
        x0, y0 = np.floor(x).astype(int), np.floor(y).astype(int)
        fx, fy = x - x0, y - y0
        return (field[y0, x0] * (1 - fx) * (1 - fy) + field[y0, x0 + 1] * fx * (1 - fy)
                + field[y0 + 1, x0] * (1 - fx) * fy + field[y0 + 1, x0 + 1] * fx * fy)

    def lookup(self, mask, px):
        x = np.clip(np.round(px[:, 0]).astype(int), 0, self.W - 1)
        y = np.clip(np.round(px[:, 1]).astype(int), 0, self.H - 1)
        return mask[y, x]


def color_of(photo, key):
    c = photo.colors.get(key)
    return np.array(c) / 255.0 if c else None


# ---------- per-object rules ----------

def head_frame():
    V = np.load(BUILD / 'shape.npz')['verts']
    g = mh.vertex_groups()
    corr = json.loads((BUILD / 'face_corr.json').read_text())
    pt = lambda i: (V[corr[i]['tri']] * np.array(corr[i]['bary'])[:, None]).sum(0)
    eye = (V[g['helper-l-eye']].mean(0) + V[g['helper-r-eye']].mean(0)) / 2
    mouth = (pt(13) + pt(14)) / 2
    return {'eye': eye, 'center_z': eye[2] - 1.0, 'mouth': mouth,
            'mouth_hw': np.linalg.norm(pt(61) - pt(291)) / 2, 'mouth_hh': max(0.12, abs(pt(13)[1] - pt(14)[1]) / 2 + 0.06)}


def in_mouth(X, fr):
    """Texels inside the lip opening (teeth, inner lips): always photographed from the front."""
    d = X - fr['mouth']
    return ((d[:, 0] / (fr['mouth_hw'] * 0.98)) ** 2 + (d[:, 1] / fr['mouth_hh']) ** 2 < 1) & (d[:, 2] < 0.08) & (d[:, 2] > -1.0)  # down the mouth cavity, not to the nape


def synth_head(X, base_skin, hair_col, fr, rng_P, weights=False):
    phi = np.abs(np.arctan2(X[:, 0], X[:, 2] - fr['center_z']))
    h = X[:, 1] - fr['eye'][1]
    hairline = np.interp(phi, [0, 0.5, 0.9, 1.3, 1.6, 1.9, 2.3, np.pi], [0.68, 0.66, 0.55, 0.38, 0.22, -0.4, -1.0, -1.15])
    # Buzz cut: dense short hair with scalp showing through, thinning over a soft hairline.
    hair = smoothstep(-0.18, 0.2, h - hairline + 0.06 * (fbm(rng_P, 25.0, 2) - 0.5))
    hair *= 0.78 + 0.22 * smoothstep(0.35, 0.65, fbm(rng_P * np.array([1, 0.35, 1]), 160.0, 2))
    stubble = smoothstep(-0.12, -0.35, h) * smoothstep(-1.9, -1.35, h) * smoothstep(2.0, 1.4, phi)
    stubble *= np.where(h < -1.15, smoothstep(1.4, 1.0, phi), 1.0)
    n_fine = fbm(rng_P, 60.0, 2)
    n_low = fbm(rng_P, 4.0, 2)
    skin = np.broadcast_to(base_skin, (len(X), 3)) * (0.97 + 0.06 * n_low[:, None]) * (0.985 + 0.03 * n_fine[:, None])
    dark = np.array([0.3, 0.24, 0.21])
    a = (0.55 * stubble * (0.5 + 0.5 * n_fine))[:, None]
    st = skin * (1 - a) + dark * a
    hr = hair_col[None] * 0.8 * (0.8 + 0.4 * fbm(rng_P * np.array([1, 0.3, 1]), 220.0, 2)[:, None])
    out = st * (1 - hair[:, None]) + hr * hair[:, None]
    return (out, hair, stubble) if weights else out


def lids(X, eyes, out):
    """Lash lines and the lid rims that turn into the eye socket: dark, as in any close-up.
    eyes: (center, radius) in MakeHuman units; out: colors (modified in place)."""
    for c, R in eyes:
        d = np.linalg.norm(X - c, axis=1) - R
        up = X[:, 1] > c[1] - 0.02
        near = d < 0.03
        lash = np.where(up, smoothstep(0.022, 0.006, d), 0.55 * smoothstep(0.012, 0.004, d)) * near
        lash *= (X[:, 2] > c[2] - R * 0.6)
        out[:] = out * (1 - 0.82 * lash[:, None]) + np.array([0.05, 0.035, 0.03]) * 0.82 * lash[:, None]


def synth_skin(X, base_skin):
    n_fine = fbm(X, 55.0, 2)
    n_low = fbm(X, 3.0, 2)
    col = base_skin[None] * (0.96 + 0.08 * n_low[:, None]) * (0.985 + 0.03 * n_fine[:, None])
    hair = smoothstep(0.62, 0.78, fbm(X * np.array([1, 3, 1]), 140.0, 1))  # sparse arm hair
    return col * (1 - 0.18 * hair[:, None])


def synth_fabric(X, base, grain=0.03, twill=0.0):
    n = fbm(X, 80.0, 2)
    col = base[None] * (1 - grain + 2 * grain * n[:, None])
    if twill:
        col *= (1 + twill * np.sin((X[:, 0] + X[:, 1] * 1.0) * 600.0))[:, None]
    return col


def banded(h, colors, sel, edges, fallback):
    """Per-texel base color interpolated from photo medians in height bands, so synthesized skin
    follows the photo's tone from forehead to neck instead of using one flat color."""
    centers, meds = [], []
    for lo, hi in zip(edges[:-1], edges[1:]):
        m = sel & (h >= lo) & (h < hi)
        if m.sum() > 300:
            centers.append((lo + hi) / 2)
            meds.append(np.median(colors[m], 0))
    if len(centers) < 2:
        return np.broadcast_to(fallback, (len(h), 3))
    meds = np.array(meds)
    return np.stack([np.interp(h, centers, meds[:, c]) for c in range(3)], 1)


def run_object(name, photo, meta, ch):
    d = np.load(BUILD / 'bake' / f'{name}.npz')
    mask = d['mask']
    Xb, Nb, vis = d['pos'][mask], d['nrm'][mask], d['vis'][mask].copy()
    forced = vis[:, 1] >= 1.5  # mouth fill, eyeballs
    vis[forced, 1] = 1.0
    X = from_bl_points(Xb)
    N = from_bl_dirs(Nb)

    if name == 'head':
        # Head camera for the face; the neck isn't tilted like the head in the photo, so it
        # blends over to the body camera between the jaw and the lower neck.
        cam = np.array(meta['head_cam'])
        px_head = (cam[:2] @ np.c_[X, np.ones(len(X))].T).T
        px_body = cameras.Perspective.from_json(meta['body_cam']).project(X)
        t = smoothstep(-1.3, -1.85, X[:, 1] - head_frame()['eye'][1])[:, None]
        px = px_head * (1 - t) + px_body * t
        classes = [HAIR, BODY_SKIN, FACE_SKIN]
    else:
        cam = cameras.Perspective.from_json(meta['body_cam'])
        px = cam.project(X)
        classes = {'skin': [BODY_SKIN, FACE_SKIN, OTHER], 'tee': [CLOTHES, OTHER], 'pants': [CLOTHES], 'belt': [CLOTHES, OTHER]}[name]

    sampled = photo.sample(px)
    luma = sampled @ np.array([0.299, 0.587, 0.114])
    gate = photo.lookup_soft(photo.class_soft(classes, erode=3), px) * photo.inside(px)
    if name == 'pants':
        gate *= smoothstep(0.28, 0.38, luma)
        gate *= smoothstep(meta['belt_y'] - 1.3, meta['belt_y'] - 0.6, X[:, 1])  # photo only shows the top of the trousers
    if name == 'belt':
        gate *= 0.0  # the photo's belt has wall-colored glints; synthesized leather reads cleaner
    if name == 'tee':
        gate *= px[:, 1] < meta_belt_px(meta, cam)
    lo, hi = 0.15, 0.7
    if name == 'head':
        # Below the jaw, steep surfaces project onto the wrong part of the photo: be stricter there.
        t_neck = smoothstep(-1.15, -1.5, X[:, 1] - head_frame()['eye'][1])
        lo, hi = 0.15 + 0.45 * t_neck, 0.7 + 0.22 * t_neck
    w = vis[:, 0] * smoothstep(lo, hi, vis[:, 1]) * gate
    if name == 'head':
        forced |= in_mouth(X, head_frame())
    w[forced] = 1.0

    # Synthesized base colors measured from confidently-photographed texels (fallback: photo medians).
    strong = w > 0.9
    band = (w > 0.3) & (w < 0.85)
    def measured(sel, fallback):
        return np.median(sampled[sel], 0) if sel.sum() > 200 else fallback

    out = ch['outfit']
    if name == 'head':
        cls = photo.lookup(photo.seg, px)
        fr = head_frame()
        lit = measured(strong & (cls == FACE_SKIN), color_of(photo, 'face_skin'))
        flat = 0.5 * (measured(band & (cls == FACE_SKIN), lit) + lit)  # between the shadowed sides and the lit face
        h = X[:, 1] - fr['eye'][1]
        skin = 0.5 * banded(h, sampled, (w > 0.5) & (cls == FACE_SKIN), np.arange(-2.8, 1.01, 0.2), flat) + 0.5 * flat
        hair = 0.75 * photo.hair_rgb + 0.25 * np.array([0.30, 0.22, 0.17])  # a touch warmer: brown, not grey
        synth, hair_w, stubble_w = synth_head(X, skin, hair, fr, X, weights=True)
        print('  head skin (flat)', (flat * 255).round(), 'hair', (hair * 255).round())
    elif name == 'skin':
        synth = synth_skin(X, measured(band, measured(strong, color_of(photo, 'body_skin'))))
    elif name == 'tee':
        base = srgb(out['tee']['color']) if out['tee'].get('color') else measured(strong, color_of(photo, 'shirt'))
        synth = synth_fabric(X, base, grain=0.06)
    elif name == 'pants':
        base = srgb(out['pants']['color']) if out['pants'].get('color') else measured(strong, color_of(photo, 'pants'))
        synth = synth_fabric(X, base, grain=0.025)
        # Stitch lines (seams, fly, pockets, hem) slightly darker; pressed creases catch a little light.
        import garments
        disp, seam = garments.pants_features(Xb, meta['tailor'])
        crease = np.clip(disp / max(meta['tailor']['crease'], 1e-6), 0, 1) * (Xb[:, 2] < meta['tailor']['crotch_z'])
        synth = synth * (1 - 0.28 * seam[:, None]) * (1 + 0.05 * crease[:, None])
    else:
        synth = synth_fabric(X, srgb(out['belt']['color']), grain=0.08)

    # Soften the photo weight in texture space so transitions are gradual.
    size = mask.shape[0]
    wmap = np.zeros(mask.shape, np.float32)
    wmap[mask] = w
    wmap = ndimage.gaussian_filter(wmap, 3.0 * size / 2048)
    w = np.minimum(wmap[mask], w + 0.15) * (w > 0)

    color = synth * (1 - w[:, None]) + sampled * w[:, None]
    if name in ('head', 'skin'):
        luma_c = (color @ np.array([0.299, 0.587, 0.114]))[:, None]
        color = luma_c + (color - luma_c) * 0.82  # the photo runs warm and pink; the page's key light adds more
    if name == 'head':
        eyes = [(from_bl_points(np.array(e['center'])), e['radius'] * 10) for e in meta['eyes'].values()]
        lids(X, eyes, color)
        write_roughness(name, X, mask, w, photo, px, hair_w, stubble_w, fr)
    img = np.zeros((size, size, 3), np.float32)
    img[mask] = np.clip(color, 0, 1)
    # Fill uncovered texels from the nearest covered one (safe mipmapping at island edges).
    idx = ndimage.distance_transform_edt(~mask, return_distances=False, return_indices=True)
    img = img[idx[0], idx[1]]
    OUT.mkdir(parents=True, exist_ok=True)
    Image.fromarray((img * 255 + 0.5).astype(np.uint8)).save(OUT / f'{name}.png')
    dbg = np.zeros(mask.shape, np.uint8)
    dbg[mask] = (w * 255).astype(np.uint8)
    Image.fromarray(dbg).save(OUT / f'{name}_weight.png')
    return float(w.mean())


def write_roughness(name, X, mask, w, photo, px, hair_w, stubble_w, fr):
    """glTF metallic-roughness map for the head (G = roughness): matte hair and stubble, satin
    skin, a slightly shinier T-zone and lips. Half resolution is plenty."""
    cls = photo.lookup(photo.seg, px)
    hair = np.maximum(hair_w * (1 - w), (cls == HAIR) * w)
    tzone = np.exp(-(X[:, 0] / 0.35) ** 2) * smoothstep(-1.4, -0.6, X[:, 1] - fr['eye'][1])
    lips = in_mouth(X, fr) | (np.hypot((X[:, 0] - fr['mouth'][0]) / (fr['mouth_hw'] * 1.15), (X[:, 1] - fr['mouth'][1]) / 0.3) < 1)
    rough = 0.56 - 0.08 * tzone + 0.3 * hair + 0.08 * stubble_w * (1 - hair)
    rough = np.where(lips, 0.42, rough)
    size = mask.shape[0]
    img = np.zeros((size, size), np.float32)
    img[mask] = np.clip(rough, 0, 1)
    idx = ndimage.distance_transform_edt(~mask, return_distances=False, return_indices=True)
    img = img[idx[0], idx[1]]
    rgb = np.stack([np.ones_like(img), img, np.zeros_like(img)], -1)
    im = Image.fromarray((rgb * 255 + 0.5).astype(np.uint8))
    im.resize((size // 2, size // 2), Image.LANCZOS).save(OUT / f'{name}_mr.png')


def meta_belt_px(meta, cam):
    """Photo y of the belt line: tee pixels below it are belt/pants, not shirt."""
    p = cam.project(np.array([[0.0, meta['belt_y'] + 0.2, 1.2]]))
    return p[0, 1]


def main():
    ch = shape.character()
    meta = json.loads((BUILD / 'bake' / 'meta.json').read_text())
    photo = Photo()
    for name in ('head', 'skin', 'tee', 'pants', 'belt'):
        share = run_object(name, photo, meta, ch)
        print(f'{name}: photo share {share:.2f}')


if __name__ == '__main__':
    main()
