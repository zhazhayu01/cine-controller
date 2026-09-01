# Cine Controller for Blender
# 电影级摄影机控制器插件入口
#
# 架构原则（详见 docs/ 规范）：
#   - Single Source of Truth：Viewport / Render / Bake 读取同一个 evaluated Camera Transform
#   - 三个独立系统域：Transform / Orientation / Optical
#   - 禁止 Incremental Transform，所有求值必须幂等
#   - Preserve Pose 必须 Matrix 验证

bl_info = {
    "name": "Cine Controller",
    "author": "zhazhayu001",
    "version": (0, 1, 0),
    "blender": (5, 2, 0),
    "location": "View3D > Sidebar > Cine",
    "description": "电影级摄影机控制器：稳定的 Origin/Aim/Focus 绑定与一致性求值",
    "category": "Camera",
}

import importlib
import sys

# 模块注册顺序（import 时只加载，不执行副作用）
_MODULES = (
    "utils",
    "core",
    "operators",
    "ui",
)

_submodules = {
    "utils": ("math_utils", "axis_utils"),
    "core": (
        "transform_system",
        "orientation_system",
        "optical_system",
        "rig",
        "preserve_pose",
    ),
    "operators": (),
    "ui": (),
}


def _reload():
    """开发期热重载：重新 import 所有子模块。"""
    import bpy

    pkg = __name__
    for mod_name in _MODULES:
        full = f"{pkg}.{mod_name}"
        if full in sys.modules:
            importlib.reload(sys.modules[full])
        for sub in _submodules.get(mod_name, ()):
            sub_full = f"{full}.{sub}"
            if sub_full in sys.modules:
                importlib.reload(sys.modules[sub_full])


def register():
    import bpy

    _reload()

    from . import utils, core, operators, ui

    for mod in (utils, core, operators, ui):
        if hasattr(mod, "register"):
            mod.register()


def unregister():
    import bpy

    from . import utils, core, operators, ui

    for mod in reversed((utils, core, operators, ui)):
        if hasattr(mod, "unregister"):
            mod.unregister()


if __name__ == "__main__":
    register()
