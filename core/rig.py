"""Rig 构建：Helper 层级 / Constraint / Driver / 参数反解。

规范关键点：
    §9   依赖 Parent Hierarchy + Constraint + Driver（Dependency Graph），
         禁止 frame_change_post / depsgraph_update_post 持续写回 Camera。
    §12  Local / World Space 显式定义；RADIUS 在 BASE 之前（位置与朝向解耦）。
    §13  Camera World Matrix 是最终真相。
    §22/23 关系用 PointerProperty，不靠 Name String 重查。
    §33  Constraint 创建显式指定 owner_space / target_space / track_axis / up_axis / influence。
    §34  Driver 绝对驱动（= horizontal，而非 += horizontal）。
    §35  简单 Driver Variable + Expression，不用自定义 Driver Namespace。

Rig 层级（遵循规范 §12 建议顺序）：
    ROOT   (Empty)  World Position = Origin（Copy Location，world→world）
      └─ YAW    (Empty)  Local rot.z = horizontal        [Driver]
          └─ PITCH  (Empty)  Local rot.x = vertical      [Driver]
              └─ DIST   (Empty)  Local loc.y = -distance  [Driver，位置，在 BASE 之前]
                  └─ BASE   (Empty)  Local rot = 反解的朝向基准   [Enable 时反解]
                      └─ OFFSET (Empty)  Local loc = cine_offset→blender_local  [Driver x3]
                          └─ AIM    (Empty)  Track To → Aim Target, influence [约束]
                              └─ LOCAL_ROT (Empty)  Local euler = (tilt, pan, -roll)  [Driver x3]
                                  └─ CAMERA  (真实 Camera 对象，local = identity)

轴约定（§58，经实测验证）：
    BASE 之后的本地轴 = camera 朝向轴：+X=Right, +Y=Up, -Z=Forward。
    因此 OFFSET.location = (offset.x, offset.y, -offset.z)。
    LOCAL_ROT：tilt=绕 +X(Right), pan=绕 +Y(Up), roll=绕 Forward(-Z) = -euler.z。

位置公式（与 utils.math_utils 一致）：
    R_z(h)·R_x(v)·(0, -d, 0) = (d·sin h·cos v, -d·cos h·cos v, -d·sin v)
"""
import bpy
from math import pi
from mathutils import Matrix, Quaternion

from ..utils import math_utils as mu


def compose_orbit_rotation(horizontal: float, vertical: float) -> Matrix:
    """YAW·PITCH 的累计旋转 R_orbit = R_z(h)·R_x(v)。

    这是「朝向基准」之前的轨道旋转，用于反解 BASE。
    """
    return (
        Matrix.Rotation(horizontal, 4, 'Z')
        @ Matrix.Rotation(vertical, 4, 'X')
    )


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
                   params.rig_dist, params.rig_base, params.rig_offset,
                   params.rig_aim, params.rig_local_rot):
        if helper is not None:
            helper.update_tag()
    context.view_layer.update()
    context.evaluated_depsgraph_get().update()


def _get_rig_collection(context):
    """获取或创建存放 Cine Rig Helper 的独立 Collection。

    集中管理：用户可在 Outliner 一眼看到 rig 结构，并可整体隐藏/禁用。
    默认在视口隐藏 + 渲染禁用 + 从 View Layer 排除（helper 是纯逻辑节点，不参与显示/渲染）。
    实测：exclude 不影响 driver/constraint 求值（camera 不在该集合内）。
    """
    coll = bpy.data.collections.get("Cine Rig")
    if coll is None:
        coll = bpy.data.collections.new("Cine Rig")
        context.scene.collection.children.link(coll)

    # 默认隐藏：视口不可见 + 渲染禁用
    coll.hide_viewport = True
    coll.hide_render = True

    # Exclude from View Layer（作用在 layer_collection 上）
    for lc in _iter_layer_collections(context.view_layer.layer_collection):
        if lc.name == "Cine Rig":
            lc.exclude = True
            break

    return coll


def _iter_layer_collections(layer_collection):
    """递归遍历 view layer 的 layer_collection 树。"""
    yield layer_collection
    for child in layer_collection.children:
        yield from _iter_layer_collections(child)


def _new_empty(context, name: str, parent=None):
    """创建一个 Empty Helper，挂到 Cine Rig Collection，并锁定防误操作。

    锁定只阻止用户在视口误选 / 手动误拖变换；driver 与 constraint 的求值不受影响。
    """
    empty = bpy.data.objects.new("CC_" + name, None)
    empty.empty_display_type = 'PLAIN_AXES'
    empty.empty_display_size = 0.25

    # 锁定：视口不可选 + 锁定 location/rotation/scale（防误操作）
    empty.hide_select = True
    empty.lock_location = (True, True, True)
    empty.lock_rotation = (True, True, True)
    empty.lock_scale = (True, True, True)

    _get_rig_collection(context).objects.link(empty)
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


def _solve_base_rotation(M0: Matrix, horizontal: float, vertical: float) -> Quaternion:
    """反解 BASE 节点的旋转，使 camera 保持 Enable 时的世界朝向。

    camera 世界朝向 = R_orbit(h,v) · R_base（OFFSET/AIM/LOCAL_ROT 均为 identity）。
    要等于 M0 的旋转 R0，则 R_base = R_orbit⁻¹ · R0。

    这样 offset 的轴（BASE 之后）= camera 实际朝向轴，pan/tilt/roll 保持 0。
    """
    r_orbit = compose_orbit_rotation(horizontal, vertical).to_quaternion()
    r0 = M0.to_quaternion()
    return r_orbit.inverted() @ r0


def build_rig(context, camera_obj, origin_obj) -> dict:
    """为 camera_obj 构建 Cine Rig，并反解参数保持位姿不跳。

    返回 {"before": M0, "after": M1, "params": (d, h, v)} 供调用方验证。
    """
    from ..utils.math_utils import solve_orbit_from_pose

    # 1. 记录修改前 Camera evaluated 世界矩阵
    M0 = read_evaluated_camera_matrix(context, camera_obj)

    # 2. 反解 orbit 参数（位置）+ BASE 朝向
    origin_world = origin_obj.matrix_world.to_translation()
    d, h, v = solve_orbit_from_pose(origin_world, M0.to_translation())
    base_quat = _solve_base_rotation(M0, h, v)

    params = camera_obj.cine
    params.distance = d
    params.horizontal = h
    params.vertical = v
    params.origin = origin_obj
    # offset 归零（位置已由 orbit 反解）；pan/tilt/roll 归零（朝向已由 BASE 反解）
    params.offset = (0.0, 0.0, 0.0)
    params.pan = 0.0
    params.tilt = 0.0
    params.roll = 0.0

    # 3. 构建 Helper 层级（DIST 在 BASE 之前）
    root = _new_empty(context, "ROOT", parent=None)
    yaw = _new_empty(context, "YAW", parent=root)
    pitch = _new_empty(context, "PITCH", parent=yaw)
    dist = _new_empty(context, "DIST", parent=pitch)
    base = _new_empty(context, "BASE", parent=dist)
    offset = _new_empty(context, "OFFSET", parent=base)
    aim = _new_empty(context, "AIM", parent=offset)
    local_rot = _new_empty(context, "LOCAL_ROT", parent=aim)

    # BASE 反解的朝向基准（用 QUATERNION 存储，避免 euler↔quat 精度损失）
    base.rotation_mode = 'QUATERNION'
    base.rotation_quaternion = base_quat
    # LOCAL_ROT 显式 XYZ 顺序（§33 不依赖默认值）
    local_rot.rotation_mode = 'XYZ'

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
    # DIST.location.y = -distance（沿本地 -Y 后退 = 轨道半径）
    _add_driver(dist, "location", 1, camera_obj, "cine.distance", "-v")
    # OFFSET.location = (offset.x, offset.y, -offset.z)（Right/Up/Forward → 本地轴）
    _add_driver(offset, "location", 0, camera_obj, "cine.offset[0]", "v")
    _add_driver(offset, "location", 1, camera_obj, "cine.offset[1]", "v")
    _add_driver(offset, "location", 2, camera_obj, "cine.offset[2]", "-v")
    # LOCAL_ROT.rotation_euler = (tilt, pan, -roll)（roll 绕 Forward=-Z）
    _add_driver(local_rot, "rotation_euler", 0, camera_obj, "cine.tilt", "v")
    _add_driver(local_rot, "rotation_euler", 1, camera_obj, "cine.pan", "v")
    _add_driver(local_rot, "rotation_euler", 2, camera_obj, "cine.roll", "-v")

    # 6. Camera 本地 transform = identity（朝向差异已进 BASE，位置已进 orbit）
    camera_obj.parent = local_rot
    camera_obj.matrix_local = Matrix.Identity(4)

    # 7. 记录 Helper 引用到参数（PointerProperty，不靠名字）
    params.rig_root = root
    params.rig_yaw = yaw
    params.rig_pitch = pitch
    params.rig_dist = dist
    params.rig_base = base
    params.rig_offset = offset
    params.rig_aim = aim
    params.rig_local_rot = local_rot
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
        if c.type == 'TRACK_TO' and c.name.startswith("CC_AIM"):
            aim.constraints.remove(c)

    if params.aim_target is None:
        return

    con = aim.constraints.new('TRACK_TO')
    con.name = "CC_AIM_TRACK"
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
        params.rig_dist, params.rig_base, params.rig_offset,
        params.rig_aim, params.rig_local_rot,
    ]

    # 1. 记录位姿
    M0 = read_evaluated_camera_matrix(context, camera_obj)

    # 2. 解除父子关系并保持世界 transform
    if camera_obj.parent is not None:
        camera_obj.parent = None
        camera_obj.matrix_world = M0

    # 3. 删除 Helper
    for helper in helpers:
        if helper is not None and helper.name in bpy.data.objects:
            bpy.data.objects.remove(helper, do_unlink=True)

    # 3b. 若 Cine Rig Collection 已空，清理之（只删自己的空集合）
    coll = bpy.data.collections.get("Cine Rig")
    if coll is not None and len(coll.objects) == 0 and len(coll.children) == 0:
        bpy.data.collections.remove(coll)

    # 4. 清空引用与状态
    params.rig_root = None
    params.rig_yaw = None
    params.rig_pitch = None
    params.rig_dist = None
    params.rig_base = None
    params.rig_offset = None
    params.rig_aim = None
    params.rig_local_rot = None
    params.enabled = False

    context.evaluated_depsgraph_get().update()
    M1 = read_evaluated_camera_matrix(context, camera_obj)
    return {"before": M0, "after": M1}
