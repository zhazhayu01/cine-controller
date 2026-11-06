"""零角度水平拍摄，距离为远近，空间偏移与摄影机轴一致。"""
from pathlib import Path
import sys
from math import pi

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import bpy
import CineController
from CineController.core import rig
from mathutils import Vector

bpy.ops.wm.read_factory_settings(use_empty=True)
CineController.register()


def close(actual, expected):
    assert (Vector(actual) - Vector(expected)).length < 1e-5, (tuple(actual), tuple(expected))


for location in (None, (0, 0, 1.9), (3, -4, 2)):
    origin = None
    if location is not None:
        bpy.ops.object.empty_add(location=location)
        origin = bpy.context.object
    bpy.ops.object.camera_add(location=(8, -6, 4))
    camera = bpy.context.object
    camera.cine.origin = origin
    assert bpy.ops.cine.enable_controller() == {'FINISHED'}
    p = camera.cine
    assert p.horizontal == p.vertical == p.pan == p.tilt == p.roll == 0
    root = Vector(location or (0, 0, 0))
    close(camera.location, (0, 0, 0))
    close(camera.rotation_euler, (0, 0, 0))
    close(camera.matrix_world.to_quaternion() @ Vector((0, 0, -1)), (0, 1, 0))
    close(camera.matrix_world.to_quaternion() @ Vector((0, 1, 0)), (0, 0, 1))
    for distance in (2, 7):
        p.distance = distance
        rig.force_update(bpy.context, camera)
        close(camera.matrix_world.translation, root + Vector((0, -distance, 0)))
    for axis, direction in enumerate(((1, 0, 0), (0, 0, 1), (0, 1, 0))):
        value = [0, 0, 0]
        value[axis] = 3
        p.offset = value
        rig.force_update(bpy.context, camera)
        close(camera.matrix_world.translation, root + Vector((0, -7, 0)) + 3*Vector(direction))
    p.offset = (0, 0, 0)
    for horizontal, vertical in ((0, 0), (pi/2, 0), (-pi/3, pi/6)):
        p.horizontal, p.vertical = horizontal, vertical
        rig.force_update(bpy.context, camera)
        forward = camera.matrix_world.to_quaternion() @ Vector((0, 0, -1))
        close(forward, (root - camera.matrix_world.translation).normalized())
    print(f'[PASS] 默认水平朝向、距离前后、偏移右/上/前、环绕朝向：Origin={location}')

# 复现截图中的旧版补偿角：垂直 90°、水平摇摄 -90°。
p.base_rotation = (1, 0, 0, 0)
p.vertical = pi/2
p.pan = -pi/2
p.distance = 1.9
rig.force_update(bpy.context, camera)
assert bpy.ops.cine.reset_space_axes() == {'FINISHED'}
assert abs(p.distance-1.9) < 1e-5
close(camera.matrix_world.translation, root + Vector((0, -1.9, 0)))
close(camera.matrix_world.to_quaternion() @ Vector((0, 0, -1)), (0, 1, 0))
print('[PASS] 已有镜头一键恢复水平轴向，保留距离')

p.pan = 0.3
p.keyframe_insert(data_path='pan', frame=1)
before = camera.matrix_world.copy()
try:
    rig.reset_space_axes(bpy.context, camera)
except ValueError:
    pass
else:
    raise AssertionError('不能静默覆盖已有旋转动画')
assert abs(p.pan-0.3) < 1e-5
print('[PASS] 已有空间动画时拒绝直接重置，保护原参数')
