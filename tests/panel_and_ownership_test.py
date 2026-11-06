"""常驻面板、未选中摄像机时操作、复制独立化及绑定失败保护。"""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import bpy
import CineController
from CineController.core import rig
from CineController.ui.panel import CINE_PT_panel

bpy.ops.wm.read_factory_settings(use_empty=True)
CineController.register()
assert CINE_PT_panel.poll(bpy.context), '空场景中面板也必须存在'
bpy.ops.object.camera_add()
camera = bpy.context.object
assert bpy.ops.cine.enable_controller() == {'FINISHED'}
camera.cine.distance = 10
rig.force_update(bpy.context, camera)
bpy.ops.mesh.primitive_cube_add()
assert CINE_PT_panel.poll(bpy.context)
assert rig.resolve_camera(bpy.context) == camera
assert bpy.ops.cine.disable_controller.poll()
assert bpy.ops.cine.bake.poll()
assert bpy.ops.cine.disable_controller() == {'FINISHED'}
assert not camera.cine.enabled
assert bpy.ops.cine.enable_controller() == {'FINISHED'}
print('[PASS] 空场景/选中非摄像机时面板常驻，并能启用/停用备用摄像机')

camera.cine.distance = 10
rig.force_update(bpy.context, camera)
copy = camera.copy()
copy.data = camera.data.copy()
bpy.context.scene.collection.objects.link(copy)
assert rig.needs_independent_graph(copy)
rig.make_independent(bpy.context, copy)
assert not rig.needs_independent_graph(copy)
assert copy.cine.internal_graph != camera.cine.internal_graph
copy.cine.distance = 20
rig.force_update(bpy.context, copy)
assert abs(copy.matrix_world.translation.length-20) < 1e-5
assert abs(camera.matrix_world.translation.length-10) < 1e-5
rig.remove_rig(bpy.context, copy)
assert camera.cine.internal_graph is not None
assert all(curve.driver.is_valid for curve in camera.cine.internal_graph.animation_data.drivers)
print('[PASS] 摄像机副本独立计算，删除副本控制器不影响原镜头')

bpy.ops.object.camera_add(location=(3, 4, 5))
animated = bpy.context.object
animated.keyframe_insert(data_path='location', frame=1)
objects_before = set(bpy.data.objects)
groups_before = set(bpy.data.node_groups)
try:
    rig.build_rig(bpy.context, animated)
except ValueError:
    pass
else:
    raise AssertionError('不能覆盖已有的摄像机变换动画')
assert set(bpy.data.objects) == objects_before and set(bpy.data.node_groups) == groups_before
assert tuple(animated.location) == (3, 4, 5)
print('[PASS] 外部变换动画冲突时不覆盖原数据，不留下半成品')

# 在真正建立计算数据块后模拟失败，检查事务回滚，而不只测试前置拒绝。
bpy.ops.object.camera_add(location=(7, -2, 4))
broken = bpy.context.object
broken.rotation_euler = (0.2, 0.3, 0.4)
broken.lock_location = (True, False, True)
bpy.context.view_layer.update()
before = rig._snapshot(broken)
groups_before = set(bpy.data.node_groups)
install = rig._install_graph
def fail_install(camera):
    install(camera)
    raise RuntimeError('测试模拟绑定中断')
rig._install_graph = fail_install
try:
    try:
        rig.build_rig(bpy.context, broken)
    except RuntimeError:
        pass
    else:
        raise AssertionError('模拟失败未发生')
finally:
    rig._install_graph = install
assert rig._snapshot(broken) == before
assert set(bpy.data.node_groups) == groups_before
assert not broken.cine.enabled and broken.cine.internal_graph is None
assert not broken.animation_data.drivers
print('[PASS] 绑定中途失败时恢复变换、锁定、参数及内部数据块')
