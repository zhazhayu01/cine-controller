"""View3D Sidebar Panel：Cine Controller 主面板。"""
import bpy

from ..core import optical_system, rig


class CINE_PT_panel(bpy.types.Panel):
    bl_label = "Cine Controller"
    bl_idname = "CINE_PT_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Cine"

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == 'CAMERA'

    def draw(self, context):
        layout = self.layout
        camera = context.active_object
        params = camera.cine

        # Origin 始终显示（启用前必须先设置 Origin）
        layout.prop(params, "origin", text="Origin")

        # Enable / Disable
        if params.enabled:
            layout.operator("cine.disable_controller", text="Disable Controller", icon='CANCEL')
            layout.operator("cine.bake", text="Bake to Keyframes", icon='KEYFRAME')
        else:
            layout.operator("cine.enable_controller", text="Enable Controller", icon='PLAY')

        if not params.enabled:
            return

        box = layout.box()
        box.label(text="Transform", icon='EMPTY_ARROWS')
        box.prop(params, "distance")
        box.prop(params, "horizontal")
        box.prop(params, "vertical")
        box.prop(params, "offset")

        box = layout.box()
        box.label(text="Orientation", icon='ORIENTATION_VIEW')
        box.prop(params, "aim_target")
        box.prop(params, "aim_influence")

        box = layout.box()
        box.label(text="Optical", icon='CAMERA_DATA')
        box.prop(params, "focus_target")


def register():
    bpy.utils.register_class(CINE_PT_panel)


def unregister():
    bpy.utils.unregister_class(CINE_PT_panel)
