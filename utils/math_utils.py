"""数学工具：矩阵比较 / 四元数角度差 / 位姿分解 / Orbit 求解。

整个插件所有模块共用这一套函数，禁止各文件手写矩阵比较或轴转换。
"""
from math import acos, pi
from mathutils import Matrix, Quaternion, Vector

# 默认浮点容差（Blender Unit / radian）
POSITION_TOLERANCE = 1e-5
ROTATION_TOLERANCE = 1e-5


def matrix_close(m1: Matrix, m2: Matrix, pos_tol=POSITION_TOLERANCE, rot_tol=ROTATION_TOLERANCE) -> bool:
    """比较两个 4x4 世界矩阵是否在容差内近似相等。

    同时比较位置（translation）与旋转（quaternion 角度差）。
    忽略 Scale 差异时传入 compare_scale=False。
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
