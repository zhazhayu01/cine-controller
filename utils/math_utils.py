"""数学工具：矩阵比较 / 四元数角度差 / 位姿分解 / Orbit 求解。

整个插件所有模块共用这一套函数，禁止各文件手写矩阵比较或轴转换。
"""
from math import acos, atan2, cos, sin, sqrt
from mathutils import Matrix, Quaternion, Vector

# 默认浮点容差（Blender Unit / radian）
POSITION_TOLERANCE = 1e-5
ROTATION_TOLERANCE = 1e-5


def matrix_close(m1: Matrix, m2: Matrix, pos_tol=POSITION_TOLERANCE, rot_tol=ROTATION_TOLERANCE) -> bool:
    """比较两个 4x4 世界矩阵是否在容差内近似相等。

    同时比较位置（translation）与旋转（quaternion 角度差），忽略 Scale。
    """
    m1 = Matrix(m1)
    m2 = Matrix(m2)
    p1 = m1.to_translation()
    p2 = m2.to_translation()
    if (p1 - p2).length > pos_tol:
        return False

    q1 = m1.to_quaternion()
    q2 = m2.to_quaternion()
    return quaternion_angle_difference(q1, q2) <= rot_tol


def quaternion_angle_difference(q1: Quaternion, q2: Quaternion) -> float:
    """返回两个四元数之间的最小角度差（弧度，[0, pi]）。"""
    q1 = Quaternion(q1).normalized()
    q2 = Quaternion(q2).normalized()
    # dot 夹到 [-1, 1] 避免 acos 域错误
    dot = max(-1.0, min(1.0, q1.dot(q2)))
    return 2.0 * abs(acos(abs(dot)))


def decompose_matrix(matrix: Matrix) -> tuple[Vector, Quaternion, Vector]:
    """把 4x4 矩阵分解为 (location, rotation_quaternion, scale)。"""
    m = Matrix(matrix)
    loc, rot, scale = m.decompose()
    return loc, rot, scale


def extract_camera_pose(matrix: Matrix) -> dict:
    """从世界矩阵提取摄影机位姿（位置 + 世界朝向）。"""
    loc, rot, scale = decompose_matrix(matrix)
    return {
        "location": loc,
        "rotation": rot,
        "scale": scale,
    }


# ---------------------------------------------------------------------------
# Orbit 求解 —— 与 rig 层级严格一致
#
# rig 层级（详见 core/rig.py）：
#     ROOT (世界位置 = Origin)
#       └─ YAW   (绕本地 Z = horizontal)
#           └─ PITCH (绕本地 X = vertical)
#               └─ BASE  (固定 rot.x = -90°，把相机 forward 从 -Z 转到水平)
#                   └─ DIST  (本地 +Z = distance，拉远)
#                       └─ CAMERA (真实相机)
#
# 因此 Camera 相对 Origin 的位置向量为：
#     rel = R_yaw(h) · R_pitch(v) · R_x(-90°) · (0, 0, d)
#         = ( -d·sin h·cos v,  d·cos h·cos v,  d·sin v )
#
# vertical = 0 → 水平环绕（Elevation 0 = 水平）
# vertical = +π/2 → 正上方俯视
# ---------------------------------------------------------------------------


def compose_orbit_matrix(origin: Vector, distance: float, horizontal: float, vertical: float) -> Vector:
    """根据 Orbit 参数绝对求解 Camera 世界位置（幂等，与 rig 层级一致）。

    与 compose_aim_world_matrix 的 translation 严格一致：
        R_z(h) · R_x(v) · R_x(90°) · (0,0,d)
        = ( d·sin h·cos v,  -d·cos h·cos v,  -d·sin v )
    """
    h = horizontal
    v = vertical
    rel = Vector((
        distance * sin(h) * cos(v),
        -distance * cos(h) * cos(v),
        -distance * sin(v),
    ))
    return Vector(origin) + rel


def solve_orbit_from_pose(origin: Vector, camera_world_pos: Vector) -> tuple[float, float, float]:
    """从 Camera 世界位置反解 (distance, horizontal, vertical)。

    与 compose_orbit_matrix 互为逆，用于 Enable / Set Origin 时反解参数。
    """
    d = Vector(camera_world_pos) - Vector(origin)
    distance = d.length
    if distance < 1e-12:
        return 0.0, 0.0, 0.0
    horizontal = atan2(d.x, -d.y)
    vertical = atan2(-d.z, sqrt(d.x * d.x + d.y * d.y))
    return distance, horizontal, vertical
