"""Disable Controller Operator。

移除 Rig，Camera 恢复为普通相机并保持当前位姿。
"""
import bpy

from ..core import rig, preserve_pose


class CINE_OT_disable(bpy.types.Operator):
    bl_idname = "cine.disable_controller"
    bl_label = "Disable Controller"
    bl_description = "移除 Cine Rig，Camera 保持当前位姿"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == 'CAMERA' and obj.cine.enabled

    def execute(self, context):
        camera = context.active_object
        result = rig.remove_rig(context, camera)
        before = result["before"]
        after = result["after"]

        if not preserve_pose.matrix_close(before, after):
            self.report({'WARNING'}, "Disable 后位姿发生变化")
            return {'CANCELLED'}

        self.report({'INFO'}, "Controller disabled")
        return {'FINISHED'}


def register():
    bpy.utils.register_class(CINE_OT_disable)


def unregister():
    bpy.utils.unregister_class(CINE_OT_disable)
