"""普通相机与插件相机共用原生场景相机视角，避免局部锁定。"""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import bpy
import CineController

bpy.ops.wm.read_factory_settings(use_empty=True)
CineController.register()
bpy.ops.cine.create_camera()
control = bpy.context.object
controlled = control.cine_camera
plain = bpy.data.objects.new('普通相机', bpy.data.cameras.new('普通相机数据'))
bpy.context.collection.objects.link(plain)
area = next(area for area in bpy.context.screen.areas if area.type == 'VIEW_3D')
region = next(region for region in area.regions if region.type == 'WINDOW')

with bpy.context.temp_override(area=area, region=region):
    space = bpy.context.space_data
    assert bpy.ops.cine.camera_view() == {'FINISHED'}
    assert not space.use_local_camera, '进入插件相机不能留下局部相机锁定'
    assert bpy.context.scene.camera == controlled
    assert space.region_3d.view_perspective == 'CAMERA'
    bpy.context.scene.camera = plain
    bpy.ops.view3d.view_camera()
    bpy.ops.view3d.view_camera()
    assert not space.use_local_camera and bpy.context.scene.camera == plain
    assert space.region_3d.view_perspective == 'CAMERA'
    bpy.context.view_layer.objects.active = plain
    assert bpy.ops.cine.camera_view() == {'FINISHED'}
    assert bpy.context.scene.camera == plain and not plain.cine.enabled
    assert not space.use_local_camera
    print('[PASS] 插件相机与普通相机可切换，原生相机视图继续跟随场景活动相机')

    # 现有视角按钮直接清除局部锁定，不新增兼容入口。
    space.use_local_camera = True
    space.camera = controlled
    assert bpy.ops.cine.camera_view() == {'FINISHED'}
    assert not space.use_local_camera and bpy.context.scene.camera == plain
    assert space.region_3d.view_perspective == 'CAMERA'
    bpy.context.view_layer.objects.active = controlled
    bpy.ops.view3d.object_as_camera()
    assert bpy.context.scene.camera == controlled, '原生设为活动相机必须正常生效'
    assert not space.use_local_camera
    print('[PASS] 现有视角按钮直接清除局部锁定，原生活动相机切换正常，无新增入口')
CineController.unregister()
