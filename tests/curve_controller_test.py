"""一键创建曲线控制器和摄像机，验证选择解析、空间跟随和烘焙。"""
from pathlib import Path
import sys
from math import pi

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import bpy
import CineController
from CineController.core import rig
from CineController.utils.math_utils import matrix_close
from mathutils import Vector, Euler

bpy.ops.wm.read_factory_settings(use_empty=True)
CineController.register()
scene = bpy.context.scene
scene.cursor.location = (2, 3, 1.5)
assert bpy.ops.cine.create_camera() == {'FINISHED'}
control = bpy.context.object
camera = rig.resolve_camera(bpy.context)
assert control.type == 'CURVE' and camera.type == 'CAMERA'
assert len(bpy.data.objects) == 2
assert camera.parent == control and camera.cine.controller == control
assert control.cine_camera == camera and scene.camera == camera
assert control.hide_render and control.show_in_front
assert any(spline.use_cyclic_u for spline in control.data.splines)
mesh = control.evaluated_get(bpy.context.evaluated_depsgraph_get()).to_mesh()
assert len(mesh.edges) > 0, '曲线必须有可显示的线段'
control.evaluated_get(bpy.context.evaluated_depsgraph_get()).to_mesh_clear()
assert all(camera.lock_location) and all(camera.lock_rotation)
assert camera.location.length < 1e-5

def close(actual, expected):
    assert (Vector(actual)-Vector(expected)).length < 2e-5, (tuple(actual), tuple(expected))

close(camera.matrix_world.translation, (2, -2, 1.5))
control.location = (4, -2, 3)
control.rotation_euler = (0.2, -0.3, pi/2)
rig.force_update(bpy.context, camera)
close(camera.matrix_world.translation, control.matrix_world @ Vector((0, -5, 0)))
close(camera.matrix_world.to_quaternion() @ Vector((0, 0, -1)),
      control.matrix_world.to_quaternion() @ Vector((0, 1, 0)))
print('[PASS] 创建两个对象：可见曲线控制器＋已绑定相机，移动旋转直接跟随')

# 外部瞄准目标必须转换到控制器空间，不能把世界坐标直接当本地坐标。
bpy.ops.object.empty_add(location=(7, 8, 9))
target = bpy.context.object
camera.cine.aim_target = target
camera.cine.aim_influence = 1
rig.force_update(bpy.context, camera)
close(camera.matrix_world.to_quaternion() @ Vector((0, 0, -1)),
      (target.matrix_world.translation-camera.matrix_world.translation).normalized())
print('[PASS] 控制器旋转后，外部瞄准目标仍正确对准')

# 指定世界空间的 Origin 时也不能重复叠加控制器的平移和旋转。
bpy.ops.object.empty_add(location=(-2, 4, 1))
origin = bpy.context.object
bpy.context.view_layer.update()
before = camera.matrix_world.copy()
camera.cine.origin = origin
rig.force_update(bpy.context, camera)
assert matrix_close(before, camera.matrix_world, pos_tol=2e-5, rot_tol=2e-5)
print('[PASS] 曲线控制器空间与外部 Origin 切换保持画面，不重复叠加变换')

control.name = '测试控制器改名'
camera.name = '测试相机改名'
bpy.context.view_layer.objects.active = control
assert rig.resolve_camera(bpy.context) == camera
assert bpy.ops.cine.bake.poll()
scene.frame_start, scene.frame_end = 1, 3
for frame in (1, 3):
    control.location = (frame, -2, 3)
    control.keyframe_insert(data_path='location', frame=frame)
poses = {}
for frame in (1, 2, 3):
    scene.frame_set(frame)
    poses[frame] = camera.matrix_world.copy()
assert bpy.ops.cine.bake() == {'FINISHED'}
assert camera.parent is None and not camera.cine.enabled
for frame in (1, 2, 3):
    scene.frame_set(frame)
    assert max(abs(poses[frame][i][j]-camera.matrix_world[i][j]) for i in range(4) for j in range(4)) < 2e-5
print('[PASS] 选择曲线即可操作对应相机，改名不失效，烘焙后脱离曲线并保持动画')

# 重复创建必须生成独立的一对，不抢占已有渲染摄像机。
first_render_camera = scene.camera
scene.cursor.location = (0, 0, 0)
assert bpy.ops.cine.create_camera() == {'FINISHED'}
second_control = bpy.context.object
second_camera = rig.resolve_camera(bpy.context)
assert second_control != control and second_camera != camera
assert second_camera.cine.internal_graph is not camera.cine.internal_graph
assert scene.camera == first_render_camera
print('[PASS] 连续创建独立镜头，不覆盖已有渲染摄像机')

# 故障注入验证只清理新创建的数据，并恢复用户的当前选择。
objects_before = set(bpy.data.objects)
curves_before = set(bpy.data.curves)
cameras_before = set(bpy.data.cameras)
graphs_before = set(bpy.data.node_groups)
install = rig._install_graph
def fail_install(camera):
    install(camera)
    raise RuntimeError('模拟创建中断')
rig._install_graph = fail_install
try:
    try:
        result = bpy.ops.cine.create_camera()
    except RuntimeError:
        result = {'CANCELLED'}
    assert result == {'CANCELLED'}
finally:
    rig._install_graph = install
assert set(bpy.data.objects) == objects_before
assert set(bpy.data.curves) == curves_before and set(bpy.data.cameras) == cameras_before
assert set(bpy.data.node_groups) == graphs_before
assert bpy.context.object == second_control and scene.cine_camera == second_camera
assert scene.camera == first_render_camera
print('[PASS] 一键创建中途失败时回滚对象、数据块及选择，不影响原有镜头')
