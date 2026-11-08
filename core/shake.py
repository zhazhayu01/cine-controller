"""多事件震动末端层：原生简单驱动器，按绝对时间求值，不写回基础运镜。"""
from math import tau
import uuid
import bpy
from mathutils import Quaternion, Vector

from .driver_graph import DriverGraph, PREFIX


def needs_independent(camera):
    graph = camera.cine.shake_graph
    if graph is None:
        return False
    curve = graph.animation_data.drivers.find(f'["{PREFIX}shake_gain"]')
    return graph.users > 1 or any(var.targets[0].id != camera for var in curve.driver.variables)


def _graph(events):
    g = DriverGraph()
    g.input('master', 'cine.shake_strength')
    g.node('shake_gain', 'master')
    g.input('fps', f'["{PREFIX}shake_fps"]', 24)
    for i in range(3):
        g.input('bp'+str(i), f'["{PREFIX}shake_base_p{i}"]')
    base = tuple(g.input('bq'+str(i), f'["{PREFIX}shake_base_q{i}"]', float(i == 0)) for i in range(4))
    channels = [[] for _ in range(6)]
    for index, event in enumerate(events):
        path = f'cine.shake_events["{event.name}"]'
        for key in ('enabled', 'start', 'duration', 'strength', 'frequency', 'decay', 'seed'):
            g.input(f'e{index}_{key}', path+'.'+key)
        prefix = 'e'+str(index)+'_'
        u = g.node(prefix+'u', f'(frame-{prefix}start)/max({prefix}duration,0.1)')
        time = g.node(prefix+'t', f'(frame-{prefix}start)/max(fps,0.001)')
        attack = g.node(prefix+'a', f'min(1,max(0,{u}/0.15))')
        release = g.node(prefix+'r', f'min(1,max(0,(1-{u})/0.15))')
        # 模式用数值输入，切换模式无需重建图。
        g.input(prefix+'continuous', path+'.kind')
        envelope = g.node(prefix+'envelope',
            f'({attack}*{attack}*(3-2*{attack})*{release}*{release}*(3-2*{release}) if {prefix}continuous else '
            f'pow(1-{u},{prefix}decay)) if {prefix}enabled and {u}>=0 and {u}<1 else 0')
        for axis in range(6):
            wave = g.node(prefix+'w'+str(axis),
                f'0.72*cos({tau}*{prefix}frequency*{time}+{axis}*0.7)+ '
                f'0.28*cos({tau}*1.79*{prefix}frequency*{time}+{prefix}seed*1.618+{axis}*1.3)')
            g.input(prefix+'amp'+str(axis), path+f'.{"position" if axis<3 else "rotation"}[{axis%3}]')
            channels[axis].append(g.node(prefix+'s'+str(axis),
                f'{wave}*{envelope}*{prefix}strength*{prefix}amp{axis}'))
    # 成对累加避免事件多时触及 Blender 的单表达式长度上限。
    sums = []
    for axis, values in enumerate(channels):
        value = '0'
        for index, item in enumerate(values):
            value = g.node(f'shake_sum{axis}_{index}', f'{value}+{item}')
        sums.append(g.node('shake_axis'+str(axis), f'({value})*shake_gain'))
    matrix = g.rotation_matrix('shake_basis', base)
    for i in range(3):
        g.node('shake_position'+str(i), f'bp{i}+{matrix[i][0]}*{sums[0]}+{matrix[i][1]}*{sums[1]}-{matrix[i][2]}*{sums[2]}')
    tilt, pan, roll = sums[3:]
    # 与基础运镜一致：XYZ 为俯仰、摇摄、负翻滚。
    local = tuple(g.node('shake_local'+str(i), expression) for i, expression in enumerate((
        f'cos({roll}/2)*cos({pan}/2)*cos({tilt}/2)-sin({roll}/2)*sin({pan}/2)*sin({tilt}/2)',
        f'cos({roll}/2)*cos({pan}/2)*sin({tilt}/2)+sin({roll}/2)*sin({pan}/2)*cos({tilt}/2)',
        f'cos({roll}/2)*sin({pan}/2)*cos({tilt}/2)-sin({roll}/2)*cos({pan}/2)*sin({tilt}/2)',
        f'-sin({roll}/2)*cos({pan}/2)*cos({tilt}/2)-cos({roll}/2)*sin({pan}/2)*sin({tilt}/2)')))
    g.quaternion_product('shake_rotation', base, local)
    return g


def _outputs(camera, storage):
    from . import rig
    for path, key, count in (('delta_location', 'shake_position', 3), ('delta_rotation_quaternion', 'shake_rotation', 4)):
        for i in range(count):
            rig._add_driver(camera, camera, path, i, 'v', {'v': (f'["{PREFIX}{key}{i}"]', float(key == 'shake_rotation' and i == 0))}, storage=storage)


def _copy_driver(source, destination):
    from . import rig
    rig._clear_driver_mapping(destination)
    destination.driver.type = 'SCRIPTED'
    destination.driver.expression = source.expression
    for variable in list(destination.driver.variables):
        destination.driver.variables.remove(variable)
    for variable in source.variables:
        copy = destination.driver.variables.new()
        copy.name, copy.type = variable.name, variable.type
        a, b = variable.targets[0], copy.targets[0]
        b.id_type, b.id, b.data_path = a.id_type, a.id, a.data_path
        b.use_fallback_value, b.fallback_value = a.use_fallback_value, a.fallback_value


def refresh(camera):
    """基础输出安装完成后调用；复制基础驱动到末端图，再叠加震动。"""
    from . import rig
    params = camera.cine
    old = params.shake_graph
    if not params.shake_enabled:
        clear(camera)
        return
    spec = _graph(params.shake_events)
    graph = bpy.data.node_groups.new('.CineShake.'+camera.name, 'ShaderNodeTree')
    params.shake_graph = graph
    try:
        graph[PREFIX+'shake_fps'] = 24.0
        curve = graph.driver_add(f'["{PREFIX}shake_fps"]')
        rig._clear_driver_mapping(curve)
        curve.driver.type = 'SCRIPTED'
        curve.driver.expression = 'fps/max(base,0.001)'
        for name, path in (('fps', 'render.fps'), ('base', 'render.fps_base')):
            variable = curve.driver.variables.new()
            variable.name, variable.type = name, 'SINGLE_PROP'
            variable.targets[0].id_type = 'SCENE'
            variable.targets[0].id = bpy.context.scene
            variable.targets[0].data_path = path
            variable.targets[0].use_fallback_value = True
            variable.targets[0].fallback_value = bpy.context.scene.path_resolve(path)
        for path, key, count in (('delta_location', 'p', 3), ('delta_rotation_quaternion', 'q', 4)):
            for i in range(count):
                prop = f'["{PREFIX}shake_base_{key}{i}"]'
                graph[PREFIX+f'shake_base_{key}{i}'] = float(key == 'q' and i == 0)
                source = camera.animation_data.drivers.find(path, index=i).driver
                destination = graph.driver_add(prop)
                _copy_driver(source, destination)
        for key, _expression, _bindings in spec.nodes:
            graph[key] = 0.0
        for key, expression, bindings in spec.nodes:
            rig._add_driver(camera, graph, f'["{key}"]', None, expression, bindings, storage=graph)
        _outputs(camera, graph)
    except Exception:
        params.shake_graph = old
        if old:
            _outputs(camera, old)
        else:
            # 初次安装部分失败时恢复已复制的基础输出，避免残留半套震动驱动和孤立数据块。
            for path, key, count in (('delta_location', 'p', 3), ('delta_rotation_quaternion', 'q', 4)):
                for i in range(count):
                    curve = graph.animation_data.drivers.find(f'["{PREFIX}shake_base_{key}{i}"]')
                    if curve:
                        _copy_driver(curve.driver, camera.driver_add(path, i))
        if graph.users == 0:
            bpy.data.node_groups.remove(graph)
        raise
    if old is not None and old.users == 0:
        bpy.data.node_groups.remove(old)


def rebuild(context, camera):
    from . import dolly_zoom, rig
    if dolly_zoom.is_enabled(camera):
        dolly_zoom._override_motion(camera)
    else:
        dolly_zoom._restore_motion(camera)
    rig.force_update(context, camera)


def clear(camera):
    graph = camera.cine.shake_graph
    camera.cine.shake_graph = None
    camera.cine.shake_enabled = False
    if graph is not None and graph.users == 0:
        bpy.data.node_groups.remove(graph)


def enable(context, camera):
    from . import rig
    if not camera.cine.enabled or camera.cine.rig_root is not None:
        raise ValueError('请先启用或升级摄像机内部控制器')
    rig.make_independent(context, camera)
    camera.cine.shake_enabled = True
    try:
        rebuild(context, camera)
    except Exception:
        camera.cine.shake_enabled = False
        rebuild(context, camera)
        raise


def disable(context, camera):
    camera.cine.shake_enabled = False
    rebuild(context, camera)


def ensure_owned(context, camera):
    if camera.cine.shake_enabled and needs_independent(camera):
        rebuild(context, camera)


def add_event(context, camera, copy_from=None):
    previous_index = camera.cine.shake_index
    event = camera.cine.shake_events.add()
    event.name = uuid.uuid4().hex
    event.label = '冲击 '+str(len(camera.cine.shake_events))
    event.start = context.scene.frame_current+context.scene.frame_subframe
    event.seed = len(camera.cine.shake_events)
    if copy_from is not None:
        for field in ('label', 'enabled', 'kind', 'start', 'duration', 'strength', 'frequency', 'decay', 'seed', 'position', 'rotation'):
            setattr(event, field, getattr(copy_from, field))
        event.label += ' 副本'
    camera.cine.shake_index = len(camera.cine.shake_events)-1
    if camera.cine.shake_enabled:
        try:
            rebuild(context, camera)
        except Exception:
            camera.cine.shake_events.remove(len(camera.cine.shake_events)-1)
            camera.cine.shake_index = previous_index
            rebuild(context, camera)
            raise
    return event


def base_world_matrix(context, camera):
    from . import rig
    if not camera.cine.shake_enabled or camera.cine.shake_graph is None:
        return rig.read_evaluated_camera_matrix(context, camera)
    graph = camera.cine.shake_graph.evaluated_get(context.evaluated_depsgraph_get())
    rotation = Quaternion(tuple(graph[PREFIX+f'shake_base_q{i}'] for i in range(4)))
    matrix = rotation.to_matrix().to_4x4()
    matrix.translation = Vector(tuple(graph[PREFIX+f'shake_base_p{i}'] for i in range(3)))
    if camera.parent:
        matrix = camera.parent.matrix_world @ camera.matrix_parent_inverse @ matrix
    return matrix
