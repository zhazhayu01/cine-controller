"""供 MCP 和脚本使用的 JSON 接口，复用插件逻辑，不依赖活动选择。"""
import json
import math
from contextlib import contextmanager

import bpy

from .core import rig, dolly_zoom, path_follow, shake

API_VERSION = 1
# 字段：所属数据、RNA 名称、输入类型、中文含义。
FIELDS = {
    'shake_strength': ('params', 'shake_strength', 'number', '全部震动事件叠加后的总强度；0 表示没有震动'),
    'distance': ('params', 'distance', 'number', '普通模式为轨道半径；希区柯克模式为联动距离，减小推进、增大后退；场景单位'),
    'horizontal_deg': ('params', 'horizontal', 'angle', '水平环绕，度'),
    'vertical_deg': ('params', 'vertical', 'angle', '垂直环绕，度；负值升高'),
    'pan_deg': ('params', 'pan', 'angle', '水平摇摄，度'),
    'tilt_deg': ('params', 'tilt', 'angle', '俯仰，度'),
    'roll_deg': ('params', 'roll', 'angle', '翻滚，度'),
    'offset': ('params', 'offset', 'vector', '镜头空间偏移：右、上、前；场景单位'),
    'origin': ('params', 'origin', 'object', '空间原点对象名；null 使用已保存中心'),
    'lens_mm': ('data', 'lens', 'number', '透视焦距，毫米'),
    'ortho_scale': ('data', 'ortho_scale', 'number', '正交相机画幅范围'),
    'sensor_width_mm': ('data', 'sensor_width', 'number', '传感器宽度，毫米'),
    'shift_x': ('data', 'shift_x', 'number', '水平构图偏移'),
    'shift_y': ('data', 'shift_y', 'number', '垂直构图偏移'),
    'clip_start': ('data', 'clip_start', 'number', '近裁剪，场景单位'),
    'clip_end': ('data', 'clip_end', 'number', '远裁剪，场景单位'),
    'thirds': ('data', 'show_composition_thirds', 'bool', '三分构图线'),
    'center': ('data', 'show_composition_center', 'bool', '中心构图线'),
    'safe_areas': ('data', 'show_safe_areas', 'bool', '安全框'),
    'passepartout': ('data', 'show_passepartout', 'bool', '画幅外遮罩'),
    'dof_enabled': ('dof', 'use_dof', 'bool', '景深开关'),
    'focus_object': ('dof', 'focus_object', 'object', '对焦目标对象名，或 null'),
    'focus_distance': ('dof', 'focus_distance', 'number', '手动对焦距离，场景单位'),
    'fstop': ('dof', 'aperture_fstop', 'number', '光圈 F 值'),
    'path_progress': ('path', 'offset_factor', 'number', '路径进度，0 到 1'),
    'path_follow': ('path', 'use_curve_follow', 'bool', '控制器是否沿轨迹切线转向'),
    'dolly_travel': ('control_params', 'dolly_travel', 'number', '希区柯克镜头轴推拉，场景单位'),
}
ACTIONS = {
    'enable_shake': '启用程序化震动层；没有事件时在当前帧添加一次冲击，可重复调用',
    'disable_shake': '停用震动并恢复基础运镜，保留所有事件，可重复调用',
    'shake_event': 'operation 为 add/update/duplicate/remove；现有事件用 event_id 指定，values 设置事件参数',
    'describe': '读取接口版本、参数、操作及控制规则，无须指定镜头',
    'list': '列出当前场景的摄像机和控制器，不修改场景',
    'get': '读取指定摄像机或控制器对应镜头的参数及最终世界位姿',
    'create': '创建已绑定曲线控制器的新镜头，可传 name；使用当前游标和插件预设',
    'set': '批量写入 values；只接受 describe 列出的参数，角度使用度',
    'move_control': '用 location 和 rotation_deg 设置控制器本地位置与 XYZ 旋转；不用于已绑定轨迹的控制器',
    'import_pose': '从 source 指定的参考相机完整反推位置与朝向，不复制光学参数',
    'bind_path': '将控制器绑定到 target 指定的单样条曲线，进度 0 到 1',
    'pause_path': '暂停轨迹并保留当前帧机位，可重复调用',
    'resume_path': '恢复轨迹和原进度动画，可重复调用',
    'enable_dolly': '启用希区柯克变焦，可指定 target 主体；重复调用不会反向关闭',
    'disable_dolly': '关闭希区柯克并返回原运镜，可重复调用',
    'keyframe': '在当前帧或 frame 指定的帧记录镜头参数、控制器或路径进度',
    'bake': '将场景帧范围的最终位姿烘焙成普通相机动画；希区柯克启用时同时烘焙焦距',
    'render_camera': '把指定镜头设为场景渲染摄像机',
    'make_independent': '独立化镜头副本的内部计算数据',
}
RULES = [
    '先 describe、list、get，再操作；每次明确传 camera 对象名或曲线控制器名。',
    '不要直接修改受控相机的位置、旋转、增量变换或内部驱动器；通过接口控制。',
    '角度字段后缀 _deg，单位是度；距离是 Blender 场景单位，unit_scale_length 表示米制换算比例。',
    '控制器负责整体空间变换；距离、环绕和偏移是相对控制器及空间原点的参数。',
    '目标镜头无须被选中；编辑模式下请先由用户完成编辑，再执行写入操作。',
    'set 不自动插帧；先设 frame，再 set，再 keyframe；同一帧的 get 用于验证结果。',
    '希区柯克启用时可改 distance、dolly_travel 或路径进度；距离减小推进，焦距自动补偿，其他普通运镜及焦距不可直接覆盖。',
    '完整反推清零偏移和瞄准权重；主面板不再提供瞄准设置。',
    '最终位姿匹配不等于画面相同；还需确认焦距、传感器、构图和渲染画面。',
    'ok=false 表示失败，读取 error；不要绕过保护修改内部数据。',
]
CLIENT_INSTRUCTIONS = '''使用 Blender MCP 操作镜头时，优先使用 Cine Controller 自动化接口。
先通过 execute_blender_code 执行以下 Python，读取插件规则和镜头清单：
import bpy
bpy.ops.cine.automation(request_json='{"action":"describe"}')
bpy.ops.cine.automation(request_json='{"action":"list"}')

之后通过同一 JSON 入口执行操作，每次明确传 camera（摄像机或曲线控制器名称）。
不要直接改受控相机的基础变换、增量变换或驱动器。角度用度，距离用场景单位。
动画按“先切帧、再设值、再插帧”执行。检查输出 JSON 的 ok，失败先读 error。
操作后读取 get 返回的最终位姿，再通过 MCP 观察工具核对画面。
插件未启用时请提示安装 Cine Controller 1.0.0，不绕过插件保护。
'''


def describe():
    from . import bl_info
    return {'api_version': API_VERSION, 'plugin_version': list(bl_info['version']),
            'actions': ACTIONS, 'fields': {key: {'type': spec[2], 'description': spec[3]}
                                         for key, spec in FIELDS.items()}, 'rules': RULES,
            'shake_event_fields': {'label': '名称', 'enabled': '布尔开关', 'kind': 'IMPACT 或 CONTINUOUS',
                'start': '开始帧', 'duration': '持续帧数', 'strength': '强度', 'frequency': '频率，Hz',
                'decay': '衰减，至少 1', 'seed': '整数种子', 'position': '右／上／前位移向量，场景单位',
                'rotation_deg': '俯仰／摇摄／翻滚向量，度'},
            'examples': [
                {'action': 'create', 'name': '产品主镜头'},
                {'action': 'set', 'camera': '产品主镜头', 'frame': 1,
                 'values': {'distance': 6, 'pan_deg': 15, 'lens_mm': 50}},
                {'action': 'keyframe', 'camera': '产品主镜头'},
                {'action': 'import_pose', 'camera': '产品主镜头', 'source': '自由相机'},
                {'action': 'bind_path', 'camera': '产品主镜头', 'target': '轨迹'},
                {'action': 'enable_dolly', 'camera': '产品主镜头', 'target': '产品'},
            ]}


def _object(name, kind=None):
    if not isinstance(name, str) or not name:
        raise ValueError('对象名称必须是非空字符串')
    obj = bpy.context.scene.objects.get(name)
    if obj is None or (kind and obj.type != kind):
        raise ValueError(f'当前场景中找不到所需对象：{name}')
    return obj


def _camera(name):
    obj = _object(name)
    if obj.type == 'CURVE' and obj.cine_camera and obj.cine_camera.cine.controller == obj:
        obj = obj.cine_camera
    if obj.type != 'CAMERA':
        raise ValueError('camera 必须指定摄像机或其曲线控制器名称')
    return obj


@contextmanager
def _context(camera=None):
    """给现有操作提供明确上下文，不改变真实活动对象和选择。"""
    overrides = {}
    window = bpy.context.window
    if window:
        area = next((a for a in window.screen.areas if a.type == 'VIEW_3D'), None)
        if area:
            overrides.update(window=window, area=area,
                             region=next(r for r in area.regions if r.type == 'WINDOW'))
    if camera:
        overrides.update(active_object=camera, object=camera,
                         selected_objects=[camera], selected_editable_objects=[camera])
    with bpy.context.temp_override(**overrides):
        yield


def _invoke(operator, camera=None):
    with _context(camera):
        result = operator()
    if result != {'FINISHED'}:
        raise ValueError('插件操作未完成')


def _owner(camera, group):
    control = camera.cine.controller
    owners = {'params': camera.cine, 'data': camera.data, 'dof': camera.data.dof,
              'path': path_follow.get_constraint(control), 'control_params': control.cine if control else None}
    return owners[group]


def _field(camera, key):
    group, path, _kind, _description = FIELDS[key]
    if key == 'distance' and dolly_zoom.is_enabled(camera) and dolly_zoom.has_distance_control(camera):
        return camera.cine.controller.cine, 'dolly_distance'
    return _owner(camera, group), path


def _read(owner, path, kind):
    value = getattr(owner, path)
    if kind == 'object':
        return value.name if value else None
    if kind == 'vector':
        return list(value)
    return math.degrees(value) if kind == 'angle' else value


def get(camera):
    rig.force_update(bpy.context, camera)
    matrix = rig.read_evaluated_camera_matrix(bpy.context, camera)
    rotation = matrix.to_quaternion()
    control = camera.cine.controller
    constraint = path_follow.get_constraint(control)
    fields = {}
    for key, (_group, _path, kind, _description) in FIELDS.items():
        owner, path = _field(camera, key)
        if owner is not None:
            fields[key] = _read(owner, path, kind)
    return {'camera': camera.name, 'controller': control.name if control else None,
            'shake': {'enabled': camera.cine.shake_enabled, 'events': [
                {'event_id': e.name, 'label': e.label, 'enabled': e.enabled, 'kind': e.kind, 'start': e.start,
                 'duration': e.duration, 'frequency': e.frequency, 'strength': e.strength, 'decay': e.decay,
                 'seed': e.seed, 'position': list(e.position), 'rotation_deg': [math.degrees(x) for x in e.rotation]}
                for e in camera.cine.shake_events]},
            'controller_owned': bool(control and control.cine_camera == camera and camera.parent == control),
            'enabled': camera.cine.enabled, 'needs_independent': rig.needs_independent_graph(camera),
            'frame': bpy.context.scene.frame_current + bpy.context.scene.frame_subframe,
            'unit_scale_length': bpy.context.scene.unit_settings.scale_length, 'projection': camera.data.type,
            'values': fields, 'dolly_enabled': dolly_zoom.is_enabled(camera),
            'dolly_target': control.cine.dolly_target.name if control and control.cine.dolly_target else None,
            'path': {'target': constraint.target.name if constraint and constraint.target else None,
                     'paused': constraint.mute if constraint else None},
            'world_position': list(matrix.translation), 'world_rotation_quaternion': list(rotation),
            'world_matrix': [list(row) for row in matrix],
            'control_location': list(control.location) if control else None,
            'control_rotation_deg': [math.degrees(x) for x in control.matrix_basis.to_euler('XYZ')] if control else None}


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError('数值必须是有限数字，不能使用布尔值、NaN 或无穷大')
    return value


def _vector(value):
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise ValueError('向量必须包含三个数值')
    result = tuple(_number(x) for x in value)
    if any(abs(x) > 3.402823466e38 for x in result):
        raise ValueError('向量分量超出 Blender 单精度数值范围')
    return result


def _check_driver(owner, path):
    animation = owner.id_data.animation_data
    full_path = owner.path_from_id(path)
    if animation and any(curve.data_path == full_path for curve in animation.drivers):
        raise ValueError(f'参数已有驱动器，不能直接覆盖：{path}')


def set_values(camera, values):
    if not isinstance(values, dict) or not values:
        raise ValueError('values 必须是非空参数字典')
    dolly = dolly_zoom.is_enabled(camera)
    assignments = []
    for key, value in values.items():
        if key not in FIELDS:
            raise ValueError(f'不支持的参数：{key}；请先 describe')
        group, path, kind, _description = FIELDS[key]
        owner, path = _field(camera, key)
        if owner is None:
            raise ValueError(f'此镜头没有对应控制器或路径：{key}')
        if dolly and key == 'distance' and not dolly_zoom.has_distance_control(camera):
            raise ValueError('旧版希区柯克需先关闭再开启一次，才能使用距离联动')
        if dolly and ((group == 'params' and key not in {'distance', 'shake_strength'}) or key in {'lens_mm', 'sensor_width_mm', 'ortho_scale'}):
            raise ValueError('希区柯克启用时不能改普通运镜、焦距或传感器，请先关闭该工具')
        if key == 'dolly_travel' and not dolly:
            raise ValueError('请先启用希区柯克工具，再调整推拉')
        if group == 'path' and (owner.mute or owner.target is None):
            raise ValueError('请先恢复有效轨迹，再修改路径参数')
        if group in {'data', 'dof'} and camera.data.users > 1:
            raise ValueError('相机数据被多个镜头共用，请先独立化相机数据')
        if kind == 'object':
            value = _object(value) if value is not None else None
            if value is camera or (key == 'origin' and value in camera.children_recursive):
                raise ValueError('不能将相机自身或其子级用作空间原点')
        elif kind == 'bool':
            if not isinstance(value, bool):
                raise ValueError(f'{key} 必须使用 true 或 false')
        elif kind == 'vector':
            value = _vector(value)
        else:
            value = _number(value)
            if kind == 'angle':
                value = math.radians(value)
            prop = owner.bl_rna.properties[path]
            if not prop.hard_min <= value <= prop.hard_max:
                raise ValueError(f'参数超出允许范围：{key}')
        _check_driver(owner, path)
        if key == 'origin':
            for affected in ('distance', 'horizontal', 'vertical', 'base_rotation', 'origin_fallback'):
                _check_driver(camera.cine, affected)
        assignments.append((key, owner, path, value))
    if values.get('clip_end', camera.data.clip_end) <= values.get('clip_start', camera.data.clip_start):
        raise ValueError('远裁剪必须大于近裁剪')
    if 'focus_distance' in values and values.get('focus_object', camera.data.dof.focus_object) is not None:
        raise ValueError('指定对焦目标时，手动对焦距离不生效；请先将 focus_object 设为 null')
    # 原点更新会反解其他参数；先更新原点，再应用用户明确给出的数值。
    assignments.sort(key=lambda item: item[0] != 'origin')
    saved = [(owner, path, tuple(getattr(owner, path)) if getattr(owner.bl_rna.properties[path], 'is_array', False)
              else getattr(owner, path)) for _key, owner, path, _value in assignments]
    motion = {field: tuple(getattr(camera.cine, field)) if field in {'offset', 'base_rotation', 'origin_fallback'}
              else getattr(camera.cine, field) for field in
              ('distance', 'horizontal', 'vertical', 'offset', 'pan', 'tilt', 'roll', 'base_rotation', 'origin_fallback')}
    try:
        for _key, owner, path, value in assignments:
            setattr(owner, path, value)
        rig.force_update(bpy.context, camera)
    except Exception:
        for owner, path, value in saved:
            setattr(owner, path, value)
        for field, value in motion.items():
            setattr(camera.cine, field, value)
        rig.force_update(bpy.context, camera)
        raise


def _dispatch(request):
    action = request.get('action')
    if action not in ACTIONS:
        raise ValueError('未知操作，请先调用 describe')
    if action == 'describe':
        return describe()
    if action == 'list':
        return [{'camera': obj.name, 'enabled': obj.cine.enabled,
                 'controller': obj.cine.controller.name if obj.cine.controller else None}
                for obj in bpy.context.scene.objects if obj.type == 'CAMERA']
    if action == 'create':
        if bpy.context.mode != 'OBJECT':
            raise ValueError('请先退出编辑或姿态模式')
        name = request.get('name')
        if name is not None and (not isinstance(name, str) or not name.strip()):
            raise ValueError('name 必须是非空字符串')
        _invoke(bpy.ops.cine.create_camera)
        camera = rig.resolve_camera(bpy.context)
        if name:
            camera.name = name
            camera.cine.controller.name = camera.name + '_Control'
        return get(camera)
    camera = _camera(request.get('camera'))
    if 'frame' in request:
        frame = _number(request['frame'])
        prop = bpy.types.Scene.bl_rna.properties['frame_current']
        if not prop.hard_min <= frame <= prop.hard_max:
            raise ValueError('帧号超出 Blender 允许范围')
        bpy.context.scene.frame_set(math.floor(frame), subframe=frame-math.floor(frame))
    if action == 'get':
        return get(camera)
    if bpy.context.mode != 'OBJECT':
        raise ValueError('请先退出编辑或姿态模式')
    if not camera.cine.enabled or camera.cine.rig_root is not None:
        raise ValueError('请先在插件中启用或升级目标镜头，或调用 create 创建已绑定镜头')
    control = camera.cine.controller
    if control is not None and (control.cine_camera != camera or camera.parent != control):
        raise ValueError('此镜头没有一对一匹配的曲线控制器，请使用独立绑定的镜头，避免影响其他相机')
    if rig.needs_independent_graph(camera) and action != 'make_independent':
        raise ValueError('镜头副本需要先调用 make_independent')
    if action == 'enable_shake':
        if not camera.cine.shake_enabled:
            _invoke(bpy.ops.cine.toggle_shake, camera)
    elif action == 'disable_shake':
        if camera.cine.shake_enabled:
            shake.disable(bpy.context, camera)
    elif action == 'shake_event':
        operation = request.get('operation')
        if operation not in {'add', 'update', 'duplicate', 'remove'}:
            raise ValueError('operation 必须是 add/update/duplicate/remove')
        index = camera.cine.shake_events.find(request.get('event_id', ''))
        if operation != 'add' and index < 0:
            raise ValueError('找不到 event_id 指定的震动事件')
        values = request.get('values', {})
        if not isinstance(values, dict):
            raise ValueError('事件 values 必须是参数字典')
        assignments = {}
        for field, value in values.items():
            if field not in {'label', 'enabled', 'kind', 'start', 'duration', 'frequency', 'strength', 'decay', 'seed', 'position', 'rotation_deg'}:
                raise ValueError('不支持的震动事件参数：'+field)
            path = 'rotation' if field == 'rotation_deg' else field
            from .core.properties import CineShakeEvent
            prop = CineShakeEvent.bl_rna.properties[path]
            if field == 'label':
                if not isinstance(value, str):
                    raise ValueError('事件名称必须是字符串')
            elif field == 'enabled':
                if not isinstance(value, bool):
                    raise ValueError('enabled 必须是布尔值')
            elif field == 'kind':
                if value not in {'IMPACT', 'CONTINUOUS'}:
                    raise ValueError('kind 必须是 IMPACT 或 CONTINUOUS')
            elif field in {'position', 'rotation_deg'}:
                value = _vector(value)
                if field == 'rotation_deg':
                    value = tuple(math.radians(x) for x in value)
                if any(x < prop.hard_min or x > prop.hard_max for x in value):
                    raise ValueError('事件向量超出允许范围')
            else:
                value = _number(value)
                if not prop.hard_min <= value <= prop.hard_max or (field == 'seed' and int(value) != value):
                    raise ValueError('事件参数超出允许范围：'+field)
                if field == 'seed':
                    value = int(value)
            assignments[path] = value
        if operation == 'remove' and assignments:
            raise ValueError('remove 不接受 values')
        if operation == 'update':
            event = camera.cine.shake_events[index]
        else:
            if index >= 0:
                camera.cine.shake_index = index
            with _context(camera):
                result = bpy.ops.cine.shake_event(action=operation.upper())
            if result != {'FINISHED'}:
                raise ValueError('震动事件编辑失败')
            event = camera.cine.shake_events[camera.cine.shake_index] if operation != 'remove' else None
        if event:
            for field in assignments:
                _check_driver(event, field)
            for field, value in assignments.items():
                setattr(event, field, value)
    elif action == 'set':
        set_values(camera, request.get('values'))
    elif action == 'move_control':
        if control is None or path_follow.get_constraint(control) is not None:
            raise ValueError('整体变换需要未绑定轨迹的曲线控制器')
        location = _vector(request['location']) if 'location' in request else None
        rotation = _vector(request['rotation_deg']) if 'rotation_deg' in request else None
        if location is None and rotation is None:
            raise ValueError('请提供 location 或 rotation_deg')
        if control.constraints:
            raise ValueError('控制器已有约束，不能直接设置基础变换')
        rotation_path = ('rotation_quaternion' if control.rotation_mode == 'QUATERNION' else
                         'rotation_axis_angle' if control.rotation_mode == 'AXIS_ANGLE' else 'rotation_euler')
        if location is not None:
            _check_driver(control, 'location')
        if rotation is not None:
            _check_driver(control, rotation_path)
        if location is not None:
            control.location = location
        if rotation is not None:
            from mathutils import Euler
            euler = Euler(tuple(math.radians(x) for x in rotation), 'XYZ')
            if rotation_path == 'rotation_quaternion':
                control.rotation_quaternion = euler.to_quaternion()
            elif rotation_path == 'rotation_axis_angle':
                axis, angle = euler.to_quaternion().to_axis_angle()
                control.rotation_axis_angle = (angle, *axis)
            else:
                control.rotation_euler = euler.to_quaternion().to_euler(control.rotation_mode)
    elif action == 'import_pose':
        rig.import_camera_position(bpy.context, camera, _object(request.get('source'), 'CAMERA'), full_pose=True)
    elif action == 'bind_path':
        path_follow.bind(bpy.context, camera, _object(request.get('target'), 'CURVE'))
    elif action in {'pause_path', 'resume_path'}:
        constraint = path_follow.get_constraint(control)
        if constraint is None:
            raise ValueError('当前镜头没有轨迹约束')
        if action == 'pause_path' and not constraint.mute:
            path_follow.unbind(bpy.context, camera)
        elif action == 'resume_path' and constraint.mute:
            path_follow.resume(bpy.context, camera)
    elif action == 'enable_dolly':
        if control is None:
            raise ValueError('希区柯克工具需要曲线控制器')
        target = _object(request['target']) if request.get('target') is not None else None
        if dolly_zoom.is_enabled(camera):
            if 'target' in request and target != control.cine.dolly_target:
                raise ValueError('请先关闭希区柯克，再更换主体')
        else:
            previous = control.cine.dolly_target
            try:
                if 'target' in request:
                    control.cine.dolly_target = target
                dolly_zoom.enable(bpy.context, camera)
            except Exception:
                control.cine.dolly_target = previous
                raise
    elif action == 'disable_dolly':
        if dolly_zoom.is_enabled(camera):
            dolly_zoom.disable(bpy.context, camera)
    elif action == 'keyframe':
        _invoke(bpy.ops.cine.keyframe_camera, camera)
    elif action == 'bake':
        _invoke(bpy.ops.cine.bake, camera)
    elif action == 'render_camera':
        bpy.context.scene.camera = camera
    elif action == 'make_independent':
        rig.make_independent(bpy.context, camera)
    return get(camera)


def call(request):
    """返回可 JSON 序列化的结果；失败不自动切换为底层直接写入。"""
    action = request.get('action') if isinstance(request, dict) else None
    try:
        if not isinstance(request, dict):
            raise ValueError('请求必须是 JSON 对象')
        return {'ok': True, 'api_version': API_VERSION, 'action': action, 'data': _dispatch(request)}
    except (ValueError, TypeError, RuntimeError, KeyError, AttributeError) as error:
        return {'ok': False, 'api_version': API_VERSION, 'action': action,
                'error': {'type': type(error).__name__, 'message': str(error)}}


class CINE_OT_automation(bpy.types.Operator):
    bl_idname = 'cine.automation'
    bl_label = 'Cine 自动化接口'
    bl_description = 'MCP JSON 入口：先传 action=describe 读取规则；所有角度用度，通过插件参数控制相机'
    bl_options = {'UNDO'}

    request_json: bpy.props.StringProperty(name='JSON 请求', default='{"action":"describe"}')

    def execute(self, context):
        try:
            result = call(json.loads(self.request_json))
        except (ValueError, TypeError) as error:
            result = {'ok': False, 'api_version': API_VERSION,
                      'error': {'type': type(error).__name__, 'message': 'JSON 格式错误：' + str(error)}}
        # MCP 的 execute_blender_code 会收集标准输出；FINISHED 不代表业务成功，必须检查 ok。
        print(json.dumps(result, ensure_ascii=False, allow_nan=False))
        return {'FINISHED'}


class CINE_OT_copy_mcp_instructions(bpy.types.Operator):
    bl_idname = 'cine.copy_mcp_instructions'
    bl_label = '复制 MCP 接入指令'
    bl_description = '复制中文规则和发现脚本，粘贴到 AI 客户端的项目指令或会话开场说明'

    def execute(self, context):
        context.window_manager.clipboard = CLIENT_INSTRUCTIONS
        self.report({'INFO'}, '已复制 MCP 接入指令，请粘贴到 AI 客户端的项目指令或会话中')
        return {'FINISHED'}


def register():
    bpy.utils.register_class(CINE_OT_automation)
    bpy.utils.register_class(CINE_OT_copy_mcp_instructions)


def unregister():
    bpy.utils.unregister_class(CINE_OT_copy_mcp_instructions)
    bpy.utils.unregister_class(CINE_OT_automation)
