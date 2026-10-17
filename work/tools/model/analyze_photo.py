"""Step 1: read the reference photo with MediaPipe (Apache-2.0, runs on CPU).

Outputs (build/analysis/):
  photo.png          the photo, EXIF-rotated
  segments.png       per-pixel class: 0 background, 1 hair, 2 body skin, 3 face skin, 4 clothes, 5 accessories
  face.json          478 face landmarks (pixels; z is relative depth in pixel units) + head pose matrix
  pose.json          33 body landmarks (pixels) with visibility
  overlay.png        everything drawn on the photo, for checking
  colors.json        median colors per class (skin, hair, shirt, pants), used by the texture step

Run:  .venv/bin/python analyze_photo.py
"""
import json
import urllib.request
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageOps
import mediapipe as mp
from mediapipe.tasks import python as mpt
from mediapipe.tasks.python import vision

HERE = Path(__file__).resolve().parent
PHOTO = HERE.parents[2] / 'Nitsan photo' / 'Profile Picture.jpg'
OUT = HERE / 'build' / 'analysis'
CACHE = HERE / 'cache' / 'mediapipe'
MODELS = {
    'face': 'https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/latest/face_landmarker.task',
    'pose': 'https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_heavy/float16/latest/pose_landmarker_heavy.task',
    'segment': 'https://storage.googleapis.com/mediapipe-models/image_segmenter/selfie_multiclass_256x256/float32/latest/selfie_multiclass_256x256.tflite',
}


def model_path(key):
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / Path(MODELS[key]).name
    if not path.exists():
        urllib.request.urlretrieve(MODELS[key], path)
    return str(path)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    img = ImageOps.exif_transpose(Image.open(PHOTO)).convert('RGB')
    img.save(OUT / 'photo.png')
    W, H = img.size
    arr = np.asarray(img)
    mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=arr)

    # Segmentation: hair / skin / clothes classes
    seg_opts = vision.ImageSegmenterOptions(
        base_options=mpt.BaseOptions(model_asset_path=model_path('segment')),
        output_category_mask=True)
    with vision.ImageSegmenter.create_from_options(seg_opts) as seg:
        cat = np.squeeze(seg.segment(mp_image).category_mask.numpy_view()).astype(np.uint8)
    if cat.shape != (H, W):
        cat = np.asarray(Image.fromarray(cat).resize((W, H), Image.NEAREST))
    Image.fromarray(cat).save(OUT / 'segments.png')

    # Face mesh
    face_opts = vision.FaceLandmarkerOptions(
        base_options=mpt.BaseOptions(model_asset_path=model_path('face')),
        num_faces=1, output_facial_transformation_matrixes=True, output_face_blendshapes=True)
    with vision.FaceLandmarker.create_from_options(face_opts) as fl:
        fr = fl.detect(mp_image)
    if not fr.face_landmarks:
        raise SystemExit('no face found')
    face = [[p.x * W, p.y * H, p.z * W] for p in fr.face_landmarks[0]]
    blend = {c.category_name: round(c.score, 4) for c in fr.face_blendshapes[0]}
    matrix = np.array(fr.facial_transformation_matrixes[0]).tolist()
    (OUT / 'face.json').write_text(json.dumps({'size': [W, H], 'points': face, 'blendshapes': blend, 'matrix': matrix}))

    # Body pose
    pose_opts = vision.PoseLandmarkerOptions(base_options=mpt.BaseOptions(model_asset_path=model_path('pose')))
    with vision.PoseLandmarker.create_from_options(pose_opts) as pl:
        pr = pl.detect(mp_image)
    pose = [[p.x * W, p.y * H, p.z * W, p.visibility] for p in pr.pose_landmarks[0]] if pr.pose_landmarks else []
    (OUT / 'pose.json').write_text(json.dumps({'size': [W, H], 'points': pose}))

    # Median colors per region (pants: clothes pixels below the belt line, shirt: above)
    hips_y = (pose[23][1] + pose[24][1]) / 2 if pose else H * 0.85
    ys = np.arange(H)[:, None].repeat(W, 1)
    def median(mask):
        px = arr[mask]
        return [int(v) for v in np.median(px, axis=0)] if len(px) else None
    colors = {
        'hair': median(cat == 1),
        'face_skin': median(cat == 3),
        'body_skin': median(cat == 2),
        'shirt': median((cat == 4) & (ys < hips_y - 0.04 * H)),
        'pants': median((cat == 4) & (ys > hips_y + 0.02 * H)),
    }
    (OUT / 'colors.json').write_text(json.dumps(colors, indent=1))

    # Debug overlay
    pal = np.array([[0, 0, 0], [255, 200, 0], [255, 120, 120], [255, 60, 200], [0, 160, 255], [0, 255, 120]], np.uint8)
    over = Image.blend(img, Image.fromarray(pal[cat]), 0.35)
    d = ImageDraw.Draw(over)
    for x, y, _ in face:
        d.point((x, y), fill=(0, 255, 0))
    for i, (x, y, _, v) in enumerate(pose):
        if v > 0.3:
            d.ellipse((x - 6, y - 6, x + 6, y + 6), outline=(255, 255, 0), width=2)
            d.text((x + 8, y - 8), str(i), fill=(255, 255, 0))
    over.save(OUT / 'overlay.png')
    print(json.dumps({'size': [W, H], 'face_points': len(face), 'pose_points': len(pose), 'colors': colors}))


if __name__ == '__main__':
    main()
