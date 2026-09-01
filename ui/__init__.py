"""ui 包：View3D Sidebar Panel。"""
import bpy

from . import panel


def register():
    panel.register()


def unregister():
    panel.unregister()
