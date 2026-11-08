"""多事件震动的绝对时间、叠加、独立层和生命周期回归。"""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import bpy
import CineController
from CineController.core import rig, shake, dolly_zoom
from CineController.utils.math_utils import matrix_close

bpy.ops.wm.read_factory_settings(use_empty=True)
CineController.register()
bpy.ops.cine.create_camera()
control = bpy.context.object
camera = control.cine_camera
scene = bpy.context.scene
base = rig.read_evaluated_camera_matrix(bpy.context, camera)
params_before = (camera.cine.distance, camera.cine.horizontal, camera.cine.vertical, camera.cine.pan, camera.cine.tilt)
first = shake.add_event(bpy.context, camera)
first.start, first.duration = 30, 12
first.rotation = (0, 0, 0)
shake.enable(bpy.context, camera)
assert not rig.needs_independent_graph(camera), '自身震动图不能误判为共享副本'

def at(frame):
    scene.frame_set(int(frame), subframe=frame-int(frame))
    rig.force_update(bpy.context, camera)
    return rig.read_evaluated_camera_matrix(bpy.context, camera)

assert matrix_close(at(29), base)
one = at(30.5)
assert (one.translation-base.translation).length > 1e-4
assert matrix_close(at(42), base)
assert matrix_close(at(30.5), one)
second = shake.add_event(bpy.context, camera, first)
second.start = 48
assert matrix_close(at(30.5), one)
assert not matrix_close(at(48.5), base)
second.start = first.start
both = at(30.5)
assert ((both.translation-base.translation)-2*(one.translation-base.translation)).length < 1e-5
second.enabled = False
assert matrix_close(at(30.5), one)
camera.cine.shake_strength = 0
assert matrix_close(at(30.5), base)
camera.cine.shake_strength = 1
assert params_before == (camera.cine.distance, camera.cine.horizontal, camera.cine.vertical, camera.cine.pan, camera.cine.tilt)
print('[PASS] 两次独立冲击互不覆盖，重叠线性叠加，总强度归零恢复基础机位，重复子帧结果一致')

first.kind = 'CONTINUOUS'
first.start, first.duration = 60, 20
assert matrix_close(at(60), base)
assert not matrix_close(at(70), base)
assert matrix_close(at(80), base)
first.start, first.duration = 10, 24
scene.render.fps = 24
low_fps = at(16)
scene.render.fps = 48
first.duration = 48
assert matrix_close(at(22), low_fps, pos_tol=2e-5)
scene.render.fps = 24
first.start, first.duration, first.kind = 1, 24, 'IMPACT'
first.rotation = (0.01, 0.005, 0.002)
at(3.25)
unshaken = shake.base_world_matrix(bpy.context, camera)
assert matrix_close(unshaken, base)
assert not matrix_close(camera.matrix_world, base)
assert all(f.driver.is_valid and f.driver.is_simple_expression for f in camera.cine.shake_graph.animation_data.drivers), [
    (f.data_path, f.driver.is_valid, f.driver.expression) for f in camera.cine.shake_graph.animation_data.drivers
    if not f.driver.is_valid or not f.driver.is_simple_expression]
print('[PASS] 持续模式首尾平滑，频率按真实秒换算，旋转与位移均由有效原生简单驱动求值')

# 希区柯克捕获和焦距计算使用基础机位，震动不引起焦距呼吸或二次叠加。
subject = bpy.data.objects.new('主体', None)
scene.collection.objects.link(subject)
control.cine.dolly_target = subject
lens = camera.data.lens
dolly_zoom.enable(bpy.context, camera)
assert abs(camera.data.lens-lens) < 1e-4
assert matrix_close(shake.base_world_matrix(bpy.context, camera), base)
assert not matrix_close(camera.matrix_world, base)
dolly_zoom.disable(bpy.context, camera)
assert matrix_close(shake.base_world_matrix(bpy.context, camera), base)
print('[PASS] 希区柯克启停不捕获震动偏移，焦距不跟随震动呼吸')

# 复制完整镜头后，各自的震动参数和内部图独立。
copy_control = control.copy()
copy_control.data = control.data.copy()
scene.collection.objects.link(copy_control)
copy_camera = camera.copy()
copy_camera.data = camera.data.copy()
scene.collection.objects.link(copy_camera)
copy_camera.parent = copy_control
copy_camera.cine.controller = copy_control
copy_control.cine_camera = copy_camera
before = camera.matrix_world.copy()
rig.make_independent(bpy.context, copy_camera)
assert copy_camera.cine.shake_graph != camera.cine.shake_graph
copy_camera.cine.shake_strength = 0
rig.force_update(bpy.context, copy_camera)
assert matrix_close(before, camera.matrix_world)
assert matrix_close(copy_camera.matrix_world, base)
print('[PASS] 完整镜头副本的震动图独立，修改副本不影响原镜头')

name = camera.name
expected = at(7.5)
file = Path(__file__).parent/'_tmp'/'shake.blend'
file.parent.mkdir(exist_ok=True)
bpy.ops.wm.save_as_mainfile(filepath=str(file))
bpy.ops.wm.open_mainfile(filepath=str(file))
scene = bpy.context.scene
camera = bpy.data.objects[name]
assert matrix_close(at(7.5), expected)
assert len(camera.cine.shake_events) == 2
shake.disable(bpy.context, camera)
assert camera.cine.shake_graph is None and matrix_close(at(7.5), base)
shake.enable(bpy.context, camera)
assert matrix_close(at(7.5), expected)
print('[PASS] 保存重载及启停不丢失事件，停用恢复基础运镜')

scene.frame_start, scene.frame_end = 1, 10
samples = {frame: at(frame) for frame in range(1, 11)}
with bpy.context.temp_override(active_object=camera, object=camera):
    bpy.ops.cine.bake()
assert camera.cine.shake_graph is None and not camera.cine.shake_enabled
for frame, matrix in samples.items():
    scene.frame_set(frame)
    assert matrix_close(rig.read_evaluated_camera_matrix(bpy.context, camera), matrix, pos_tol=4e-5, rot_tol=4e-5)
print('[PASS] 震动与运镜一起烘焙，最终位姿逐帧一致并清理震动数据块')

bpy.ops.cine.create_camera()
camera = rig.resolve_camera(bpy.context)
shake.add_event(bpy.context, camera)
before = rig.read_evaluated_camera_matrix(bpy.context, camera)
groups = set(bpy.data.node_groups)
original_add = rig._add_driver
failed = [False]
def fail_output(cam, owner, path, index, *args, **kwargs):
    if owner == camera and path == 'delta_rotation_quaternion' and kwargs.get('storage') == camera.cine.shake_graph and not failed[0]:
        failed[0] = True
        raise RuntimeError('模拟末端震动输出安装失败')
    return original_add(cam, owner, path, index, *args, **kwargs)
try:
    rig._add_driver = fail_output
    try:
        shake.enable(bpy.context, camera)
        raise AssertionError('应触发安装失败')
    except RuntimeError:
        pass
finally:
    rig._add_driver = original_add
assert failed[0] and not camera.cine.shake_enabled and camera.cine.shake_graph is None
assert set(bpy.data.node_groups) == groups
assert matrix_close(rig.read_evaluated_camera_matrix(bpy.context, camera), before)
print('[PASS] 部分输出安装失败时恢复基础驱动，不留下孤立震动数据块')
CineController.unregister()
