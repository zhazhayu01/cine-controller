"""ui 包：View3D Sidebar Panel。"""
import bpy

from . import icons, help, panel, effects


def register():
    icons.register()
    help.register()
    panel.register()
    effects.register()


def unregister():
    effects.unregister()
    panel.unregister()
    help.unregister()
    icons.unregister()
