"""图标中文说明与原生参数中文翻译；不复制参数、不改变用户语言配置。"""
import bpy

INFO = {
    'position_source': ('参考相机', 'camera', '先用自由相机摆好镜头，再点击右侧按钮完整反推位置和朝向'),
    'origin': ('空间原点', 'origin', '环绕使用的中心目标；留空时使用镜头已保存的中心'),
    'distance': ('距离', 'distance', '相机与空间原点之间的轨道半径；控制远近，不是上下移动'),
    'dolly_distance': ('距离（希区柯克）', 'distance', '减小距离向主体推进，增大距离后退；焦距同步补偿；实体主体按投影包围盒高度保持，参考点按所在平面保持'),
    'horizontal': ('水平环绕', 'orbit_h', '围绕空间原点横向移动机位；区别于相机自身水平摇摄'),
    'vertical': ('垂直环绕', 'orbit_v', '围绕空间原点纵向移动机位；负角度升高，正角度降低'),
    'pan': ('水平摇摄', 'pan', '相机位置不变，绕镜头向上轴左右转动朝向'),
    'tilt': ('俯仰', 'tilt', '相机位置不变，绕镜头向右轴上下转动朝向'),
    'roll': ('翻滚', 'roll', '相机位置不变，绕镜头前向轴转动画面，使地平线倾斜'),
    'lens': ('焦距', 'lens', '以毫米为单位；焦距越大，取景越窄。希区柯克启用时由工具联动'),
    'ortho_scale': ('正交范围', 'lens', '正交相机的取景范围，数值越大，画面包含的范围越大'),
    'use_dof': ('景深', 'dof', '开启后使用对焦目标或对焦距离，并通过光圈控制前后景虚化'),
    'focus_object': ('对焦目标', 'focus', '将此物体位置作为焦点；指定后不使用手动对焦距离，不改变机位'),
    'focus_distance': ('对焦距离', 'focus_distance', '相机到焦平面的距离；指定对焦目标后由目标位置决定'),
    'aperture_fstop': ('光圈', 'aperture', '光圈 F 值；数值越小，通常景深越浅、背景越虚'),
    'dolly_target': ('希区柯克主体', 'subject', '选择变焦推拉时需要保持画面大小的主体；启用前设置'),
    'dolly_travel': ('希区柯克推拉', 'dolly', '沿捕获的镜头前向推进或后退，工具自动补偿焦距'),
    'path_target': ('轨迹曲线', 'path', '选择独立的单样条曲线，用于驱动控制器中心移动'),
    'offset_factor': ('路径进度', 'progress', '0 对应路径起点，1 对应终点；可插入关键帧制作轨迹运动'),
    'use_curve_follow': ('跟随轨迹朝向', 'path_follow', '开启后控制器沿曲线切线转向；关闭时保留控制器原旋转'),
    'type': ('投影方式', 'camera', '透视相机有近大远小关系；正交相机不随距离改变投影大小'),
    'sensor_fit': ('传感器适配', 'lens', '选择按画幅宽度、高度或自动方式适配传感器尺寸'),
    'sensor_width': ('传感器宽度', 'lens', '传感器的宽度，单位为毫米；与焦距共同决定视角'),
    'sensor_height': ('传感器高度', 'lens', '传感器的高度，单位为毫米'),
    'clip_start': ('近裁剪', 'distance', '比此距离更靠近相机的几何体不参与取景'),
    'clip_end': ('远裁剪', 'distance', '比此距离更远离相机的几何体不参与取景'),
    'shift_x': ('水平镜头偏移', 'center', '水平平移画幅，不旋转相机，可用于偏心构图'),
    'shift_y': ('垂直镜头偏移', 'center', '垂直平移画幅，不旋转相机，可用于建筑构图'),
    'show_composition_thirds': ('三分构图线', 'thirds', '在相机视图中显示横向和纵向三等分参考线，不进入渲染'),
    'show_composition_center': ('中心构图线', 'center', '在相机视图中显示画面中心参考线，不进入渲染'),
    'show_composition_center_diagonal': ('对角构图线', 'center', '在相机视图中显示对角参考线，不进入渲染'),
    'show_composition_golden': ('黄金分割线', 'thirds', '在相机视图中显示黄金分割参考线，不进入渲染'),
    'show_safe_areas': ('安全框', 'safe', '显示动作与字幕的安全区域参考框，不进入渲染'),
    'show_passepartout': ('画幅外遮罩', 'mask', '遮暗相机画幅之外的区域，帮助集中注意力'),
    'passepartout_alpha': ('遮罩不透明度', 'mask', '控制画幅外遮罩的深浅；0 为完全透明，1 为完全遮挡'),
}


class CINE_OT_parameter_info(bpy.types.Operator):
    bl_idname = 'cine.parameter_info'
    bl_label = '参数说明'
    bl_description = '查看此参数的中文名称和作用'
    help_text: bpy.props.StringProperty(name='说明', options={'HIDDEN', 'SKIP_SAVE'})

    @classmethod
    def description(cls, context, properties):
        return properties.help_text

    def execute(self, context):
        self.report({'INFO'}, self.help_text.replace('\n', '：'))
        return {'FINISHED'}


class CINE_OT_toggle_guide(bpy.types.Operator):
    bl_idname = 'cine.toggle_guide'
    bl_label = '构图参考'
    bl_description = '显示或隐藏相机视图中的构图参考'
    bl_options = {'UNDO'}
    field: bpy.props.EnumProperty(name='构图类型', items=[(key, INFO[key][0], INFO[key][2]) for key in
        ('show_composition_thirds', 'show_composition_center', 'show_safe_areas', 'show_passepartout')])

    @classmethod
    def description(cls, context, properties):
        title, _icon, detail = INFO[properties.field]
        return title+'\n'+detail

    def execute(self, context):
        from ..core import rig
        camera = rig.resolve_camera(context)
        if camera is None:
            return {'CANCELLED'}
        setattr(camera.data, self.field, not getattr(camera.data, self.field))
        return {'FINISHED'}


def register():
    for cls in (CINE_OT_parameter_info, CINE_OT_toggle_guide):
        bpy.utils.register_class(cls)
    translations = {}
    for owner in (bpy.types.Camera, bpy.types.CameraDOFSettings, bpy.types.FollowPathConstraint):
        for field, (title, _icon, detail) in INFO.items():
            prop = owner.bl_rna.properties.get(field)
            if prop is None:
                continue
            translations[('*', prop.name)] = title
            if prop.description:
                translations[('*', prop.description)] = detail
            translations[(prop.translation_context, prop.name)] = title
    for source, target in (('Perspective', '透视'), ('Orthographic', '正交'), ('Panoramic', '全景'),
                           ('Auto', '自动'), ('Horizontal', '横向'), ('Vertical', '纵向')):
        translations[('*', source)] = target
    bpy.app.translations.register(__name__, {'zh_HANS': translations, 'zh_CN': translations})


def unregister():
    bpy.app.translations.unregister(__name__)
    for cls in (CINE_OT_toggle_guide, CINE_OT_parameter_info):
        bpy.utils.unregister_class(cls)
