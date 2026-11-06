"""旧版 Helper 控制器保留参数动画升级，失败不删除旧结构。"""
from pathlib import Path
import sys
sys.path[:0] = [str(Path(__file__).resolve().parents[2]), str(Path(__file__).resolve().parent)]
import bpy
import CineController
from CineController.core import rig
from CineController.utils.math_utils import matrix_close
from reference_rig import create_reference

bpy.ops.wm.read_factory_settings(use_empty=True)
CineController.register()
bpy.ops.object.empty_add(location=(2, 3, 1))
origin = bpy.context.object
bpy.ops.object.empty_add(location=(5, -2, 7))
aim = bpy.context.object
bpy.ops.object.camera_add()
camera = bpy.context.object
p = camera.cine
p.origin, p.aim_target = origin, aim
p.base_rotation = (0.8, 0.2, -0.3, 0.47958315)
helpers = create_reference(camera, origin, aim)
for frame in (1, 10, 20):
    bpy.context.scene.frame_set(frame)
    p.distance, p.horizontal, p.vertical = 10+frame/10, frame/10, frame/50
    p.offset = (1, -2, 0.5)
    p.pan, p.tilt, p.roll = (0.1, -0.2, 0.3)
    p.aim_influence = 0.7
    for field in ('distance', 'horizontal', 'vertical', 'offset', 'pan', 'tilt', 'roll', 'aim_influence'):
        p.keyframe_insert(data_path=field, frame=frame)
poses = {}
for frame in range(1, 21):
    bpy.context.scene.frame_set(frame)
    poses[frame] = camera.matrix_world.copy()
action = camera.animation_data.action
count = len(bpy.data.objects)
rig.upgrade_rig(bpy.context, camera)
assert camera.animation_data.action == action
assert len(bpy.data.objects) == count-8
assert p.rig_root is None and p.internal_graph is not None
for frame in range(1, 21):
    bpy.context.scene.frame_set(frame)
    assert matrix_close(poses[frame], camera.matrix_world, pos_tol=3e-5, rot_tol=3e-5), f'升级动画漂移：{frame}'
print('[PASS] 旧结构升级保留画面和 20 帧动画，移除 8 个辅助对象')

# 升级完成后停用，也应恢复原有锁定状态。
rig.remove_rig(bpy.context, camera)
assert not camera.lock_rotation_w

# 在生成新驱动器后模拟升级中断，旧层级及其关系必须仍然完整。
bpy.ops.object.camera_add()
legacy = bpy.context.object
legacy.cine.origin, legacy.cine.aim_target = origin, aim
legacy.cine.distance = 12
helpers = create_reference(legacy, origin, aim)
before = rig._snapshot(legacy)
objects_before = set(bpy.data.objects)
groups_before = set(bpy.data.node_groups)
install = rig._install_graph
def fail_install(camera):
    install(camera)
    raise RuntimeError('测试模拟升级中断')
rig._install_graph = fail_install
try:
    try:
        rig.upgrade_rig(bpy.context, legacy)
    except RuntimeError:
        pass
    else:
        raise AssertionError('模拟升级失败未发生')
finally:
    rig._install_graph = install
assert set(bpy.data.objects) == objects_before
assert set(bpy.data.node_groups) == groups_before
assert rig._snapshot(legacy) == before
assert legacy.cine.rig_root == helpers[0]
assert legacy.cine.enabled and legacy.cine.internal_graph is None
print('[PASS] 升级中断保留完整旧结构，正常停用恢复原锁定状态')
