"""高级震动的启停及多事件编辑入口。"""
import bpy
from ..core import rig, shake


class CINE_OT_toggle_shake(bpy.types.Operator):
    bl_idname = 'cine.toggle_shake'
    bl_label = '程序化震动'
    bl_description = '启停独立震动层；每次冲击独立计时，重叠时叠加，不改基础运镜'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        camera = rig.resolve_camera(context)
        return camera is not None and camera.cine.enabled and camera.cine.rig_root is None

    def execute(self, context):
        camera = rig.resolve_camera(context)
        try:
            if camera.cine.shake_enabled:
                shake.disable(context, camera)
            else:
                if not camera.cine.shake_events:
                    shake.add_event(context, camera)
                shake.enable(context, camera)
        except (ValueError, RuntimeError) as error:
            self.report({'ERROR'}, str(error))
            return {'CANCELLED'}
        return {'FINISHED'}


def _remove_curves(camera, prefix):
    animation = camera.animation_data
    if animation is None:
        return
    for curve in list(animation.drivers):
        if curve.data_path.startswith(prefix):
            animation.drivers.remove(curve)
    owners = [(animation, 'action')]
    owners.extend((strip, 'action') for track in animation.nla_tracks for strip in track.strips)
    for owner, attr in owners:
        action = getattr(owner, attr)
        if action is None or not any(fc.data_path.startswith(prefix) for fc in rig._action_curves(action)):
            continue
        if action.users > 1:
            action = action.copy()
            setattr(owner, attr, action)
        collections = []
        if hasattr(action, 'fcurves'):
            collections.append(action.fcurves)
        for layer in getattr(action, 'layers', ()):
            for strip in layer.strips:
                collections.extend(bag.fcurves for bag in getattr(strip, 'channelbags', ()))
        for curves in collections:
            for curve in list(curves):
                if curve.data_path.startswith(prefix):
                    curves.remove(curve)


class CINE_OT_shake_event(bpy.types.Operator):
    bl_idname = 'cine.shake_event'
    bl_label = '编辑震动事件'
    bl_description = '添加、复制或删除独立震动事件；每个事件保存自己的时间、强度和频率'
    bl_options = {'REGISTER', 'UNDO'}
    action: bpy.props.EnumProperty(name='操作', items=[('ADD', '添加', '在当前帧添加一次冲击'),
        ('DUPLICATE', '复制', '复制当前事件，之后可修改发生时间'), ('REMOVE', '删除', '仅删除当前事件及其动画')])

    @classmethod
    def poll(cls, context):
        camera = rig.resolve_camera(context)
        return camera is not None and camera.cine.enabled

    def execute(self, context):
        camera = rig.resolve_camera(context)
        params = camera.cine
        rig.make_independent(context, camera)
        index = min(params.shake_index, len(params.shake_events)-1)
        if self.action != 'ADD' and index < 0:
            return {'CANCELLED'}
        try:
            if self.action == 'ADD':
                shake.add_event(context, camera)
            elif self.action == 'DUPLICATE':
                shake.add_event(context, camera, params.shake_events[index])
            else:
                prefix = params.shake_events[index].path_from_id()+'.'
                _remove_curves(camera, prefix)
                params.shake_events.remove(index)
                params.shake_index = max(0, index-1)
                if params.shake_enabled:
                    shake.rebuild(context, camera)
        except (ValueError, RuntimeError) as error:
            self.report({'ERROR'}, str(error))
            return {'CANCELLED'}
        return {'FINISHED'}


def register():
    for cls in (CINE_OT_toggle_shake, CINE_OT_shake_event):
        bpy.utils.register_class(cls)


def unregister():
    for cls in (CINE_OT_shake_event, CINE_OT_toggle_shake):
        bpy.utils.unregister_class(cls)
