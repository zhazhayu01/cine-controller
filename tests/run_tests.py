"""P0 Smoke Test —— 在 headless Blender 中运行。

用法:
    blender -b -P tests/run_tests.py

验证第一里程碑核心：
    A. Enable 后 Camera 位姿不跳
    B. Distance / Horizontal / Vertical Driver 生效
    C. Focus Target 移动不改变 Camera Transform
    D. Aim 影响 Orientation 但不影响 Position
    G. 重复求值幂等
"""
import sys
import os

# 让 blender 能 import 插件根目录（E:/ 是 CineController 的父目录）
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PARENT = os.path.dirname(ROOT)
if PARENT not in sys.path:
    sys.path.insert(0, PARENT)

import bpy

# 清空默认场景
bpy.ops.wm.read_factory_settings(use_empty=True)

# 注册插件
import CineController  # noqa: E402
CineController.register()


def report(name, ok, detail=""):
    status = "PASS" if ok else "FAIL"
    print(f"[{status}] {name} {detail}")
    return ok


results = []

# ---------------------------------------------------------------------------
# 场景搭建：Origin / Camera / Cube / Focus Target / Aim Target
# ---------------------------------------------------------------------------
bpy.ops.object.camera_add(location=(0.0, -10.0, 1.5))
camera = bpy.context.active_object

bpy.ops.object.empty_add(type='PLAIN_AXES', location=(0.0, 0.0, 0.0))
origin = bpy.context.active_object
origin.name = "Origin"

bpy.ops.object.empty_add(type='PLAIN_AXES', location=(0.0, 0.0, 2.0))
focus = bpy.context.active_object
focus.name = "FocusTarget"

bpy.ops.object.empty_add(type='PLAIN_AXES', location=(0.0, 0.0, 3.0))
aim = bpy.context.active_object
aim.name = "AimTarget"

bpy.ops.mesh.primitive_cube_add(location=(0.0, 0.0, 0.0))

# 选中 camera 作为 active
bpy.context.view_layer.objects.active = camera

from CineController.core import rig, preserve_pose
from CineController.utils.math_utils import quaternion_angle_difference

# ---------------------------------------------------------------------------
# A. Enable 后不跳
# ---------------------------------------------------------------------------
camera.cine.origin = origin
before = camera.matrix_world.copy()

result = rig.build_rig(bpy.context, camera, origin)
after = result["after"]

ok = preserve_pose.matrix_close(before, after)
results.append(report(
    "A. Enable 后位姿不跳",
    ok,
    f"(pos_err={(before.to_translation() - after.to_translation()).length:.2e})"
))

params = camera.cine

# ---------------------------------------------------------------------------
# B. Driver 生效：改 Distance / Horizontal / Vertical 后位置变化
# ---------------------------------------------------------------------------
pos_before = camera.matrix_world.to_translation().copy()

params.distance += 2.0
rig.force_update(bpy.context, camera)
pos_dist = camera.matrix_world.to_translation()
dist_moved = (pos_dist - pos_before).length > 1.0
results.append(report("B1. Distance Driver 生效", dist_moved))

params.distance -= 2.0
params.horizontal += 1.0  # 绕 Z 转 1 弧度
rig.force_update(bpy.context, camera)
pos_h = camera.matrix_world.to_translation()
h_moved = (pos_h - pos_before).length > 1.0
results.append(report("B2. Horizontal Driver 生效", h_moved))

params.horizontal -= 1.0
params.vertical += 0.5
rig.force_update(bpy.context, camera)
pos_v = camera.matrix_world.to_translation()
v_moved = (pos_v - pos_before).length > 1.0
results.append(report("B3. Vertical Driver 生效", v_moved))

# 复原参数并验证回到原位（幂等 + 绝对驱动）
params.vertical -= 0.5
rig.force_update(bpy.context, camera)
pos_restore = camera.matrix_world.to_translation()
restored = (pos_restore - pos_before).length < 1e-4
results.append(report("B4. 参数复原后回到原位（绝对驱动）", restored))

# ---------------------------------------------------------------------------
# C. Focus 独立性：绑定/移动 Focus 不改变 Camera Transform
# ---------------------------------------------------------------------------
before_focus = camera.matrix_world.copy()
params.focus_target = focus
rig.force_update(bpy.context, camera)
after_focus_bind = camera.matrix_world.copy()

focus.location = (5.0, 5.0, 5.0)
rig.force_update(bpy.context, camera)
after_focus_move = camera.matrix_world.copy()

ok1 = preserve_pose.matrix_close(before_focus, after_focus_bind)
ok2 = preserve_pose.matrix_close(before_focus, after_focus_move)
results.append(report("C1. 绑定 Focus 不改变 Transform", ok1))
results.append(report("C2. 移动 Focus 不改变 Transform", ok2))

dof_bound = camera.data.dof.focus_object == focus
results.append(report("C3. DOF focus_object 绑定成功", dof_bound))

# ---------------------------------------------------------------------------
# D. Aim 影响 Orientation 但不影响 Position
# ---------------------------------------------------------------------------
before_aim = camera.matrix_world.copy()
params.aim_target = aim
params.aim_influence = 1.0
rig.force_update(bpy.context, camera)
after_aim = camera.matrix_world.copy()

pos_before_aim = before_aim.to_translation()
pos_after_aim = after_aim.to_translation()
pos_unchanged = (pos_before_aim - pos_after_aim).length < 1e-4
results.append(report("D1. Aim 不改变 Position", pos_unchanged))

rot_changed = quaternion_angle_difference(
    before_aim.to_quaternion(), after_aim.to_quaternion()) > 0.01
results.append(report("D2. Aim 改变 Orientation", rot_changed))
# ---------------------------------------------------------------------------
# G. 重复求值幂等
# ---------------------------------------------------------------------------
depsgraph = bpy.context.evaluated_depsgraph_get()
m1 = camera.evaluated_get(depsgraph).matrix_world.copy()
for _ in range(5):
    depsgraph.update()
m2 = camera.evaluated_get(depsgraph).matrix_world.copy()
results.append(report("G. 重复求值幂等", preserve_pose.matrix_close(m1, m2)))

# ---------------------------------------------------------------------------
# 汇总
# ---------------------------------------------------------------------------
print()
total = len(results)
passed = sum(results)
print(f"===== {passed}/{total} PASS =====")
if passed != total:
    print("!!!! 存在失败项 !!!!")
    sys.exit(1)
