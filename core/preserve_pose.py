"""Preserve Pose —— 整个插件的基础算法（规范 §30 / §31）。

统一底层，适用：
    Enable Controller / Set Origin / Change Origin Mode / Repair Rig /
    Remove Controller / Rebind Aim / Future Rig Upgrade

统一逻辑：
    1. 获取 Current Evaluated Camera World Matrix
    2. 修改内部结构
    3. 反解 / 设置 Controller Parameters
    4. Force Dependency Graph Update
    5. 再次读取 Evaluated Camera Matrix
    6. 比较 Before / After
    7. 超出容差则回滚或报错
"""
import bpy

from ..utils.math_utils import matrix_close, POSITION_TOLERANCE, ROTATION_TOLERANCE


def preserve_camera_pose(context, camera_obj, mutate_fn, pos_tol=POSITION_TOLERANCE, rot_tol=ROTATION_TOLERANCE) -> bool:
    """执行结构修改并验证 Camera 位姿保持不变。

    Args:
        context:   bpy.context
        camera_obj: 目标 Camera Object
        mutate_fn: callable，执行内部结构修改（如 build rig / rebind constraint）。
                   签名 mutate_fn() -> None。
        pos_tol / rot_tol: 容差。

    Returns:
        bool: True 表示位姿在容差内保持；False 表示发生漂移。
    """
    from .rig import read_evaluated_camera_matrix

    # 1. 记录修改前
    before = read_evaluated_camera_matrix(context, camera_obj)

    # 2-3. 执行修改（内部负责反解参数）
    mutate_fn()

    # 4. 强制 Dependency Graph 更新
    depsgraph = context.evaluated_depsgraph_get()
    depsgraph.update()

    # 5. 读取修改后
    after = read_evaluated_camera_matrix(context, camera_obj)

    # 6-7. 比较
    return matrix_close(before, after, pos_tol=pos_tol, rot_tol=rot_tol)
