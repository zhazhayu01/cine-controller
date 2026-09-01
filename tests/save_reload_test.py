"""P0 Save/Reload 回归测试（规范 §44/45）—— 真实 .blend 保存与重开。

流程：
    创建场景 → Enable Controller → 多帧记录 Matrix → Save .blend
    → open_mainfile 重开 → 重新记录 Matrix → 逐帧对比

这是整个插件最高优先级的测试：关掉再打开，镜头必须完全一样。
"""
import sys
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PARENT = os.path.dirname(ROOT)
if PARENT not in sys.path:
    sys.path.insert(0, PARENT)

import bpy
import json

bpy.ops.wm.read_factory_settings(use_empty=True)

import CineController
CineController.register()

from CineController.core import rig, preserve_pose

TMP = os.path.join(ROOT, "tests", "_tmp_reload.blend")


def report(name, ok, detail=""):
    print(f"[{'PASS' if ok else 'FAIL'}] {name} {detail}")
    return ok


results = []

# ---------------------------------------------------------------------------
# 阶段 1：建场景 + Enable + 记录多帧矩阵 + Save
# ---------------------------------------------------------------------------
bpy.ops.object.camera_add(location=(0.0, -10.0, 1.5))
camera = bpy.context.active_object

bpy.ops.object.empty_add(type='PLAIN_AXES', location=(0.0, 0.0, 0.0))
origin = bpy.context.active_object

bpy.ops.object.empty_add(type='PLAIN_AXES', location=(0.0, 0.0, 3.0))
aim = bpy.context.active_object

bpy.ops.object.empty_add(type='PLAIN_AXES', location=(0.0, 0.0, 2.0))
focus = bpy.context.active_object

bpy.context.view_layer.objects.active = camera
camera.cine.origin = origin
camera.cine.aim_target = aim
camera.cine.aim_influence = 1.0
camera.cine.focus_target = focus

rig.build_rig(bpy.context, camera, origin)

# 制造真实的参数动画（keyframe，保存后随帧求值）
frames = [1, 20, 50, 100]
matrices_before = {}
for f in frames:
    bpy.context.scene.frame_set(f)
    camera.cine.horizontal = 0.05 * f
    camera.cine.vertical = 0.01 * f
    camera.cine.distance = 10.0 + 0.05 * f
    # 插关键帧：让参数动画真实存在于 .blend
    camera.cine.keyframe_insert(data_path="horizontal", frame=f)
    camera.cine.keyframe_insert(data_path="vertical", frame=f)
    camera.cine.keyframe_insert(data_path="distance", frame=f)
    rig.force_update(bpy.context, camera)
    matrices_before[str(f)] = [list(row) for row in camera.matrix_world]

bpy.ops.wm.save_as_mainfile(filepath=TMP)
print(f"阶段1完成：已保存 {TMP}")

# ---------------------------------------------------------------------------
# 阶段 2：重开文件 → 重新记录矩阵 → 逐帧对比
# ---------------------------------------------------------------------------
bpy.ops.wm.open_mainfile(filepath=TMP)

# 重开后重新定位 camera（名字是 Camera，用类型找）
camera = next(o for o in bpy.data.objects if o.type == 'CAMERA')

ok_reload_state = camera.cine.enabled and camera.cine.rig_root is not None
results.append(report("R1. 重载后 Controller 状态保留", ok_reload_state))

matrices_after = {}
for f in frames:
    bpy.context.scene.frame_set(f)
    rig.force_update(bpy.context, camera)
    matrices_after[str(f)] = [list(row) for row in camera.matrix_world]

all_close = True
max_err = 0.0
for f in frames:
    b = preserve_pose.matrix_close(
        __import__("mathutils").Matrix(matrices_before[str(f)]),
        __import__("mathutils").Matrix(matrices_after[str(f)]),
    )
    if not b:
        all_close = False
    # 算位置误差
    pb = __import__("mathutils").Matrix(matrices_before[str(f)]).to_translation()
    pa = __import__("mathutils").Matrix(matrices_after[str(f)]).to_translation()
    err = (pb - pa).length
    max_err = max(max_err, err)

results.append(report(
    "R2. Save/Reload 逐帧矩阵一致",
    all_close,
    f"(max_pos_err={max_err:.2e})"
))

# 清理临时文件
if os.path.exists(TMP):
    os.remove(TMP)

print()
total = len(results)
passed = sum(results)
print(f"===== {passed}/{total} PASS =====")
if passed != total:
    print("!!!! 存在失败项 !!!!")
    sys.exit(1)
