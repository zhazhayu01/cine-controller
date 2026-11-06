"""独立进程保存/重开、禁用脚本自动执行、真实 RENDER 依赖图回归。

普通运行启动两个独立 Blender 进程；--stage 参数仅供测试子进程使用。
"""
from pathlib import Path
import json
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
import bpy
import CineController
from CineController.core import rig
from CineController.utils.math_utils import compose_orbit_matrix, matrix_close, quaternion_angle_difference
from mathutils import Matrix, Quaternion, Vector


def frames():
    return ((1, 0), (7, 0.5), (20, 0), (3, 0.25))


def expected_matrix(camera, depsgraph):
    p = camera.cine
    control = p.controller.evaluated_get(depsgraph) if p.controller else None
    if control and control.cine.dolly_enabled:
        settings = control.cine
        matrix = Quaternion(settings.dolly_base_rotation).to_matrix().to_4x4()
        matrix.translation = Vector(settings.dolly_base_position) + Vector(settings.dolly_forward)*settings.dolly_travel
        return control.matrix_world @ matrix
    pre = rig.compose_orbit_rotation(p.horizontal, p.vertical).to_quaternion() @ Quaternion(p.base_rotation)
    origin = p.origin.evaluated_get(depsgraph).matrix_world.translation if p.origin else Vector(p.origin_fallback)
    if p.origin and control:
        origin = control.matrix_world.inverted() @ origin
    position = compose_orbit_matrix(origin, p.distance, p.horizontal, p.vertical)
    position += pre @ Vector((p.offset.x, p.offset.y, -p.offset.z))
    if p.aim_target is not None:
        target = p.aim_target.evaluated_get(depsgraph).matrix_world.translation
        if control:
            target = control.matrix_world.inverted() @ target
        direction = target - position
        if direction.length > 1e-10:
            pre = pre.slerp(direction.to_track_quat('-Z', 'Y'), p.aim_influence)
    local = __import__('mathutils').Euler((p.tilt, p.pan, -p.roll), 'XYZ').to_quaternion()
    matrix = (pre @ local).to_matrix().to_4x4()
    matrix.translation = position
    return control.matrix_world @ matrix if control else matrix


def write(directory):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    CineController.register()
    curve_mode = '--curve' in sys.argv or '--dolly' in sys.argv
    control = None
    if curve_mode:
        bpy.context.scene.cursor.location = (2, 3, 1)
        bpy.ops.cine.create_camera()
        control = bpy.context.object
        camera = rig.resolve_camera(bpy.context)
    bpy.ops.object.empty_add()
    parent = bpy.context.object
    bpy.ops.object.empty_add(location=(1, 2, 3))
    origin = bpy.context.object
    origin.parent = parent
    bpy.ops.object.empty_add(location=(5, -3, 8))
    aim = bpy.context.object
    aim.parent = parent
    if not curve_mode:
        bpy.ops.object.camera_add()
        camera = bpy.context.object
        rig.build_rig(bpy.context, camera, origin)
    else:
        camera.cine.origin = origin
    camera.cine.aim_target = aim
    bpy.context.scene.camera = camera
    for frame in (1, 20):
        if control:
            control.location = (frame/3, -frame/5, 2)
            control.rotation_euler = (frame/100, -0.2, frame/20)
            control.keyframe_insert(data_path='location', frame=frame)
            control.keyframe_insert(data_path='rotation_euler', frame=frame)
        parent.location = (frame/5, frame/10, -frame/20)
        parent.keyframe_insert(data_path='location', frame=frame)
        p = camera.cine
        p.distance, p.horizontal, p.vertical = 10+frame/5, frame/5, frame/100
        p.offset = (1, -2, 3)
        p.pan, p.tilt, p.roll = (frame/50, -0.2, 0.3)
        p.aim_influence = 0.25 + frame/40
        for field in ('distance', 'horizontal', 'vertical', 'offset', 'pan', 'tilt', 'roll', 'aim_influence'):
            p.keyframe_insert(data_path=field, frame=frame)
    poses = []
    lenses = []
    if '--dolly' in sys.argv:
        bpy.context.scene.frame_set(1)
        bpy.ops.cine.toggle_dolly_zoom()
        for frame, travel in ((1, -1), (20, 1.5)):
            control.cine.dolly_travel = travel
            control.keyframe_insert(data_path='cine.dolly_travel', frame=frame)
    for frame, subframe in frames():
        bpy.context.scene.frame_set(frame, subframe=subframe)
        # 不调用 force_update：直接检查时间线首次求值，防止依赖链延迟一帧。
        expected = expected_matrix(camera, bpy.context.evaluated_depsgraph_get())
        assert matrix_close(expected, camera.matrix_world, pos_tol=3e-5, rot_tol=3e-5), (
            frame, subframe, (expected.translation-camera.matrix_world.translation).length,
            quaternion_angle_difference(expected.to_quaternion(), camera.matrix_world.to_quaternion()))
        poses.append([list(row) for row in camera.matrix_world])
        lenses.append(camera.data.lens)
        if '--dolly' in sys.argv:
            settings = control.cine
            target = settings.dolly_target.evaluated_get(bpy.context.evaluated_depsgraph_get()).matrix_world.translation
            forward = (expected.to_3x3() @ Vector((0, 0, -1))).normalized()
            depth = (target-expected.translation).dot(forward)
            reference_lens = max(1.0, settings.dolly_base_lens*max(depth, 1e-6)/settings.dolly_reference_depth)
            assert abs(camera.data.lens-reference_lens) < 1e-3
    (directory/'expected.json').write_text(json.dumps({'poses': poses, 'lenses': lenses}), encoding='utf-8')
    bpy.context.scene.render.resolution_x = 4
    bpy.context.scene.render.resolution_y = 4
    bpy.context.scene.render.resolution_percentage = 100
    bpy.ops.wm.save_as_mainfile(filepath=str(directory/'controller.blend'))
    print('[PASS] 参数动画和父级目标动画首次求值/子帧正确')


def read(directory):
    CineController.register()
    bpy.ops.wm.open_mainfile(filepath=str(directory/'controller.blend'))
    scene = bpy.context.scene
    camera = scene.camera
    saved = json.loads((directory/'expected.json').read_text(encoding='utf-8'))
    expected = saved['poses']
    rendered = []
    rendered_lenses = []

    class TestEngine(bpy.types.RenderEngine):
        bl_idname = 'CINE_TEST_ENGINE'
        bl_label = 'Cine 内部渲染依赖图测试'

        def render(self, depsgraph):
            assert depsgraph.mode == 'RENDER'
            rendered.append(depsgraph.scene_eval.camera.matrix_world.copy())
            rendered_lenses.append(depsgraph.scene_eval.camera.data.lens)
            result = self.begin_result(0, 0, 4, 4)
            result.layers[0].passes['Combined'].rect = [(0, 0, 0, 1)] * 16
            self.end_result(result)

    bpy.utils.register_class(TestEngine)
    scene.render.engine = TestEngine.bl_idname
    for index, (frame, subframe) in enumerate(frames()):
        scene.frame_set(frame, subframe=subframe)
        assert matrix_close(Matrix(expected[index]), camera.matrix_world, pos_tol=3e-5, rot_tol=3e-5)
        bpy.ops.render.render()
        assert len(rendered) == index+1, '实际渲染引擎没有执行'
        assert matrix_close(Matrix(expected[index]), rendered[-1], pos_tol=3e-5, rot_tol=3e-5)
        assert abs(camera.data.lens-saved['lenses'][index]) < 1e-3
        assert abs(rendered_lenses[-1]-saved['lenses'][index]) < 1e-3
    assert all(f.driver.is_valid and f.driver.is_simple_expression
               for owner in (camera, camera.cine.internal_graph) for f in owner.animation_data.drivers)
    assert len(bpy.data.objects) == (5 if '--curve' in sys.argv or '--dolly' in sys.argv else 4), '文件中只能有摄像机、控制曲线及用户目标'
    if camera.cine.controller:
        assert camera.parent == camera.cine.controller
        assert camera.cine.controller.cine_camera == camera
    print('[PASS] 独立进程重开、禁用脚本自动执行、4 次真实 RENDER 依赖图一致')


if '--stage' in sys.argv:
    index = sys.argv.index('--stage')
    stage, directory = sys.argv[index+1:index+3]
    (write if stage == 'write' else read)(Path(directory))
else:
    temporary_root = ROOT / 'tests' / '_tmp'
    temporary_root.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='cine-render-', dir=temporary_root) as directory:
        for mode in ([], ['--curve'], ['--dolly']):
            for stage in ('write', 'read'):
                result = subprocess.run([bpy.app.binary_path, '--factory-startup', '-b', '--disable-autoexec',
                                         '--python-exit-code', '1', '-P', __file__, '--', '--stage', stage, directory] + mode,
                                        capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=90)
                assert result.returncode == 0, result.stdout + result.stderr
                assert 'Dependency cycle' not in result.stdout + result.stderr, '检测到依赖循环'
                for line in result.stdout.splitlines():
                    if '[PASS]' in line:
                        label = '希区柯克模式：' if '--dolly' in mode else '曲线模式：' if mode else '普通模式：'
                        print('[PASS] ' + label + line.removeprefix('[PASS] '))
