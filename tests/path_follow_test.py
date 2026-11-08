"""原生路径绑定的真实求值、朝向、插帧、暂停恢复和保存回归。"""
from pathlib import Path
from math import pi
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import bpy
from mathutils import Vector
import CineController
from CineController.core import rig, path_follow
from CineController.utils.math_utils import matrix_close

bpy.ops.wm.read_factory_settings(use_empty=True)
CineController.register()
bpy.ops.cine.create_camera()
control = bpy.context.object
camera = control.cine_camera
curve = bpy.data.curves.new('轨迹数据', 'CURVE')
curve.dimensions = '3D'
spline = curve.splines.new('POLY')
spline.points.add(1)
spline.points[0].co = (0, 0, 0, 1)
spline.points[1].co = (0, 10, 0, 1)
path = bpy.data.objects.new('轨迹', curve)
bpy.context.collection.objects.link(path)
path.location = (2, 3, 4)
path.rotation_euler.z = pi/2
camera.cine.path_target = path
control.location = (4, -3, 2)
before_rotation = control.rotation_euler.copy()
assert bpy.ops.cine.bind_path() == {'FINISHED'}
constraint = path_follow.get_constraint(control)
assert constraint is not None and curve.use_path and constraint.use_fixed_location
assert not constraint.use_curve_follow
assert control.rotation_euler == before_rotation

def evaluate():
    rig.force_update(bpy.context, camera)
    depsgraph = bpy.context.evaluated_depsgraph_get()
    return control.evaluated_get(depsgraph).matrix_world.copy(), rig.read_evaluated_camera_matrix(bpy.context, camera)

for progress in (0, 0.25, 0.5, 0.75, 1):
    constraint.offset_factor = progress
    actual, cam = evaluate()
    expected = path.matrix_world @ Vector((0, 10*progress, 0))
    assert (actual.translation - expected).length < 2e-5, (progress, actual.translation, expected)
    assert (cam.translation - (actual @ Vector((0, -5, 0)))).length < 2e-5, '相机轨道相对控制器中心求值'
constraint.use_curve_follow = True
before, cam_before = evaluate()
forward = before.to_quaternion() @ Vector((0, 1, 0))
tangent = path.matrix_world.to_quaternion() @ Vector((0, 1, 0))
assert forward.dot(tangent) > 0.99999
print('[PASS] 控制器中心沿变换后的轨迹运动，进度 0 到 1、朝向跟随和相机相对距离正确')

constraint.offset_factor = 0.1
current, _camera_matrix = evaluate()
subject = bpy.data.objects.new('希区柯克主体', None)
bpy.context.collection.objects.link(subject)
subject.location = current.translation
control.cine.dolly_target = subject
bpy.ops.cine.toggle_dolly_zoom()
base_lens = camera.data.lens
constraint.offset_factor = 0.3
_current, dolly_camera = evaluate()
forward = dolly_camera.to_quaternion() @ Vector((0, 0, -1))
depth = (subject.location-dolly_camera.translation).dot(forward)
expected_lens = base_lens*depth/control.cine.dolly_reference_depth
assert abs(camera.data.lens-expected_lens) < 1e-3
bpy.ops.cine.toggle_dolly_zoom()
print('[PASS] 轨迹驱动控制器时，希区柯克焦距仍按实际主体深度联动')

for frame, progress in ((1, 0.1), (20, 0.9)):
    bpy.context.scene.frame_set(frame)
    constraint.offset_factor = progress
    assert bpy.ops.cine.keyframe_camera() == {'FINISHED'}
action_paths = {fc.data_path for fc in rig._action_curves(control.animation_data.action)}
assert constraint.path_from_id('offset_factor') in action_paths
assert not action_paths.intersection(rig.TRANSFORM_PATHS), '轨迹模式不应给控制器变换插帧'
bpy.context.scene.frame_set(10, subframe=0.5)
before, cam_before = evaluate()
assert bpy.ops.cine.toggle_path() == {'FINISHED'}
paused, cam_paused = evaluate()
assert constraint.mute and matrix_close(before, paused) and matrix_close(cam_before, cam_paused)
assert bpy.ops.cine.toggle_path() == {'FINISHED'}
after, cam_after = evaluate()
assert not constraint.mute and matrix_close(before, after) and matrix_close(cam_before, cam_after)
print('[PASS] 插帧记录原生路径进度，子帧暂停/恢复保留机位和朝向，不丢失动画')

name = camera.name
filepath = Path(__file__).parent/'_tmp'/'path_follow.blend'
filepath.parent.mkdir(exist_ok=True)
bpy.ops.wm.save_as_mainfile(filepath=str(filepath))
bpy.ops.wm.open_mainfile(filepath=str(filepath))
camera = bpy.data.objects[name]
control = camera.cine.controller
constraint = path_follow.get_constraint(control)
path = constraint.target
restored, cam_restored = evaluate()
assert matrix_close(before, restored) and matrix_close(cam_before, cam_restored)
print('[PASS] 保存重载后路径约束、进度动画、朝向和最终相机位姿一致')

# 路径变换与曲线动画由原生求值链处理，不依赖插件逐帧写回。
path.location.x += 2
moved, cam_moved = evaluate()
assert abs((moved.translation-restored.translation).x-2) < 1e-5
bpy.context.scene.frame_start, bpy.context.scene.frame_end = 1, 20
samples = {}
for frame in range(1, 21):
    bpy.context.scene.frame_set(frame)
    samples[frame] = evaluate()[1]
assert bpy.ops.cine.bake() == {'FINISHED'}
for frame, expected in samples.items():
    bpy.context.scene.frame_set(frame)
    assert matrix_close(rig.read_evaluated_camera_matrix(bpy.context, camera), expected, pos_tol=5e-5, rot_tol=5e-5)
print('[PASS] 路径物体移动实时更新，路径运镜逐帧烘焙保留最终位姿')

# 新镜头用于冲突与循环保护检查。
bpy.ops.cine.create_camera()
control = bpy.context.object
camera = control.cine_camera
path.parent = control
try:
    path_follow.bind(bpy.context, camera, path)
    raise AssertionError('不能绑定依赖自身的轨迹')
except ValueError as error:
    assert '依赖' in str(error)
assert not control.constraints
path.parent = None
control.keyframe_insert(data_path='location', frame=1)
try:
    path_follow.bind(bpy.context, camera, path)
    raise AssertionError('不能覆盖原控制器动画')
except ValueError as error:
    assert '动画' in str(error)
assert not control.constraints
control.animation_data_clear()
path_follow.bind(bpy.context, camera, path)
bpy.data.objects.remove(path, do_unlink=True)
evaluate()
path_follow.unbind(bpy.context, camera)
replacement_data = bpy.data.curves.new('替换轨迹数据', 'CURVE')
replacement_data.dimensions = '3D'
replacement_spline = replacement_data.splines.new('BEZIER')
replacement_spline.bezier_points.add(1)
for point, co in zip(replacement_spline.bezier_points, ((0, 0, 0), (3, 5, 2))):
    point.co = co
    point.handle_left_type = point.handle_right_type = 'AUTO'
replacement = bpy.data.objects.new('替换轨迹', replacement_data)
bpy.context.collection.objects.link(replacement)
constraint = path_follow.bind(bpy.context, camera, replacement)
assert constraint.target == replacement and not constraint.mute and len(control.constraints) == 1
constraint.offset_factor = 1
last, _camera = evaluate()
assert (last.translation-Vector((3, 5, 2))).length < 2e-5
print('[PASS] 拒绝自身依赖及变换动画冲突，轨迹删除后仍可安全暂停')
print('[PASS] 轨迹删除后可重新绑定贝塞尔曲线，不累加约束')
CineController.unregister()
