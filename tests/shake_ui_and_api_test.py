"""高级面板折叠、事件编辑和 MCP 接口回归。"""
from pathlib import Path
from types import SimpleNamespace
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import bpy
import CineController
from CineController import automation
from CineController.core import rig
from CineController.ui import effects, panel

bpy.ops.wm.read_factory_settings(use_empty=True)
CineController.register()
bpy.ops.cine.create_camera()
camera = bpy.context.object.cine_camera

def request(action, **kwargs):
    result = automation.call({'action': action, 'camera': camera.name, **kwargs})
    assert result['ok'], result
    return result['data']

request('enable_shake')
first = camera.cine.shake_events[0]
first_id = first.name
request('shake_event', operation='update', event_id=first_id,
        values={'label': '第一次落地', 'start': 30, 'frequency': 8, 'rotation_deg': [0.4, 0.1, 0]})
request('shake_event', operation='add', values={'label': '第二次落地', 'start': 48, 'duration': 8, 'strength': 0.5})
second = camera.cine.shake_events[1]
second_id = second.name
first_path = first.path_from_id('strength')
second_path = second.path_from_id('strength')
camera.keyframe_insert(data_path=first_path, frame=1)
camera.keyframe_insert(data_path=second_path, frame=1)
request('shake_event', operation='remove', event_id=first_id)
assert camera.cine.shake_events[0].name == second_id
paths = {fc.data_path for fc in rig._action_curves(camera.animation_data.action)}
assert first_path not in paths and second_path in paths
request('shake_event', operation='duplicate', event_id=second_id, values={'start': 70})
assert len(camera.cine.shake_events) == 2
assert camera.cine.shake_events[1].name != second_id
state = request('get')['shake']
assert state['events'][0]['event_id'] == second_id and state['events'][1]['start'] == 70
request('disable_shake')
request('disable_shake')
assert not camera.cine.shake_enabled
request('enable_shake')
request('enable_shake')
assert camera.cine.shake_enabled and len(camera.cine.shake_events) == 2
bad = automation.call({'action': 'shake_event', 'camera': camera.name, 'operation': 'add', 'values': {'duration': -5}})
assert not bad['ok'] and len(camera.cine.shake_events) == 2
print('[PASS] MCP 多事件添加、编辑、复制、幂等启停与删除；删除不会破坏其他事件动画路径')

class Layout:
    operations = []
    fields = []
    def row(self, **_kwargs): return Layout()
    def column(self, **_kwargs): return Layout()
    def label(self, **_kwargs): pass
    def separator(self): pass
    def prop(self, owner, path, **_kwargs):
        assert path in owner.bl_rna.properties
        self.fields.append(path)
    def operator(self, identifier, **_kwargs):
        namespace, name = identifier.split('.')
        getattr(getattr(bpy.ops, namespace), name).get_rna_type()
        self.operations.append(identifier)
        return SimpleNamespace()
    def template_list(self, name, _id, owner, path, active, index, **_kwargs):
        assert path in owner.bl_rna.properties and index in active.bl_rna.properties
        assert name == 'CINE_UL_shake_events'

panel.CINE_PT_panel.draw(SimpleNamespace(layout=Layout()), bpy.context)
assert 'cine.toggle_shake' not in Layout.operations and 'cine.toggle_dolly_zoom' not in Layout.operations
assert not {'shake_strength', 'dolly_target', 'dolly_travel'}.intersection(Layout.fields)
for cls in effects.CLASSES:
    if issubclass(cls, bpy.types.Panel):
        assert 'DEFAULT_CLOSED' in cls.bl_options
        cls.draw(SimpleNamespace(layout=Layout()), bpy.context)
assert effects.CINE_PT_shake.bl_parent_id == effects.CINE_PT_dolly.bl_parent_id == 'CINE_PT_advanced'
assert effects.CINE_PT_shake_detail.bl_parent_id == 'CINE_PT_shake'
assert 'cine.toggle_shake' in Layout.operations and 'cine.toggle_dolly_zoom' in Layout.operations
assert 'shake_strength' in Layout.fields and 'frequency' in Layout.fields
print('[PASS] 震动与希区柯克仅在默认折叠的高级效果内，方向和种子再折叠一层，主面板无新增效果入口')
CineController.unregister()
