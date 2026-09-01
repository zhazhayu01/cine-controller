"""P0 Bake 一致性测试（规范 §42）—— Live Matrix ≈ Baked Matrix 每帧成立。

Bake 的唯一数据来源是 evaluated Camera Matrix（§40），禁止独立重算。
"""
import sys
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PARENT = os.path.dirname(ROOT)
if PARENT not in sys.path:
    sys.path.insert(0, PARENT)

import bpy

bpy.ops.wm.read_factory_settings(use_empty=True)

import CineController
CineController.register()

from CineController.core import rig, preserve_pose
from mathutils import Matrix


def report(name, ok, detail=""):
    print(f"[{'PASS' if ok else 'FAIL'}] {name} {detail}")
    return ok


results = []

# ---------------------------------------------------------------------------
# 场景：Moving Origin + Aim + Focus + 参数动画
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

scene = bpy.context.scene
scene.frame_start = 1
scene.frame_end = 30

# Origin 自身动画（Moving Origin）
origin.keyframe_insert(data_path="location", frame=1)
origin.location = (3.0, 2.0, 0.0)
origin.keyframe_insert(data_path="location", frame=30)

# 参数动画
for f in (1, 15, 30):
    scene.frame_set(f)
    camera.cine.horizontal = 0.1 * f
    camera.cine.vertical = 0.02 * f
    camera.cine.distance = 10.0 + 0.1 * f
    camera.cine.keyframe_insert(data_path="horizontal", frame=f)
    camera.cine.keyframe_insert(data_path="vertical", frame=f)
    camera.cine.keyframe_insert(data_path="distance", frame=f)

# ---------------------------------------------------------------------------
# 记录每帧 Live Matrix
# ---------------------------------------------------------------------------
live = {}
for f in range(scene.frame_start, scene.frame_end + 1):
    scene.frame_set(f)
    rig.force_update(bpy.context, camera)
    live[f] = camera.matrix_world.copy()

# ---------------------------------------------------------------------------
# Bake
# ---------------------------------------------------------------------------
bpy.ops.cine.bake()

# ---------------------------------------------------------------------------
# 对比 Live vs Baked（Bake 后 camera 已被写成关键帧，直接读）
# ---------------------------------------------------------------------------
max_err = 0.0
all_close = True
for f in range(scene.frame_start, scene.frame_end + 1):
    scene.frame_set(f)
    depsgraph = bpy.context.evaluated_depsgraph_get()
    depsgraph.update()
    cam_eval = camera.evaluated_get(depsgraph)
    baked = cam_eval.matrix_world.copy()

    if not preserve_pose.matrix_close(live[f], baked):
        all_close = False
    err = (live[f].to_translation() - baked.to_translation()).length
    max_err = max(max_err, err)

results.append(report(
    "B. Live Matrix ≈ Baked Matrix 每帧成立",
    all_close,
    f"(max_pos_err={max_err:.2e})"
))

# 验证 Bake 后旋转模式是 QUATERNION（§43）
results.append(report(
    "B2. Bake 使用 Quaternion 旋转模式",
    camera.rotation_mode == 'QUATERNION',
))

# 验证关键帧确实被写入（Bake 后 rig 已移除，camera 有 animation_data）
has_anim = camera.animation_data is not None and camera.animation_data.action is not None
results.append(report("B3. Bake 后 camera 有动画数据（关键帧已写入）", has_anim))

print()
total = len(results)
passed = sum(results)
print(f"===== {passed}/{total} PASS =====")
if passed != total:
    print("!!!! 存在失败项 !!!!")
    sys.exit(1)
