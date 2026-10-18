"""Step 6: final materials and glTF export, in two variants.

Loads build/character.blend, assigns the generated textures and PBR materials, and writes:
  build/nitsan_desktop.glb  full geometry, full-size textures (4096 head and arms)
  build/nitsan_mobile.glb   same geometry (optimize.mjs simplifies it), textures at half size
Materials: photo-based color maps; tiled detail normals (detail.py) through texture transforms;
cotton sheen on the tee and trousers; glossy cornea (clearcoat) on the eyes; the sneakers keep
their own normal and roughness maps. With --preview it also renders build/preview/final_sheet.png.

Run:  .venv/bin/python export.py [--preview]
"""
import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import bpy
import numpy as np
from PIL import Image

import bl
import detail
import extras
import shape
import shoes

BUILD = HERE / 'build'
VARIANTS = {'desktop': 1.0, 'mobile': 0.5}
TEXTURED = ('head', 'skin', 'tee', 'pants', 'belt')
DOUBLE_SIDED = {'tee', 'pants', 'belt'}
# object → (roughness, detail tile, detail strength, sheen weight, sheen roughness)
LOOK = {
    'head': (0.5, 'skin', 0.35, 0.0, 0.0),
    'skin': (0.52, 'skin', 0.4, 0.0, 0.0),
    'tee': (0.9, 'tee', 0.55, 0.1, 0.5),
    'pants': (0.86, 'twill', 0.45, 0.3, 0.5),
    'belt': (0.38, 'leather', 0.5, 0.0, 0.0),
}


def srgb_to_linear(c):
    c = np.asarray(c, float)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def bsdf_of(mat):
    return mat.node_tree.nodes['Principled BSDF']


def new_material(name, roughness=0.6, metallic=0.0, double_sided=False):
    mat = bpy.data.materials.new(name)
    b = bsdf_of(mat)
    b.inputs['Roughness'].default_value = roughness
    b.inputs['Metallic'].default_value = metallic
    mat.use_backface_culling = not double_sided
    return mat


def image_node(mat, path, non_color=False, repeat=None):
    nt = mat.node_tree
    tex = nt.nodes.new('ShaderNodeTexImage')
    tex.image = bpy.data.images.load(str(path))
    if non_color:
        tex.image.colorspace_settings.name = 'Non-Color'
    if repeat:
        uv = nt.nodes.new('ShaderNodeUVMap')
        mp = nt.nodes.new('ShaderNodeMapping')
        mp.vector_type = 'POINT'
        mp.inputs['Scale'].default_value = (repeat, repeat, 1.0)
        nt.links.new(uv.outputs['UV'], mp.inputs['Vector'])
        nt.links.new(mp.outputs['Vector'], tex.inputs['Vector'])
    return tex


def normal_map(mat, path, strength, repeat=None):
    nt = mat.node_tree
    tex = image_node(mat, path, non_color=True, repeat=repeat)
    nm = nt.nodes.new('ShaderNodeNormalMap')
    nm.inputs['Strength'].default_value = strength
    nt.links.new(tex.outputs['Color'], nm.inputs['Color'])
    nt.links.new(nm.outputs['Normal'], bsdf_of(mat).inputs['Normal'])


def detail_repeat(name, size):
    """UV repeat that makes one detail tile cover TILE_MM on this object (texels are uniform)."""
    d = np.load(BUILD / 'bake' / f'{name}.npz')
    P, m = d['pos'], d['mask']
    dx = np.linalg.norm(P[:, 1:] - P[:, :-1], axis=-1)
    texel_mm = float(np.median(dx[m[:, 1:] & m[:, :-1]])) * 1000
    return round(texel_mm * size / detail.TILE_MM[LOOK[name][1]], 2)


def textured_material(name, tex_dir, repeat):
    rough, tile, strength, sheen, sheen_rough = LOOK[name]
    mat = new_material(name, rough, double_sided=name in DOUBLE_SIDED)
    b = bsdf_of(mat)
    col = image_node(mat, tex_dir / f'{name}.png')
    mat.node_tree.links.new(col.outputs['Color'], b.inputs['Base Color'])
    normal_map(mat, BUILD / 'detail' / f'{tile}.png', strength, repeat)
    if sheen:  # the glTF exporter writes the tint as the sheen color and ignores the weight
        b.inputs['Sheen Weight'].default_value = 1.0
        b.inputs['Sheen Roughness'].default_value = sheen_rough
        b.inputs['Sheen Tint'].default_value = (sheen, sheen, sheen, 1)
    if name in ('head', 'skin'):
        b.inputs['Specular IOR Level'].default_value = 0.45
    if name == 'tee':
        b.inputs['Specular IOR Level'].default_value = 0.3  # black cotton: little gloss
    if (tex_dir / f'{name}_mr.png').exists():  # roughness map (G channel)
        mr = image_node(mat, tex_dir / f'{name}_mr.png', non_color=True)
        sep = mat.node_tree.nodes.new('ShaderNodeSeparateColor')
        mat.node_tree.links.new(mr.outputs['Color'], sep.inputs['Color'])
        mat.node_tree.links.new(sep.outputs['Green'], b.inputs['Roughness'])
        mat.node_tree.links.new(sep.outputs['Blue'], b.inputs['Metallic'])
    return mat


def shoe_material():
    d = BUILD / 'shoe'
    mat = new_material('sneaker', 0.6)
    nt, b = mat.node_tree, bsdf_of(mat)
    col = image_node(mat, d / 'color.png')
    nt.links.new(col.outputs['Color'], b.inputs['Base Color'])
    orm = image_node(mat, d / 'orm.png', non_color=True)
    sep = nt.nodes.new('ShaderNodeSeparateColor')
    nt.links.new(orm.outputs['Color'], sep.inputs['Color'])
    nt.links.new(sep.outputs['Green'], b.inputs['Roughness'])
    nt.links.new(sep.outputs['Blue'], b.inputs['Metallic'])
    normal_map(mat, d / 'normal.png', 1.0)
    return mat


def eye_material(meta, iris_rgb):
    path = BUILD / 'textures' / 'eye.png'
    extras.eye_texture(path, iris_rgb, meta['eyes']['l']['iris_uv'])
    mat = new_material('eye', 0.35)
    b = bsdf_of(mat)
    tex = image_node(mat, path)
    mat.node_tree.links.new(tex.outputs['Color'], b.inputs['Base Color'])
    b.inputs['Coat Weight'].default_value = 1.0  # wet cornea: sharp highlights
    b.inputs['Coat Roughness'].default_value = 0.03
    return mat


def iris_color(ch):
    if ch.get('eyes', {}).get('iris'):
        h = ch['eyes']['iris'].lstrip('#')
        return srgb_to_linear([int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)])
    a = BUILD / 'analysis'
    pts = json.loads((a / 'face.json').read_text())['points']
    hd = np.asarray(Image.open(a / 'photo_hd.png').convert('RGB'), np.float32) / 255
    k = hd.shape[1] / json.loads((a / 'face.json').read_text())['size'][0]
    samples = []
    for c, ring in ((468, range(469, 473)), (473, range(474, 478))):
        cx, cy = np.array(pts[c][:2]) * k
        r = np.mean([np.hypot(pts[i][0] * k - cx, pts[i][1] * k - cy) for i in ring]) * 0.8
        y, x = np.mgrid[int(cy - r):int(cy + r), int(cx - r):int(cx + r)]
        inside = np.hypot(x - cx, y - cy) < r
        px = hd[y[inside], x[inside]]
        luma = px @ np.array([0.299, 0.587, 0.114])
        samples.append(px[(luma > np.percentile(luma, 20)) & (luma < np.percentile(luma, 70))])
    rgb = np.median(np.vstack(samples), 0)
    return srgb_to_linear(rgb) * 1.4  # the photo's irises sit in lid shadow


def assign(ob, mat):
    ob.data.materials.clear()
    ob.data.materials.append(mat)


def variant_textures(variant, scale):
    out = BUILD / 'textures' / variant
    out.mkdir(parents=True, exist_ok=True)
    for name in TEXTURED + ('head_mr',):
        src = BUILD / 'textures' / f'{name}.png'
        if not src.exists():
            continue
        im = Image.open(src)
        if scale != 1.0:
            im = im.resize((int(im.width * scale), int(im.height * scale)), Image.LANCZOS)
        im.save(out / f'{name}.png')
    return out


def setup_scene(tex_dir):
    bpy.ops.wm.open_mainfile(filepath=str(BUILD / 'character.blend'))
    ch = shape.character()
    meta = json.loads((BUILD / 'bake' / 'meta.json').read_text())
    for ob in list(bpy.data.objects):
        if ob.type != 'MESH':
            bpy.data.objects.remove(ob)
    import bake
    for name in TEXTURED:
        assign(bpy.data.objects[name], textured_material(name, tex_dir, detail_repeat(name, bake.TEXTURED[name])))
    assign(bpy.data.objects['buckle'], new_material('buckle', 0.22, 1.0))
    bsdf_of(bpy.data.materials['buckle']).inputs['Base Color'].default_value = (0.8, 0.8, 0.82, 1)
    pants_px = np.asarray(Image.open(BUILD / 'textures' / 'pants.png').convert('RGB').resize((64, 64)), float) / 255
    loops = new_material('loops', 0.86)
    bsdf_of(loops).inputs['Base Color'].default_value = (*srgb_to_linear(np.median(pants_px.reshape(-1, 3), 0)), 1)
    assign(bpy.data.objects['loops'], loops)
    shoe = shoe_material()
    for side in ('l', 'r'):
        assign(bpy.data.objects[f'shoe_{side}'], shoe)
    eye = eye_material(meta, iris_color(ch))
    for side in ('l', 'r'):
        assign(bpy.data.objects[f'eye_{side}'], eye)
    chain = new_material('necklace', 0.16, 1.0)
    bsdf_of(chain).inputs['Base Color'].default_value = (0.92, 0.91, 0.89, 1)
    assign(bpy.data.objects['necklace'], chain)
    beads = new_material('bracelet', 0.22)
    bsdf_of(beads).inputs['Base Color'].default_value = (0.012, 0.012, 0.014, 1)
    bsdf_of(beads).inputs['Coat Weight'].default_value = 0.6
    assign(bpy.data.objects['bracelet'], beads)
    for ob in bpy.data.objects:
        for attr in list(ob.data.color_attributes):
            ob.data.color_attributes.remove(attr)  # bake-only data
        if 'force_photo' in ob.data.attributes:
            ob.data.attributes.remove(ob.data.attributes['force_photo'])


def main():
    detail.build()
    for variant, scale in VARIANTS.items():
        setup_scene(variant_textures(variant, scale))
        out = BUILD / f'nitsan_{variant}.glb'
        bpy.ops.export_scene.gltf(filepath=str(out), export_format='GLB', export_yup=True, export_apply=True,
                                  export_image_format='WEBP', export_image_quality=90, export_texcoords=True,
                                  export_normals=True, export_tangents=False, export_materials='EXPORT',
                                  export_animations=False, export_skins=False)
        print('exported', out.name, round(out.stat().st_size / 1e6, 2), 'MB')
    if '--preview' in sys.argv:
        setup_scene(BUILD / 'textures' / 'desktop')
        preview()


def preview():
    scene = bpy.context.scene
    target = (0, 0, 0.1)
    bl.area_light('key', (2.5, -4, 3), target, 900, 3)
    bl.area_light('fill', (-4, -2, 1.5), target, 350, 3)
    bl.area_light('rim', (0, 4, 3), target, 500, 3)
    cam = bpy.data.cameras.new('cam')
    cam.type = 'ORTHO'
    co = bpy.data.objects.new('cam', cam)
    scene.collection.objects.link(co)
    scene.camera = co
    scene.view_settings.view_transform = 'Standard'
    out = BUILD / 'preview'
    tiles = []
    meta = json.loads((BUILD / 'bake' / 'meta.json').read_text())
    eye_z = meta['eyes_bl'][0][2]
    views = (('front', 0, 2.0, 0.1, 420, 840), ('three-quarter', 35, 2.0, 0.1, 420, 840),
             ('profile', 90, 2.0, 0.1, 420, 840), ('back', 180, 2.0, 0.1, 420, 840),
             ('face', 0, 0.3, eye_z - 0.03, 420, 420), ('face34', 35, 0.3, eye_z - 0.03, 420, 420),
             ('faceside', 75, 0.3, eye_z - 0.03, 420, 420), ('faceback', 150, 0.3, eye_z - 0.03, 420, 420))
    for view, ang, scale, z, w, h in views:
        a = math.radians(ang)
        cam.ortho_scale = scale
        co.location = (8 * math.sin(a), -8 * math.cos(a), z)
        co.rotation_euler = (math.pi / 2, 0, a)
        p = out / f'final_{view}.png'
        bl.render(p, w, h, samples=24)
        tiles.append(p)
    sheet = Image.new('RGB', (420 * 4, 840 + 420), (40, 40, 44))
    for i, p in enumerate(tiles):
        im = Image.open(p)
        sheet.paste(im, ((i % 4) * 420, 0 if i < 4 else 840))
    sheet.save(out / 'final_sheet.png')


if __name__ == '__main__':
    main()
