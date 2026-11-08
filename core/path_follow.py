"""控制器路径绑定：使用原生路径约束，不创建辅助物体或逐帧回调。"""
from . import rig

NAME = '.Cine_Path'
OWNER = '_cine_path_owned'
PAUSED = '_cine_path_paused_transform'


def _restore_paused_transform(control):
    state = control.get(PAUSED)
    if state is not None:
        control.rotation_mode = state['rotation_mode']
        for field in rig.TRANSFORM_PATHS:
            setattr(control, field, state[field])


def get_constraint(control):
    if control is None or not control.get(OWNER, False):
        return None
    constraint = control.constraints.get(NAME)
    return constraint if constraint and constraint.type == 'FOLLOW_PATH' else None


def _has_transform_animation(control):
    animation = control.animation_data
    if not animation:
        return False
    curves = list(animation.drivers) + list(rig._action_curves(animation.action))
    for track in animation.nla_tracks:
        for strip in track.strips:
            curves.extend(rig._action_curves(strip.action))
    return any(curve.data_path in rig.TRANSFORM_PATHS for curve in curves)


def _depends_on_control(path, camera, control):
    """检查路径父级、约束与对象驱动依赖，避免路径反过来依赖当前镜头。"""
    pending, visited = [path], set()
    while pending:
        obj = pending.pop()
        if obj in (camera, control):
            return True
        if obj in visited:
            continue
        visited.add(obj)
        if obj.parent is not None:
            pending.append(obj.parent)
        for constraint in obj.constraints:
            target = getattr(constraint, 'target', None)
            if target is not None and not constraint.mute and constraint.influence:
                pending.append(target)
        if obj.animation_data:
            for curve in obj.animation_data.drivers:
                for variable in curve.driver.variables:
                    for target in variable.targets:
                        if getattr(target.id, 'constraints', None) is not None:
                            pending.append(target.id)
    return False


def bind(context, camera, path):
    control = camera.cine.controller
    if not camera.cine.enabled or control is None or camera.parent != control or control.cine_camera != camera:
        raise ValueError('轨迹绑定需要已启用且一对一绑定的曲线控制器')
    if path is None or path.type != 'CURVE' or path == control:
        raise ValueError('请选择另一条曲线作为轨迹')
    if len(path.data.splines) != 1:
        raise ValueError('轨迹曲线必须只包含一条样条，请先分离多条样条')
    spline = path.data.splines[0]
    if len(spline.bezier_points if spline.type == 'BEZIER' else spline.points) < 2:
        raise ValueError('轨迹至少需要两个控制点')
    if _depends_on_control(path, camera, control):
        raise ValueError('轨迹不能依赖当前控制器或摄像机，避免循环依赖')
    if control.library is not None or path.data.library is not None:
        raise ValueError('请先将控制器和轨迹数据设为本地数据或创建库覆盖')
    existing = get_constraint(control)
    if control.constraints and not (existing and len(control.constraints) == 1
                                    and (existing.mute or existing.target is None)):
        raise ValueError('控制器已有约束，请先解除已有约束再绑定轨迹')
    if _has_transform_animation(control):
        raise ValueError('控制器已有变换动画或驱动，请先整理这些通道；轨迹绑定后改用路径进度插帧')
    before = rig._snapshot(control)
    old_use_path = path.data.use_path
    previous = {key: getattr(existing, key) for key in
                ('target', 'mute', 'use_fixed_location', 'use_curve_follow', 'use_curve_radius',
                 'forward_axis', 'up_axis', 'offset_factor')} if existing else None
    constraint = None
    try:
        _restore_paused_transform(control)
        path.data.use_path = True
        constraint = existing or control.constraints.new('FOLLOW_PATH')
        constraint.name = NAME
        constraint.target = path
        constraint.use_fixed_location = True
        constraint.use_curve_follow = False
        constraint.use_curve_radius = False
        constraint.forward_axis = 'FORWARD_Y'
        constraint.up_axis = 'UP_Z'
        if existing is None:
            constraint.offset_factor = 0
        constraint.mute = False
        # 路径约束会叠加原位置；清除平移后控制器中心才落在样条上。
        control.location = (0, 0, 0)
        control.delta_location = (0, 0, 0)
        control[OWNER] = True
        rig.force_update(context, camera)
        if not constraint.is_valid:
            raise ValueError('路径约束无效，请检查轨迹曲线')
    except Exception:
        if existing is not None:
            for key, value in previous.items():
                setattr(existing, key, value)
        elif constraint is not None:
            control.constraints.remove(constraint)
        if existing is None and OWNER in control:
            del control[OWNER]
        path.data.use_path = old_use_path
        rig._restore_snapshot(control, before)
        rig.force_update(context, camera)
        raise
    if PAUSED in control:
        del control[PAUSED]
    return constraint


def unbind(context, camera):
    """暂停轨迹，保持当前帧控制器位姿；保留约束和路径动画。"""
    control = camera.cine.controller
    constraint = get_constraint(control)
    if constraint is None:
        raise ValueError('当前控制器没有插件创建的轨迹约束')
    if _has_transform_animation(control) or len(control.constraints) != 1:
        raise ValueError('控制器另有变换动画或约束，请先整理后解除轨迹，或直接烘焙相机')
    rig.force_update(context, camera)
    matrix = control.evaluated_get(context.evaluated_depsgraph_get()).matrix_world.copy()
    control[PAUSED] = {field: list(getattr(control, field)) for field in rig.TRANSFORM_PATHS}
    control[PAUSED]['rotation_mode'] = control.rotation_mode
    # 保留进度关键帧，约束留存并静音，之后可恢复绑定而不丢失轨迹动画。
    constraint.mute = True
    control.delta_location = (0, 0, 0)
    control.delta_rotation_euler = (0, 0, 0)
    control.delta_rotation_quaternion = (1, 0, 0, 0)
    control.delta_scale = (1, 1, 1)
    control.matrix_world = matrix
    rig.force_update(context, camera)


def resume(context, camera):
    control = camera.cine.controller
    constraint = get_constraint(control)
    if constraint is None or constraint.target is None:
        raise ValueError('原轨迹已被删除，请在轨迹选择框中指定新曲线并重新绑定')
    if _has_transform_animation(control) or len(control.constraints) != 1:
        raise ValueError('控制器另有变换动画或约束，请先整理后恢复轨迹')
    if _depends_on_control(constraint.target, camera, control):
        raise ValueError('轨迹不能依赖当前控制器或摄像机，避免循环依赖')
    _restore_paused_transform(control)
    control.location = (0, 0, 0)
    control.delta_location = (0, 0, 0)
    constraint.mute = False
    rig.force_update(context, camera)
    if PAUSED in control:
        del control[PAUSED]
