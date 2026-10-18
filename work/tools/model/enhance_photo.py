"""Step 1b: a sharper, 4x larger copy of the photo for texturing close-ups.

  - Real-ESRGAN x4 (BSD-3-Clause) upscales the whole photo, in overlapping tiles.
  - GFPGAN v1.4 (Apache-2.0) restores the face on an aligned 512 px crop; the result is blended
    back over the upscale at `face_restore` strength (character.json → texture), so it adds
    detail without replacing your face.
Both run on CPU through onnxruntime. Models are fetched from GitHub releases into cache/onnx/.

Landmark and camera fits keep using the original photo coordinates; texture.py samples this
image at 4x those coordinates.

Output: build/analysis/photo_hd.png (+ build/preview/enhance_face.png before/after crop)
Run:  .venv/bin/python enhance_photo.py
"""
import json
import sys
from pathlib import Path

import numpy as np
import onnxruntime as ort
from PIL import Image
from scipy import ndimage

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import shape  # noqa: E402

BUILD = HERE / 'build'
MODELS = HERE / 'cache' / 'onnx'
SCALE = 4
# FFHQ 512 alignment template: eye (image left), eye (image right), nose tip, mouth corners.
TEMPLATE = np.array([[192.98138, 239.94708], [318.90277, 240.1936], [256.63416, 314.01935],
                     [201.26117, 371.41043], [313.08905, 371.15118]])
FIVE = [468, 473, 1, 61, 291]  # MediaPipe: iris centers, nose tip, mouth corners


def session(name):
    opts = ort.SessionOptions()
    opts.intra_op_num_threads = 4
    return ort.InferenceSession(str(MODELS / name), opts, providers=['CPUExecutionProvider'])


def upscale(rgb, tile=192, pad=16):
    """Real-ESRGAN x4 in tiles with overlap; rgb float32 HxWx3 in 0..1."""
    sess = session('real_esrgan_x4.onnx')
    H, W, _ = rgb.shape
    out = np.zeros((H * SCALE, W * SCALE, 3), np.float32)
    for y in range(0, H, tile):
        for x in range(0, W, tile):
            y0, x0 = max(0, y - pad), max(0, x - pad)
            y1, x1 = min(H, y + tile + pad), min(W, x + tile + pad)
            inp = rgb[y0:y1, x0:x1].transpose(2, 0, 1)[None]
            res = sess.run(None, {'input': np.ascontiguousarray(inp)})[0][0].transpose(1, 2, 0)
            cy, cx = (y - y0) * SCALE, (x - x0) * SCALE
            h, w = min(tile, H - y) * SCALE, min(tile, W - x) * SCALE
            out[y * SCALE:y * SCALE + h, x * SCALE:x * SCALE + w] = res[cy:cy + h, cx:cx + w]
        print(f'  upscale {min(H, y + tile)}/{H}', flush=True)
    return np.clip(out, 0, 1)


def similarity(src, dst):
    """Least-squares similarity transform (2x3) mapping src points onto dst points."""
    ms, md = src.mean(0), dst.mean(0)
    s, d = src - ms, dst - md
    a = (s * d).sum() / (s * s).sum()
    b = (s[:, 0] * d[:, 1] - s[:, 1] * d[:, 0]).sum() / (s * s).sum()
    R = np.array([[a, -b], [b, a]])
    t = md - R @ ms
    return np.c_[R, t]


def warp(img, M, size, mode='nearest'):
    """Sample img (HxWx3 float) at the inverse of M for an output of size (w, h)."""
    A = np.vstack([M, [0, 0, 1]])
    inv = np.linalg.inv(A)
    w, h = size
    ys, xs = np.mgrid[0:h, 0:w].astype(np.float32)
    sx = inv[0, 0] * xs + inv[0, 1] * ys + inv[0, 2]
    sy = inv[1, 0] * xs + inv[1, 1] * ys + inv[1, 2]
    return np.stack([ndimage.map_coordinates(img[..., c], [sy, sx], order=3, mode=mode, cval=0.0) for c in range(img.shape[-1])], -1)


def restore_face(photo, hd, points, strength):
    sess = session('gfpgan_1.4.onnx')
    five = np.array([points[i][:2] for i in FIVE])
    M = similarity(five, TEMPLATE)
    crop = np.clip(warp(photo, M, (512, 512)), 0, 1)
    inp = ((crop - 0.5) / 0.5).transpose(2, 0, 1)[None].astype(np.float32)
    res = sess.run(None, {'input': inp})[0][0].transpose(1, 2, 0)
    res = np.clip((res + 1) / 2, 0, 1)
    # Paste back into the 4x image: map HD coords → crop coords.
    M_hd = M @ np.diag([1 / SCALE, 1 / SCALE, 1])
    corners = np.array([[0, 0], [512, 0], [0, 512], [512, 512]], float)
    A = np.linalg.inv(np.vstack([M_hd, [0, 0, 1]]))
    box = (A[:2, :2] @ corners.T).T + A[:2, 2]
    x0, y0 = np.floor(box.min(0)).astype(int)
    x1, y1 = np.ceil(box.max(0)).astype(int)
    x0, y0 = max(x0, 0), max(y0, 0)
    x1, y1 = min(x1, hd.shape[1]), min(y1, hd.shape[0])
    M_local = M_hd @ np.array([[1, 0, x0], [0, 1, y0], [0, 0, 1]], float)
    back = warp(res, np.linalg.inv(np.vstack([M_local, [0, 0, 1]]))[:2], (x1 - x0, y1 - y0))
    # Soft mask: an ellipse inside the crop, faded at the edges.
    yy, xx = np.mgrid[0:512, 0:512]
    r = np.hypot((xx - 256) / 205.0, (yy - 280) / 215.0)  # reaches zero inside the crop on every side
    mask = np.clip((1.0 - r) / 0.25, 0, 1).astype(np.float32)
    mask_back = warp(mask[..., None], np.linalg.inv(np.vstack([M_local, [0, 0, 1]]))[:2], (x1 - x0, y1 - y0), mode='constant')
    a = np.clip(mask_back, 0, 1) * strength
    region = hd[y0:y1, x0:x1]
    hd[y0:y1, x0:x1] = region * (1 - a) + back * a
    return hd, (x0, y0, x1, y1), crop, res


def add_photo_grain(photo, hd, amount):
    """Both models smooth skin. Put back the photo's own mid-frequency detail (freckles, pores,
    stubble, fine wrinkles), taken from a plain bicubic enlargement."""
    H, W = hd.shape[:2]
    up = np.asarray(Image.fromarray((photo * 255 + 0.5).astype(np.uint8)).resize((W, H), Image.BICUBIC), np.float32) / 255.0
    lo = np.stack([ndimage.gaussian_filter(up[..., c], 7.0) for c in range(3)], -1)
    fine = np.stack([ndimage.gaussian_filter(up[..., c], 1.6) for c in range(3)], -1)  # JPEG blocks out
    detail = fine - lo
    luma = detail @ np.array([0.299, 0.587, 0.114], np.float32)
    return np.clip(hd + amount * (0.6 * detail + 0.4 * luma[..., None]), 0, 1)


def _polyline_dist(shape_hw, pts):
    """Distance (pixels) from every pixel to a polyline."""
    H, W = shape_hw
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    best = np.full((H, W), 1e9, np.float32)
    for a, b in zip(pts[:-1], pts[1:]):
        d = b - a
        t = np.clip(((xx - a[0]) * d[0] + (yy - a[1]) * d[1]) / max(d @ d, 1e-6), 0, 1)
        best = np.minimum(best, np.hypot(xx - (a[0] + t * d[0]), yy - (a[1] + t * d[1])))
    return best


def remove_accessories(hd, acc):
    """The necklace and bracelet are modeled in 3D, so paint them out of the photo (otherwise
    they would show twice: on the skin and as geometry)."""
    import shoes  # reuse its diffusion inpainting
    luma = hd @ np.array([0.299, 0.587, 0.114], np.float32)
    mask = np.zeros(luma.shape, bool)
    # Necklace: bright thin line near the picked path.
    pts = np.array(acc['necklace_px'] + [acc['clasp_px']], float) * SCALE + (SCALE - 1) / 2
    pts = pts[np.argsort(pts[:, 0])]
    x0, y0 = (pts.min(0) - 60).astype(int)
    x1, y1 = (pts.max(0) + 60).astype(int)
    sub = luma[y0:y1, x0:x1]
    near = _polyline_dist(sub.shape, pts - [x0, y0]) < 7 * SCALE
    bright = sub - ndimage.median_filter(sub, size=25) > 0.05
    mask[y0:y1, x0:x1] = ndimage.binary_dilation(near & bright, iterations=SCALE * 4)  # + the dark halo
    # Bracelet: dark beads around the picked point.
    cx, cy = np.array(acc['bracelet_px'], float) * SCALE
    yy, xx = np.mgrid[0:hd.shape[0], 0:hd.shape[1]]
    ell = ((xx - cx) / (34 * SCALE)) ** 2 + ((yy - cy) / (42 * SCALE)) ** 2 < 1
    mask |= ndimage.binary_dilation(ell & (luma < 0.3), iterations=SCALE * 2) & ell
    return shoes._inpaint(hd, mask, iters=120), mask


def main():
    ch = shape.character()
    strength = ch.get('texture', {}).get('face_restore', 0.6)
    a = BUILD / 'analysis'
    photo = np.asarray(Image.open(a / 'photo.png').convert('RGB'), np.float32) / 255.0
    points = json.loads((a / 'face.json').read_text())['points']
    raw = a / 'photo_x4.png'  # the slow step (~6 min on 4 cores) is cached
    if raw.exists() and Image.open(raw).size == (photo.shape[1] * SCALE, photo.shape[0] * SCALE):
        hd = np.asarray(Image.open(raw), np.float32) / 255.0
    else:
        hd = upscale(photo)
        Image.fromarray((hd * 255 + 0.5).astype(np.uint8)).save(raw)
    hd, box, crop, res = restore_face(photo, hd, points, strength)
    hd = add_photo_grain(photo, hd, ch.get('texture', {}).get('photo_grain', 0.7))
    if ch.get('accessories'):
        hd, acc_mask = remove_accessories(hd, ch['accessories'])
    Image.fromarray((hd * 255 + 0.5).astype(np.uint8)).save(a / 'photo_hd.png')
    x0, y0, x1, y1 = box
    before = Image.fromarray((photo * 255).astype(np.uint8)).crop((x0 // SCALE, y0 // SCALE, x1 // SCALE, y1 // SCALE)).resize((x1 - x0, y1 - y0), Image.BICUBIC)
    after = Image.fromarray((hd[y0:y1, x0:x1] * 255 + 0.5).astype(np.uint8))
    sheet = Image.new('RGB', (before.width * 2, before.height))
    sheet.paste(before, (0, 0))
    sheet.paste(after, (before.width, 0))
    sheet.thumbnail((1600, 1600))
    (BUILD / 'preview').mkdir(exist_ok=True)
    sheet.save(BUILD / 'preview' / 'enhance_face.png')
    print('photo_hd', hd.shape[1], 'x', hd.shape[0], 'face restore', strength)


if __name__ == '__main__':
    main()
