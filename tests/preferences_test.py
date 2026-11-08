"""紧凑界面设置、新镜头默认值与当前镜头高级设置回归。"""
from pathlib import Path
from types import SimpleNamespace
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import bpy
import CineController
from CineController import preferences
from CineController.core import rig
from CineController.ui.panel import CINE_PT_panel, CINE_PT_camera_settings

bpy.ops.wm.read_factory_settings(use_empty=True)
CineController.register()
bpy.ops.cine.create_camera()
original = rig.resolve_camera(bpy.context)
old_lens = original.data.lens
addon = bpy.context.preferences.addons.new()
addon.module = preferences.ADDON_ID
prefs = preferences.get_preferences(bpy.context)
assert prefs is not None and not prefs.show_labels
prefs.default_distance = 8
prefs.default_lens = 85
prefs.default_sensor_width = 32
prefs.default_clip_start = 0.2
prefs.default_clip_end = 800
prefs.default_thirds = True
prefs.default_safe_areas = True
bpy.ops.cine.create_camera()
camera = rig.resolve_camera(bpy.context)
assert camera.cine.distance == 8 and camera.data.lens == 85
assert camera.data.sensor_width == 32 and abs(camera.data.clip_start-0.2) < 1e-5
assert camera.data.clip_end == 800 and camera.data.show_composition_thirds and camera.data.show_safe_areas
assert original.data.lens == old_lens, '默认值不能改变已有镜头'
prefs.default_clip_start, prefs.default_clip_end = 100, 50
objects_before = set(bpy.data.objects)
try:
    result = bpy.ops.cine.create_camera()
except RuntimeError:
    result = {'CANCELLED'}
assert result == {'CANCELLED'} and set(bpy.data.objects) == objects_before
assert rig.resolve_camera(bpy.context) == camera
prefs.default_clip_start, prefs.default_clip_end = 0.2, 800


class Layout:
    fields = []
    operations = []
    def row(self, **_kwargs): return Layout()
    def column(self, **_kwargs): return Layout()
    def box(self): return Layout()
    def separator(self): pass
    def label(self, **_kwargs): pass
    def prop(self, data, path, **kwargs):
        assert path in data.bl_rna.properties
        self.fields.append((data, path, kwargs))
    def operator(self, identifier, **kwargs):
        namespace, name = identifier.split('.')
        getattr(getattr(bpy.ops, namespace), name).get_rna_type()
        self.operations.append((identifier, kwargs))
        return SimpleNamespace()


CINE_PT_panel.draw(SimpleNamespace(layout=Layout()), bpy.context)
assert all(kwargs.get('text') == '' for _name, kwargs in Layout.operations)
assert not any(path in {'sensor_width', 'clip_start', 'clip_end', 'show_composition_golden'} for _data, path, _kw in Layout.fields)
assert any(path == 'distance' and kw['text'] == '' for _data, path, kw in Layout.fields)
Layout.fields.clear()
preferences.CINE_Preferences.draw(SimpleNamespace(layout=Layout(), bl_rna=prefs.bl_rna), bpy.context)
assert all(path == 'show_labels' or path.startswith('default_') for _data, path, _kw in Layout.fields), '插件设置只能编辑通用选项和预设'
Layout.fields.clear()
CINE_PT_camera_settings.draw(SimpleNamespace(layout=Layout()), bpy.context)
assert any(data == camera.data and path == 'sensor_width' for data, path, _kw in Layout.fields)
assert any(data == camera.data and path == 'show_composition_golden' for data, path, _kw in Layout.fields)
Layout.fields.clear()
CINE_PT_panel.draw(SimpleNamespace(layout=Layout()), bpy.context)
for field in ('focus_object', 'focus_distance'):
    assert any(path == field for _data, path, _kw in Layout.fields), field
assert not any(path == 'dolly_target' for _data, path, _kw in Layout.fields), '低频希区柯克设置必须放入高级面板'
original.data.dof.focus_distance = 17
camera.data.dof.focus_distance = 4
assert original.data.dof.focus_distance == 17, '逐镜头对焦参数不能相互覆盖'
camera.data.sensor_width = 40
assert prefs.default_sensor_width == 32, '当前镜头与新镜头默认值应相互独立'
prefs.show_labels = True
Layout.fields.clear()
CINE_PT_panel.draw(SimpleNamespace(layout=Layout()), bpy.context)
assert any(path == 'distance' and kw['text'] == '距离' for _data, path, kw in Layout.fields)
CineController.unregister()
CineController.register()
assert preferences.get_preferences(bpy.context).show_labels
bpy.context.preferences.addons.remove(bpy.context.preferences.addons.get(preferences.ADDON_ID))
CineController.unregister()
print('[PASS] 图标主面板、逐镜头设置与插件预设分离、参数名称开关及新镜头默认值；已有镜头不受影响')
