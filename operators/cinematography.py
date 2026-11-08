"""曲线控制器的镜头关键帧、相机视图、构图与希区柯克工具入口。"""
import bpy

from ..core import rig, dolly_zoom, path_follow

SPACE_FIELDS = ('distance', 'horizontal', 'vertical', 'offset', 'pan', 'tilt', 'roll')
OPTICAL_FIELDS = ('lens', 'ortho_scale', 'sensor_width', 'shift_x', 'shift_y',
                  'dof.focus_distance', 'dof.aperture_fstop')


def _key(owner, path, frame, group):
    animation = owner.animation_data
    if animation and any(curve.data_path == path for curve in animation.drivers):
        return  # 不给工具或外部驱动器的输出插关键帧。
    owner.keyframe_insert(data_path=path, frame=frame, group=group)


class CINE_OT_import_camera_position(bpy.types.Operator):
    bl_idname = 'cine.import_camera_position'
    bl_label = '从参考相机反推完整位姿'
    bl_description = '相对控制器和空间原点反推位置与朝向：距离、水平与垂直环绕、摇摄、俯仰、翻滚；清零偏移并关闭瞄准影响'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        camera = rig.resolve_camera(context)
        return camera is not None and camera.cine.enabled and camera.cine.position_source is not None

    def execute(self, context):
        camera = rig.resolve_camera(context)
        try:
            distance, _horizontal, _vertical = rig.import_camera_position(context, camera, camera.cine.position_source, full_pose=True)
        except (ValueError, RuntimeError) as error:
            self.report({'ERROR'}, str(error))
            return {'CANCELLED'}
        self.report({'INFO'}, f'已匹配参考相机的位置和朝向，距离 {distance:.3f}')
        return {'FINISHED'}


class CINE_OT_keyframe_camera(bpy.types.Operator):
    bl_idname = 'cine.keyframe_camera'
    bl_label = '插入镜头关键帧'
    bl_description = '记录控制器移动旋转、相机空间参数、焦距及镜头偏移；希区柯克启用时记录推拉量'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        camera = rig.resolve_camera(context)
        return context.mode == 'OBJECT' and camera is not None and camera.cine.enabled

    def execute(self, context):
        camera = rig.resolve_camera(context)
        control = camera.cine.controller
        frame = context.scene.frame_current + context.scene.frame_subframe
        if control is not None and camera.parent == control:
            constraint = path_follow.get_constraint(control)
            if constraint is not None:
                if not constraint.mute:
                    _key(control, constraint.path_from_id('offset_factor'), frame, 'Cine 轨迹')
            else:
                _key(control, 'location', frame, 'Cine 控制器')
                path = 'rotation_quaternion' if control.rotation_mode == 'QUATERNION' else 'rotation_axis_angle' if control.rotation_mode == 'AXIS_ANGLE' else 'rotation_euler'
                _key(control, path, frame, 'Cine 控制器')
        if dolly_zoom.is_enabled(camera):
            _key(control, 'cine.dolly_travel', frame, 'Cine 希区柯克')
            if dolly_zoom.has_distance_control(camera):
                _key(control, 'cine.dolly_distance', frame, 'Cine 希区柯克')
        else:
            for field in SPACE_FIELDS:
                _key(camera, 'cine.' + field, frame, 'Cine 空间')
        for field in OPTICAL_FIELDS:
            _key(camera.data, field, frame, 'Cine 光学')
        if camera.cine.shake_enabled:
            _key(camera, 'cine.shake_strength', frame, 'Cine 震动')
        self.report({'INFO'}, f'已记录镜头关键帧：{frame:g}')
        return {'FINISHED'}


class CINE_OT_toggle_dolly_zoom(bpy.types.Operator):
    bl_idname = 'cine.toggle_dolly_zoom'
    bl_label = '希区柯克变焦'
    bl_description = '启用时捕获当前镜头和主体深度，推拉与焦距自动联动；停用时返回原参数运镜'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def description(cls, context, properties):
        camera = rig.resolve_camera(context)
        if camera is not None and dolly_zoom.is_enabled(camera):
            return '停用希区柯克，返回原空间参数和焦距动画；保留当前效果请使用烘焙'
        return '启用希区柯克，捕获当前机位与主体深度；调整推拉数值时自动补偿焦距'

    @classmethod
    def poll(cls, context):
        camera = rig.resolve_camera(context)
        return camera is not None and camera.cine.enabled and camera.cine.controller is not None and camera.parent == camera.cine.controller

    def execute(self, context):
        camera = rig.resolve_camera(context)
        try:
            if dolly_zoom.is_enabled(camera):
                dolly_zoom.disable(context, camera)
            else:
                dolly_zoom.enable(context, camera)
        except (ValueError, RuntimeError) as error:
            self.report({'ERROR'}, str(error))
            return {'CANCELLED'}
        return {'FINISHED'}


class CINE_OT_camera_view(bpy.types.Operator):
    bl_idname = 'cine.camera_view'
    bl_label = '进入此相机视图'
    bl_description = '将所选摄像机或控制器对应镜头设为场景活动相机并进入视图，使用 Blender 标准相机切换'

    @classmethod
    def poll(cls, context):
        return rig.resolve_camera(context) is not None and context.area is not None and context.area.type == 'VIEW_3D'

    def execute(self, context):
        context.space_data.use_local_camera = False
        context.scene.camera = rig.resolve_camera(context)
        context.space_data.region_3d.view_perspective = 'CAMERA'
        return {'FINISHED'}


class CINE_OT_set_render_camera(bpy.types.Operator):
    bl_idname = 'cine.set_render_camera'
    bl_label = '设为渲染相机'
    bl_description = '将当前控制器对应的摄像机设为场景渲染摄像机'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return rig.resolve_camera(context) is not None

    def execute(self, context):
        context.scene.camera = rig.resolve_camera(context)
        return {'FINISHED'}


class CINE_OT_reset_lens_shift(bpy.types.Operator):
    bl_idname = 'cine.reset_lens_shift'
    bl_label = '清零镜头偏移'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return rig.resolve_camera(context) is not None

    def execute(self, context):
        data = rig.resolve_camera(context).data
        data.shift_x = data.shift_y = 0
        return {'FINISHED'}


CLASSES = (CINE_OT_import_camera_position, CINE_OT_keyframe_camera, CINE_OT_toggle_dolly_zoom, CINE_OT_camera_view,
           CINE_OT_set_render_camera, CINE_OT_reset_lens_shift)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
