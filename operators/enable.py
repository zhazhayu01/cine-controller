"""启用控制器 Operator。

事务化：记录原位姿 → 清零并绑定 → 验证清零结果 → 失败恢复原位姿。
"""
import bpy

from ..core import rig, preserve_pose


class CINE_OT_enable(bpy.types.Operator):
    bl_idname = "cine.enable_controller"
    bl_label = "启用控制器"
    bl_description = "基础位置/旋转归零，以空间原点为基准启用控制器，默认水平朝 +Y、Z 向上"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = rig.resolve_camera(context)
        return obj is not None and obj.type == 'CAMERA'

    def execute(self, context):
        camera = rig.resolve_camera(context)
        params = camera.cine

        if params.enabled:
            self.report({'WARNING'}, "控制器已启用")
            return {'CANCELLED'}

        # 未指定 Origin 时直接使用世界原点，不创建辅助对象。
        origin = params.origin
        try:
            result = rig.build_rig(context, camera, origin)
        except (ValueError, RuntimeError) as error:
            self.report({'ERROR'}, str(error))
            return {'CANCELLED'}
        before = result["before"]
        after = result["after"]

        if not preserve_pose.matrix_close(result["expected"], after):
            # 失败回滚：移除 Rig，恢复位姿
            rig.remove_rig(context, camera)
            camera.matrix_world = before
            self.report({'ERROR'}, "绑定后的位姿与默认空间基准不符，已恢复原位姿")
            return {'CANCELLED'}

        self.report({'INFO'}, f"控制器已启用（距离={result['params'][0]:.3f}）")
        return {'FINISHED'}


class CINE_OT_upgrade(bpy.types.Operator):
    bl_idname = 'cine.upgrade_controller'
    bl_label = '升级内部控制器'
    bl_description = '将旧版空物体层级迁移为摄像机内部驱动器，保留画面和参数动画'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        camera = rig.resolve_camera(context)
        return camera is not None and camera.cine.enabled and camera.cine.rig_root is not None

    def execute(self, context):
        try:
            rig.upgrade_rig(context, rig.resolve_camera(context))
        except (ValueError, RuntimeError) as error:
            self.report({'ERROR'}, str(error))
            return {'CANCELLED'}
        self.report({'INFO'}, '已升级为内部控制器，旧版辅助对象已移除')
        return {'FINISHED'}


class CINE_OT_make_independent(bpy.types.Operator):
    bl_idname = 'cine.make_independent'
    bl_label = '独立化摄像机副本'
    bl_description = '将复制摄像机的内部计算数据独立，避免多个镜头共用控制结果'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        camera = rig.resolve_camera(context)
        return camera is not None and camera.cine.enabled and rig.needs_independent_graph(camera)

    def execute(self, context):
        rig.make_independent(context, rig.resolve_camera(context))
        return {'FINISHED'}


class CINE_OT_reset_space_axes(bpy.types.Operator):
    bl_idname = 'cine.reset_space_axes'
    bl_label = '重置为水平轴向'
    bl_description = '清零环绕、偏移和局部旋转，恢复水平拍摄基准；保留距离、原点和瞄准设置'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        camera = rig.resolve_camera(context)
        return camera is not None and camera.cine.enabled and camera.cine.internal_graph is not None

    def execute(self, context):
        try:
            rig.reset_space_axes(context, rig.resolve_camera(context))
        except ValueError as error:
            self.report({'ERROR'}, str(error))
            return {'CANCELLED'}
        return {'FINISHED'}


def register():
    bpy.utils.register_class(CINE_OT_enable)
    bpy.utils.register_class(CINE_OT_upgrade)
    bpy.utils.register_class(CINE_OT_make_independent)
    bpy.utils.register_class(CINE_OT_reset_space_axes)


def unregister():
    bpy.utils.unregister_class(CINE_OT_reset_space_axes)
    bpy.utils.unregister_class(CINE_OT_make_independent)
    bpy.utils.unregister_class(CINE_OT_upgrade)
    bpy.utils.unregister_class(CINE_OT_enable)
