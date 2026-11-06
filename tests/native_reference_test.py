"""随机组合与 Blender 原生父级/Track To 逐一比较，避免自证公式正确。"""
from pathlib import Path
import sys
import random
import math

sys.path[:0] = [str(Path(__file__).resolve().parents[2]), str(Path(__file__).resolve().parent)]
import bpy
import CineController
from CineController.core import rig
from CineController.utils.math_utils import quaternion_angle_difference
from reference_rig import create_reference

bpy.ops.wm.read_factory_settings(use_empty=True)
CineController.register()
bpy.ops.object.empty_add(location=(2, 3, -1))
origin = bpy.context.object
bpy.ops.object.empty_add(location=(5, -2, 8))
aim = bpy.context.object
bpy.ops.object.camera_add()
camera = bpy.context.object
rig.build_rig(bpy.context, camera, origin)
camera.cine.aim_target = aim
bpy.ops.object.camera_add()
reference = bpy.context.object
helpers = create_reference(reference, origin, aim, source=camera)
rng = random.Random(240204)
max_position = max_rotation = 0.0
for i in range(120):
    p = camera.cine
    p.horizontal = rng.uniform(-20, 20)
    p.vertical = rng.uniform(-1.5, 1.5)
    p.distance = rng.uniform(0.1, 30)
    p.offset = tuple(rng.uniform(-3, 3) for _ in range(3))
    p.pan, p.tilt, p.roll = (rng.uniform(-math.pi, math.pi) for _ in range(3))
    p.aim_influence = (0, 0.25, 0.7, 1)[i % 4]
    origin.location = tuple(rng.uniform(-5, 5) for _ in range(3))
    aim.location = tuple(rng.uniform(-8, 8) for _ in range(3))
    for helper in helpers:
        helper.update_tag()
    rig.force_update(bpy.context, camera)
    actual = rig.read_evaluated_camera_matrix(bpy.context, camera)
    expected = rig.read_evaluated_camera_matrix(bpy.context, reference)
    pos = (actual.translation - expected.translation).length
    rot = quaternion_angle_difference(actual.to_quaternion(), expected.to_quaternion())
    max_position = max(max_position, pos)
    max_rotation = max(max_rotation, rot)
    assert pos < 3e-5 and rot < 3e-5, f'场景 {i}: pos={pos}, rot={rot}'
print(f'[PASS] 120 组原生参照：位置误差 {max_position:.2e}，旋转误差 {max_rotation:.2e}')

# 目标与机位重合、极点、180° 朝向必须保持有限数值。
for point in ((0, 0, 0), (0, 0, 10), (0, 0, -10), (0, 10, 0)):
    camera.cine.offset = (0, 0, 0)
    camera.cine.distance = 0
    origin.location = (0, 0, 0)
    aim.location = point
    camera.cine.aim_influence = 1
    rig.force_update(bpy.context, camera)
    assert all(math.isfinite(x) for row in camera.matrix_world for x in row)
print('[PASS] 重合目标、极点和 180° 朝向无无效数值')
