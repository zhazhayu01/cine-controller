# Cine Controller for Blender

电影级摄影机控制器（Cine Camera Rig）Blender 插件。

**目标平台**：Blender 5.2 LTS
**当前版本**：0.1

## 核心承诺

一个已经调好的镜头，在保存、关闭、重新打开 Blender 之后，必须还是原来的镜头。

```text
Camera(Viewport, Frame N)
=
Camera(Render, Frame N)
=
Camera(After Reload, Frame N)
=
Camera(Baked, Frame N)
```

允许的差异只有浮点容差，不允许肉眼可见变化。

## 架构：Single Source of Truth

```text
Cine Controller Parameters
        ↓
Blender Dependency Graph
        ↓
FINAL Controller Transform
        ↓
Actual Camera Evaluated Transform
        ↓
┌──────────────┬──────────────┬──────────────┐
│ Viewport     │ Render       │ Bake         │
└──────────────┴──────────────┴──────────────┘
```

Viewport、Render、Bake 必须读取同一个最终 evaluated Camera Transform。

## 三个独立系统域

| 系统 | 职责 | 输出 |
|------|------|------|
| Transform System | Origin / Distance / Horizontal / Vertical / Position Offset | Camera Position |
| Orientation System | Aim Target / Aim Influence / Pan / Tilt / Roll | Camera Rotation |
| Optical System | Lens / Sensor / Shift / DOF / Focus Target / Focus Distance / F-Stop | Camera Data |

- Focus System 与 Transform System 完全解耦。
- Optical 变化绝不触发 Rig Rebuild。

## 目录结构

```text
CineController/
├── __init__.py            # 插件入口：bl_info + register/unregister
├── core/                  # 核心求解逻辑（纯函数，无 UI 依赖）
│   ├── transform_system.py
│   ├── orientation_system.py
│   ├── optical_system.py
│   ├── rig.py             # Rig 构建 / 约束 / Driver / Helper
│   └── preserve_pose.py   # Preserve Pose 统一底层算法
├── operators/             # bpy.types.Operator
├── ui/                    # Panel / UI
├── utils/
│   ├── math_utils.py      # matrix_close / quaternion_angle / decompose...
│   └── axis_utils.py      # 轴转换唯一入口
└── tests/                 # 自动化一致性测试
    └── scenes/            # camera_consistency.blend 等测试场景
```

## 硬性工程规则（Codex 开发约束）

1. Camera 最终结果只能有一个 Source of Truth。
2. Dependency Graph 是实时求值核心。
3. Viewport / Render / Bake 共用同一个 evaluated Camera result。
4. Focus System 与 Transform System 完全解耦。
5. 禁止 Focus Target 修改或初始化 Camera Transform。
6. 禁止 File Load 正常状态下重新初始化 Camera。
7. 禁止 Incremental Transform（`camera.location += offset`）。
8. 所有实时计算必须满足 Idempotent。
9. Local / World Space 必须显式定义。
10. Axis 转换必须集中在统一 Utility。
11. Preserve Pose 必须 Matrix 验证（位置 ≤ 1e-5 unit，旋转 ≤ 1e-5 rad）。
12. Bake 必须读取 evaluated Camera Matrix。
13. Camera Rename / Target Rename 不能破坏关系（名字不是身份）。
14. Pointer / Constraint Target 优先于 Name String。
15. Render 不允许重新计算另一套 Camera。
16. 任何失败优先保护用户已调好的 Camera。
17. Realtime Wrong / Bake Correct 仍属于严重 Bug。
18. Save / Reload Matrix Regression Test 是 P0。
19. Focus Save / Reload Regression Test 是永久测试。
20. V1 不通过一致性测试，不进入 V1.1。

完整规范见：`docs/Cine_Controller_稳定性与统一求值规范.md`

## 第一里程碑

最小场景（Origin / Camera / Cube / Focus Target / Aim Target）：

1. Enable Controller 后 Camera 不跳
2. Horizontal 0 → 720° 正常
3. Focus Target 移动不改变 Camera Transform
4. Save / Close / Reload 后 Camera 不漂
5. Viewport Matrix = Render Matrix
6. Live Matrix = Baked Matrix

全部通过后才继续开发 Offset / Pan / Tilt / Roll / UI。
