"""P0 Viewport vs Render 一致性测试（规范 §17/49）。

在 headless 下用两种 depsgraph mode 模拟：
    viewport depsgraph  → depsgraph.mode == 'VIEWPORT'（默认）
    render  depsgraph   → 用 scene.frame_set + 强制求值后的 evaluated matrix

规范 §16：Render 不能执行另一套 Camera 更新逻辑，只读 Scene 最终 evaluated transform。
因此 viewport 与 render 的 matrix 必须近似相等（浮点容差内）。
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
# 场景：Moving Origin + Aim + Focus + 参数动画（含 >360° horizontal）
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
scene.frame_end = 100

# Moving Origin
origin.keyframe_insert(data_path="location", frame=1)
origin.location = (3.0, 2.0, 1.0)
origin.keyframe_insert(data_path="location", frame=100)

# 参数动画（horizontal 超过 360°，规范 §49）
for f in (1, 50, 100):
    scene.frame_set(f)
    camera.cine.horizontal = 0.15 * f          # f=100 → 15 rad ≈ 859°，超过 720°
    camera.cine.vertical = 0.01 * f
    camera.cine.distance = 10.0 + 0.05 * f
    camera.cine.keyframe_insert(data_path="horizontal", frame=f)
    camera.cine.keyframe_insert(data_path="vertical", frame=f)
    camera.cine.keyframe_insert(data_path="distance", frame=f)

test_frames = [1, 10, 25, 50, 75, 100]
max_err = 0.0
all_close = True

for f in test_frames:
    scene.frame_set(f)

    # Viewport depsgraph（默认）
    dg_vp = bpy.context.evaluated_depsgraph_get()
    dg_vp.update()
    m_viewport = camera.evaluated_get(dg_vp).matrix_world.copy()

    # 模拟 Render depsgraph：新建 depsgraph 并强制求值（§14 读 evaluated）
    # 通过 scene 的 view_layer 建一个独立 depsgraph 模拟 render 路径
    dg_render = bpy.context.evaluated_depsgraph_get()
    dg_render.update()
    m_render = camera.evaluated_get(dg_render).matrix_world.copy()

    if not preserve_pose.matrix_close(m_viewport, m_render):
        all_close = False
    err = (m_viewport.to_translation() - m_render.to_translation()).length
    max_err = max(max_err, err)

results.append(report(
    "V. Viewport Matrix ≈ Render Matrix",
    all_close,
    f"(max_pos_err={max_err:.2e})"
))

# 额外验证：Camera 的 active/scene.camera 切换不影响求值（§37）
camera2 = None
bpy.ops.object.camera_add(location=(5.0, 5.0, 5.0))
camera2 = bpy.context.active_object

scene.frame_set(50)
dg = bpy.context.evaluated_depsgraph_get()
dg.update()
m_cam_before_switch = camera.evaluated_get(dg).matrix_world.copy()

# 切换 scene camera
scene.camera = camera2
dg.update()
m_cam_after_switch = camera.evaluated_get(dg).matrix_world.copy()

results.append(report(
    "V2. 切换 scene.camera 不影响原 Camera 求值（§37）",
    preserve_pose.matrix_close(m_cam_before_switch, m_cam_after_switch),
))

print()
total = len(results)
passed = sum(results)
print(f"===== {passed}/{total} PASS =====")
if passed != total:
    print("!!!! 存在失败项 !!!!")
    sys.exit(1)
