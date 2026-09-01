"""operators 包：bpy.types.Operator。

第一里程碑：Enable / Disable / Bake。
高风险 Operator 遵循 §72 事务化：记录位姿 → 修改 → 验证 → 失败回滚。
"""
import bpy

from . import enable, disable, bake


def register():
    enable.register()
    disable.register()
    bake.register()


def unregister():
    bake.unregister()
    disable.unregister()
    enable.unregister()
