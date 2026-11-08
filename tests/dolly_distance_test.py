"""按用户的主面板距离工作流验证希区柯克的真实投影比例。"""
from pathlib import Path
from types import SimpleNamespace
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import bpy
from mathutils import Vector
from bpy_extras.object_utils import world_to_camera_view
import CineController
from CineController import automation
from CineController.core import rig
from CineController.ui import panel

bpy.ops.wm.read_factory_settings(use_empty=True)
CineController.register()
bpy.ops.cine.create_camera()
control = bpy.context.object
camera = control.cine_camera
subject = bpy.data.objects.new('主体参考平面', None)
bpy.context.collection.objects.link(subject)
control.cine.dolly_target = subject
camera.data.lens = 50

def height():
    a = world_to_camera_view(bpy.context.scene, camera, Vector((0, 0, -1)))
    b = world_to_camera_view(bpy.context.scene, camera, Vector((0, 0, 1)))
    return abs(b.y-a.y)

rig.force_update(bpy.context, camera)
reference_height = height()
bpy.ops.cine.toggle_dolly_zoom()
for distance, expected_lens in ((3, 30), (7, 70), (5, 50)):
    result = automation.call({'action': 'set', 'camera': camera.name, 'values': {'distance': distance}})
    assert result['ok'], result
    assert abs(camera.data.lens-expected_lens) < 1e-4
    assert abs(height()/reference_height-1) < 2e-5
    assert abs(result['data']['values']['distance']-distance) < 1e-5
print('[PASS] 主面板同义距离通过自动化接口联动焦距，主体参考平面的投影高度保持')

class Layout:
    fields = []
    def __init__(self, enabled=True): self.enabled = enabled
    def row(self, **_kwargs): return Layout(self.enabled)
    def column(self, **_kwargs): return Layout(self.enabled)
    def label(self, **_kwargs): pass
    def prop(self, owner, path, **_kwargs): self.fields.append((owner, path, self.enabled))
    def operator(self, *_args, **_kwargs): return SimpleNamespace()

panel.CINE_PT_panel.draw(SimpleNamespace(layout=Layout()), bpy.context)
distance_fields = [(owner, path) for owner, path, enabled in Layout.fields
                   if path == 'dolly_distance' and enabled]
assert len(distance_fields) == 1, '希区柯克启用后，主面板距离必须可编辑并连到实际运动'
owner, path = distance_fields[0]
setattr(owner, path, 3)
rig.force_update(bpy.context, camera)
assert abs(height()/reference_height-1) < 2e-5
background_a = world_to_camera_view(bpy.context.scene, camera, Vector((0, 10, -1)))
background_b = world_to_camera_view(bpy.context.scene, camera, Vector((0, 10, 1)))
background_height = abs(background_b.y-background_a.y)
setattr(owner, path, 7)
rig.force_update(bpy.context, camera)
a = world_to_camera_view(bpy.context.scene, camera, Vector((0, 10, -1)))
b = world_to_camera_view(bpy.context.scene, camera, Vector((0, 10, 1)))
assert abs(abs(b.y-a.y)-background_height) > 0.01
assert abs(height()/reference_height-1) < 2e-5
print('[PASS] 主面板距离可直接拖动，主体大小保持而不同深度的背景比例发生变化')

scene = bpy.context.scene
for frame, distance in ((1, 5), (10, 3)):
    scene.frame_set(frame)
    setattr(owner, path, distance)
    bpy.ops.cine.keyframe_camera()
for frame, subframe in ((1, 0), (4, 0.5), (10, 0)):
    scene.frame_set(frame, subframe=subframe)
    assert abs(height()/reference_height-1) < 2e-5
name = camera.name
file = Path(__file__).parent/'_tmp'/'dolly_distance.blend'
file.parent.mkdir(exist_ok=True)
bpy.ops.wm.save_as_mainfile(filepath=str(file))
bpy.ops.wm.open_mainfile(filepath=str(file))
camera = bpy.data.objects[name]
control = camera.cine.controller
for frame, subframe in ((1, 0), (4, 0.5), (10, 0)):
    scene = bpy.context.scene
    scene.frame_set(frame, subframe=subframe)
    assert abs(height()/reference_height-1) < 2e-5
print('[PASS] 距离动画、子帧和保存重载后的主体投影大小保持')

# 指定主体不在控制器中心时，补偿必须使用真实主体深度，不能仅套距离比。
bpy.ops.cine.create_camera()
camera = rig.resolve_camera(bpy.context)
control = camera.cine.controller
control.location = (2, -1, 3)
control.rotation_euler = (0.4, 0.6, 1.2)
camera.cine.distance = 9
camera.cine.horizontal, camera.cine.vertical = 0.3, -0.2
camera.cine.pan, camera.cine.tilt, camera.cine.roll = 0.5, 0.2, 0.1
rig.force_update(bpy.context, camera)
matrix = camera.matrix_world.copy()
forward = matrix.to_quaternion() @ Vector((0, 0, -1))
up = matrix.to_quaternion() @ Vector((0, 1, 0))
subject = bpy.data.objects.new('偏离控制器中心的主体', None)
bpy.context.collection.objects.link(subject)
subject.location = matrix.translation+forward*6
control.cine.dolly_target = subject
def tilted_height():
    a = world_to_camera_view(bpy.context.scene, camera, subject.location-up)
    b = world_to_camera_view(bpy.context.scene, camera, subject.location+up)
    return ((a.x-b.x)**2+(a.y-b.y)**2)**0.5
reference_height = tilted_height()
bpy.ops.cine.toggle_dolly_zoom()
for distance in (9, 7, 11):
    control.cine.dolly_distance = distance
    rig.force_update(bpy.context, camera)
    assert abs(tilted_height()/reference_height-1) < 3e-5
print('[PASS] 控制器旋转、镜头俯仰摇摄及主体偏离原点时，仍按实际光轴深度补偿')

bpy.ops.cine.create_camera()
camera = rig.resolve_camera(bpy.context)
control = camera.cine.controller
bpy.ops.mesh.primitive_cube_add(size=2)
subject = bpy.context.object
control.cine.dolly_target = subject
def bounds_height():
    coordinates = [world_to_camera_view(bpy.context.scene, camera, subject.matrix_world @ Vector(corner))
                   for corner in subject.bound_box]
    return max(co.y for co in coordinates)-min(co.y for co in coordinates)
rig.force_update(bpy.context, camera)
reference_height = bounds_height()
from CineController.core import dolly_zoom
dolly_zoom.enable(bpy.context, camera)
control.cine.dolly_distance = 3
rig.force_update(bpy.context, camera)
assert abs(bounds_height()/reference_height-1) < 3e-5, f'实体主体画面高度变化：{bounds_height()/reference_height-1:.1%}'
for distance in (3, 4, 7, 10):
    control.cine.dolly_distance = distance
    rig.force_update(bpy.context, camera)
    assert abs(bounds_height()/reference_height-1) < 3e-5
subject.rotation_euler = (0.2, 0.4, 0.3)
subject.scale = (1.2, 0.7, 1.5)
rig.force_update(bpy.context, camera)
assert abs(bounds_height()/reference_height-1) < 3e-5
subject.location.y = 1
rig.force_update(bpy.context, camera)
assert abs(bounds_height()/reference_height-1) < 3e-5
print('[PASS] 实体主体使用投影包围盒补偿，可见画面高度保持而非仅原点所在平面')
CineController.unregister()
