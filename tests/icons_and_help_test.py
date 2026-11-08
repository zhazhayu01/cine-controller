"""验证自绘图标、深浅主题、中文说明及预览资源清理。"""
from pathlib import Path
from types import SimpleNamespace
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import bpy
import CineController
from CineController.ui import icons, help as tips

CineController.register()
root = Path(icons.__file__).parent/'assets'
names = {path.stem for path in (root/'dark').glob('*.png')}
assert len(names) == 25
assert names == {path.stem for path in (root/'light').glob('*.png')}
assert names == {path.stem for path in (root/'svg').glob('*.svg')}
assert len(icons._previews) == 50
for name in names:
    for theme in ('dark', 'light'):
        preview = icons._previews[theme+'/'+name]
        if not bpy.app.background:
            assert preview.icon_id > 0
        image = bpy.data.images.load(str(root/theme/(name+'.png')), check_existing=False)
        assert tuple(image.size) == (64, 64)
        alpha = image.pixels[3::4]
        assert max(alpha) == 1 and min(alpha) == 0 and any(0 < a < 1 for a in alpha)
        bpy.data.images.remove(image)
color = bpy.context.preferences.themes[0].user_interface.wcol_regular.inner
saved_color = tuple(color)
try:
    color[:] = (0.15, 0.15, 0.15, 1)
    if not bpy.app.background:
        assert icons.kwargs('pan')['icon_value'] == icons._previews['dark/pan'].icon_id
    color[:] = (0.85, 0.85, 0.85, 1)
    if not bpy.app.background:
        assert icons.kwargs('pan')['icon_value'] == icons._previews['light/pan'].icon_id
finally:
    color[:] = saved_color
assert icons.kwargs('不存在', 'CAMERA_DATA') == {'icon': 'CAMERA_DATA'}
print('[PASS] 25 个自绘图标具备透明抗锯齿、SVG 源文件、深浅主题版本及缺失回退')

for field, (title, icon, detail) in tips.INFO.items():
    assert icon in names, field
    assert any('\u4e00' <= ch <= '\u9fff' for ch in title+detail)
    assert tips.CINE_OT_parameter_info.description(None, SimpleNamespace(help_text=title+'\n'+detail)) == title+'\n'+detail
view = bpy.context.preferences.view
language, translate = view.language, view.use_translate_tooltips
try:
    view.language = 'zh_HANS'
    view.use_translate_tooltips = True
    description = bpy.types.Camera.bl_rna.properties['lens'].description
    translated = bpy.app.translations.pgettext_tip(description)
    assert translated != description and any('\u4e00' <= ch <= '\u9fff' for ch in translated)
finally:
    view.language, view.use_translate_tooltips = language, translate
bpy.ops.cine.create_camera()
camera = bpy.context.object.cine_camera
old_lens = camera.data.lens
guide = camera.data.show_composition_thirds
bpy.ops.cine.toggle_guide(field='show_composition_thirds')
assert camera.data.show_composition_thirds is not guide
assert camera.data.lens == old_lens
print('[PASS] 图标说明独立中文，中文界面原生焦距提示可翻译，构图按钮仍写原生相机数据')

previews = icons._previews
CineController.unregister()
assert icons._previews is None
CineController.register()
assert icons._previews is not previews and len(icons._previews) == 50
CineController.unregister()
assert icons._previews is None
print('[PASS] 插件反复启停会清理并重建预览资源，不遗留加载句柄')
if '--gui-icons' in sys.argv:
    def finish():
        bpy.ops.wm.quit_blender()
    bpy.app.timers.register(finish, first_interval=0.5)
