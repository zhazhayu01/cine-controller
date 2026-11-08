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
from CineController.core import rig, path_follow, shake
from CineController.utils.math_utils import compose_orbit_matrix, matrix_close, quaternion_angle_difference
from mathutils import Matrix, Quaternion, Vector


def frames():
    return ((1, 0), (7, 0.5), (20, 0), (3, 0.25))


def expected_base_matrix(camera, depsgraph):
    p = camera.cine
    control = p.controller.evaluated_get(depsgraph) if p.controller else None
    if control and control.cine.dolly_enabled:
        settings = control.cine
        matrix = Quaternion(settings.dolly_base_rotation).to_matrix().to_4x4()
        travel = settings.dolly_travel + settings.dolly_base_distance-settings.dolly_distance
        matrix.translation = Vector(settings.dolly_base_position) + Vector(settings.dolly_forward)*travel
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


def expected_matrix(camera, depsgraph):
    from math import cos, tau
    from mathutils import Euler
    matrix = expected_base_matrix(camera, depsgraph)
    if not camera.cine.shake_enabled:
        return matrix
    scene = depsgraph.scene_eval
    frame = scene.frame_current+scene.frame_subframe
    values = [0.0]*6
    for event in camera.cine.shake_events:
        u = (frame-event.start)/event.duration
        if not event.enabled or not 0 <= u < 1:
            continue
        if event.kind == 'IMPACT':
            envelope = (1-u)**event.decay
        else:
            a, r = min(1, u/0.15), min(1, (1-u)/0.15)
            envelope = a*a*(3-2*a)*r*r*(3-2*r)
        time = (frame-event.start)/(scene.render.fps/scene.render.fps_base)
        for axis, amplitude in enumerate((*event.position, *event.rotation)):
            wave = 0.72*cos(tau*event.frequency*time+axis*0.7)+0.28*cos(tau*1.79*event.frequency*time+event.seed*1.618+axis*1.3)
            values[axis] += wave*envelope*event.strength*amplitude*camera.cine.shake_strength
    offset = Euler((values[3], values[4], -values[5]), 'XYZ').to_matrix().to_4x4()
    offset.translation = Vector((values[0], values[1], -values[2]))
    return matrix @ offset


def write(directory):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    CineController.register()
    path_mode = '--path' in sys.argv
    curve_mode = '--curve' in sys.argv or '--dolly' in sys.argv or '--shake' in sys.argv or path_mode
    control = None
    if curve_mode:
        bpy.context.scene.cursor.location = (2, 3, 1)
        bpy.ops.cine.create_camera()
        control = bpy.context.object
        camera = rig.resolve_camera(bpy.context)
    path_constraint = None
    if path_mode:
        data = bpy.data.curves.new('轨迹数据', 'CURVE')
        data.dimensions = '3D'
        spline = data.splines.new('POLY')
        spline.points.add(1)
        spline.points[0].co = (0, 0, 0, 1)
        spline.points[1].co = (0, 10, 4, 1)
        path = bpy.data.objects.new('轨迹', data)
        bpy.context.collection.objects.link(path)
        path_constraint = path_follow.bind(bpy.context, camera, path)
        path_constraint.use_curve_follow = True
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
        if path_constraint:
            path_constraint.offset_factor = (frame-1)/19
            control.keyframe_insert(data_path=path_constraint.path_from_id('offset_factor'), frame=frame)
        elif control:
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
        if '--bounds' in sys.argv:
            rig.force_update(bpy.context, camera)
            matrix = camera.matrix_world.copy()
            anchor = matrix.translation + (matrix.to_quaternion() @ Vector((0, 0, -1)))*20
            bpy.ops.mesh.primitive_cube_add(size=2, location=anchor)
            control.cine.dolly_target = bpy.context.object
        bpy.ops.cine.toggle_dolly_zoom()
        for frame, travel in ((1, -1), (20, 1.5)):
            control.cine.dolly_travel = travel
            control.keyframe_insert(data_path='cine.dolly_travel', frame=frame)
            control.cine.dolly_distance = control.cine.dolly_base_distance + (0.5 if frame == 1 else -0.5)
            control.keyframe_insert(data_path='cine.dolly_distance', frame=frame)
    if '--shake' in sys.argv:
        first = shake.add_event(bpy.context, camera)
        first.start, first.duration, first.frequency = 1, 25, 6
        second = shake.add_event(bpy.context, camera)
        second.start, second.duration, second.frequency, second.kind = 7, 8, 11, 'CONTINUOUS'
        shake.enable(bpy.context, camera)
    for frame, subframe in frames():
        bpy.context.scene.frame_set(frame, subframe=subframe)
        # 不调用 force_update：直接检查时间线首次求值，防止依赖链延迟一帧。
        expected = expected_matrix(camera, bpy.context.evaluated_depsgraph_get())
        if path_constraint:
            progress = path_constraint.offset_factor
            assert (control.matrix_world.translation-Vector((0, 10*progress, 4*progress))).length < 2e-5
        assert matrix_close(expected, camera.matrix_world, pos_tol=3e-5, rot_tol=3e-5), (
            frame, subframe, (expected.translation-camera.matrix_world.translation).length,
            quaternion_angle_difference(expected.to_quaternion(), camera.matrix_world.to_quaternion()))
        poses.append([list(row) for row in camera.matrix_world])
        lenses.append(camera.data.lens)
        if '--dolly' in sys.argv:
            settings = control.cine
            target = settings.dolly_target.evaluated_get(bpy.context.evaluated_depsgraph_get()).matrix_world.translation
            optical_matrix = expected_base_matrix(camera, bpy.context.evaluated_depsgraph_get())
            forward = (optical_matrix.to_3x3() @ Vector((0, 0, -1))).normalized()
            depth = (target-optical_matrix.translation).dot(forward)
            reference_lens = max(1.0, settings.dolly_base_lens*max(depth, 1e-6)/settings.dolly_reference_depth)
            if settings.dolly_use_bounds:
                subject = settings.dolly_target.evaluated_get(bpy.context.evaluated_depsgraph_get())
                view = optical_matrix.normalized().inverted()
                corners = [view @ (subject.matrix_world @ Vector(corner)) for corner in subject.bound_box]
                projected = [corner[settings.dolly_span_axis]/max(-corner.z, 1e-6) for corner in corners]
                reference_lens = max(1, settings.dolly_base_lens*settings.dolly_reference_span/max(max(projected)-min(projected), 1e-9))
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
    assert len(bpy.data.objects) == (6 if '--path' in sys.argv or '--bounds' in sys.argv else 5 if '--curve' in sys.argv or '--dolly' in sys.argv or '--shake' in sys.argv else 4), '文件中只能有摄像机、控制曲线、轨迹及用户目标'
    if camera.cine.shake_graph:
        assert all(f.driver.is_valid and f.driver.is_simple_expression for f in camera.cine.shake_graph.animation_data.drivers)
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
        for mode in ([], ['--curve'], ['--dolly'], ['--dolly', '--bounds'], ['--path'], ['--shake'], ['--dolly', '--shake']):
            for stage in ('write', 'read'):
                result = subprocess.run([bpy.app.binary_path, '--factory-startup', '-b', '--disable-autoexec',
                                         '--python-exit-code', '1', '-P', __file__, '--', '--stage', stage, directory] + mode,
                                        capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=90)
                assert result.returncode == 0, result.stdout + result.stderr
                assert 'Dependency cycle' not in result.stdout + result.stderr, '检测到依赖循环'
                for line in result.stdout.splitlines():
                    if '[PASS]' in line:
                        label = ('震动与希区柯克：' if '--shake' in mode and '--dolly' in mode else '程序化震动：' if '--shake' in mode else
                                 '实体希区柯克模式：' if '--bounds' in mode else '样条轨迹模式：' if '--path' in mode else '希区柯克模式：' if '--dolly' in mode else '曲线模式：' if mode else '普通模式：')
                        print('[PASS] ' + label + line.removeprefix('[PASS] '))
