"""core 包：表达式编译、控制器生命周期与光学参数，无 UI 依赖。"""
from . import driver_graph, properties, optical_system, rig, preserve_pose


def register():
    properties.register()


def unregister():
    properties.unregister()
