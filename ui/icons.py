"""自绘图标预览生命周期；按当前按钮底色选择深浅版本。"""
from pathlib import Path
import bpy
import bpy.utils.previews

_previews = None
# 已有准确原生语义的通用功能优先用原生图标，避免图片缩放和主题灰度不一致。
NATIVE = {'path': 'CURVE_BEZCURVE', 'path_bind': 'LINKED'}


def register():
    global _previews
    unregister()
    _previews = bpy.utils.previews.new()
    root = Path(__file__).parent/'assets'
    for theme in ('dark', 'light'):
        for path in sorted((root/theme).glob('*.png')):
            _previews.load(theme+'/'+path.stem, str(path), 'IMAGE')


def unregister():
    global _previews
    if _previews is not None:
        bpy.utils.previews.remove(_previews)
        _previews = None


def kwargs(name, fallback='QUESTION'):
    if name in NATIVE:
        return {'icon': NATIVE[name]}
    if _previews is not None:
        color = bpy.context.preferences.themes[0].user_interface.wcol_regular.inner
        theme = 'dark' if sum(color[:3])/3 < 0.5 else 'light'
        preview = _previews.get(theme+'/'+name)
        if preview and preview.icon_id:
            return {'icon_value': preview.icon_id}
    return {'icon': fallback}
