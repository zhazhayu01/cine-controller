"""摄像机内部控制器：原生驱动器求值、绑定、解绑和旧版升级。

不创建 Empty/Collection，不注册驱动命名空间或逐帧写回处理器。
基础变换固定为单位变换，空间计算通过增量位置/四元数输出。
"""
import bpy
from mathutils import Matrix, Vector, Quaternion

from .driver_graph import PREFIX, build_graph
from ..utils.math_utils import solve_orbit_from_pose
from ..utils.axis_utils import default_camera_rotation

LEGACY_HELPERS = ('rig_root', 'rig_yaw', 'rig_pitch', 'rig_dist', 'rig_base',
                  'rig_offset', 'rig_aim', 'rig_local_rot')
TRANSFORM_PATHS = {'location', 'rotation_euler', 'rotation_quaternion',
                   'rotation_axis_angle', 'scale', 'delta_location',
                   'delta_rotation_euler', 'delta_rotation_quaternion', 'delta_scale'}
STATE_KEY = PREFIX + 'restore'


def resolve_camera(context):
    """面板与操作共用目标：选中摄像机 → 上次控制的摄像机 → 渲染摄像机。"""
    obj = getattr(context, 'active_object', None)
    if obj is not None and obj.type == 'CAMERA':
        return obj
    if obj is not None and obj.type == 'CURVE' and obj.cine_camera is not None:
        camera = obj.cine_camera
        if camera.cine.controller == obj:
            return camera
    scene = getattr(context, 'scene', None)
    return (scene.cine_camera or scene.camera) if scene is not None else None


def read_evaluated_camera_matrix(context, camera_obj):
    return camera_obj.evaluated_get(context.evaluated_depsgraph_get()).matrix_world.copy()


def force_update(context, camera_obj):
    """仅供脚本强制求值；播放、渲染与目标动画由 Blender 依赖图驱动。"""
    camera_obj.update_tag()
    if camera_obj.cine.controller is not None:
        camera_obj.cine.controller.update_tag()
    context.view_layer.update()
    context.evaluated_depsgraph_get().update()


def compose_orbit_rotation(horizontal, vertical):
    return Matrix.Rotation(horizontal, 4, 'Z') @ Matrix.Rotation(vertical, 4, 'X')


def _action_curves(action):
    """兼容旧 Action 与 Blender 4.4+ 分层 Action。"""
    if action is None:
        return
    yield from getattr(action, 'fcurves', ())
    for layer in getattr(action, 'layers', ()):
        for strip in layer.strips:
            for bag in getattr(strip, 'channelbags', ()):
                yield from bag.fcurves


def _check_camera(camera):
    """先验证再写入，不覆盖外部变换驱动器、关键帧和约束。"""
    if camera.library is not None:
        raise ValueError('请先将链接摄像机设为本地对象或创建库覆盖')
    controller = camera.cine.controller
    if controller is not None and (controller.type != 'CURVE' or controller in camera.children_recursive):
        raise ValueError('控制对象必须是摄像机子级之外的曲线')
    if any(c.influence != 0 and not c.mute for c in camera.constraints):
        raise ValueError('摄像机存在外部变换约束，请先烘焙或停用这些约束')
    animation = camera.animation_data
    if animation:
        for driver in animation.drivers:
            if driver.data_path in TRANSFORM_PATHS:
                raise ValueError('摄像机已有变换驱动器，请先移除或烘焙后再启用')
        actions = [animation.action]
        for track in animation.nla_tracks:
            for strip in track.strips:
                actions.append(strip.action)
        for action in actions:
            if any(curve.data_path in TRANSFORM_PATHS for curve in _action_curves(action)):
                raise ValueError('摄像机已有位置/旋转动画，请先复制摄像机或整理动画后再启用')
    if any(key.startswith(PREFIX) for key in camera.keys()):
        raise ValueError('摄像机存在内部控制器数据，请先停用或升级已有控制器')
    for target in (camera.cine.origin, camera.cine.aim_target):
        if target is not None and (target == camera or target in camera.children_recursive):
            raise ValueError('空间原点或瞄准目标不能使用摄像机自身或其子级，避免循环依赖')


def _snapshot(camera):
    attrs = TRANSFORM_PATHS | {'matrix_parent_inverse', 'lock_location', 'lock_rotation',
                              'lock_scale', 'lock_rotations_4d', 'lock_rotation_w'}
    state = {}
    for attr in attrs:
        value = getattr(camera, attr)
        state[attr] = value.copy() if hasattr(value, 'copy') else tuple(value) if hasattr(value, '__len__') else value
    state['parent'] = camera.parent
    state['rotation_mode'] = camera.rotation_mode
    return state


def _reset_camera(camera):
    camera.parent = None
    camera.matrix_parent_inverse = Matrix.Identity(4)
    camera.rotation_mode = 'QUATERNION'
    camera.location = (0, 0, 0)
    camera.rotation_euler = (0, 0, 0)
    camera.rotation_quaternion = (1, 0, 0, 0)
    camera.rotation_axis_angle = (0, 0, 1, 0)
    camera.scale = (1, 1, 1)
    camera.delta_location = (0, 0, 0)
    camera.delta_rotation_euler = (0, 0, 0)
    camera.delta_rotation_quaternion = (1, 0, 0, 0)
    camera.delta_scale = (1, 1, 1)


def _restore_snapshot(camera, state):
    # 切换旋转模式会转换当前旋转，必须先恢复模式，再恢复各通道数值。
    camera.rotation_mode = state['rotation_mode']
    camera.parent = state['parent']
    for key, value in state.items():
        if key not in {'rotation_mode', 'parent'}:
            setattr(camera, key, value)


def _add_driver(camera, owner, path, index, expression, bindings, source_object=None, storage=None):
    curve = owner.driver_add(path) if index is None else owner.driver_add(path, index)
    _clear_driver_mapping(curve)
    driver = curve.driver
    driver.type = 'SCRIPTED'
    for variable in list(driver.variables):
        driver.variables.remove(variable)
    driver.expression = expression
    for name, (source_path, fallback) in bindings.items():
        var = driver.variables.new()
        var.name = name
        var.type = 'SINGLE_PROP'
        target = var.targets[0]
        _set_driver_target(camera, target, source_path, source_object=source_object, storage=storage)
        target.use_fallback_value = True
        target.fallback_value = fallback


def _clear_driver_mapping(curve):
    """原样输出表达式；默认 Bezier 映射会将接近端点的矩阵分量吸附为 0/1。"""
    curve.keyframe_points.clear()
    for modifier in list(curve.modifiers):
        curve.modifiers.remove(modifier)


def _set_driver_target(camera, target, source_path, source_object=None, storage=None):
    # 通过摄像机指针路径解析目标，删除目标时仍有有效 ID，fallback 才能生效。
    internal = source_path.startswith(f'["{PREFIX}')
    target.id_type = 'NODETREE' if internal else 'OBJECT'
    target.id = (storage or camera.cine.internal_graph) if internal else (source_object or camera)
    target.data_path = source_path


def _retarget_inputs(camera):
    if camera.cine.internal_graph is None:
        return
    for key, _expression, bindings in build_graph(controller_space=camera.cine.controller is not None).nodes:
        curve = camera.cine.internal_graph.animation_data.drivers.find(f'["{key}"]')
        for variable in curve.driver.variables:
            path = bindings[variable.name][0]
            if '.matrix_world' in path:
                _set_driver_target(camera, variable.targets[0], path)


def _install_graph(camera):
    graph = build_graph(controller_space=camera.cine.controller is not None)
    # 使用独立数据块隔离 Object.PARAMETERS 与中间驱动结果；它不是场景对象。
    storage = bpy.data.node_groups.new('.CineController.' + camera.name, 'ShaderNodeTree')
    camera.cine.internal_graph = storage
    for key, _expression, _bindings in graph.nodes:
        storage[key] = 0.0
    for key, expression, bindings in graph.nodes:
        _add_driver(camera, storage, f'["{key}"]', None, expression, bindings)
    for path, index, expression, bindings in graph.outputs:
        _add_driver(camera, camera, path, index, expression, bindings)


def needs_independent_graph(camera):
    """Blender 原生复制会共享任意数据块指针，显式识别摄像机副本。"""
    storage = camera.cine.internal_graph
    if storage is None:
        return False
    curve = storage.animation_data.drivers.find('["_cine2_orb0"]')
    from . import dolly_zoom
    return storage.users > 1 or any(v.targets[0].id != camera for v in curve.driver.variables) or dolly_zoom.needs_independent(camera)


def make_independent(context, camera):
    """复制内部计算数据并重新绑定输入，保持副本参数与原摄像机独立。"""
    if not needs_independent_graph(camera):
        return
    old = camera.cine.internal_graph
    new = old.copy()
    new.name = '.CineController.' + camera.name
    camera.cine.internal_graph = new
    for curve in new.animation_data.drivers:
        for variable in curve.driver.variables:
            target = variable.targets[0]
            if target.id == old:
                target.id = new
            elif target.id_type == 'OBJECT' and target.data_path.startswith('cine.'):
                target.id = camera
    for curve in camera.animation_data.drivers:
        for variable in curve.driver.variables:
            if variable.targets[0].id == old:
                variable.targets[0].id = new
    _retarget_inputs(camera)
    from . import dolly_zoom
    dolly_zoom.ensure_owned(camera)
    force_update(context, camera)


def _clear_graph(camera):
    """只移除本控制器拥有的通道；外部自定义属性与光学动画保持不变。"""
    animation = camera.animation_data
    if animation:
        for curve in list(animation.drivers):
            if curve.data_path in {'location', 'rotation_quaternion', 'scale',
                                   'delta_location', 'delta_rotation_quaternion'}:
                camera.driver_remove(curve.data_path, curve.array_index)
    storage = camera.cine.internal_graph
    camera.cine.internal_graph = None
    if storage is not None and storage.users == 0:
        bpy.data.node_groups.remove(storage)


def build_rig(context, camera_obj, origin_obj=None):
    """清零基础变换并建立内部控制器，失败时恢复修改前数据。"""
    if camera_obj.cine.enabled:
        raise ValueError('此摄像机已启用控制器')
    if origin_obj == camera_obj:
        raise ValueError('摄像机不能将自身作为空间原点')
    _check_camera(camera_obj)
    before = read_evaluated_camera_matrix(context, camera_obj)
    original = _snapshot(camera_obj)
    params = camera_obj.cine
    saved_params = {key: getattr(params, key) for key in ('distance', 'horizontal', 'vertical', 'pan', 'tilt', 'roll', 'rig_version')}
    for key in ('offset', 'base_rotation', 'origin_fallback'):
        saved_params[key] = tuple(getattr(params, key))
    saved_origin = params.origin
    saved_panel_camera = context.scene.cine_camera
    try:
        _reset_camera(camera_obj)
        controller = params.controller
        if controller is not None:
            camera_obj.parent = controller
        context.view_layer.update()
        params.origin = origin_obj
        origin = _origin_in_control_space(camera_obj, origin_obj)
        params.origin_fallback = origin
        # 基础通道归零，控制空间以 Origin 为零点；不再从世界零点反解出补偿环绕角。
        params.distance = params.horizontal = params.vertical = 0.0
        params.base_rotation = default_camera_rotation()
        params.offset = (0, 0, 0)
        params.pan = params.tilt = params.roll = 0.0
        camera_obj[STATE_KEY] = {
            'rotation_mode': original['rotation_mode'],
            'lock_location': list(original['lock_location']),
            'lock_rotation': list(original['lock_rotation']),
            'lock_scale': list(original['lock_scale']),
            'lock_rotations_4d': original['lock_rotations_4d'],
            'lock_rotation_w': original['lock_rotation_w'],
        }
        _install_graph(camera_obj)
        camera_obj.lock_location = camera_obj.lock_rotation = camera_obj.lock_scale = (True, True, True)
        camera_obj.lock_rotations_4d = camera_obj.lock_rotation_w = True
        params.rig_version = 2
        params.enabled = True
        context.scene.cine_camera = camera_obj
        force_update(context, camera_obj)
        after = read_evaluated_camera_matrix(context, camera_obj)
        expected = default_camera_rotation().to_matrix().to_4x4()
        expected.translation = origin
        # 预设 Aim 仍按用户的瞄准设置控制朝向。
        if params.aim_target is not None and params.aim_influence > 0:
            expected = after.copy()
            expected.translation = controller.matrix_world @ origin if controller else origin
        elif controller is not None:
            expected = controller.matrix_world @ expected
        return {'before': before, 'expected': expected, 'after': after,
                'params': (params.distance, params.horizontal, params.vertical)}
    except Exception:
        _clear_graph(camera_obj)
        if STATE_KEY in camera_obj:
            del camera_obj[STATE_KEY]
        params.enabled = False
        _restore_snapshot(camera_obj, original)
        for key, value in saved_params.items():
            setattr(params, key, value)
        params.origin = saved_origin
        context.scene.cine_camera = saved_panel_camera
        force_update(context, camera_obj)
        raise


def _origin_in_control_space(camera, origin):
    if origin is None:
        return Vector((0, 0, 0))
    position = origin.matrix_world.translation
    controller = camera.cine.controller
    return controller.matrix_world.inverted_safe() @ position if controller else position


def reset_space_axes(context, camera):
    """旧镜头显式恢复水平拍摄基准，保留 Distance、Origin、Aim 与光学参数。"""
    from . import dolly_zoom
    if dolly_zoom.is_enabled(camera):
        raise ValueError('请先停用希区柯克工具，再重置普通空间轴向')
    fields = ('horizontal', 'vertical', 'offset', 'pan', 'tilt', 'roll', 'base_rotation')
    paths = {'cine.' + field for field in fields}
    animation = camera.animation_data
    if animation is not None:
        curves = list(animation.drivers) + list(_action_curves(animation.action))
        for track in animation.nla_tracks:
            for strip in track.strips:
                curves.extend(_action_curves(strip.action))
        if any(curve.data_path in paths for curve in curves):
            raise ValueError('环绕、偏移或旋转参数已有动画/驱动，请先整理这些通道再重置轴向')
    make_independent(context, camera)
    # 修复 0.2.0 已保存驱动器的默认映射，仅处理本控制器拥有的通道。
    owned_paths = {'location', 'rotation_quaternion', 'scale', 'delta_location', 'delta_rotation_quaternion'}
    for curve in camera.animation_data.drivers:
        if curve.data_path in owned_paths:
            _clear_driver_mapping(curve)
    for curve in camera.cine.internal_graph.animation_data.drivers:
        _clear_driver_mapping(curve)
    params = camera.cine
    params.horizontal = params.vertical = params.pan = params.tilt = params.roll = 0.0
    params.offset = (0, 0, 0)
    params.base_rotation = default_camera_rotation()
    force_update(context, camera)


def import_camera_position(context, camera, source):
    """从参考相机当前帧的最终位置反推轨道参数，不改变参考相机。"""
    from . import dolly_zoom
    params = camera.cine
    if not params.enabled or params.rig_root is not None or params.internal_graph is None:
        raise ValueError('请先启用或升级当前镜头的内部控制器')
    if source is None or source == camera or source.type != 'CAMERA':
        raise ValueError('请选择另一台摄像机作为位置参考')
    if dolly_zoom.is_enabled(camera):
        raise ValueError('请先停用希区柯克工具，再导入普通机位')
    fields = ('distance', 'horizontal', 'vertical', 'offset')
    paths = {'cine.' + field for field in fields}
    animation = camera.animation_data
    if animation is not None:
        curves = list(animation.drivers) + list(_action_curves(animation.action))
        for track in animation.nla_tracks:
            for strip in track.strips:
                curves.extend(_action_curves(strip.action))
        if any(curve.data_path in paths for curve in curves):
            raise ValueError('距离、环绕或偏移已有动画/驱动，请先整理这些通道再导入机位')
    context.view_layer.update()
    depsgraph = context.evaluated_depsgraph_get()
    world_position = source.evaluated_get(depsgraph).matrix_world.translation.copy()
    controller = params.controller
    inverse = Matrix.Identity(4)
    if controller is not None:
        matrix = controller.evaluated_get(depsgraph).matrix_world
        if abs(matrix.to_3x3().determinant()) <= 1e-12:
            raise ValueError('控制器缩放为零或接近零，无法反推相对位置')
        inverse = matrix.inverted()
    position = inverse @ world_position
    origin = (inverse @ params.origin.evaluated_get(depsgraph).matrix_world.translation
              if params.origin is not None else Vector(params.origin_fallback))
    values = solve_orbit_from_pose(origin, position)
    make_independent(context, camera)
    saved = (params.distance, params.horizontal, params.vertical, tuple(params.offset))
    try:
        params.distance, params.horizontal, params.vertical = values
        params.offset = (0, 0, 0)
        force_update(context, camera)
        actual = read_evaluated_camera_matrix(context, camera).translation
        if (actual - world_position).length > 1e-4 * max(1, (world_position - inverse.inverted().translation).length):
            raise ValueError('反推位置与参考相机不一致，已恢复原参数')
    except Exception:
        params.distance, params.horizontal, params.vertical, params.offset = saved
        force_update(context, camera)
        raise
    return values


def _apply_origin(context, camera_obj, new_origin):
    """重设原点时保持当前画面，不把旧 Offset 叠加两次。"""
    params = camera_obj.cine
    if params.rig_root is not None:
        return  # 旧版结构通过显式升级入口迁移。
    if new_origin == camera_obj:
        return
    # 目标指针已改变，使用旧参数重建旧的几何基准。
    pre = compose_orbit_rotation(params.horizontal, params.vertical).to_quaternion() @ Quaternion(params.base_rotation)
    position = camera_obj.matrix_world.translation
    if params.controller is not None:
        position = params.controller.matrix_world.inverted_safe() @ position
    position -= pre @ Vector((params.offset.x, params.offset.y, -params.offset.z))
    origin = _origin_in_control_space(camera_obj, new_origin) if new_origin else Vector(params.origin_fallback)
    params.origin_fallback = origin
    params.distance, params.horizontal, params.vertical = solve_orbit_from_pose(origin, position)
    params.base_rotation = compose_orbit_rotation(params.horizontal, params.vertical).to_quaternion().inverted() @ pre
    _retarget_inputs(camera_obj)
    camera_obj.update_tag()


def _apply_aim(context, camera_obj):
    """所有瞄准参数均有显式驱动依赖，无须重建约束或写回变换。"""
    if camera_obj.cine.rig_root is None:
        _retarget_inputs(camera_obj)
    camera_obj.update_tag()


def _delete_legacy_helpers(params):
    for attr in LEGACY_HELPERS:
        helper = getattr(params, attr)
        setattr(params, attr, None)
        if helper is not None:
            bpy.data.objects.remove(helper, do_unlink=True)
    collection = bpy.data.collections.get('Cine Rig')
    if collection and not collection.objects and not collection.children:
        bpy.data.collections.remove(collection)


def remove_rig(context, camera_obj):
    """停用后保留最终世界画面，恢复基础通道可编辑性。"""
    make_independent(context, camera_obj)
    before = read_evaluated_camera_matrix(context, camera_obj)
    from . import dolly_zoom
    if dolly_zoom.is_enabled(camera_obj):
        dolly_zoom.disable(context, camera_obj, preserve_lens=True)
    params = camera_obj.cine
    legacy = params.rig_root is not None
    params.enabled = False
    restore = dict(camera_obj.get(STATE_KEY, {}))
    if not legacy:
        _clear_graph(camera_obj)
    _reset_camera(camera_obj)
    if legacy:
        _delete_legacy_helpers(params)
    for key, value in restore.items():
        setattr(camera_obj, key, value)
    if STATE_KEY in camera_obj:
        del camera_obj[STATE_KEY]
    camera_obj.matrix_world = before
    force_update(context, camera_obj)
    return {'before': before, 'after': read_evaluated_camera_matrix(context, camera_obj)}


def upgrade_rig(context, camera):
    """显式迁移旧 Helper 结构；沿用控制参数、动画和基准朝向。"""
    params = camera.cine
    if params.rig_root is None:
        raise ValueError('此摄像机没有需要升级的旧版控制器')
    before = read_evaluated_camera_matrix(context, camera)
    base = params.rig_base.rotation_quaternion.copy()
    root_position = params.rig_root.matrix_world.translation.copy()
    original = _snapshot(camera)
    old_base, old_origin = tuple(params.base_rotation), tuple(params.origin_fallback)
    _check_camera(camera)
    try:
        _reset_camera(camera)
        params.base_rotation = base
        params.origin_fallback = root_position
        camera[STATE_KEY] = {key: list(original[key]) for key in ('lock_location', 'lock_rotation', 'lock_scale')}
        camera[STATE_KEY]['rotation_mode'] = original['rotation_mode']
        camera[STATE_KEY]['lock_rotations_4d'] = original['lock_rotations_4d']
        camera[STATE_KEY]['lock_rotation_w'] = original['lock_rotation_w']
        _install_graph(camera)
        camera.lock_location = camera.lock_rotation = camera.lock_scale = (True, True, True)
        camera.lock_rotations_4d = camera.lock_rotation_w = True
        force_update(context, camera)
        after = read_evaluated_camera_matrix(context, camera)
        from ..utils.math_utils import matrix_close
        if not matrix_close(before, after, pos_tol=3e-5, rot_tol=3e-5):
            raise ValueError('新旧控制器计算结果不一致，已取消升级')
    except Exception:
        _clear_graph(camera)
        if STATE_KEY in camera:
            del camera[STATE_KEY]
        _restore_snapshot(camera, original)
        params.base_rotation, params.origin_fallback = old_base, old_origin
        force_update(context, camera)
        raise
    _delete_legacy_helpers(params)
    params.rig_version = 2
    context.scene.cine_camera = camera
    return {'before': before, 'after': after}
