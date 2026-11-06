"""常驻紧凑侧栏：图标操作、数值输入与原生悬停提示。"""
import bpy

from ..core import rig, dolly_zoom
from ..preferences import get_preferences, GUIDES


def _prop(layout, data, path, icon, name, labels=False):
    # 数值控件不直接传 icon，避免 Blender 把无文字数值框挤成仅图标按钮。
    row = layout.row(align=True)
    row.label(text='', icon=icon)
    row.prop(data, path, text=name if labels else '')


class CINE_PT_panel(bpy.types.Panel):
    bl_label = 'Cine'
    bl_idname = 'CINE_PT_panel'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Cine'
    bl_ui_units_x = 15

    @classmethod
    def poll(cls, context):
        return context.scene is not None

    def draw(self, context):
        layout = self.layout
        prefs = get_preferences(context)
        labels = prefs.show_labels if prefs is not None else False
        camera = rig.resolve_camera(context)
        row = layout.row(align=True)
        row.operator('cine.create_camera', text='', icon='ADD')
        row.operator('cine.camera_view', text='', icon='VIEW_CAMERA')
        row.operator('cine.set_render_camera', text='', icon='RENDER_STILL')
        row.operator('cine.keyframe_camera', text='', icon='KEY_HLT')
        row.operator('cine.open_preferences', text='', icon='PREFERENCES')

        active = context.active_object
        direct = active is not None and (active == camera or (active.type == 'CURVE' and active.cine_camera == camera))
        if camera is not None and direct:
            layout.label(text=camera.name, icon='CAMERA_DATA')
        else:
            layout.prop(context.scene, 'cine_camera', text='', icon='CAMERA_DATA')
        if camera is None:
            return
        params = camera.cine
        if params.rig_root is not None:
            layout.operator('cine.upgrade_controller', text='', icon='FILE_REFRESH')
            return
        row = layout.row(align=True)
        if not params.enabled:
            row.operator('cine.enable_controller', text='', icon='PLAY')
            return
        if rig.needs_independent_graph(camera):
            row.operator('cine.make_independent', text='', icon='DUPLICATE')
            return
        dolly = dolly_zoom.is_enabled(camera)
        row.operator('cine.disable_controller', text='', icon='CANCEL')
        row.operator('cine.bake', text='', icon='KEYFRAME')
        reset = row.row(align=True)
        reset.enabled = not dolly
        reset.operator('cine.reset_space_axes', text='', icon='FILE_REFRESH')
        if params.controller is not None:
            row.operator('cine.toggle_dolly_zoom', text='', icon='CAMERA_STEREO', depress=dolly)

        row = layout.row(align=True)
        row.enabled = not dolly
        _prop(row, params, 'position_source', 'CAMERA_DATA', '参考相机', labels)
        row.operator('cine.import_camera_position', text='', icon='IMPORT')

        motion = layout.column(align=True)
        motion.enabled = not dolly
        _prop(motion, params, 'origin', 'OBJECT_ORIGIN', '原点', labels)
        _prop(motion, params, 'distance', 'DRIVER_DISTANCE', '距离', labels)
        row = motion.row(align=True)
        _prop(row, params, 'horizontal', 'ORIENTATION_GLOBAL', '水平', labels)
        _prop(row, params, 'vertical', 'ORIENTATION_NORMAL', '垂直', labels)
        row = motion.row(align=True)
        for index, axis in enumerate('XYZ'):
            row.prop(params, 'offset', index=index, text=axis)
        row = motion.row(align=True)
        _prop(row, params, 'pan', 'ORIENTATION_VIEW', '摇摄', labels)
        _prop(row, params, 'tilt', 'CON_ROTLIKE', '俯仰', labels)
        _prop(row, params, 'roll', 'DRIVER_ROTATIONAL_DIFFERENCE', '翻滚', labels)
        _prop(motion, params, 'aim_target', 'CON_TRACKTO', '瞄准', labels)
        if params.aim_target is not None:
            _prop(motion, params, 'aim_influence', 'IPO_LINEAR', '权重', labels)

        row = layout.row()
        row.enabled = not dolly
        if camera.data.type == 'ORTHO':
            _prop(row, camera.data, 'ortho_scale', 'CAMERA_DATA', '范围', labels)
        else:
            _prop(row, camera.data, 'lens', 'CAMERA_DATA', '焦距', labels)
        _prop(layout, camera.data.dof, 'use_dof', 'SHADING_RENDERED', '景深', labels)
        _prop(layout, camera.data.dof, 'focus_object', 'CON_TRACKTO', '对焦目标', labels)
        row = layout.row(align=True)
        row.enabled = camera.data.dof.focus_object is None
        _prop(row, camera.data.dof, 'focus_distance', 'DRIVER_DISTANCE', '对焦距离', labels)
        if camera.data.dof.use_dof:
            _prop(layout, camera.data.dof, 'aperture_fstop', 'SHADING_RENDERED', '光圈', labels)

        row = layout.row(align=True)
        for field, icon in (('show_composition_thirds', 'GRID'), ('show_composition_center', 'PIVOT_CURSOR'),
                            ('show_safe_areas', 'SHADING_BBOX'), ('show_passepartout', 'MOD_MASK')):
            row.prop(camera.data, field, text='', icon=icon, toggle=True)
        if params.controller is not None:
            row = layout.row()
            row.enabled = not dolly
            _prop(row, params.controller.cine, 'dolly_target', 'CAMERA_STEREO', '希区柯克主体', labels)
        if dolly:
            _prop(layout, params.controller.cine, 'dolly_travel', 'DRIVER_DISTANCE', '推拉', labels)
            storage = params.controller.cine.dolly_graph
            if storage and storage.get('_cine2_depth', 1) <= 0:
                layout.label(text='主体在镜头后方', icon='ERROR')


class CINE_PT_camera_settings(bpy.types.Panel):
    bl_label = '相机设置'
    bl_idname = 'CINE_PT_camera_settings'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Cine'
    bl_parent_id = 'CINE_PT_panel'
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        return rig.resolve_camera(context) is not None

    def draw(self, context):
        camera = rig.resolve_camera(context)
        data = camera.data
        layout = self.layout
        optical = layout.column()
        optical.enabled = not dolly_zoom.is_enabled(camera)
        for field, name in (('type', '投影'), ('sensor_fit', '传感器适配'),
                            ('sensor_width', '传感器宽度'), ('sensor_height', '传感器高度')):
            optical.prop(data, field, text=name)
        for field, name in (('clip_start', '近裁剪'), ('clip_end', '远裁剪'),
                            ('shift_x', '水平偏移'), ('shift_y', '垂直偏移')):
            layout.prop(data, field, text=name)
        layout.operator('cine.reset_lens_shift', text='', icon='LOOP_BACK')
        for field, name in GUIDES:
            layout.prop(data, field, text=name)
        layout.prop(data, 'passepartout_alpha', text='遮罩不透明度')


CLASSES = (CINE_PT_panel, CINE_PT_camera_settings)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
