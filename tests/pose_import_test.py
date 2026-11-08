"""完整位姿反推：真实求值结果、极端角度、旧瞄准及失败保护。"""
from pathlib import Path
from math import pi
import random
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import bpy
from mathutils import Matrix, Quaternion
import CineController
from CineController.core import rig
from CineController.utils.math_utils import quaternion_angle_difference

bpy.ops.wm.read_factory_settings(use_empty=True)
CineController.register()
bpy.ops.cine.create_camera()
control = bpy.context.object
camera = control.cine_camera
source = bpy.data.objects.new('自由相机', bpy.data.cameras.new('自由镜头'))
bpy.context.collection.objects.link(source)
camera.cine.position_source = source
origin = bpy.data.objects.new('空间原点', None)
bpy.context.collection.objects.link(origin)
parent = bpy.data.objects.new('自由相机父级', None)
bpy.context.collection.objects.link(parent)
source.parent = parent
parent.location = (3, -2, 4)
parent.rotation_euler = (0.3, -0.5, 0.6)
source.rotation_mode = 'QUATERNION'
rng = random.Random(707)

def check_pose():
    expected = rig.read_evaluated_camera_matrix(bpy.context, source)
    before = source.matrix_world.copy()
    assert bpy.ops.cine.import_camera_position() == {'FINISHED'}
    actual = rig.read_evaluated_camera_matrix(bpy.context, camera)
    assert (actual.translation - expected.translation).length < 4e-5
    error = quaternion_angle_difference(actual.to_quaternion(), expected.to_quaternion())
    assert error < 2e-5, error
    assert camera.cine.aim_influence == 0
    assert source.matrix_world == before
    assert tuple(camera.cine.offset) == (0, 0, 0)

for index in range(120):
    control.location = tuple(rng.uniform(-8, 8) for _ in range(3))
    control.rotation_euler = tuple(rng.uniform(-pi, pi) for _ in range(3))
    control.scale = (1.5, 1.5, 1.5) if index % 2 else (1, 1, 1)
    origin.location = tuple(rng.uniform(-4, 4) for _ in range(3))
    camera.cine.origin = origin if index % 2 else None
    camera.cine.aim_target = origin
    camera.cine.aim_influence = 0.8
    camera.cine.offset = (1, -2, 3)
    # 升级镜头也可能存有不同基准朝向，完整反推不能假定固定基准。
    camera.cine.base_rotation = Quaternion((0.3, 0.7, 0.2), 0.4) if index % 3 else (1, 0, 0, 0)
    source.location = tuple(rng.uniform(-10, 10) for _ in range(3))
    source.rotation_quaternion = Quaternion(tuple(rng.uniform(-1, 1) for _ in range(3)), rng.uniform(-pi, pi))
    rig.force_update(bpy.context, camera)
    check_pose()
print('[PASS] 120 组完整位姿：旋转/等比缩放控制器、父级参考相机、外部原点、旧版基准与瞄准影响')

source.parent = None
control.matrix_world = Matrix.Identity(4)
camera.cine.origin = None
camera.cine.origin_fallback = (0, 0, 0)
camera.cine.base_rotation = (1, 0, 0, 0)
for position in ((0, 0, 0), (0, 0, 5), (0, 0, -5)):
    for axis in ((1, 0, 0), (0, 1, 0), (0, 0, 1)):
        for angle in (pi/2, -pi/2, pi, pi - 1e-6):
            source.location = position
            source.rotation_quaternion = Quaternion(axis, angle)
            rig.force_update(bpy.context, camera)
            check_pose()
print('[PASS] 中心重合、上下极点、正负 90 度及 180 度旋转都能复现参考朝向')

fields = ('distance', 'horizontal', 'vertical', 'pan', 'tilt', 'roll', 'aim_influence')
saved = tuple(getattr(camera.cine, field) for field in fields)
camera.keyframe_insert(data_path='cine.pan', frame=1)
try:
    rig.import_camera_position(bpy.context, camera, source, full_pose=True)
    raise AssertionError('不能覆盖角度动画')
except ValueError as error:
    assert '动画' in str(error)
assert saved == tuple(getattr(camera.cine, field) for field in fields)
camera.animation_data.action = None
for scale in ((1, 2, 1), (-1, 1, 1)):
    control.scale = scale
    try:
        rig.import_camera_position(bpy.context, camera, source, full_pose=True)
        raise AssertionError('应拒绝非等比或镜像控制空间')
    except ValueError as error:
        assert '缩放' in str(error)
assert saved == tuple(getattr(camera.cine, field) for field in fields)
control.scale = (1, 1, 1)
print('[PASS] 保护旋转动画，拒绝镜像/非等比控制空间，失败不改变参数')

# 强制制造验证失败，确认位置、旋转、瞄准权重和偏移一起回滚。
output = camera.animation_data.drivers.find('delta_rotation_quaternion', index=0)
expression = output.driver.expression
output.driver.expression = '0.123'
camera.cine.aim_influence = 0.5
saved = tuple(getattr(camera.cine, field) for field in fields)
try:
    rig.import_camera_position(bpy.context, camera, source, full_pose=True)
    raise AssertionError('应检测到朝向不一致')
except ValueError as error:
    assert '朝向' in str(error)
assert saved == tuple(getattr(camera.cine, field) for field in fields)
output.driver.expression = expression
rig.force_update(bpy.context, camera)
print('[PASS] 实际朝向验证失败时恢复位置、旋转和瞄准权重')

plain = bpy.data.objects.new('无曲线镜头', bpy.data.cameras.new('无曲线数据'))
bpy.context.collection.objects.link(plain)
rig.build_rig(bpy.context, plain)
rig.import_camera_position(bpy.context, plain, source, full_pose=True)
expected = rig.read_evaluated_camera_matrix(bpy.context, source)
actual = rig.read_evaluated_camera_matrix(bpy.context, plain)
assert (actual.translation - expected.translation).length < 1e-5
assert quaternion_angle_difference(actual.to_quaternion(), expected.to_quaternion()) < 2e-5
print('[PASS] 未使用曲线父级的内部镜头也能完整反推')

bpy.ops.cine.import_camera_position()
expected = rig.read_evaluated_camera_matrix(bpy.context, camera)
name = camera.name
path = Path(__file__).parent / '_tmp' / 'pose_import.blend'
path.parent.mkdir(exist_ok=True)
bpy.ops.wm.save_as_mainfile(filepath=str(path))
bpy.ops.wm.open_mainfile(filepath=str(path))
camera = bpy.data.objects[name]
rig.force_update(bpy.context, camera)
actual = rig.read_evaluated_camera_matrix(bpy.context, camera)
assert (actual.translation - expected.translation).length < 1e-5
assert quaternion_angle_difference(actual.to_quaternion(), expected.to_quaternion()) < 2e-5
assert camera.cine.position_source is not None
print('[PASS] 完整反推后的参数、最终位姿和参考相机指针保存重载一致')
CineController.unregister()
