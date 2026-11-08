"""用真实依赖图验证参考机位反推、相对坐标及动画保护。"""
from pathlib import Path
from math import pi
import random
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import bpy
from mathutils import Matrix, Vector
import CineController
from CineController.core import rig

bpy.ops.wm.read_factory_settings(use_empty=True)
CineController.register()
bpy.ops.cine.create_camera()
control = bpy.context.object
camera = control.cine_camera
source = bpy.data.objects.new('自由相机', bpy.data.cameras.new('参考镜头'))
bpy.context.collection.objects.link(source)
camera.cine.position_source = source
origin = bpy.data.objects.new('外部空间原点', None)
bpy.context.collection.objects.link(origin)
source_parent = bpy.data.objects.new('参考相机父级', None)
bpy.context.collection.objects.link(source_parent)
source.parent = source_parent
source_parent.location = (3, 7, -2)
source_parent.rotation_euler = (0.2, -0.5, 0.7)
camera.cine.pan, camera.cine.tilt, camera.cine.roll = 0.2, -0.3, 0.4
angles = (camera.cine.pan, camera.cine.tilt, camera.cine.roll)
rng = random.Random(604)

for index in range(40):
    control.location = tuple(rng.uniform(-10, 10) for _ in range(3))
    control.rotation_euler = tuple(rng.uniform(-pi, pi) for _ in range(3))
    control.scale = (1.4, 0.8, 2.0) if index % 2 else (1, 1, 1)
    origin.location = tuple(rng.uniform(-5, 5) for _ in range(3))
    camera.cine.origin = origin if index % 2 else None
    if camera.cine.origin is None:
        camera.cine.origin_fallback = (1, -2, 3)
    source.location = tuple(rng.uniform(-10, 10) for _ in range(3))
    source.rotation_euler = (0.6, 0.3, -0.7)
    camera.cine.offset = (1, -2, 3)
    rig.force_update(bpy.context, camera)
    before = source.matrix_world.copy()
    expected = source.evaluated_get(bpy.context.evaluated_depsgraph_get()).matrix_world.translation.copy()
    rig.import_camera_position(bpy.context, camera, source)
    actual = rig.read_evaluated_camera_matrix(bpy.context, camera).translation
    assert (actual - expected).length < 3e-5, (index, actual, expected)
    assert tuple(camera.cine.offset) == (0, 0, 0)
    assert (camera.cine.pan, camera.cine.tilt, camera.cine.roll) == angles
    assert source.matrix_world == before, '不能修改参考相机'
print('[PASS] 40 组位置反推底层兼容：控制器变换、非均匀缩放、外部原点及参考相机父级')

control.matrix_world = Matrix.Identity(4)
source.parent = None
camera.cine.origin = None
camera.cine.origin_fallback = (0, 0, 0)
for position, distance, vertical in (((0, 0, 0), 0, 0), ((0, 0, 5), 5, -pi/2),
                                     ((0, 0, -5), 5, pi/2), ((0, -5, 0), 5, 0)):
    source.location = position
    rig.import_camera_position(bpy.context, camera, source)
    assert abs(camera.cine.distance - distance) < 1e-5
    assert abs(camera.cine.vertical - vertical) < 1e-5
print('[PASS] 中心重合、上下极点及默认前后方向的参数正确')

saved = (camera.cine.distance, camera.cine.horizontal, camera.cine.vertical, tuple(camera.cine.offset))
camera.keyframe_insert(data_path='cine.distance', frame=1)
try:
    rig.import_camera_position(bpy.context, camera, source)
    raise AssertionError('应该保护已有动画')
except ValueError as error:
    assert '动画' in str(error)
assert saved == (camera.cine.distance, camera.cine.horizontal, camera.cine.vertical, tuple(camera.cine.offset))
camera.animation_data.action = None
control.scale = (0, 1, 1)
try:
    rig.import_camera_position(bpy.context, camera, source)
    raise AssertionError('应该拒绝奇异控制器矩阵')
except ValueError as error:
    assert '缩放' in str(error)
control.scale = (1, 1, 1)
bpy.ops.cine.toggle_dolly_zoom()
try:
    rig.import_camera_position(bpy.context, camera, source)
    raise AssertionError('应该保护希区柯克运行状态')
except ValueError as error:
    assert '希区柯克' in str(error)
bpy.ops.cine.toggle_dolly_zoom()
print('[PASS] 已有轨道动画、零缩放及希区柯克运行状态不会被覆盖')
CineController.unregister()
