"""插件偏好设置：仅保存通用界面选项和新镜头预设。"""
import bpy

ADDON_ID = __package__
GUIDES = (
    ('show_composition_thirds', '三分线'), ('show_composition_center', '中心线'),
    ('show_composition_center_diagonal', '对角线'), ('show_composition_golden', '黄金分割'),
    ('show_safe_areas', '安全框'), ('show_passepartout', '画幅外遮罩'),
)


def get_preferences(context):
    addon = context.preferences.addons.get(ADDON_ID)
    return addon.preferences if addon is not None else None


def apply_defaults(context, camera):
    """只在创建新镜头时应用，不改变已有镜头。"""
    prefs = get_preferences(context)
    if prefs is None:
        return
    if prefs.default_clip_end <= prefs.default_clip_start:
        raise ValueError('默认远裁剪必须大于近裁剪')
    camera.cine.distance = prefs.default_distance
    data = camera.data
    data.lens = prefs.default_lens
    data.sensor_width = prefs.default_sensor_width
    data.clip_start = prefs.default_clip_start
    data.clip_end = prefs.default_clip_end
    data.show_composition_thirds = prefs.default_thirds
    data.show_safe_areas = prefs.default_safe_areas


class CINE_Preferences(bpy.types.AddonPreferences):
    bl_idname = ADDON_ID

    show_labels: bpy.props.BoolProperty(
        name='显示参数名称', default=False,
        description='主面板额外显示短名称；关闭时使用图标、数值和悬停说明',
    )
    default_distance: bpy.props.FloatProperty(name='距离', default=5, min=0, subtype='DISTANCE')
    default_lens: bpy.props.FloatProperty(name='焦距（mm）', default=50, min=1, soft_max=5000)
    default_sensor_width: bpy.props.FloatProperty(name='传感器宽度', default=36, min=1)
    default_clip_start: bpy.props.FloatProperty(name='近裁剪', default=0.1, min=0.001, subtype='DISTANCE')
    default_clip_end: bpy.props.FloatProperty(name='远裁剪', default=1000, min=0.002, subtype='DISTANCE')
    default_thirds: bpy.props.BoolProperty(name='三分线', default=False)
    default_safe_areas: bpy.props.BoolProperty(name='安全框', default=False)

    def draw(self, context):
        layout = self.layout
        layout.prop(self, 'show_labels')
        box = layout.box()
        box.label(text='新建镜头默认值', icon='ADD')
        for field in ('default_distance', 'default_lens', 'default_sensor_width', 'default_clip_start',
                      'default_clip_end', 'default_thirds', 'default_safe_areas'):
            box.prop(self, field)


class CINE_OT_open_preferences(bpy.types.Operator):
    bl_idname = 'cine.open_preferences'
    bl_label = 'Cine 插件设置'
    bl_description = '打开通用界面选项和新建镜头预设；已有镜头的参数请在相机面板调整'

    @classmethod
    def poll(cls, context):
        return context.window is not None

    def execute(self, context):
        bpy.ops.preferences.addon_show(module=ADDON_ID)
        return {'FINISHED'}


def register():
    bpy.utils.register_class(CINE_Preferences)
    bpy.utils.register_class(CINE_OT_open_preferences)


def unregister():
    bpy.utils.unregister_class(CINE_OT_open_preferences)
    bpy.utils.unregister_class(CINE_Preferences)
