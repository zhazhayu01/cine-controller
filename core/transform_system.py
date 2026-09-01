"""Transform System —— 只负责摄影机空间位置。

参数：
    Origin / Distance / Horizontal / Vertical / Position Offset

输出：
    Camera Position

规则：
    - 只能被 Orientation 读取，绝不能被反向修改。
    - 禁止 Incremental Transform，所有求值从参数绝对推导。
    - 不依赖 Viewport / Render / 选中对象等 UI 状态。
"""
from mathutils import Matrix, Vector


def solve_camera_position(params) -> Vector:
    """从 Transform 参数绝对求解 Camera 世界位置（幂等）。

    params 预期包含：
        origin: Vector        Origin Target 世界位置
        distance: float       轨道半径
        horizontal: float     绕 World Z 的方位角（弧度）
        vertical: float       绕本地 X 的仰角（弧度）
        offset: Vector        Cine 逻辑偏移（X=Right, Y=Up, Z=Forward）

    求值顺序（规范 §57）：
        Origin → Horizontal Orbit → Vertical Orbit → Distance → Position Offset
    """
    # 1. 起点：Origin 世界位置
    origin = Vector(params["origin"])

    # 2. Horizontal orbit：绕世界 Z
    horizontal = params.get("horizontal", 0.0)
    # 3. Vertical orbit：绕本地 X（先水平旋转，再仰角）
    vertical = params.get("vertical", 0.0)
    distance = params.get("distance", 0.0)

    # 初始方向：Camera 位于 Origin +Z 上方，朝向 -Z（forward）
    # 这里构造「轨道方向向量」：先水平，再垂直
    # 基础向量：沿世界 -Y（Camera forward 默认指向 -Y？）—— 以规范为准，见 axis_utils。

    # 方向：从 Origin 指向 Camera 的向量
    # 使用球坐标：horizontal 绕 Z，vertical 为仰角
    from math import cos, sin
    h = horizontal
    v = vertical
    # Camera 相对 Origin 的偏移向量（先算距离方向，再乘距离）
    direction = Vector((cos(v) * cos(h), cos(v) * sin(h), sin(v)))
    position = origin + direction * distance

    # 4. Position Offset：Cine 逻辑偏移，需转换为世界偏移
    #    世界偏移 = Camera 朝向 × Cine Offset
    offset = params.get("offset", Vector((0.0, 0.0, 0.0)))
    if any(offset):
        # 需要 Camera 世界朝向才能正确应用 Offset —— 由 Orientation 提供
        # 此处返回未加 Offset 的 position，Offset 在合成阶段处理（见 rig.py）
        pass

    return position


def solve_camera_position_full(params) -> Vector:
    """包含 Position Offset 的完整求解。

    当调用方能提供 Camera 世界朝向时使用（与 Orientation 联合求解）。
    """
    position = solve_camera_position(params)
    offset = params.get("offset", Vector((0.0, 0.0, 0.0)))
    if any(offset):
        from ..utils.axis_utils import camera_right_world, camera_up_world, camera_forward_world
        rot = params.get("rotation", None)
        if rot is not None:
            right = camera_right_world(rot)
            up = camera_up_world(rot)
            forward = camera_forward_world(rot)
            world_offset = right * offset.x + up * offset.y + forward * offset.z
            position += world_offset
    return position
