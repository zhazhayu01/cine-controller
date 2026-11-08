"""operators 包：bpy.types.Operator。

统一注册镜头操作与高级效果。
高风险 Operator 遵循 事务化：记录位姿 → 修改 → 验证 → 失败回滚。
"""
import bpy

from . import enable, disable, bake, create, cinematography, path, shake


def register():
    create.register()
    enable.register()
    disable.register()
    bake.register()
    cinematography.register()
    path.register()
    shake.register()


def unregister():
    shake.unregister()
    path.unregister()
    cinematography.unregister()
    bake.unregister()
    disable.unregister()
    enable.unregister()
    create.unregister()
