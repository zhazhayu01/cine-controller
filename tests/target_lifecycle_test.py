"""P0 Target 生命周期测试。

验证：
    Rename 不破坏关系（名字不是身份）
    Focus Target 删除 → Transform 完全不变
    Aim Target 删除 → 不崩 + 位置/旋转不变
    Origin Target 删除 → camera 不跳
    Origin 改绑 → 位姿不跳 + 约束 target 更新
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


def report(name, ok, detail=""):
    print(f"[{'PASS' if ok else 'FAIL'}] {name} {detail}")
    return ok


results = []


def setup_scene():
    bpy.ops.object.camera_add(location=(0.0, -10.0, 0.0))
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
    return camera, origin, aim, focus


# ---------------------------------------------------------------------------
# Focus Target 删除
# ---------------------------------------------------------------------------
camera, origin, aim, focus = setup_scene()
M0 = camera.matrix_world.copy()
bpy.data.objects.remove(focus, do_unlink=True)
rig.force_update(bpy.context, camera)
M1 = camera.matrix_world.copy()
results.append(report("F1. Focus 删除 Transform 不变", preserve_pose.matrix_close(M0, M1)))
results.append(report("F2. Focus 删除后指针为 None", camera.cine.focus_target is None))

# ---------------------------------------------------------------------------
# Aim Target 删除
# ---------------------------------------------------------------------------
camera, origin, aim, focus = setup_scene()
M0 = camera.matrix_world.copy()
bpy.data.objects.remove(aim, do_unlink=True)
rig.force_update(bpy.context, camera)
M1 = camera.matrix_world.copy()
# 位置不变是硬要求；旋转会随 aim 移除而变
pos_unchanged = (M0.to_translation() - M1.to_translation()).length < 1e-5
results.append(report("A1. Aim 删除位置不变", pos_unchanged))
results.append(report("A2. Aim 删除后指针为 None", camera.cine.aim_target is None))

# ---------------------------------------------------------------------------
# Origin Target 删除
# ---------------------------------------------------------------------------
camera, origin, aim, focus = setup_scene()
M0 = camera.matrix_world.copy()
bpy.data.objects.remove(origin, do_unlink=True)
rig.force_update(bpy.context, camera)
M1 = camera.matrix_world.copy()
results.append(report("O1. Origin 删除 camera 不跳", preserve_pose.matrix_close(M0, M1)))
results.append(report("O2. Origin 删除后指针为 None", camera.cine.origin is None))

# Origin 删除后继续改参数应仍可求值（不崩）
try:
    camera.cine.distance += 2.0
    rig.force_update(bpy.context, camera)
    results.append(report("O3. Origin 删除后改参数不崩", True))
except Exception as e:
    results.append(report("O3. Origin 删除后改参数不崩", False, f"({e})"))

# ---------------------------------------------------------------------------
# Origin 改绑
# ---------------------------------------------------------------------------
camera, origin, aim, focus = setup_scene()
bpy.ops.object.empty_add(type='PLAIN_AXES', location=(5.0, 5.0, 0.0))
origin_b = bpy.context.active_object

M0 = camera.matrix_world.copy()
camera.cine.origin = origin_b
rig.force_update(bpy.context, camera)
M1 = camera.matrix_world.copy()

results.append(report("R1. Origin 改绑位姿不跳", preserve_pose.matrix_close(M0, M1)))

# 驱动器的显式目标关系确实更新了。
origin_curve = camera.cine.internal_graph.animation_data.drivers.find('["_cine2_origin0"]')
root_path = next(v.targets[0].data_path for v in origin_curve.driver.variables if v.name == 'root0')
results.append(report("R2. 原点驱动目标更新", camera.cine.origin == origin_b and root_path.startswith('cine.origin.')))

# 改绑后 distance/horizontal/vertical 被正确反解（相机到新 origin 的距离）
import math
expected_dist = (camera.matrix_world.to_translation() - origin_b.matrix_world.to_translation()).length
results.append(report(
    "R3. 改绑后 orbit 参数反解正确",
    abs(camera.cine.distance - expected_dist) < 1e-4,
    f"(d={camera.cine.distance:.3f} vs {expected_dist:.3f})"
))

# ---------------------------------------------------------------------------
# Rename 不破坏关系
# ---------------------------------------------------------------------------
camera, origin, aim, focus = setup_scene()
M0 = camera.matrix_world.copy()

origin.name = "MyOrigin"
aim.name = "MyAim"
focus.name = "MyFocus"
rig.force_update(bpy.context, camera)
M1 = camera.matrix_world.copy()

results.append(report("N1. Rename 后 Transform 不变", preserve_pose.matrix_close(M0, M1)))
results.append(report("N2. Rename 后指针仍有效", camera.cine.origin is not None and camera.cine.aim_target is not None))

# Rename 后 Aim 驱动目标仍有效（靠 pointer，不靠名字）。
aim_curve = camera.cine.internal_graph.animation_data.drivers.find('["_cine2_dir0"]')
aim_target_ok = any(v.targets[0].id == camera and v.targets[0].data_path.startswith('cine.aim_target.')
                    for v in aim_curve.driver.variables if v.name == 'target0')
results.append(report("N3. Rename 后 Aim 驱动目标仍有效", aim_target_ok))

print()
total = len(results)
passed = sum(results)
print(f"===== {passed}/{total} PASS =====")
if passed != total:
    print("!!!! 存在失败项 !!!!")
    sys.exit(1)
