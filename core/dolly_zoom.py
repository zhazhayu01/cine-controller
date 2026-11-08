"""希区柯克变焦：捕获当前镜头，按实际光轴深度补偿焦距。

运行输入全部来自曲线控制器及主体，避免 Camera Data → Camera Transform
再反向驱动 Lens 的依赖循环。不注册逐帧回调或 Python 驱动函数。
"""
import bpy
from mathutils import Vector

from .driver_graph import DriverGraph, PREFIX


def is_enabled(camera):
    control = camera.cine.controller
    return control is not None and control.cine_camera == camera and control.cine.dolly_enabled


def has_distance_control(camera):
    control = camera.cine.controller
    return bool(control and control.cine.dolly_graph
                and PREFIX+'effective_travel' in control.cine.dolly_graph)


def compensation_warning(camera):
    control = camera.cine.controller
    graph = control.cine.dolly_graph if control else None
    if graph is None:
        return ''
    if graph.get(PREFIX+'bounds_depth', graph.get(PREFIX+'depth', 1)) <= 1e-6:
        return '主体穿过镜头，已超出有效补偿范围'
    raw = graph.get(PREFIX+'raw_lens', camera.data.lens)
    prop = bpy.types.Camera.bl_rna.properties['lens']
    if raw < prop.hard_min or raw > prop.hard_max:
        return '焦距达到极限，无法继续保持主体大小'
    return ''


def needs_independent(camera):
    if not is_enabled(camera):
        return False
    control = camera.cine.controller
    graph = control.cine.dolly_graph
    if graph is None:
        return False
    first = graph.animation_data.drivers.find(f'["{PREFIX}wp0"]')
    return graph.users > 1 or any(v.targets[0].id != (graph if v.targets[0].id_type == 'NODETREE' else control)
                                 for v in first.driver.variables)


def ensure_owned(camera):
    """复制完整镜头时独立化光学数据，避免副本修改/停用原镜头的联动。"""
    if not needs_independent(camera):
        return
    from . import rig
    control = camera.cine.controller
    old = control.cine.dolly_graph
    graph = old.copy()
    graph.name = '.CineDolly.' + camera.name
    control.cine.dolly_graph = graph
    for curve in graph.animation_data.drivers:
        for variable in curve.driver.variables:
            target = variable.targets[0]
            if target.id == old:
                target.id = graph
            elif target.id_type == 'OBJECT':
                target.id = control
    _override_motion(camera)
    rig._add_driver(camera, camera.data, 'lens', None, 'v', {'v': (f'["{PREFIX}lens"]', control.cine.dolly_base_lens)},
                    source_object=control, storage=graph)


def _lens_graph(use_bounds=False):
    graph = DriverGraph()
    for axis in range(3):
        graph.input(f'p{axis}', f'cine.dolly_base_position[{axis}]')
        graph.input(f'f{axis}', f'cine.dolly_forward[{axis}]')
        graph.input(f't{axis}', f'cine.dolly_target.matrix_world[3][{axis}]')
        graph.input(f'a{axis}', f'cine.dolly_anchor[{axis}]')
        for column in range(4):
            graph.input(f'c{axis}{column}', f'matrix_world[{column}][{axis}]')
    graph.input('target', 'cine.dolly_target.matrix_world[3][3]')
    graph.input('travel', 'cine.dolly_travel')
    graph.input('distance', 'cine.dolly_distance')
    graph.input('distance_base', 'cine.dolly_base_distance')
    travel = graph.node('effective_travel', 'travel+distance_base-distance')
    graph.input('base', 'cine.dolly_base_lens')
    graph.input('reference', 'cine.dolly_reference_depth', 1)
    for axis in range(3):
        graph.node(f'wp{axis}', f'c{axis}3+' + '+'.join(f'c{axis}{j}*(p{j}+f{j}*{travel})' for j in range(3)))
        graph.node(f'wf{axis}', '+'.join(f'c{axis}{j}*f{j}' for j in range(3)))
        graph.node(f'subject{axis}', f't{axis} if target else a{axis}')
    graph.node('length', 'sqrt(wf0*wf0+wf1*wf1+wf2*wf2)')
    graph.node('depth', '(' + '+'.join(f'(subject{i}-wp{i})*wf{i}' for i in range(3)) + ')/max(length,1e-9)')
    raw = 'base*max(depth,1e-6)/max(reference,1e-6)'
    if use_bounds:
        # 直接从主体几何和控制器求投影比例，不反读相机变换或光学数据。
        graph.input('span_reference', 'cine.dolly_reference_span')
        graph.input('span_axis', 'cine.dolly_span_axis')
        for label, field in (('right', 'dolly_right'), ('up', 'dolly_up')):
            for axis in range(3):
                graph.input(f'{label}{axis}', f'cine.{field}[{axis}]')
            for axis in range(3):
                graph.node(f'w{label}{axis}', '+'.join(f'c{axis}{j}*{label}{j}' for j in range(3)))
            graph.node(f'{label}_length', 'sqrt('+ '+'.join(f'w{label}{j}*w{label}{j}' for j in range(3))+')')
        for axis in range(3):
            for column in range(4):
                graph.input(f'm{axis}{column}', f'cine.dolly_target.matrix_world[{column}][{axis}]')
        xs, ys, depths = [], [], []
        for corner in range(8):
            for axis in range(3):
                graph.input(f'b{corner}{axis}', f'cine.dolly_target.bound_box[{corner}][{axis}]')
            for axis in range(3):
                graph.node(f'rel{corner}{axis}', f'm{axis}3-wp{axis}+'+
                           '+'.join(f'm{axis}{j}*b{corner}{j}' for j in range(3)))
            depth = graph.node(f'z{corner}', '('+'+'.join(f'rel{corner}{j}*wf{j}' for j in range(3))+')/max(length,1e-9)')
            depths.append(depth)
            for label, projected in (('right', xs), ('up', ys)):
                projected.append(graph.node(('px' if label == 'right' else 'py')+str(corner),
                    '('+'+'.join(f'rel{corner}{j}*w{label}{j}' for j in range(3))+
                    f')/max({label}_length,1e-9)/max({depth},1e-6)'))
        graph.node('bounds_depth', 'min('+','.join(depths)+')')
        width = graph.node('bounds_width', 'max('+','.join(xs)+')-min('+','.join(xs)+')')
        height = graph.node('bounds_height', 'max('+','.join(ys)+')-min('+','.join(ys)+')')
        graph.node('bounds_span', f'{height} if span_axis else {width}')
        raw = f'base*span_reference/max(bounds_span,1e-9) if target else ({raw})'
    graph.node('raw_lens', raw)
    lens = bpy.types.Camera.bl_rna.properties['lens']
    graph.node('lens', f'min({lens.hard_max},max({lens.hard_min},raw_lens))')
    return graph


def _override_motion(camera):
    from . import rig
    control = camera.cine.controller
    for index in range(3):
        bindings = {
            'n': (f'["{PREFIX}pos{index}"]', 0),
            'p': (f'cine.dolly_base_position[{index}]', 0),
            'f': (f'cine.dolly_forward[{index}]', 0),
            't': ('cine.dolly_travel', 0), 'on': ('cine.dolly_enabled', 0),
            'd': ('cine.dolly_distance', 0), 'b': ('cine.dolly_base_distance', 0),
        }
        rig._add_driver(camera, camera, 'delta_location', index, 'p+f*(t+b-d) if on else n', bindings, source_object=control)
    for index in range(4):
        bindings = {'n': (f'["{PREFIX}out{index}"]', float(index == 0)),
                    'q': (f'cine.dolly_base_rotation[{index}]', float(index == 0)),
                    'on': ('cine.dolly_enabled', 0)}
        rig._add_driver(camera, camera, 'delta_rotation_quaternion', index, 'q if on else n', bindings, source_object=control)
    from . import shake
    shake.refresh(camera)


def _restore_motion(camera):
    from . import rig
    for path, prefix, count in (('delta_location', 'pos', 3), ('delta_rotation_quaternion', 'out', 4)):
        for index in range(count):
            rig._add_driver(camera, camera, path, index, 'v', {'v': (f'["{PREFIX}{prefix}{index}"]', float(path != 'delta_location' and index == 0))})
    from . import shake
    shake.refresh(camera)


def enable(context, camera):
    from . import rig
    control = camera.cine.controller
    if not camera.cine.enabled or control is None or camera.parent != control:
        raise ValueError('希区柯克工具需要已绑定曲线控制器的摄像机')
    if control.cine_camera != camera:
        raise ValueError('此曲线属于另一台相机，请创建独立的相机与控制器后启用')
    if is_enabled(camera):
        ensure_owned(camera)
        return
    if camera.data.type != 'PERSP':
        raise ValueError('希区柯克变焦仅支持透视摄像机')
    if camera.data.users > 1:
        raise ValueError('摄像机数据被多个镜头共用，请先将相机数据独立化')
    animation = camera.data.animation_data
    if animation and any(curve.data_path == 'lens' for curve in animation.drivers):
        raise ValueError('焦距已有外部驱动器，不能覆盖')
    props = control.cine
    target = props.dolly_target or camera.cine.aim_target or camera.cine.origin
    if target == camera or target in camera.children_recursive:
        raise ValueError('主体不能是摄像机自身或其子级，避免循环依赖')
    rig.make_independent(context, camera)
    rig.force_update(context, camera)
    from . import shake
    world = shake.base_world_matrix(context, camera)
    anchor = target.matrix_world.translation.copy() if target else control.matrix_world.translation.copy()
    forward = (world.to_3x3() @ Vector((0, 0, -1))).normalized()
    depth = (anchor-world.translation).dot(forward)
    if depth <= 1e-4:
        raise ValueError('主体必须在镜头前方；请先调整机位或指定希区柯克主体')
    local = control.matrix_world.inverted_safe() @ world
    props.dolly_target = target
    props.dolly_anchor = anchor
    props.dolly_base_position = local.translation
    props.dolly_base_rotation = local.to_quaternion()
    props.dolly_forward = local.to_quaternion() @ Vector((0, 0, -1))
    props.dolly_right = local.to_quaternion() @ Vector((1, 0, 0))
    props.dolly_up = local.to_quaternion() @ Vector((0, 1, 0))
    props.dolly_use_bounds = False
    props.dolly_reference_span = 0
    if target is not None and target.type in {'MESH', 'CURVE', 'SURFACE', 'FONT', 'META'}:
        evaluated = target.evaluated_get(context.evaluated_depsgraph_get())
        view = world.normalized().inverted()
        corners = [view @ (evaluated.matrix_world @ Vector(corner)) for corner in evaluated.bound_box]
        if min(-corner.z for corner in corners) <= 1e-4:
            raise ValueError('主体包围盒穿过或位于镜头后方，请先调整机位')
        spans = [max(corner[axis]/-corner.z for corner in corners)
                 -min(corner[axis]/-corner.z for corner in corners) for axis in (0, 1)]
        props.dolly_span_axis = 1 if spans[1] > 1e-8 else 0
        props.dolly_reference_span = spans[props.dolly_span_axis]
        props.dolly_use_bounds = props.dolly_reference_span > 1e-8
    props.dolly_base_lens = camera.data.lens
    props.dolly_reference_depth = depth
    props.dolly_base_distance = camera.cine.distance
    if not any(curve.data_path == 'cine.dolly_distance' for curve in rig._action_curves(control.animation_data.action if control.animation_data else None)):
        props.dolly_distance = props.dolly_base_distance
    # 已有推拉关键帧可继续使用；新工具从零推拉量开始。
    if not any(curve.data_path == 'cine.dolly_travel' for curve in rig._action_curves(control.animation_data.action if control.animation_data else None)):
        props.dolly_travel = 0.0
    storage = bpy.data.node_groups.new('.CineDolly.' + camera.name, 'ShaderNodeTree')
    props.dolly_graph = storage
    try:
        graph = _lens_graph(props.dolly_use_bounds)
        for key, _expression, _bindings in graph.nodes:
            storage[key] = 0.0
        for key, expression, bindings in graph.nodes:
            rig._add_driver(camera, storage, f'["{key}"]', None, expression, bindings, source_object=control, storage=storage)
        _override_motion(camera)
        rig._add_driver(camera, camera.data, 'lens', None, 'v', {'v': (f'["{PREFIX}lens"]', props.dolly_base_lens)},
                        source_object=control, storage=storage)
        props.dolly_enabled = True
        rig.force_update(context, camera)
    except Exception:
        disable(context, camera)
        raise


def disable(context, camera, preserve_lens=False):
    """移除联动；正常停用恢复原参数和焦距动画，烘焙/解绑可保留当前焦距。"""
    from . import rig
    control = camera.cine.controller
    if control is None:
        return
    if control.cine_camera != camera:
        raise ValueError('不能停用另一台相机的希区柯克工具')
    ensure_owned(camera)
    props = control.cine
    lens = camera.data.lens if preserve_lens else props.dolly_base_lens
    storage = props.dolly_graph
    props.dolly_enabled = False
    camera.data.driver_remove('lens')
    if camera.cine.internal_graph:
        _restore_motion(camera)
    props.dolly_graph = None
    if storage is not None and storage.users == 0:
        bpy.data.node_groups.remove(storage)
    camera.data.lens = lens
    camera.data.update_tag()
    context.scene.frame_set(context.scene.frame_current, subframe=context.scene.frame_subframe)
    rig.force_update(context, camera)
