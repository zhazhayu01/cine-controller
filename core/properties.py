"""PropertyGroup 参数定义。

参数挂在 Camera 对象上（PointerProperty），由 Blender 自身保存到 .blend，
File Load 后自然恢复，插件不在 load_post 里重新初始化。

每个 Property 的 update 必须最小副作用（规范 §66）：
    Distance / Horizontal / Vertical → 只通过 Driver 影响对应 Helper 节点
    Aim → 只影响 Aim 约束
    Focus → 只影响 Camera Data DOF
"""
import bpy


def _aim_update(self, context):
    """Aim 变化：只重建/更新 AIM 节点的 Track To 约束，不触碰 Transform。"""
    from . import rig
    camera = self.id_data
    if camera is not None and camera.type == 'CAMERA' and camera.cine.enabled:
        rig._apply_aim(context, camera)


def _focus_update(self, context):
    """Focus 变化：只写 Camera Data DOF，绝不触碰 Camera Transform。"""
    from . import optical_system
    camera = self.id_data
    if camera is not None and camera.type == 'CAMERA':
        optical_system.apply_focus_to_camera(
            camera,
            focus_target=self.focus_target,
        )


class CineControllerParams(bpy.types.PropertyGroup):
    """Cine Controller 全部参数（Single Source of Truth 的输入端）。"""

    # ---- 身份 / 状态 ----
    enabled: bpy.props.BoolProperty(
        name="Enabled",
        default=False,
        description="Controller 是否启用",
    )
    rig_uuid: bpy.props.StringProperty(
        name="Rig UUID",
        default="",
        description="用于识别这套 Rig 属于哪个 Camera（身份，不参与 Transform）",
    )
    rig_version: bpy.props.IntProperty(
        name="Rig Version",
        default=1,
        description="Rig 数据结构版本，用于未来升级迁移",
    )

    # ---- Transform System ----
    origin: bpy.props.PointerProperty(
        name="Origin",
        type=bpy.types.Object,
        description="轨道原点目标（World Position 来源）",
    )
    distance: bpy.props.FloatProperty(
        name="Distance",
        default=10.0,
        subtype='DISTANCE',
        description="Camera 到 Origin 的轨道半径",
    )
    horizontal: bpy.props.FloatProperty(
        name="Horizontal",
        default=0.0,
        subtype='ANGLE',
        description="绕 World Z 的水平方位角（弧度）",
    )
    vertical: bpy.props.FloatProperty(
        name="Vertical",
        default=0.0,
        subtype='ANGLE',
        description="仰角（弧度），0=水平，+90°=正上方俯视",
    )
    offset: bpy.props.FloatVectorProperty(
        name="Offset",
        default=(0.0, 0.0, 0.0),
        subtype='TRANSLATION',
        size=3,
        description="Cine 逻辑偏移（X=Right, Y=Up, Z=Forward）",
    )

    # ---- Orientation System ----
    aim_target: bpy.props.PointerProperty(
        name="Aim Target",
        type=bpy.types.Object,
        update=_aim_update,
        description="朝向目标（只影响 Orientation）",
    )
    aim_influence: bpy.props.FloatProperty(
        name="Aim Influence",
        default=0.0,
        min=0.0,
        max=1.0,
        update=_aim_update,
        description="Aim 混合权重 [0,1]，由 Blender Track To 约束处理",
    )
    pan: bpy.props.FloatProperty(
        name="Pan",
        default=0.0,
        subtype='ANGLE',
        description="绕 Camera Up（本地 +Y）的水平摇摄角（弧度）",
    )
    tilt: bpy.props.FloatProperty(
        name="Tilt",
        default=0.0,
        subtype='ANGLE',
        description="绕 Camera Right（本地 +X）的俯仰角（弧度）",
    )
    roll: bpy.props.FloatProperty(
        name="Roll",
        default=0.0,
        subtype='ANGLE',
        description="绕 Camera Forward（本地 -Z）的翻滚角（弧度）",
    )

    # ---- Optical System ----
    focus_target: bpy.props.PointerProperty(
        name="Focus Target",
        type=bpy.types.Object,
        update=_focus_update,
        description="焦点目标（只影响 Camera Data DOF，与 Transform 完全解耦）",
    )

    # ---- Rig Helper 引用（内部，PointerProperty，不靠名字查找）----
    rig_root: bpy.props.PointerProperty(type=bpy.types.Object)
    rig_yaw: bpy.props.PointerProperty(type=bpy.types.Object)
    rig_pitch: bpy.props.PointerProperty(type=bpy.types.Object)
    rig_base: bpy.props.PointerProperty(type=bpy.types.Object)
    rig_dist: bpy.props.PointerProperty(type=bpy.types.Object)
    rig_offset: bpy.props.PointerProperty(type=bpy.types.Object)
    rig_aim: bpy.props.PointerProperty(type=bpy.types.Object)
    rig_local_rot: bpy.props.PointerProperty(type=bpy.types.Object)


def register():
    bpy.utils.register_class(CineControllerParams)
    # 挂在 Object 上：所有对象都能带这套参数，但只有 Camera 会真正启用。
    bpy.types.Object.cine = bpy.props.PointerProperty(type=CineControllerParams)


def unregister():
    del bpy.types.Object.cine
    bpy.utils.unregister_class(CineControllerParams)
