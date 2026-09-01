"""Enable Controller Operator。

事务化：记录 Camera 位姿 → build_rig 反解参数 → Matrix 验证 → 失败回滚。
"""
import bpy

from ..core import rig, preserve_pose


class CINE_OT_enable(bpy.types.Operator):
    bl_idname = "cine.enable_controller"
    bl_label = "Enable Controller"
    bl_description = "为当前 Camera 启用 Cine Controller（保持位姿不跳）"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == 'CAMERA'

    def execute(self, context):
        camera = context.active_object
        params = camera.cine

        if params.enabled:
            self.report({'WARNING'}, "Controller already enabled")
            return {'CANCELLED'}

        # Origin：未指定时回退到 (0,0,0) 世界原点（用空对象承载）
        origin = params.origin
        if origin is None:
            self.report({'ERROR'}, "请先设置 Origin Target")
            return {'CANCELLED'}

        result = rig.build_rig(context, camera, origin)
        before = result["before"]
        after = result["after"]

        if not preserve_pose.matrix_close(before, after):
            # 失败回滚：移除 Rig，恢复位姿
            rig.remove_rig(context, camera)
            camera.matrix_world = before
            self.report({'ERROR'}, "Enable 导致位姿漂移，已回滚")
            return {'CANCELLED'}

        self.report({'INFO'}, f"Controller enabled (d={result['params'][0]:.3f})")
        return {'FINISHED'}


def register():
    bpy.utils.register_class(CINE_OT_enable)


def unregister():
    bpy.utils.unregister_class(CINE_OT_enable)
