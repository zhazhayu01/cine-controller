"""轴转换唯一入口。

全插件禁止各文件手写符号转换。所有「Cine 逻辑轴 ↔ Blender 本地轴」的映射
只允许在这里发生。

坐标定义（Blender 世界）：
    Z = Up

Blender Camera 本地轴：
    -Z = Forward（前）
    +Y = Up
    +X = Right

Cine Controller 逻辑轴：
    Offset X = Camera Right
    Offset Y = Camera Up
    Offset Z = Camera Forward
"""
from mathutils import Vector


def cine_offset_to_blender_local(offset: Vector) -> Vector:
    """Cine Offset (X=Right, Y=Up, Z=Forward) → Blender Camera 本地 (X=Right, Y=Up, -Z=Forward)。"""
    return Vector((offset.x, offset.y, -offset.z))


def blender_local_to_cine_offset(local: Vector) -> Vector:
    """Blender Camera 本地 → Cine Offset。与上一函数互为逆。"""
    return Vector((local.x, local.y, -local.z))


def camera_forward_world(rotation_quaternion) -> Vector:
    """给定 Camera 世界四元数，返回世界空间 Forward 向量（Camera 本地 -Z 映射到世界）。"""
    from mathutils import Quaternion
    q = Quaternion(rotation_quaternion)
    return q @ Vector((0.0, 0.0, -1.0))


def camera_up_world(rotation_quaternion) -> Vector:
    from mathutils import Quaternion
    q = Quaternion(rotation_quaternion)
    return q @ Vector((0.0, 1.0, 0.0))


def camera_right_world(rotation_quaternion) -> Vector:
    from mathutils import Quaternion
    q = Quaternion(rotation_quaternion)
    return q @ Vector((1.0, 0.0, 0.0))
