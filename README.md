# Cine Controller for Blender

电影级摄影机控制器（Cine Camera Rig）Blender 插件。

**目标平台**：Blender 5.2 LTS
**当前版本**：0.1.0（第一里程碑已完成）

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

允许的差异只有浮点容差，不允许肉眼可见变化。三条质量标准：

> - 今天调好、绑定 Origin/Aim/Focus，保存后关机，第二天打开镜头必须完全一样。
> - Camera View 里看到什么，正式 Render 就是什么。
> - 交付导出（Houdini / Unreal / Alembic / FBX）时只要 Bake，得到的动画与实时 Controller 完全一致。

## 功能状态

| 功能 | 状态 |
|------|------|
| Enable / Disable Controller | ✅ 已实现（事务化 + 位姿不跳） |
| Origin / Distance / Horizontal / Vertical | ✅ 已实现（Driver 绝对驱动） |
| Aim Target / Aim Influence | ✅ 已实现（Track To 约束） |
| Focus Target | ✅ 已实现（DOF，与 Transform 解耦） |
| Bake to Keyframes | ✅ 已实现（采样 evaluated matrix） |
| Position Offset / Pan / Tilt / Roll | ⬜ 未实现（规范要求里程碑 1 通过后开发） |

## 安装

1. 把整个 `CineController/` 目录复制到 Blender addons 目录，或
   在 `Edit > Preferences > Add-ons > Install` 选择本目录的 `__init__.py` 所在包。
2. 搜索 **Cine Controller** 并启用。
3. 选中一个 Camera，在 `3D Viewport > Sidebar (N) > Cine` 面板操作。

## 快速上手

1. 场景里放一个 Camera、一个 Empty（作为 Origin）。
2. 选中 Camera，面板里设 **Origin** 指向那个 Empty，点 **Enable Controller**。
3. 调整 Distance / Horizontal / Vertical，相机绕 Origin 轨道运动。
4. 需要看向某个目标：设 **Aim Target** + **Aim Influence**。
5. 需要焦点：设 **Focus Target**（只影响 DOF，绝不影响机位）。
6. 交付时点 **Bake to Keyframes**，得到普通 Camera 关键帧动画。

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
实时求值依赖 Parent Hierarchy + Constraint + Driver，**不使用**
`frame_change_post` / `depsgraph_update_post` / `load_post` 写回 Camera。

### Rig 层级

```text
ROOT   (Empty)  World Position = Origin（Copy Location，world→world）
  └─ YAW    (Empty)  Local rot.z = horizontal        [Driver]
      └─ PITCH  (Empty)  Local rot.x = vertical      [Driver]
          └─ BASE   (Empty)  Local rot.x = +90°      [固定，把 -Z forward 转到水平]
              └─ DIST   (Empty)  Local loc.z = distance  [Driver]
                  └─ AIM    (Empty)  Track To → Aim Target  [约束]
                      └─ CAMERA  (真实 Camera 对象)
```

Camera 相对 Origin 的位置（与 rig 求值严格一致）：

```text
R_z(h) · R_x(v) · R_x(90°) · (0,0,d)
= ( d·sin h·cos v,  -d·cos h·cos v,  -d·sin v )
```

vertical = 0 → 水平环绕；vertical = +90° → 正上方俯视。

### 三个独立系统域

| 系统 | 职责 | 输出 |
|------|------|------|
| Transform System | Origin / Distance / Horizontal / Vertical / Position Offset | Camera Position |
| Orientation System | Aim Target / Aim Influence / Pan / Tilt / Roll | Camera Rotation |
| Optical System | Lens / Sensor / Shift / DOF / Focus Target / Focus Distance / F-Stop | Camera Data |

- Focus System 与 Transform System **完全解耦**，Focus Target 绝不经 Helper 影响机位。
- Optical 变化绝不触发 Rig Rebuild。

## 目录结构

```text
CineController/
├── __init__.py                # 插件入口：bl_info + register/unregister + 热重载
├── core/                      # 核心求解逻辑（纯函数，无 UI 依赖）
│   ├── properties.py          # PropertyGroup 参数 + 最小副作用 update
│   ├── transform_system.py    # 位置求解
│   ├── orientation_system.py  # 旋转求解
│   ├── optical_system.py      # DOF / Lens 写入
│   ├── rig.py                 # Rig 构建 / 约束 / Driver / force_update
│   └── preserve_pose.py       # Preserve Pose 统一底层（Matrix 验证）
├── operators/
│   ├── enable.py              # Enable（事务化 + 失败回滚）
│   ├── disable.py             # Disable
│   └── bake.py                # Bake（采样 → 解绑 → 写 quaternion）
├── ui/
│   └── panel.py               # View3D Sidebar 面板
├── utils/
│   ├── math_utils.py          # matrix_close / quaternion_angle / orbit 反解
│   └── axis_utils.py          # 轴转换唯一入口（-Z = Forward 映射）
├── tests/                     # P0 自动化一致性测试
│   ├── run_tests.py           # Enable不跳 / Driver / Focus独立 / Aim / 幂等
│   ├── save_reload_test.py    # 真实 save+reload 逐帧矩阵一致
│   ├── bake_test.py           # Live ≈ Baked 每帧
│   ├── viewport_render_test.py# Viewport ≈ Render + scene.camera 切换
│   ├── run_all.sh             # 一键跑全部
│   └── scenes/                # 测试场景（camera_consistency.blend 等）
└── docs/                      # 稳定性与统一求值规范
```

## 测试

```bash
# 一键跑全部 P0 测试（需本机已装 Blender 5.2）
bash tests/run_all.sh

# 或单独跑
blender -b -P tests/run_tests.py
```

当前测试结果：**4 套 18 项全部通过，矩阵误差 0**。

| 测试 | 覆盖 | 结果 |
|------|------|------|
| run_tests | Enable 不跳 / Driver 生效 / Focus 独立 / Aim 只转朝向 / 幂等 | 11/11 |
| save_reload_test | 真实 .blend save + reload 逐帧矩阵一致 | 2/2 |
| bake_test | Live ≈ Baked 每帧 + Quaternion | 3/3 |
| viewport_render_test | Viewport ≈ Render + scene.camera 切换 | 2/2 |

> 已知 headless 限制：后台模式下直接改 Python 属性不会自动触发 Driver 重求值
> （Blender issue #91140），测试里统一走 `rig.force_update()`（内部 `update_tag()`）。

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

## 开发规范（简记）

- 求值顺序：Origin → Horizontal → Vertical → Distance → Base → Offset → Aim → Pan/Tilt/Roll → FINAL。
- Axis 约定：Blender 世界 `Z=Up`；Camera 本地 `-Z=Forward`、`+Y=Up`、`+X=Right`。符号映射只在 `axis_utils.py`。
- Preserve Pose 是 Enable / Set Origin / Repair / Remove 的统一底层。
- 所有 Helper 身份靠 PointerProperty 记录，**不靠对象名字符串**重查。
