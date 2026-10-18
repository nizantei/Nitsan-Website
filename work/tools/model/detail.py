"""Tileable detail normal maps, repeated over each object's UVs (KHR_texture_transform), so
close-ups show surface texture without giant per-object normal maps:

  skin     pores, fine creases          tee      jersey knit + slub
  twill    chino twill + slub           leather  pebble grain

Each tile is generated from periodic (FFT-filtered) noise, so it repeats without seams.
TILE_MM is the real-world size of one tile; export.py turns it into a UV repeat per object.
Output: build/detail/<name>.png (tangent space, OpenGL / glTF convention)
"""
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
OUT = HERE / 'build' / 'detail'
SIZE = 1024
TILE_MM = {'skin': 24.0, 'tee': 18.0, 'twill': 22.0, 'leather': 30.0}


def periodic_noise(rng, size, lo, hi):
    """Band-limited noise with wavelengths between lo and hi pixels; tiles seamlessly."""
    f = np.fft.fftfreq(size)
    fx, fy = np.meshgrid(f, f)
    k = np.hypot(fx, fy) + 1e-9
    band = (k >= 1 / hi) & (k <= 1 / lo)
    spec = (rng.normal(size=(size, size)) + 1j * rng.normal(size=(size, size))) * band / k
    n = np.real(np.fft.ifft2(spec))
    return (n - n.mean()) / (n.std() + 1e-9)


def blobs(rng, size, count, radius, depth):
    """Periodic field of small pits (pores / pebbles)."""
    h = np.zeros((size, size))
    r = int(radius * 3) + 1
    yy, xx = np.mgrid[-r:r + 1, -r:r + 1]
    for _ in range(count):
        cx, cy = rng.integers(0, size, 2)
        rad = radius * rng.uniform(0.6, 1.4)
        g = np.exp(-(xx ** 2 + yy ** 2) / (2 * rad ** 2)) * depth * rng.uniform(0.5, 1.0)
        ys, xs = (np.arange(-r, r + 1) + cy) % size, (np.arange(-r, r + 1) + cx) % size
        h[np.ix_(ys, xs)] -= g
    return h


def to_normal(h, strength):
    dx = (np.roll(h, -1, 1) - np.roll(h, 1, 1)) / 2
    dy = (np.roll(h, -1, 0) - np.roll(h, 1, 0)) / 2
    n = np.stack([-dx * strength, dy * strength, np.ones_like(h)], -1)  # image rows go down, +Y up
    n /= np.linalg.norm(n, axis=-1, keepdims=True)
    return ((n * 0.5 + 0.5) * 255 + 0.5).astype(np.uint8)


def skin(rng):
    h = blobs(rng, SIZE, 1800, 3.0, 1.0)
    h += 0.35 * periodic_noise(rng, SIZE, 3, 12)
    creases = periodic_noise(rng, SIZE, 30, 200)
    h += 0.25 * np.abs(np.gradient(creases)[0])  # faint micro-creases
    return to_normal(h, 0.9)


def tee(rng):
    y, x = np.mgrid[0:SIZE, 0:SIZE].astype(float)
    cols, rows = 26, 32  # knit wales and courses per tile (~0.7 mm)
    u, v = x / SIZE * cols, y / SIZE * rows
    loop = np.cos(np.pi * (u % 1 - 0.5)) ** 2 * (0.6 + 0.4 * np.cos(2 * np.pi * (v + 0.25 * np.sign(np.sin(np.pi * u)))))
    slub = periodic_noise(rng, SIZE, 40, 400)
    h = 0.8 * loop + 0.35 * slub + 0.2 * periodic_noise(rng, SIZE, 2, 6)
    return to_normal(h, 1.6)


def twill(rng):
    y, x = np.mgrid[0:SIZE, 0:SIZE].astype(float)
    lines = 44  # diagonal ribs per tile, ~0.5 mm apart (repeats exactly across the edge)
    ribs = np.sin(2 * np.pi * (x + y) / SIZE * lines)
    slub = periodic_noise(rng, SIZE, 30, 300)
    h = 0.5 * ribs + 0.45 * slub + 0.25 * periodic_noise(rng, SIZE, 2, 8)
    return to_normal(h, 1.2)


def leather(rng):
    h = -blobs(rng, SIZE, 2600, 5.0, 1.0)
    h += 0.4 * periodic_noise(rng, SIZE, 4, 30)
    return to_normal(h, 0.7)


def build():
    OUT.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(11)
    for name, fn in (('skin', skin), ('tee', tee), ('twill', twill), ('leather', leather)):
        Image.fromarray(fn(rng)).save(OUT / f'{name}.png')
    return OUT


if __name__ == '__main__':
    build()
