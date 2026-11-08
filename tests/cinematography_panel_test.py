"""校验面板各状态下的真实 RNA 路径、操作入口和不新增键位的约定。"""
from pathlib import Path
from types import SimpleNamespace
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import bpy
import CineController
from CineController.core import rig
from CineController.ui import panel

bpy.ops.wm.read_factory_settings(use_empty=True)

def keymaps():
    config = bpy.context.window_manager.keyconfigs.addon
    return {(km.name, item.idname, item.type, item.value) for km in config.keymaps for item in km.keymap_items} if config else set()

before_keys = keymaps()
CineController.register()
assert keymaps() == before_keys, '不应增加 K 或其他键位绑定'


class Layout:
    def row(self, **_kwargs): return Layout()
    def box(self): return Layout()
    def column(self, **_kwargs): return Layout()
    def separator(self): pass
    def label(self, **_kwargs): pass
    def prop(self, data, path, **_kwargs):
        assert path in data.bl_rna.properties, (type(data), path)
        if 'icon' in _kwargs:
            assert _kwargs['icon'] in bpy.types.UILayout.bl_rna.functions['prop'].parameters['icon'].enum_items
    def operator(self, identifier, **kwargs):
        namespace, name = identifier.split('.')
        getattr(getattr(bpy.ops, namespace), name).get_rna_type()
        if 'icon' in kwargs:
            assert kwargs['icon'] in bpy.types.UILayout.bl_rna.functions['operator'].parameters['icon'].enum_items
        assert kwargs.get('text') == '', '主面板操作按钮应只显示图标'
        return SimpleNamespace()


def draw():
    for cls in panel.CLASSES:
        if cls.poll(bpy.context):
            cls.draw(SimpleNamespace(layout=Layout()), bpy.context)

draw()
bpy.ops.cine.create_camera()
camera = rig.resolve_camera(bpy.context)
draw()
bpy.ops.cine.toggle_dolly_zoom()
draw()
# 禁用/重启用插件时，更新后的子面板和光学运行数据都应重新绑定。
before = camera.matrix_world.copy()
before_lens = camera.data.lens
CineController.unregister()
CineController.register()
rig.force_update(bpy.context, camera)
assert camera.cine.controller == bpy.context.object
assert abs(camera.data.lens-before_lens) < 1e-4
assert max(abs(before[i][j]-camera.matrix_world[i][j]) for i in range(4) for j in range(4)) < 2e-5
draw()
bpy.ops.cine.toggle_dolly_zoom()
data = bpy.data.curves.new('轨迹数据', 'CURVE')
data.dimensions = '3D'
spline = data.splines.new('POLY')
spline.points.add(1)
spline.points[1].co = (0, 4, 0, 1)
trajectory = bpy.data.objects.new('轨迹', data)
bpy.context.collection.objects.link(trajectory)
camera.cine.path_target = trajectory
assert bpy.ops.cine.bind_path() == {'FINISHED'}
draw()
assert bpy.ops.cine.toggle_path() == {'FINISHED'}
draw()
assert bpy.ops.cine.toggle_path() == {'FINISHED'}
draw()
bpy.ops.mesh.primitive_cube_add()
draw()
assert rig.resolve_camera(bpy.context) == camera
bpy.ops.cine.set_render_camera()
assert bpy.context.scene.camera == camera
CineController.unregister()
assert keymaps() == before_keys
print('[PASS] 空场景、曲线选择、希区柯克启停及普通物体选择时面板 RNA/操作有效，不新增任何键位')
