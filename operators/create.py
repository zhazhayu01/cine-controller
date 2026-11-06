"""一键创建摄像机和可见曲线控制器，失败只清理本次新建的数据。"""
import bpy

from ..core import rig
from ..core.controller_shape import create_curve_data
from ..preferences import apply_defaults


class CINE_OT_create_camera(bpy.types.Operator):
    bl_idname = 'cine.create_camera'
    bl_label = '创建相机和曲线控制器'
    bl_description = '在 3D 游标处创建曲线控制器和已绑定相机，选中曲线即可移动、旋转和调整镜头'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.scene is not None and context.mode == 'OBJECT'

    def execute(self, context):
        scene = context.scene
        previous_selection = list(context.selected_objects)
        previous_active = context.view_layer.objects.active
        previous_render_camera = scene.camera
        previous_panel_camera = scene.cine_camera
        control = camera = curve_data = camera_data = None
        try:
            curve_data = create_curve_data()
            control = bpy.data.objects.new('Cine_Control', curve_data)
            scene.collection.objects.link(control)
            control.location = scene.cursor.location
            control.show_in_front = True
            control.show_name = True
            control.hide_render = True
            control.display_type = 'WIRE'
            control.color = (1.0, 0.45, 0.05, 1.0)
            control.lock_scale = (True, True, True)

            camera_data = bpy.data.cameras.new('Cine_Camera')
            camera = bpy.data.objects.new('Cine_Camera', camera_data)
            scene.collection.objects.link(camera)
            camera.cine.controller = control
            control.cine_camera = camera
            rig.build_rig(context, camera)
            camera.cine.distance = 5.0
            apply_defaults(context, camera)
            rig.force_update(context, camera)
            if scene.camera is None:
                scene.camera = camera
            for obj in context.selected_objects:
                obj.select_set(False)
            control.select_set(True)
            context.view_layer.objects.active = control
        except Exception as error:
            if camera is not None:
                if camera.cine.internal_graph is not None:
                    rig._clear_graph(camera)
                bpy.data.objects.remove(camera, do_unlink=True)
            if control is not None:
                bpy.data.objects.remove(control, do_unlink=True)
            if camera_data is not None and camera_data.users == 0:
                bpy.data.cameras.remove(camera_data)
            if curve_data is not None and curve_data.users == 0:
                bpy.data.curves.remove(curve_data)
            scene.camera = previous_render_camera
            scene.cine_camera = previous_panel_camera
            for obj in previous_selection:
                obj.select_set(True)
            context.view_layer.objects.active = previous_active
            self.report({'ERROR'}, f'创建失败，已清理本次新建数据：{error}')
            return {'CANCELLED'}
        self.report({'INFO'}, '已创建并绑定摄像机，移动或旋转曲线控制器即可操作镜头')
        return {'FINISHED'}


def register():
    bpy.utils.register_class(CINE_OT_create_camera)


def unregister():
    bpy.utils.unregister_class(CINE_OT_create_camera)
