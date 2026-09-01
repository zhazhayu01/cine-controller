"""Rig 构建：Helper 层级 / Constraint / Driver / PointerProperty 关系。

规范关键点（§12 / §13 / §33 / §34）：
    - Helper 明确 Local / World Space。
    - Constraint 创建时显式指定 owner_space / target_space / track_axis / up_axis / mix_mode / influence。
    - Driver 必须绝对驱动（= horizontal，而不是 += horizontal）。
    - 关系用 PointerProperty / Constraint Target / Parent，优先于 Name String。

Rig 层级（建议结构）：
    ROOT       World Position
      YAW      Local Rotation (Horizontal)
        PITCH  Local Rotation (Vertical)
          RADIUS  Local Translation (Distance)
            BASE  Local Rotation
              OFFSET  Local Translation (Position Offset)
                AIM  Evaluated World Orientation via Constraint
                  LOCAL_ROT  Local Rotation (Pan/Tilt/Roll)
                    FINAL  World Evaluated Result → Actual Camera
"""
import bpy


def build_rig(camera_obj, origin_target=None, aim_target=None) -> dict:
    """为指定 Camera 构建 Cine Rig Helper 层级。

    返回 rig 结构 dict（后续模块据此操作 Helper）。
    注意：构建后必须调用 preserve_pose 反解参数，保证 Camera 不跳。
    """
    raise NotImplementedError("Rig 构建在里程碑 1 实现：Origin / Distance / Horizontal / Vertical / Aim / Focus")


def read_evaluated_camera_matrix(context, camera_obj) -> object:
    """读取 Camera 的 evaluated 世界矩阵（规范 §14）。

    统一入口：Bake / 对比测试 / Preserve Pose 都走这里。
    """
    depsgraph = context.evaluated_depsgraph_get()
    camera_eval = camera_obj.evaluated_get(depsgraph)
    return camera_eval.matrix_world.copy()
