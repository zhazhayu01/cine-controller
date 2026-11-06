"""停用控制器 Operator。

移除 Rig，Camera 恢复为普通相机并保持当前位姿。
"""
import bpy

from ..core import rig, preserve_pose, dolly_zoom


class CINE_OT_disable(bpy.types.Operator):
    bl_idname = "cine.disable_controller"
    bl_label = "停用控制器"
    bl_description = "移除内部控制器，摄像机保持当前位姿"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = rig.resolve_camera(context)
        if obj is not None and dolly_zoom.is_enabled(obj):
            cls.poll_message_set('希区柯克启用期间，请先停用该工具，或烘焙机位和焦距后再解除控制器')
            return False
        return obj is not None and obj.type == 'CAMERA' and obj.cine.enabled

    def execute(self, context):
        camera = rig.resolve_camera(context)
        result = rig.remove_rig(context, camera)
        before = result["before"]
        after = result["after"]

        if not preserve_pose.matrix_close(before, after):
            self.report({'WARNING'}, "停用后位姿发生变化")
            return {'CANCELLED'}

        self.report({'INFO'}, "控制器已停用")
        return {'FINISHED'}


def register():
    bpy.utils.register_class(CINE_OT_disable)


def unregister():
    bpy.utils.unregister_class(CINE_OT_disable)
