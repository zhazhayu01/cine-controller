"""core 包：核心求解逻辑（纯函数，无 UI 依赖）。"""
from . import properties, transform_system, orientation_system, optical_system, rig, preserve_pose


def register():
    properties.register()


def unregister():
    properties.unregister()
