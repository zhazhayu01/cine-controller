"""P0 Offset / Pan / Tilt / Roll 专项测试（规范 §61/62/63）。

验证第二阶段的完整参数：
    - Offset 沿 Camera Right/Up/Forward 正确移动
    - Pan 绕 Up 水平摇摄
    - Tilt 绕 Right 俯仰
    - Roll 绕 Forward 翻滚（不改 forward，改 up）
    - 所有参数绝对驱动 + 幂等（参数归零回到原位）
"""
import sys
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PARENT = os.path.dirname(ROOT)
if PARENT not in sys.path:
    sys.path.insert(0, PARENT)

import bpy
from mathutils import Vector

bpy.ops.wm.read_factory_settings(use_empty=True)

import CineController
CineController.register()

from CineController.core import rig, preserve_pose


def report(name, ok, detail=""):
    print(f"[{'PASS' if ok else 'FAIL'}] {name} {detail}")
    return ok


results = []

# ---------------------------------------------------------------------------
# 场景
# ---------------------------------------------------------------------------
bpy.ops.object.camera_add(location=(0.0, -10.0, 0.0))
camera = bpy.context.active_object

bpy.ops.object.empty_add(type='PLAIN_AXES', location=(0.0, 0.0, 0.0))
origin = bpy.context.active_object

bpy.context.view_layer.objects.active = camera
camera.cine.origin = origin

rig.build_rig(bpy.context, camera, origin)

params = camera.cine


def cam_pose():
    """返回 (position, forward, up, right) 世界向量。"""
    dg = bpy.context.evaluated_depsgraph_get()
    dg.update()
    M = camera.evaluated_get(dg).matrix_world
    q = M.to_quaternion()
    return (
        M.to_translation(),
        q @ Vector((0, 0, -1)),  # forward
        q @ Vector((0, 1, 0)),   # up
        q @ Vector((1, 0, 0)),   # right
    )


pos0, fwd0, up0, right0 = cam_pose()

# ---------------------------------------------------------------------------
# Offset 测试
# ---------------------------------------------------------------------------
# Offset X = Right，设 +2 → camera 沿 right 移动 2
params.offset = (2.0, 0.0, 0.0)
rig.force_update(bpy.context, camera)
pos, fwd, up, right = cam_pose()
moved_right = (pos - pos0).length > 1.9
dir_ok = abs((pos - pos0).normalized().dot(right0)) > 0.99
results.append(report("O1. Offset X 沿 Right 移动", moved_right and dir_ok))

params.offset = (0.0, 0.0, 0.0)
rig.force_update(bpy.context, camera)

# Offset Y = Up，设 +3 → camera 沿 up 移动 3
params.offset = (0.0, 3.0, 0.0)
rig.force_update(bpy.context, camera)
pos, fwd, up, right = cam_pose()
moved_up = (pos - pos0).length > 2.9
dir_ok = abs((pos - pos0).normalized().dot(up0)) > 0.99
results.append(report("O2. Offset Y 沿 Up 移动", moved_up and dir_ok))

params.offset = (0.0, 0.0, 0.0)
rig.force_update(bpy.context, camera)

# Offset Z = Forward，设 +4 → camera 沿 forward 移动 4
params.offset = (0.0, 0.0, 4.0)
rig.force_update(bpy.context, camera)
pos, fwd, up, right = cam_pose()
moved_fwd = (pos - pos0).length > 3.9
dir_ok = abs((pos - pos0).normalized().dot(fwd0)) > 0.99
results.append(report("O3. Offset Z 沿 Forward 移动", moved_fwd and dir_ok))

params.offset = (0.0, 0.0, 0.0)
rig.force_update(bpy.context, camera)
pos, fwd, up, right = cam_pose()
results.append(report("O4. Offset 归零回到原位（绝对驱动）", (pos - pos0).length < 1e-4))

# ---------------------------------------------------------------------------
# Pan / Tilt / Roll 测试
# ---------------------------------------------------------------------------
# Roll：绕 Forward，forward 不变，up 变
import math
params.roll = math.radians(30)
rig.force_update(bpy.context, camera)
pos, fwd, up, right = cam_pose()
fwd_unchanged = (fwd - fwd0).length < 1e-4
up_changed = (up - up0).length > 0.3
results.append(report("P1. Roll 绕 Forward（fwd 不变，up 变）", fwd_unchanged and up_changed))
params.roll = 0.0
rig.force_update(bpy.context, camera)

# Tilt：绕 Right，forward 在垂直面内转
params.tilt = math.radians(20)
rig.force_update(bpy.context, camera)
pos, fwd, up, right = cam_pose()
fwd_changed = (fwd - fwd0).length > 0.1
results.append(report("P2. Tilt 改变 forward", fwd_changed))
params.tilt = 0.0
rig.force_update(bpy.context, camera)

# Pan：绕 Up，forward 在水平面内转
params.pan = math.radians(25)
rig.force_update(bpy.context, camera)
pos, fwd, up, right = cam_pose()
fwd_changed = (fwd - fwd0).length > 0.1
results.append(report("P3. Pan 改变 forward", fwd_changed))
params.pan = 0.0
rig.force_update(bpy.context, camera)

# 归零后完全复原
pos, fwd, up, right = cam_pose()
fully_restored = (pos - pos0).length < 1e-4 and (fwd - fwd0).length < 1e-4 and (up - up0).length < 1e-4
results.append(report("P4. pan/tilt/roll 归零完全复原（幂等）", fully_restored))

# ---------------------------------------------------------------------------
# Offset + Pan/Tilt/Roll 组合后，位置只由 offset 决定（pan/tilt/roll 不改位置）
# ---------------------------------------------------------------------------
params.offset = (0.0, 0.0, 5.0)
rig.force_update(bpy.context, camera)
pos_offset_only, _, _, _ = cam_pose()

params.pan = math.radians(40)
params.tilt = math.radians(15)
params.roll = math.radians(10)
rig.force_update(bpy.context, camera)
pos_combo, _, _, _ = cam_pose()

pos_unchanged_by_rot = (pos_offset_only - pos_combo).length < 1e-4
results.append(report("P5. pan/tilt/roll 不改变位置（只改朝向）", pos_unchanged_by_rot))

print()
total = len(results)
passed = sum(results)
print(f"===== {passed}/{total} PASS =====")
if passed != total:
    print("!!!! 存在失败项 !!!!")
    sys.exit(1)
