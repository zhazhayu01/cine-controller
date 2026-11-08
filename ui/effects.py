"""低频功能：高级效果及子面板默认折叠，不占用日常主面板。"""
import bpy
from ..core import rig, dolly_zoom
from ..preferences import get_preferences
from . import icons
from .panel import _prop


def _event(camera):
    p = camera.cine
    return p.shake_events[min(p.shake_index, len(p.shake_events)-1)] if p.shake_events else None


class CINE_UL_shake_events(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        layout.prop(item, 'enabled', text='')
        layout.prop(item, 'label', text='', emboss=False)
        layout.label(text=f'{item.start:g} 帧')


class CINE_PT_advanced(bpy.types.Panel):
    bl_label = '高级效果'
    bl_idname = 'CINE_PT_advanced'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Cine'
    bl_parent_id = 'CINE_PT_panel'
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        camera = rig.resolve_camera(context)
        return camera is not None and camera.cine.enabled and camera.cine.rig_root is None

    def draw(self, context):
        pass


class CINE_PT_dolly(bpy.types.Panel):
    bl_label = '希区柯克变焦'
    bl_idname = 'CINE_PT_dolly'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Cine'
    bl_parent_id = 'CINE_PT_advanced'
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        camera = rig.resolve_camera(context)
        return camera is not None and camera.cine.controller is not None

    def draw(self, context):
        camera = rig.resolve_camera(context)
        enabled = dolly_zoom.is_enabled(camera)
        prefs = get_preferences(context)
        labels = prefs.show_labels if prefs else False
        target = self.layout.row()
        target.enabled = not enabled
        _prop(target, camera.cine.controller.cine, 'dolly_target', 'CAMERA_STEREO', '主体', labels)
        self.layout.operator('cine.toggle_dolly_zoom', text='停用' if enabled else '启用',
                             depress=enabled, **icons.kwargs('dolly', 'CAMERA_STEREO'))
        if enabled:
            _prop(self.layout, camera.cine.controller.cine, 'dolly_travel', 'DRIVER_DISTANCE', '附加推拉', labels)
            warning = dolly_zoom.compensation_warning(camera)
            if warning:
                self.layout.label(text=warning, icon='ERROR')


class CINE_PT_shake(bpy.types.Panel):
    bl_label = '程序化震动'
    bl_idname = 'CINE_PT_shake'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Cine'
    bl_parent_id = 'CINE_PT_advanced'
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        camera = rig.resolve_camera(context)
        p = camera.cine
        self.layout.operator('cine.toggle_shake', text='停用震动' if p.shake_enabled else '启用震动',
                             icon='MOD_WAVE', depress=p.shake_enabled)
        if not p.shake_enabled:
            return
        self.layout.prop(p, 'shake_strength')
        row = self.layout.row()
        row.template_list('CINE_UL_shake_events', '', p, 'shake_events', p, 'shake_index', rows=3)
        buttons = row.column(align=True)
        for action, icon in (('ADD', 'ADD'), ('DUPLICATE', 'DUPLICATE'), ('REMOVE', 'REMOVE')):
            buttons.operator('cine.shake_event', text='', icon=icon).action = action
        event = _event(camera)
        if event:
            for field in ('kind', 'start', 'duration', 'strength', 'frequency'):
                self.layout.prop(event, field)
            if event.kind == 'IMPACT':
                self.layout.prop(event, 'decay')


class CINE_PT_shake_detail(bpy.types.Panel):
    bl_label = '方向与随机'
    bl_idname = 'CINE_PT_shake_detail'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Cine'
    bl_parent_id = 'CINE_PT_shake'
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        camera = rig.resolve_camera(context)
        return camera is not None and camera.cine.shake_enabled and _event(camera) is not None

    def draw(self, context):
        event = _event(rig.resolve_camera(context))
        self.layout.label(text='位移：右／上／前')
        for index, name in enumerate(('右', '上', '前')):
            self.layout.prop(event, 'position', index=index, text=name)
        self.layout.label(text='旋转：镜头自身轴')
        for index, name in enumerate(('俯仰', '摇摄', '翻滚')):
            self.layout.prop(event, 'rotation', index=index, text=name)
        self.layout.prop(event, 'seed')


CLASSES = (CINE_UL_shake_events, CINE_PT_advanced, CINE_PT_dolly, CINE_PT_shake, CINE_PT_shake_detail)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
