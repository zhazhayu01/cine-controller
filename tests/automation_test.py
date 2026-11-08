"""通过与 MCP 相同的 Python 执行/标准输出通道验证 JSON 自动化入口。"""
from pathlib import Path
from contextlib import redirect_stdout
import io
import json
import math
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import bpy
import CineController
from CineController.core import rig
from CineController.utils.math_utils import matrix_close

bpy.ops.wm.read_factory_settings(use_empty=True)
CineController.register()


def request(payload, ok=True):
    # 上游 execute_blender_code 使用 exec(code, {"bpy": bpy}) 并收集标准输出。
    code = 'import bpy\nbpy.ops.cine.automation(request_json=' + repr(json.dumps(payload)) + ')'
    capture = io.StringIO()
    with redirect_stdout(capture):
        exec(code, {'bpy': bpy})
    lines = [line for line in capture.getvalue().splitlines() if line.startswith('{"ok":')]
    assert len(lines) == 1, capture.getvalue()
    result = json.loads(lines[0])
    assert result['ok'] is ok, result
    return result.get('data', result.get('error'))


manifest = request({'action': 'describe'})
assert manifest['api_version'] == 1 and 'bind_path' in manifest['actions']
assert manifest['fields']['pan_deg']['type'] == 'angle'
assert request({'action': 'list'}) == []
first = request({'action': 'create', 'name': '镜头甲'})
second = request({'action': 'create', 'name': '镜头乙'})
camera = bpy.data.objects[first['camera']]
other = bpy.data.objects[second['camera']]
active_before = bpy.context.view_layer.objects.active
selection_before = set(bpy.context.selected_objects)
result = request({'action': 'set', 'camera': first['controller'],
                  'values': {'distance': 8, 'horizontal_deg': 30, 'vertical_deg': -20,
                             'pan_deg': 15, 'tilt_deg': -5, 'roll_deg': 10,
                             'lens_mm': 70, 'dof_enabled': True, 'focus_distance': 8, 'thirds': True}})
assert abs(camera.cine.horizontal-math.radians(30)) < 1e-6
assert abs(result['values']['tilt_deg']+5) < 1e-4 and camera.data.lens == 70
assert other.cine.distance == 5 and other.data.lens == 50
assert bpy.context.view_layer.objects.active == active_before and set(bpy.context.selected_objects) == selection_before
request({'action': 'keyframe', 'camera': first['camera'], 'frame': 1})
request({'action': 'move_control', 'camera': first['camera'], 'frame': 20,
         'location': [2, 3, 4], 'rotation_deg': [0, 0, 40]})
request({'action': 'set', 'camera': first['camera'], 'values': {'pan_deg': 30}})
request({'action': 'keyframe', 'camera': first['camera']})
assert bpy.context.view_layer.objects.active == active_before
assert camera.animation_data.action is not None
assert request({'action': 'get', 'camera': first['camera'], 'frame': 7.5})['frame'] == 7.5
print('[PASS] MCP 执行通道发现接口、创建多镜头、度数换算、明确目标及动画插帧；不改变选择')

before = other.cine.distance
request({'action': 'set', 'camera': other.name, 'values': {'distance': 12, 'wrong_field': 1}}, ok=False)
request({'action': 'set', 'camera': other.name, 'values': {'distance': 12, 'lens_mm': -2}}, ok=False)
request({'action': 'set', 'camera': other.name, 'values': {'distance': 12, 'path_progress': 0.5}}, ok=False)
request({'action': 'set', 'camera': other.name, 'values': {'distance': float('nan')}}, ok=False)
request({'action': 'set', 'camera': other.name, 'values': {'distance': True}}, ok=False)
assert other.cine.distance == before
duplicate = other.copy()
bpy.context.collection.objects.link(duplicate)
duplicate.name = '不完整副本'
assert not request({'action': 'get', 'camera': duplicate.name})['controller_owned']
request({'action': 'move_control', 'camera': duplicate.name, 'location': [10, 0, 0]}, ok=False)
bpy.data.objects.remove(duplicate, do_unlink=True)
request({'action': 'get'}, ok=False)
request({'action': 'get', 'camera': '不存在'}, ok=False)
request({'action': '删除全部'}, ok=False)
assert len(request({'action': 'list'})) == 2
print('[PASS] 未知字段、错误类型、非法数值、未绑定参数和缺失镜头返回结构化错误，不部分写入')

target = bpy.data.objects.new('目标', None)
bpy.context.collection.objects.link(target)
target.location = (1, 2, 3)
request({'action': 'set', 'camera': other.name,
         'values': {'origin': target.name, 'distance': 6, 'pan_deg': 10, 'focus_object': target.name}})
assert other.cine.origin == target and other.data.dof.focus_object == target
request({'action': 'set', 'camera': other.name, 'values': {'focus_distance': 5}}, ok=False)
request({'action': 'set', 'camera': other.name,
         'values': {'focus_object': None, 'focus_distance': 6}})
assert other.data.dof.focus_object is None
request({'action': 'set', 'camera': other.name, 'values': {'origin': other.name}}, ok=False)
print('[PASS] 原点与对焦目标按对象名解析，支持 null；对焦目标与手动距离保护有效')

# 故障发生在第一项写入之后时，所有待写字段和原点回调副作用均恢复。
from CineController import automation
original_update = rig.force_update
counter = [0]
def fail_once(context, camera):
    counter[0] += 1
    if counter[0] == 1:
        raise RuntimeError('测试故障')
    original_update(context, camera)
before = automation.get(other)
try:
    rig.force_update = fail_once
    request({'action': 'set', 'camera': other.name,
             'values': {'origin': None, 'distance': 15, 'lens_mm': 90}}, ok=False)
finally:
    rig.force_update = original_update
after = automation.get(other)
assert before['values'] == after['values'] and before['world_position'] == after['world_position']
assert not [obj for obj in bpy.data.objects if obj.name.startswith('目标.')], '回滚不能复制目标对象'
print('[PASS] 批量设置失败时恢复全部字段及原点回调副作用，不产生额外对象')

source = bpy.data.objects.new('自由相机', bpy.data.cameras.new('参考数据'))
bpy.context.collection.objects.link(source)
source.location = (3, -4, 2)
source.rotation_euler = (0.3, -0.5, 0.7)
request({'action': 'import_pose', 'camera': other.name, 'source': source.name})
assert matrix_close(rig.read_evaluated_camera_matrix(bpy.context, other), source.matrix_world)
request({'action': 'enable_dolly', 'camera': other.name})
request({'action': 'enable_dolly', 'camera': other.name})
assert request({'action': 'get', 'camera': other.name})['dolly_enabled']
request({'action': 'set', 'camera': other.name, 'values': {'lens_mm': 85}}, ok=False)
request({'action': 'set', 'camera': other.name, 'values': {'horizontal_deg': 8}}, ok=False)
request({'action': 'set', 'camera': other.name, 'values': {'dolly_travel': 0.2}})
request({'action': 'disable_dolly', 'camera': other.name})
request({'action': 'disable_dolly', 'camera': other.name})
assert not request({'action': 'get', 'camera': other.name})['dolly_enabled']
print('[PASS] 完整反推与希区柯克调用复用插件逻辑，启停幂等且保护受驱动焦距')

data = bpy.data.curves.new('轨迹数据', 'CURVE')
data.dimensions = '3D'
spline = data.splines.new('POLY')
spline.points.add(1)
spline.points[0].co = (0, 0, 0, 1)
spline.points[1].co = (0, 6, 2, 1)
path = bpy.data.objects.new('轨迹', data)
bpy.context.collection.objects.link(path)
request({'action': 'bind_path', 'camera': other.name, 'target': path.name})
request({'action': 'set', 'camera': other.name, 'values': {'path_progress': 0.5, 'path_follow': True}})
request({'action': 'keyframe', 'camera': other.name, 'frame': 1})
request({'action': 'pause_path', 'camera': other.name})
request({'action': 'pause_path', 'camera': other.name})
request({'action': 'set', 'camera': other.name, 'values': {'path_progress': 0.9}}, ok=False)
request({'action': 'resume_path', 'camera': other.name})
request({'action': 'resume_path', 'camera': other.name})
request({'action': 'move_control', 'camera': other.name, 'location': [1, 2, 3]}, ok=False)
request({'action': 'render_camera', 'camera': other.name})
assert bpy.context.scene.camera == other
bpy.context.scene.frame_start, bpy.context.scene.frame_end = 1, 3
request({'action': 'bake', 'camera': other.name})
assert not other.cine.enabled
print('[PASS] 轨迹绑定、进度、幂等暂停恢复、渲染镜头及烘焙均可通过 JSON 入口执行')

CineController.unregister()
CineController.register()
assert request({'action': 'describe'})['api_version'] == 1
CineController.unregister()
print('[PASS] 插件重新启用后自动化操作可重新发现')
