"""PropertyGroup 参数定义。

参数挂在 Camera 对象上（PointerProperty），由 Blender 自身保存到 .blend，
File Load 后自然恢复，插件不在 load_post 里重新初始化。

每个 Property 的 update 必须最小副作用（规范 §66）：
    Distance / Horizontal / Vertical → 由原生 Driver 计算空间变换
    Aim → 只影响内部朝向计算
    Focus → 只影响 Camera Data DOF
"""
import bpy


def _target_poll(self, target):
    return target != self.id_data and target not in self.id_data.children_recursive


def _origin_update(self, context):
    """Origin 变化：反解新 orbit 参数，保持位姿不跳。

    只在 Controller 已启用时生效；未启用时 build_rig 会读取 origin。
    """
    from . import rig
    camera = self.id_data
    if camera is not None and camera.type == 'CAMERA' and camera.cine.enabled:
        rig._apply_origin(context, camera, self.origin)


def _aim_update(self, context):
    """Aim 目标变化时更新驱动依赖，不写回摄像机变换。"""
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
        name="已启用",
        default=False,
        description="控制器是否启用",
    )
    rig_uuid: bpy.props.StringProperty(
        name="控制器标识",
        default="",
        description="识别控制器所属摄像机，不参与变换计算",
    )
    rig_version: bpy.props.IntProperty(
        name="控制器版本",
        default=1,
        description="控制器数据结构版本，用于升级迁移",
    )

    # ---- Transform System ----
    position_source: bpy.props.PointerProperty(
        name="参考相机", type=bpy.types.Object,
        poll=lambda self, obj: obj.type == 'CAMERA' and obj != self.id_data,
        description="先用自由相机摆好机位，再导入其位置；不复制朝向、焦距或动画",
    )
    controller: bpy.props.PointerProperty(
        name="曲线控制器", type=bpy.types.Object,
        poll=lambda _self, obj: obj.type == 'CURVE', options={'HIDDEN'},
        description="可见的整体移动/旋转控制对象；内部运算仍保留在摄像机上",
    )
    origin: bpy.props.PointerProperty(
        name="空间原点",
        type=bpy.types.Object,
        update=_origin_update,
        poll=_target_poll,
        description="轨道原点目标，使用目标的世界位置",
    )
    distance: bpy.props.FloatProperty(
        name="距离",
        default=10.0,
        subtype='DISTANCE',
        description="摄像机到空间原点的轨道半径",
    )
    horizontal: bpy.props.FloatProperty(
        name="水平环绕",
        default=0.0,
        subtype='ANGLE',
        description="绕空间竖直轴的水平方位角",
    )
    vertical: bpy.props.FloatProperty(
        name="垂直环绕",
        default=0.0,
        subtype='ANGLE',
        description="垂直环绕角，0 为水平，-90° 位于中心正上方，+90° 位于中心正下方",
    )
    offset: bpy.props.FloatVectorProperty(
        name="空间偏移（右 / 上 / 前）",
        default=(0.0, 0.0, 0.0),
        subtype='TRANSLATION',
        size=3,
        description="镜头空间偏移：X 为向右、Y 为向上、Z 为向前",
    )

    # ---- Orientation System ----
    aim_target: bpy.props.PointerProperty(
        name="瞄准目标",
        type=bpy.types.Object,
        update=_aim_update,
        poll=_target_poll,
        description="镜头瞄准的目标，只影响朝向",
    )
    aim_influence: bpy.props.FloatProperty(
        name="瞄准权重",
        default=0.0,
        min=0.0,
        max=1.0,
        description="瞄准混合权重，0 为原朝向，1 为完全瞄准目标",
    )
    pan: bpy.props.FloatProperty(
        name="水平摇摄",
        default=0.0,
        subtype='ANGLE',
        description="绕镜头向上轴（本地 +Y）的水平摇摄角",
    )
    tilt: bpy.props.FloatProperty(
        name="俯仰",
        default=0.0,
        subtype='ANGLE',
        description="绕镜头向右轴（本地 +X）的俯仰角",
    )
    roll: bpy.props.FloatProperty(
        name="翻滚",
        default=0.0,
        subtype='ANGLE',
        description="绕镜头前向轴（本地 -Z）的翻滚角",
    )

    # ---- Optical System ----
    focus_target: bpy.props.PointerProperty(
        name="对焦目标",
        type=bpy.types.Object,
        update=_focus_update,
        description="焦点目标，只影响景深，不改变摄像机位姿",
    )

    # ---- 希区柯克运行数据存于曲线控制器，隔离镜头数据与相机求值之间的循环依赖 ----
    dolly_enabled: bpy.props.BoolProperty(default=False, options={'HIDDEN'})
    dolly_travel: bpy.props.FloatProperty(
        name="镜头轴推拉", default=0.0, subtype='DISTANCE',
        update=lambda self, _context: self.id_data.update_tag(),
        description="正值沿镜头前向推进，负值后退；焦距自动补偿主体的画面大小",
    )
    dolly_target: bpy.props.PointerProperty(
        name="希区柯克主体", type=bpy.types.Object,
        description="留空时使用瞄准目标或空间原点，否则锁定启用时的控制器中心",
    )
    dolly_graph: bpy.props.PointerProperty(type=bpy.types.NodeTree, options={'HIDDEN'})
    dolly_base_position: bpy.props.FloatVectorProperty(size=3, options={'HIDDEN'})
    dolly_base_rotation: bpy.props.FloatVectorProperty(size=4, default=(1, 0, 0, 0), options={'HIDDEN'})
    dolly_forward: bpy.props.FloatVectorProperty(size=3, default=(0, 1, 0), options={'HIDDEN'})
    dolly_anchor: bpy.props.FloatVectorProperty(size=3, options={'HIDDEN'})
    dolly_base_lens: bpy.props.FloatProperty(default=50, options={'HIDDEN'})
    dolly_reference_depth: bpy.props.FloatProperty(default=5, options={'HIDDEN'})

    # ---- 内部空间基准：保存在工程里，不生成辅助对象 ----
    internal_graph: bpy.props.PointerProperty(type=bpy.types.NodeTree, options={'HIDDEN'})
    base_rotation: bpy.props.FloatVectorProperty(
        size=4, default=(1.0, 0.0, 0.0, 0.0), options={'HIDDEN'},
    )
    origin_fallback: bpy.props.FloatVectorProperty(
        size=3, default=(0.0, 0.0, 0.0), options={'HIDDEN'},
    )

    # ---- 仅供旧版工程升级读取，新控制器不使用 Helper ----
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
    bpy.types.Scene.cine_camera = bpy.props.PointerProperty(
        name="摄像机", type=bpy.types.Object,
        poll=lambda _self, obj: obj.type == 'CAMERA',
        description="未选中摄像机时，Cine 面板继续控制此摄像机",
    )
    bpy.types.Object.cine_camera = bpy.props.PointerProperty(
        name="控制的摄像机", type=bpy.types.Object,
        poll=lambda _self, obj: obj.type == 'CAMERA', options={'HIDDEN'},
    )


def unregister():
    del bpy.types.Object.cine_camera
    del bpy.types.Scene.cine_camera
    del bpy.types.Object.cine
    bpy.utils.unregister_class(CineControllerParams)
