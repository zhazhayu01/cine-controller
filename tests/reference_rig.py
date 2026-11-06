"""测试用原生层级参照，独立检查内部数学计算及旧工程升级。"""
import bpy
from mathutils import Matrix


def create_reference(camera, origin, aim, source=None):
    source = source or camera
    helpers = []
    parent = None
    for name in ('ROOT', 'YAW', 'PITCH', 'DIST', 'BASE', 'OFFSET', 'AIM', 'LOCAL_ROT'):
        obj = bpy.data.objects.new('Reference_' + name, None)
        bpy.context.scene.collection.objects.link(obj)
        obj.parent = parent
        parent = obj
        helpers.append(obj)
    root, yaw, pitch, dist, base, offset, aim_node, local_rot = helpers
    root.constraints.new('COPY_LOCATION').target = origin
    base.rotation_mode = 'QUATERNION'
    base.rotation_quaternion = source.cine.base_rotation
    bindings = [(yaw, 'rotation_euler', 2, 'horizontal', 'v'),
                (pitch, 'rotation_euler', 0, 'vertical', 'v'),
                (dist, 'location', 1, 'distance', '-v')]
    bindings += [(offset, 'location', i, f'offset[{i}]', '-v' if i == 2 else 'v') for i in range(3)]
    bindings += [(local_rot, 'rotation_euler', i, field, '-v' if i == 2 else 'v')
                 for i, field in enumerate(('tilt', 'pan', 'roll'))]
    con = aim_node.constraints.new('TRACK_TO')
    con.target = aim
    con.track_axis = 'TRACK_NEGATIVE_Z'
    con.up_axis = 'UP_Y'
    bindings.append((con, 'influence', None, 'aim_influence', 'v'))
    for owner, path, index, field, expression in bindings:
        curve = owner.driver_add(path) if index is None else owner.driver_add(path, index)
        curve.driver.expression = expression
        variable = curve.driver.variables.new()
        variable.name = 'v'
        variable.type = 'SINGLE_PROP'
        variable.targets[0].id = source
        variable.targets[0].data_path = 'cine.' + field
    camera.parent = local_rot
    camera.matrix_parent_inverse = Matrix.Identity(4)
    camera.matrix_basis = Matrix.Identity(4)
    for attr, helper in zip(('rig_root', 'rig_yaw', 'rig_pitch', 'rig_dist', 'rig_base',
                            'rig_offset', 'rig_aim', 'rig_local_rot'), helpers):
        setattr(camera.cine, attr, helper)
    camera.cine.enabled = True
    camera.cine.rig_version = 1
    bpy.context.view_layer.update()
    return helpers
