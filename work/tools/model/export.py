"""Step 6: final materials and glTF export, in two variants.

Loads build/character.blend, assigns the generated textures and plain materials (sneakers,
buckle), removes helper objects, and writes:
  build/nitsan_desktop.glb  full geometry, 2048 head/arms textures
  build/nitsan_mobile.glb   ~45% geometry, textures at half size
With --preview it also renders a textured turnaround to build/preview/final_sheet.png.

Run:  .venv/bin/python export.py [--preview]
"""
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import bpy
from PIL import Image

VARIANTS = {'desktop': {'tex_scale': 1.0, 'decimate': None}, 'mobile': {'tex_scale': 0.5, 'decimate': 0.45}}

import bl
import shape

BUILD = HERE / 'build'
TEXTURED = {'head': 0.55, 'skin': 0.55, 'tee': 0.92, 'pants': 0.85, 'belt': 0.45}
DOUBLE_SIDED = {'tee', 'pants', 'belt'}


def hex_rgba(h):
    h = h.lstrip('#')
    srgb = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    lin = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in srgb]
    return (*lin, 1.0)


def material(name, color=None, image=None, roughness=0.6, metallic=0.0, double_sided=False):
    mat = bpy.data.materials.new(name)
    nt = mat.node_tree
    bsdf = nt.nodes['Principled BSDF']
    bsdf.inputs['Roughness'].default_value = roughness
    bsdf.inputs['Metallic'].default_value = metallic
    if image:
        tex = nt.nodes.new('ShaderNodeTexImage')
        tex.image = bpy.data.images.load(str(image))
        nt.links.new(tex.outputs['Color'], bsdf.inputs['Base Color'])
    elif color:
        bsdf.inputs['Base Color'].default_value = color
    mat.use_backface_culling = not double_sided
    return mat


def assign(ob, mat):
    ob.data.materials.clear()
    ob.data.materials.append(mat)


def variant_textures(variant, scale):
    out = BUILD / 'textures' / variant
    out.mkdir(parents=True, exist_ok=True)
    for name in TEXTURED:
        im = Image.open(BUILD / 'textures' / f'{name}.png')
        if scale != 1.0:
            im = im.resize((int(im.width * scale), int(im.height * scale)), Image.LANCZOS)
        im.save(out / f'{name}.png')
    return out


def setup_scene(tex_dir, decimate=None):
    bpy.ops.wm.open_mainfile(filepath=str(BUILD / 'character.blend'))
    ch = shape.character()
    sn = ch['outfit']['sneakers']
    for ob in list(bpy.data.objects):
        if ob.type != 'MESH':
            bpy.data.objects.remove(ob)
    for name, rough in TEXTURED.items():
        assign(bpy.data.objects[name], material(name, image=tex_dir / f'{name}.png', roughness=rough, double_sided=name in DOUBLE_SIDED))
    assign(bpy.data.objects['buckle'], material('buckle', color=(0.75, 0.75, 0.78, 1), roughness=0.25, metallic=1.0))
    upper = material('sneaker_upper', color=hex_rgba(sn['upper']), roughness=0.55)
    sole = material('sneaker_sole', color=hex_rgba(sn['sole']), roughness=0.7)
    laces = material('sneaker_laces', color=hex_rgba(sn['laces']), roughness=0.85)
    for side in ('l', 'r'):
        assign(bpy.data.objects[f'shoe_{side}'], upper)
        assign(bpy.data.objects[f'sole_{side}'], sole)
        assign(bpy.data.objects[f'laces_{side}'], laces)
    for ob in bpy.data.objects:
        for attr in list(ob.data.color_attributes):
            ob.data.color_attributes.remove(attr)  # bake-only data
        if 'force_photo' in ob.data.attributes:
            ob.data.attributes.remove(ob.data.attributes['force_photo'])
        if decimate and len(ob.data.polygons) > 2000:
            m = ob.modifiers.new('decimate', 'DECIMATE')
            m.ratio = decimate if ob.name != 'head' else min(1.0, decimate * 1.4)


def main():
    for variant, cfg in VARIANTS.items():
        setup_scene(variant_textures(variant, cfg['tex_scale']), cfg['decimate'])
        out = BUILD / f'nitsan_{variant}.glb'
        bpy.ops.export_scene.gltf(filepath=str(out), export_format='GLB', export_yup=True, export_apply=True,
                                  export_image_format='WEBP', export_texcoords=True, export_normals=True,
                                  export_materials='EXPORT', export_animations=False, export_skins=False)
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
    out = BUILD / 'preview'
    tiles = []
    for view, ang, scale, z, w, h in (('front', 0, 2.0, 0.1, 420, 840), ('three-quarter', 35, 2.0, 0.1, 420, 840),
                                      ('profile', 90, 2.0, 0.1, 420, 840), ('back', 180, 2.0, 0.1, 420, 840),
                                      ('face', 0, 0.38, 0.84, 420, 420), ('face34', 35, 0.38, 0.84, 420, 420),
                                      ('faceside', 75, 0.38, 0.84, 420, 420), ('faceback', 150, 0.38, 0.84, 420, 420)):
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
