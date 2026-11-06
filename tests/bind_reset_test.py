"""基础通道归零，最终画面采用空间原点及内部水平朝向，不继承旧父级。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import bpy
from math import pi
from mathutils import Matrix
import CineController
from CineController.core import rig

bpy.ops.wm.read_factory_settings(use_empty=True)
CineController.register()


def is_identity(matrix):
    return max(abs(matrix[i][j] - (i == j)) for i in range(4) for j in range(4)) < 1e-5


for mode in ('XYZ', 'QUATERNION', 'AXIS_ANGLE'):
    for origin_location in ((0, 0, 0), (3, -4, 2)):
        bpy.ops.object.empty_add(location=origin_location)
        origin = bpy.context.object
        bpy.ops.object.empty_add(location=(4, 5, 6))
        old_parent = bpy.context.object
        old_parent.rotation_euler = (0.2, 0.3, 0.4)
        bpy.context.view_layer.update()
        bpy.ops.object.camera_add(location=(7, -10, 3))
        camera = bpy.context.object
        camera.parent = old_parent
        camera.matrix_parent_inverse = old_parent.matrix_world.inverted()
        camera.rotation_mode = mode
        camera.rotation_euler = (0.4, 0.2, 0.6)
        camera.rotation_quaternion = (0.5, 0.5, 0.5, 0.5)
        camera.rotation_axis_angle = (0.8, 0, 1, 0)
        camera.scale = (2, 3, 4)
        camera.delta_location = (1, 2, 3)
        camera.delta_rotation_euler = (0.1, 0.2, 0.3)
        camera.delta_rotation_quaternion = (0.5, 0.5, 0.5, 0.5)
        camera.delta_scale = (1.5, 2, 2.5)
        camera.cine.origin = origin
        bpy.context.view_layer.update()

        result = bpy.ops.cine.enable_controller()
        rig.force_update(bpy.context, camera)
        assert result == {'FINISHED'}, f"绑定失败：{mode}, {origin_location}"
        expected = Matrix.Rotation(pi/2, 4, 'X')
        expected.translation = origin_location
        def same_pose():
            return max(abs(camera.matrix_world[i][j]-expected[i][j]) for i in range(4) for j in range(4)) < 1e-5
        assert same_pose(), f"未采用默认水平空间：{mode}, {origin_location}"
        assert camera.location.length < 1e-5 and camera.rotation_euler.to_quaternion().angle < 1e-5, "基础位置/旋转未归零"
        assert is_identity(camera.matrix_parent_inverse), "残留旧父级逆矩阵"
        assert camera.parent is None and camera.cine.internal_graph is not None, "未启用内部控制器"
        assert all(camera.lock_location) and all(camera.lock_rotation), "基础位置/旋转未锁定"
        old_parent.location.x += 10
        rig.force_update(bpy.context, camera)
        assert same_pose(), "旧父级仍影响摄像机"
        rig.remove_rig(bpy.context, camera)
        assert same_pose(), "解绑后变换发生变化"
        print(f"[PASS] 绑定清零 {mode}, Origin={origin_location}")

print("===== 6/6 PASS =====")
