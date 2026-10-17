"""Small Blender (bpy) helpers shared by the pipeline scripts. Scenes use MakeHuman axes
(Y up, front +Z) unless a script converts; cameras then look down -Z with Y up."""
import bpy
import numpy as np


def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    world = bpy.data.worlds.new('world')
    world.color = (0.18, 0.19, 0.22)
    scene.world = world
    return scene


def mesh_object(name, verts, faces, smooth=True, collection=None):
    me = bpy.data.meshes.new(name)
    me.from_pydata([tuple(map(float, v)) for v in verts], [], [list(dict.fromkeys(f)) for f in faces])
    me.update()
    if smooth:
        me.shade_smooth()
    ob = bpy.data.objects.new(name, me)
    (collection or bpy.context.scene.collection).objects.link(ob)
    return ob


def set_point_colors(ob, colors, name='col'):
    """Per-vertex RGBA (0..1) as a color attribute."""
    attr = ob.data.color_attributes.new(name, 'FLOAT_COLOR', 'POINT')
    attr.data.foreach_set('color', np.asarray(colors, np.float32).ravel())
    return attr


def attribute_material(name, attr='col', roughness=0.55):
    mat = bpy.data.materials.new(name)
    nt = mat.node_tree
    bsdf = nt.nodes['Principled BSDF']
    bsdf.inputs['Roughness'].default_value = roughness
    node = nt.nodes.new('ShaderNodeAttribute')
    node.attribute_name = attr
    nt.links.new(node.outputs['Color'], bsdf.inputs['Base Color'])
    return mat


def area_light(name, location, target, energy, size=4.0):
    light = bpy.data.lights.new(name, 'AREA')
    light.energy = energy
    light.size = size
    ob = bpy.data.objects.new(name, light)
    bpy.context.scene.collection.objects.link(ob)
    ob.location = location
    direction = np.asarray(target, float) - np.asarray(location, float)
    from mathutils import Vector
    ob.rotation_euler = Vector(direction).to_track_quat('-Z', 'Y').to_euler()
    return ob


def ortho_camera(center_xy, scale, z=50.0, name='cam'):
    """Orthographic camera looking down -Z (front view in MakeHuman axes)."""
    cam = bpy.data.cameras.new(name)
    cam.type = 'ORTHO'
    cam.ortho_scale = scale
    cam.clip_end = 200
    ob = bpy.data.objects.new(name, cam)
    bpy.context.scene.collection.objects.link(ob)
    ob.location = (center_xy[0], center_xy[1], z)
    bpy.context.scene.camera = ob
    return ob


def render(path, width, height, samples=16):
    s = bpy.context.scene
    s.render.engine = 'CYCLES'
    s.cycles.device = 'CPU'
    s.cycles.samples = samples
    s.cycles.use_denoising = False
    s.render.resolution_x, s.render.resolution_y = width, height
    s.render.resolution_percentage = 100
    s.render.film_transparent = False
    s.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)
    return path
