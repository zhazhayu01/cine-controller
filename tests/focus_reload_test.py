"""P0 Focus Save/Reload 永久回归测试（规范 §46）。

这是针对「Camera 插件已知类型 bug」的专项测试，必须长期保留：
    Camera + Origin + Focus Target → Enable → Bind Focus → Save → Reload
    → Camera Matrix 必须一致 → 移动 Focus Target → Camera 完全不变 → 再 Save/Reload 仍不变。
"""
import sys
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PARENT = os.path.dirname(ROOT)
if PARENT not in sys.path:
    sys.path.insert(0, PARENT)

import bpy
from mathutils import Matrix

bpy.ops.wm.read_factory_settings(use_empty=True)

import CineController
CineController.register()

from CineController.core import rig, preserve_pose

TMP = os.path.join(ROOT, "tests", "_tmp_focus_reload.blend")


def report(name, ok, detail=""):
    print(f"[{'PASS' if ok else 'FAIL'}] {name} {detail}")
    return ok


results = []

# ---------------------------------------------------------------------------
# 阶段 1：建场景 + Enable + Bind Focus + 记录 M1 + Save
# ---------------------------------------------------------------------------
bpy.ops.object.camera_add(location=(0.0, -10.0, 1.5))
camera = bpy.context.active_object

bpy.ops.object.empty_add(type='PLAIN_AXES', location=(0.0, 0.0, 0.0))
origin = bpy.context.active_object

bpy.ops.object.empty_add(type='PLAIN_AXES', location=(0.0, 0.0, 2.0))
focus = bpy.context.active_object

bpy.context.view_layer.objects.active = camera
camera.cine.origin = origin
camera.cine.focus_target = focus

rig.build_rig(bpy.context, camera, origin)
rig.force_update(bpy.context, camera)
M1 = camera.matrix_world.copy()

bpy.ops.wm.save_as_mainfile(filepath=TMP)

# ---------------------------------------------------------------------------
# 阶段 2：Reload → 读 M2 → 对比
# ---------------------------------------------------------------------------
bpy.ops.wm.open_mainfile(filepath=TMP)
camera = next(o for o in bpy.data.objects if o.type == 'CAMERA')
rig.force_update(bpy.context, camera)
M2 = camera.matrix_world.copy()

results.append(report(
    "FR1. Save/Reload 后 Camera Matrix 一致",
    preserve_pose.matrix_close(M1, M2),
    f"(pos_err={(M1.to_translation()-M2.to_translation()).length:.2e})"
))

# 验证 focus 绑定在 reload 后仍有效（靠 pointer，不靠名字）
focus_after = camera.cine.focus_target
results.append(report("FR2. Reload 后 Focus 指针仍有效", focus_after is not None))

# ---------------------------------------------------------------------------
# 阶段 3：移动 Focus Target → Camera 完全不变
# ---------------------------------------------------------------------------
M3 = camera.matrix_world.copy()
focus_after.location = (5.0, 5.0, 5.0)
rig.force_update(bpy.context, camera)
M4 = camera.matrix_world.copy()

results.append(report(
    "FR3. 移动 Focus Target Camera 完全不变",
    preserve_pose.matrix_close(M3, M4),
))

# ---------------------------------------------------------------------------
# 阶段 4：再 Save/Reload → 仍不变
# ---------------------------------------------------------------------------
bpy.ops.wm.save_as_mainfile(filepath=TMP)
bpy.ops.wm.open_mainfile(filepath=TMP)
camera = next(o for o in bpy.data.objects if o.type == 'CAMERA')
rig.force_update(bpy.context, camera)
M5 = camera.matrix_world.copy()

results.append(report(
    "FR4. 移动 Focus 后再 Save/Reload 仍不变",
    preserve_pose.matrix_close(M3, M5),
))

# 清理
if os.path.exists(TMP):
    os.remove(TMP)

print()
total = len(results)
passed = sum(results)
print(f"===== {passed}/{total} PASS =====")
if passed != total:
    print("!!!! 存在失败项 !!!!")
    sys.exit(1)
