"""Orientation System —— 只负责摄影机旋转。

参数：
    Aim Target / Aim Influence / Pan / Tilt / Roll

输出：
    Camera Rotation

规则：
    - 可以依赖 Transform 输出的位置（如 Aim 朝向），但绝不反向修改 Transform 参数。
    - 禁止 Aim 系统重新设置 Origin / Distance / Horizontal / Vertical / Offset。
    - Aim Influence 0 → 1 的混合必须来自 Blender Constraint，不做 Python 每帧 slerp。
"""
from mathutils import Matrix, Quaternion, Vector


def solve_camera_orientation(params) -> Quaternion:
    """从 Orientation 参数绝对求解 Camera 世界旋转（幂等）。

    params 预期包含：
        position: Vector      Camera 世界位置（来自 Transform System）
        aim_target: Vector|None   Aim Target 世界位置
        aim_influence: float  [0, 1]，由 Constraint 处理时为参考值
        pan: float
        tilt: float
        roll: float

    返回世界空间 Quaternion。
    """
    position = Vector(params.get("position", (0.0, 0.0, 0.0)))
    aim_target = params.get("aim_target", None)
    pan = params.get("pan", 0.0)
    tilt = params.get("tilt", 0.0)
    roll = params.get("roll", 0.0)

    # 基础朝向：默认 Camera 世界朝向（-Z forward, +Y up）
    base_quat = _default_camera_rotation()

    # Aim：若提供 target 且 influence > 0，计算指向 target 的朝向
    if aim_target is not None:
        aim_target = Vector(aim_target)
        influence = params.get("aim_influence", 0.0)
        aim_quat = _look_at(position, aim_target)
        if influence >= 1.0:
            base_quat = aim_quat
        elif influence > 0.0:
            base_quat = base_quat.slerp(aim_quat, influence)

    # Pan / Tilt / Roll：本地旋转叠加
    # Pan 绕本地 Y（Camera Up），Tilt 绕本地 X（Camera Right），Roll 绕本地 Z（Forward）
    q_pan = Quaternion(Vector((0.0, 1.0, 0.0)), pan)
    q_tilt = Quaternion(Vector((1.0, 0.0, 0.0)), tilt)
    q_roll = Quaternion(Vector((0.0, 0.0, 1.0)), roll)
    local = q_roll @ q_tilt @ q_pan

    return base_quat @ local


def _default_camera_rotation() -> Quaternion:
    """默认 Camera 世界朝向：Forward=-Z（世界），Up=+Y（世界）。

    即本地 -Z 映射到世界 -Y？不——默认 Blender Camera 朝向为 Forward=-Z。
    返回单位四元数即可（后续由具体 Rig 定义基准朝向）。
    """
    return Quaternion((1.0, 0.0, 0.0, 0.0))


def _look_at(position: Vector, target: Vector) -> Quaternion:
    """计算从 position 指向 target 的世界朝向（Forward = -Z）。

    使用 Blender 常用 Track 逻辑：Forward 指向 target，Up 尽量保持世界 +Z。
    """
    from mathutils import Matrix
    direction = (Vector(target) - Vector(position))
    if direction.length_squared < 1e-12:
        return _default_camera_rotation()

    forward = direction.normalized()

    # up 轴：世界 Z，但当 forward 接近 ±Z 时退化为 Y 轴避免万向锁
    world_up = Vector((0.0, 0.0, 1.0))
    if abs(forward.dot(world_up)) > 0.999:
        world_up = Vector((0.0, 1.0, 0.0))

    # Camera 本地 forward 是 -Z，所以 world forward 对应本地 -Z
    # 构造旋转矩阵：本地 -Z → world forward
    right = forward.cross(world_up)
    if right.length_squared < 1e-12:
        right = Vector((1.0, 0.0, 0.0))
    right.normalize()
    up = right.cross(forward)
    up.normalize()

    # 列主序：矩阵的列是本地轴在世界空间的表示
    # 本地 X=right, Y=up, Z=-forward（因为 forward 是 -Z）
    mat = Matrix((
        (right.x, up.x, -forward.x, 0.0),
        (right.y, up.y, -forward.y, 0.0),
        (right.z, up.z, -forward.z, 0.0),
        (0.0, 0.0, 0.0, 1.0),
    ))
    return mat.to_quaternion()
