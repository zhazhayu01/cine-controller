"""控制器轨迹绑定、暂停与恢复入口。"""
import bpy

from ..core import rig, path_follow


class CINE_OT_bind_path(bpy.types.Operator):
    bl_idname = 'cine.bind_path'
    bl_label = '绑定样条轨迹'
    bl_description = '将控制器中心移到轨迹起点；之后调整路径进度，原相机距离与环绕继续作为相对偏移'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        camera = rig.resolve_camera(context)
        return camera is not None and camera.cine.enabled and camera.cine.controller is not None

    def execute(self, context):
        camera = rig.resolve_camera(context)
        try:
            path_follow.bind(context, camera, camera.cine.path_target)
        except (ValueError, RuntimeError) as error:
            self.report({'ERROR'}, str(error))
            return {'CANCELLED'}
        return {'FINISHED'}


class CINE_OT_toggle_path(bpy.types.Operator):
    bl_idname = 'cine.toggle_path'
    bl_label = '暂停或恢复轨迹'
    bl_description = '暂停时保持当前控制器位姿，恢复时重新沿轨迹求值；保留路径进度动画'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        camera = rig.resolve_camera(context)
        return camera is not None and path_follow.get_constraint(camera.cine.controller) is not None

    def execute(self, context):
        camera = rig.resolve_camera(context)
        constraint = path_follow.get_constraint(camera.cine.controller)
        try:
            if constraint.mute:
                path_follow.resume(context, camera)
            else:
                path_follow.unbind(context, camera)
        except (ValueError, RuntimeError) as error:
            self.report({'ERROR'}, str(error))
            return {'CANCELLED'}
        return {'FINISHED'}


CLASSES = (CINE_OT_bind_path, CINE_OT_toggle_path)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
