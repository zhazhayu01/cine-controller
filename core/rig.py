"""Rig 构建：Helper 层级 / Constraint / Driver / 参数反解。

规范关键点：
    §9   依赖 Parent Hierarchy + Constraint + Driver（Dependency Graph），
         禁止 frame_change_post / depsgraph_update_post 持续写回 Camera。
    §12  Local / World Space 显式定义。
    §13  Camera World Matrix 是最终真相。
    §22/23 关系用 PointerProperty，不靠 Name String 重查。
    §33  Constraint 创建显式指定 owner_space / target_space / track_axis / up_axis / influence。
    §34  Driver 绝对驱动（= horizontal，而非 += horizontal）。
    §35  简单 Driver Variable + Expression，不用自定义 Driver Namespace。

Rig 层级：
    ROOT   (Empty)  World Position = Origin（Copy Location，world→world）
      └─ YAW    (Empty)  Local rot.z = horizontal        [Driver]
          └─ PITCH  (Empty)  Local rot.x = vertical      [Driver]
              └─ BASE   (Empty)  Local rot.x = +90°      [固定，把 camera -Z forward 转到水平]
                  └─ DIST   (Empty)  Local loc.z = distance  [Driver]
                      └─ AIM    (Empty)  Track To → Aim Target, influence [约束]
                          └─ CAMERA  (真实 Camera 对象，local transform 反解补偿)
"""
import bpy
from math import pi
from mathutils import Matrix

from ..utils import math_utils as mu

# BASE 固定旋转：+90° 绕 X，使「distance 沿 +Z」映射为「水平轨道」，相机 forward(-Z) 保持水平看回原点。
BASE_ANGLE = pi / 2.0

# Helper 命名前缀（仅作显示用；身份识别靠 PointerProperty，不靠名字）
RIG_PREFIX = "CC_"


def compose_rig_rotation(horizontal: float, vertical: float) -> Matrix:
    """Rig 祖先链的累计旋转矩阵 R_rig = R_z(h) · R_x(v) · R_x(90°)。

    与 Blender 中 ROOT→YAW→PITCH→BASE 的父子链求值结果一致。
    用于 Enable 时反解 Camera 本地旋转以保持位姿。
    """
    return (
        Matrix.Rotation(horizontal, 4, 'Z')
        @ Matrix.Rotation(vertical, 4, 'X')
        @ Matrix.Rotation(BASE_ANGLE, 4, 'X')
    )


def compose_aim_world_matrix(origin_world, distance, horizontal, vertical) -> Matrix:
    """AIM 节点（相机父级）的世界矩阵（不含 Track To 约束效果，即 aim_influence=0 时）。

    用于反解 Camera 本地 transform。
    """
    t_origin = Matrix.Translation(origin_world)
    r_rig = compose_rig_rotation(horizontal, vertical)
    t_dist = Matrix.Translation((0.0, 0.0, distance))
    return t_origin @ r_rig @ t_dist


def read_evaluated_camera_matrix(context, camera_obj) -> Matrix:
    """读取 Camera 的 evaluated 世界矩阵（规范 §14）。

    统一入口：Bake / 对比测试 / Preserve Pose 都走这里。
    """
    depsgraph = context.evaluated_depsgraph_get()
    camera_eval = camera_obj.evaluated_get(depsgraph)
    return camera_eval.matrix_world.copy()


def force_update(context, camera_obj):
    """程序化修改参数后强制 Depsgraph 重新求值。

    在 GUI 中用户改属性会自动触发更新；但在 headless / 脚本 / 后台渲染场景下，
    直接改 Python 属性不会自动 tag Depsgraph（Blender 已知行为 issue #91140），
    需要显式 update_tag + view_layer.update 才能让 Driver 重新求值。

    规范 §36 要求架构兼容 Background Render，因此提供此统一入口。
    """
    # tag 所有相关对象（Camera + Helper 链）为需要更新
    camera_obj.update_tag()
    params = camera_obj.cine
    for helper in (params.rig_root, params.rig_yaw, params.rig_pitch,
                   params.rig_base, params.rig_dist, params.rig_aim):
        if helper is not None:
            helper.update_tag()
    context.view_layer.update()
    context.evaluated_depsgraph_get().update()


def _new_empty(context, name: str, parent=None):
    """创建一个 Empty Helper 并挂到场景集合。"""
    empty = bpy.data.objects.new(RIG_PREFIX + name, None)
    empty.empty_display_type = 'PLAIN_AXES'
    empty.empty_display_size = 0.25
    context.scene.collection.objects.link(empty)
    if parent is not None:
        empty.parent = parent
    return empty


def _add_driver(obj, data_path: str, index: int, target_id, source_path: str, expression: str):
    """给 obj 的 data_path[index] 加一个绝对 Driver。

    变量为单值 SINGLE_PROP，expression 直接引用变量名（绝对驱动，非增量）。
    """
    fcurve = obj.driver_add(data_path, index)
    driver = fcurve.driver
    driver.type = 'SCRIPTED'
    var = driver.variables.new()
    var.name = "v"
    var.type = 'SINGLE_PROP'
    t = var.targets[0]
    t.id_type = 'OBJECT'
    t.id = target_id
    t.data_path = source_path
    driver.expression = expression
    return driver


def _solve_camera_local(M0: Matrix, origin_world, distance, horizontal, vertical) -> Matrix:
    """反解 Camera 本地矩阵，使最终世界矩阵 = M0（位姿保持）。"""
    aim_world = compose_aim_world_matrix(origin_world, distance, horizontal, vertical)
    return aim_world.inverted() @ M0


def build_rig(context, camera_obj, origin_obj) -> dict:
    """为 camera_obj 构建 Cine Rig，并反解参数保持位姿不跳。

    返回 {"before": M0, "after": M1, "params": (d, h, v)} 供调用方验证。
    """
    from ..utils.math_utils import solve_orbit_from_pose

    # 1. 记录修改前 Camera evaluated 世界矩阵
    M0 = read_evaluated_camera_matrix(context, camera_obj)

    # 2. 反解 orbit 参数
    origin_world = origin_obj.matrix_world.to_translation()
    d, h, v = solve_orbit_from_pose(origin_world, M0.to_translation())

    params = camera_obj.cine
    params.distance = d
    params.horizontal = h
    params.vertical = v
    params.origin = origin_obj

    # 3. 构建 Helper 层级
    root = _new_empty(context, "ROOT", parent=None)
    yaw = _new_empty(context, "YAW", parent=root)
    pitch = _new_empty(context, "PITCH", parent=yaw)
    base = _new_empty(context, "BASE", parent=pitch)
    dist = _new_empty(context, "DIST", parent=base)
    aim = _new_empty(context, "AIM", parent=dist)

    # BASE 固定旋转 +90°（绕 X）
    base.rotation_euler = (BASE_ANGLE, 0.0, 0.0)

    # 4. ROOT 跟随 Origin 世界位置（Copy Location，显式 world→world）
    con = root.constraints.new('COPY_LOCATION')
    con.target = origin_obj
    con.target_space = 'WORLD'
    con.owner_space = 'WORLD'
    con.use_x = True
    con.use_y = True
    con.use_z = True

    # 5. Driver：绝对驱动
    # YAW.rotation_euler.z = horizontal
    _add_driver(yaw, "rotation_euler", 2, camera_obj, "cine.horizontal", "v")
    # PITCH.rotation_euler.x = vertical
    _add_driver(pitch, "rotation_euler", 0, camera_obj, "cine.vertical", "v")
    # DIST.location.z = distance
    _add_driver(dist, "location", 2, camera_obj, "cine.distance", "v")

    # 6. 反解 Camera 本地 transform（保持位姿）
    camera_local = _solve_camera_local(M0, origin_world, d, h, v)
    camera_obj.parent = aim
    camera_obj.matrix_local = camera_local

    # 7. 记录 Helper 引用到参数（PointerProperty，不靠名字）
    params.rig_root = root
    params.rig_yaw = yaw
    params.rig_pitch = pitch
    params.rig_base = base
    params.rig_dist = dist
    params.rig_aim = aim
    params.enabled = True

    # 8. 更新 Depsgraph 后读取结果
    context.evaluated_depsgraph_get().update()
    M1 = read_evaluated_camera_matrix(context, camera_obj)

    return {"before": M0, "after": M1, "params": (d, h, v)}


def _apply_aim(context, camera_obj):
    """根据 aim_target / aim_influence 设置 AIM 节点的 Track To 约束。

    只影响 Orientation，绝不触碰 Transform 参数。
    """
    params = camera_obj.cine
    aim = params.rig_aim
    if aim is None:
        return

    # 清除旧的 Cine Aim 约束（用名字前缀识别自己的约束）
    for c in aim.constraints:
        if c.type == 'TRACK_TO' and c.name.startswith(RIG_PREFIX + "AIM"):
            aim.constraints.remove(c)

    if params.aim_target is None:
        return

    con = aim.constraints.new('TRACK_TO')
    con.name = RIG_PREFIX + "AIM_TRACK"
    con.target = params.aim_target
    con.track_axis = 'TRACK_NEGATIVE_Z'
    con.up_axis = 'UP_Y'
    con.target_space = 'WORLD'
    con.owner_space = 'WORLD'
    con.influence = params.aim_influence


def remove_rig(context, camera_obj):
    """移除 Rig：恢复 Camera 独立世界 transform（保持位姿），删除 Helper。

    遵循 §70：只删除自己 PointerProperty 记录的 Helper。
    """
    params = camera_obj.cine
    helpers = [
        params.rig_root, params.rig_yaw, params.rig_pitch,
        params.rig_base, params.rig_dist, params.rig_aim,
    ]

    # 1. 记录位姿
    M0 = read_evaluated_camera_matrix(context, camera_obj)

    # 2. 解除父子关系并保持世界 transform
    if camera_obj.parent is not None:
        camera_obj.parent = None
        camera_obj.matrix_world = M0

    # 3. 删除 Helper（子级 Empty 随父级删除前需先解除相机 parent 已完成）
    for helper in helpers:
        if helper is not None and helper.name in bpy.data.objects:
            bpy.data.objects.remove(helper, do_unlink=True)

    # 4. 清空引用与状态
    params.rig_root = None
    params.rig_yaw = None
    params.rig_pitch = None
    params.rig_base = None
    params.rig_dist = None
    params.rig_aim = None
    params.enabled = False

    context.evaluated_depsgraph_get().update()
    M1 = read_evaluated_camera_matrix(context, camera_obj)
    return {"before": M0, "after": M1}
