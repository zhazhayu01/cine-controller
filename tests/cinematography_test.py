"""控制器镜头关键帧、焦距、构图及希区柯克投影/烘焙回归。"""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import bpy
import CineController
from CineController.core import rig
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector

bpy.ops.wm.read_factory_settings(use_empty=True)
CineController.register()
bpy.ops.cine.create_camera()
control = bpy.context.object
camera = rig.resolve_camera(bpy.context)
scene = bpy.context.scene
camera.data.lens = 35
assert bpy.ops.cine.keyframe_camera() == {'FINISHED'}
assert camera.animation_data.action is not None
assert control.animation_data.action is not None
assert any(f.data_path == 'lens' for f in rig._action_curves(camera.data.animation_data.action))
assert not any(f.data_path in rig.TRANSFORM_PATHS for f in rig._action_curves(camera.animation_data.action))
assert bpy.context.object == control
print('[PASS] 选中曲线一键记录控制器变换、相机空间参数及焦距，保留选择')

# 原生焦距动画在启停联动之后仍应保留。
camera.data.lens = 70
camera.data.keyframe_insert(data_path='lens', frame=10)
scene.frame_set(1)
for field in ('show_composition_thirds', 'show_composition_center', 'show_composition_golden', 'show_safe_areas'):
    setattr(camera.data, field, True)
camera.data.shift_x, camera.data.shift_y = 0.1, -0.1
assert bpy.ops.cine.reset_lens_shift() == {'FINISHED'}
assert camera.data.shift_x == camera.data.shift_y == 0
print('[PASS] 构图参考线使用原生相机设置，镜头偏移可独立归零')

def image_height():
    a = world_to_camera_view(scene, camera, Vector((0, 0, -0.5)))
    b = world_to_camera_view(scene, camera, Vector((0, 0, 0.5)))
    return abs(b.y-a.y)

initial_height = image_height()
initial_action = camera.data.animation_data.action
assert bpy.ops.cine.toggle_dolly_zoom() == {'FINISHED'}
assert control.cine.dolly_enabled
assert not bpy.ops.cine.disable_controller.poll()
objects = set(bpy.data.objects)
for travel, lens in ((2, 21), (-2, 49), (0, 35)):
    control.cine.dolly_travel = travel
    rig.force_update(bpy.context, camera)
    assert abs(camera.data.lens-lens) < 1e-4, (camera.data.lens, lens)
    assert abs(image_height()-initial_height) < 2e-5
assert set(bpy.data.objects) == objects
control.location.y = 1
rig.force_update(bpy.context, camera)
assert abs(camera.data.lens-28) < 1e-4
assert abs(image_height()-initial_height) < 2e-5
control.location.y = 0
rig.force_update(bpy.context, camera)
assert all(f.driver.is_valid and f.driver.is_simple_expression for f in control.cine.dolly_graph.animation_data.drivers)
assert camera.data.animation_data.action == initial_action
print('[PASS] 希区柯克推拉自动联动焦距，主体投影大小保持，不新增场景对象或覆盖原 Lens 动画')

# 复制完整控制器和相机时，独立化不能改动原镜头的光学联动。
copy_control = control.copy()
copy_control.data = control.data.copy()
scene.collection.objects.link(copy_control)
copy_camera = camera.copy()
copy_camera.data = camera.data.copy()
scene.collection.objects.link(copy_camera)
copy_camera.parent = copy_control
copy_camera.cine.controller = copy_control
copy_control.cine_camera = copy_camera
rig.make_independent(bpy.context, copy_camera)
copy_control.cine.dolly_travel = 2
rig.force_update(bpy.context, copy_camera)
assert abs(copy_camera.data.lens-21) < 1e-4
assert abs(camera.data.lens-35) < 1e-4
rig.remove_rig(bpy.context, copy_camera)
assert control.cine.dolly_enabled and control.cine.dolly_graph is not None
print('[PASS] 完整镜头副本的空间和光学数据独立，停用副本不影响原镜头')

assert bpy.ops.cine.toggle_dolly_zoom() == {'FINISHED'}
assert not control.cine.dolly_enabled and control.cine.dolly_graph is None
assert not camera.data.animation_data.drivers
assert camera.data.animation_data.action == initial_action
assert abs(camera.data.lens-35) < 1e-4
scene.frame_set(10)
assert abs(camera.data.lens-70) < 1e-4
scene.frame_set(1)

scene.frame_start, scene.frame_end = 1, 3
assert bpy.ops.cine.toggle_dolly_zoom() == {'FINISHED'}
for frame, travel in ((1, -1), (3, 2)):
    scene.frame_set(frame)
    control.cine.dolly_travel = travel
    assert bpy.ops.cine.keyframe_camera() == {'FINISHED'}
poses, lenses = {}, {}
for frame in range(1, 4):
    scene.frame_set(frame)
    poses[frame] = camera.matrix_world.copy()
    lenses[frame] = camera.data.lens
assert bpy.ops.cine.bake() == {'FINISHED'}
assert camera.parent is None and not camera.cine.enabled
assert not control.cine.dolly_enabled and control.cine.dolly_graph is None
assert not camera.data.animation_data.drivers
for frame in range(1, 4):
    scene.frame_set(frame)
    assert max(abs(poses[frame][i][j]-camera.matrix_world[i][j]) for i in range(4) for j in range(4)) < 2e-5
    assert abs(lenses[frame]-camera.data.lens) < 1e-4
print('[PASS] 希区柯克动画烘焙保留位置、旋转与每帧焦距，并清理联动驱动器')

from CineController.core import dolly_zoom
bpy.ops.cine.create_camera()
protected = rig.resolve_camera(bpy.context)
graphs_before = set(bpy.data.node_groups)
driver = protected.data.driver_add('lens')
driver.driver.expression = '60'
try:
    dolly_zoom.enable(bpy.context, protected)
except ValueError:
    pass
else:
    raise AssertionError('不能覆盖外部焦距驱动器')
assert protected.data.animation_data.drivers[0] == driver
assert driver.driver.expression == '60'
assert set(bpy.data.node_groups) == graphs_before
protected.data.driver_remove('lens')
rig.force_update(bpy.context, protected)

# 最后写入 Lens 驱动时模拟异常，必须恢复普通运动链并清理光学数据块。
before = protected.matrix_world.copy()
add_driver = rig._add_driver
def fail_lens(camera, owner, path, *args, **kwargs):
    if owner == protected.data and path == 'lens':
        raise RuntimeError('模拟光学驱动创建中断')
    return add_driver(camera, owner, path, *args, **kwargs)
rig._add_driver = fail_lens
try:
    try:
        dolly_zoom.enable(bpy.context, protected)
    except RuntimeError:
        pass
    else:
        raise AssertionError('模拟失败未发生')
finally:
    rig._add_driver = add_driver
assert not dolly_zoom.is_enabled(protected)
assert protected.cine.controller.cine.dolly_graph is None
assert set(bpy.data.node_groups) == graphs_before
assert max(abs(before[i][j]-protected.matrix_world[i][j]) for i in range(4) for j in range(4)) < 2e-5
print('[PASS] 保护外部 Lens 驱动器，光学创建中断时清理数据并恢复普通运镜')
