"""无辅助对象控制器：结构、锁定、动画与目标依赖回归。"""
import os
import sys

from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import bpy
import CineController
from CineController.core import rig
from mathutils import Matrix

bpy.ops.wm.read_factory_settings(use_empty=True)
CineController.register()
bpy.ops.object.camera_add(location=(4, 5, 6))
camera = bpy.context.object
objects_before = set(bpy.data.objects)
collections_before = set(bpy.data.collections)
groups_before = set(bpy.data.node_groups)
assert bpy.ops.cine.enable_controller() == {'FINISHED'}
assert set(bpy.data.objects) == objects_before, "启用不应生成辅助对象"
assert set(bpy.data.collections) == collections_before, "启用不应生成辅助集合"
assert camera.parent is None
assert all(camera.lock_location) and all(camera.lock_rotation)
camera.cine.distance = 10
camera.cine.horizontal = 0.5
rig.force_update(bpy.context, camera)
assert camera.location.length < 1e-6
assert camera.rotation_quaternion == __import__('mathutils').Quaternion()
assert camera.matrix_world.translation.length > 9.99
assert all(f.driver.is_valid and f.driver.is_simple_expression
           for owner in (camera, camera.cine.internal_graph) for f in owner.animation_data.drivers)
assert all(len(f.driver.expression) < 256
           for owner in (camera, camera.cine.internal_graph) for f in owner.animation_data.drivers)
assert not camera.constraints
before = camera.matrix_world.copy()
rig.remove_rig(bpy.context, camera)
assert max(abs(before[i][j] - camera.matrix_world[i][j]) for i in range(4) for j in range(4)) < 1e-5
assert not camera.animation_data.drivers
assert not any(k.startswith('_cine2_') for k in camera.keys())
assert set(bpy.data.node_groups) == groups_before
assert not any(camera.lock_location)
print('[PASS] 无辅助对象、基础通道锁定、原生驱动器、解绑清理')
