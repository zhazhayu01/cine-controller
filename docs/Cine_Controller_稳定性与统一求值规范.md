# Cine Controller 稳定性与统一求值规范

版本：0.1  
适用项目：Cine Controller for Blender  
目标平台：Blender 5.2 LTS  
用途：作为 Cine Controller V1 产品需求的补充工程规范，重点解决摄像机在文件重载、Dependency Graph 求值、Viewport / Render 差异、Target 绑定、Bake 等场景中的一致性问题。

---

# 1. 文档目标

Cine Controller 的第一优先级不是“功能多”，而是：

> 一个已经调好的镜头，在保存、关闭、重新打开 Blender 之后，必须还是原来的镜头。

其次必须保证：

> Viewport 中看到的摄影机结果、Render 时真正使用的摄影机结果、Bake 后得到的普通 Camera Animation，三者必须一致。

本插件不能接受以下情况：

- 保存前 Camera 正常，重新打开项目后坐标漂移。
- 绑定 Focus Target 后，下次打开文件 Camera 位置发生变化。
- Viewport Camera View 正常，但正式 Render 时机位不同。
- Scrub Timeline 时正常，播放时 Camera 跳动。
- Viewport 中 Aim 正常，渲染时 Aim 朝向不一致。
- Camera Bake 后结果反而是正确的，但未 Bake 的实时 Rig 是错误的。
- Camera 在某些帧重新求值后发生 Offset 累加。
- File Load 时插件重复执行初始化，导致 Camera 再次被 Offset。
- Target 被删除、重命名、重新绑定后引发 Camera Transform 变化。
- Helper Rig 的 Local / World Transform 在 Reload 后被错误恢复。

如果出现：

> “Bake 成关键帧后就是对的，但实时 Controller 在 Viewport / Render / Reload 中不一致”

应该视为插件架构问题，而不是正常现象。

---

# 2. 核心原则：Single Source of Truth

整个 Cine Controller 必须只有一套真正的 Camera Transform 求解结果。

禁止同时存在：

```text
Viewport 求一套
Render 求一套
Bake 再求一套
```

正确结构：

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

Viewport、Render、Bake 都必须读取同一个最终 evaluated Camera Transform。

禁止 Bake 使用另一套独立数学算法重新计算摄影机。

Bake 的职责是：

> 采样当前真实 evaluated result，而不是“重新推算一个理论 Camera”。

---

# 3. 系统必须拆成三个独立域

整个插件拆成：

```text
A. TRANSFORM SYSTEM
B. ORIENTATION SYSTEM
C. OPTICAL SYSTEM
```

---

# 4. Transform System

负责：

- Origin
- Distance
- Horizontal
- Vertical
- Position Offset

输出：

```text
Camera Position
```

这套系统只负责摄影机空间位置。

---

# 5. Orientation System

负责：

- Aim Target
- Aim Influence
- Pan
- Tilt
- Roll

输出：

```text
Camera Rotation
```

Orientation 可以依赖 Transform 输出的位置。

例如：

```text
Camera Position
      ↓
Aim Target
      ↓
Camera Orientation
```

但不能反向修改 Transform 参数。

禁止 Aim 系统重新设置：

- Origin
- Distance
- Horizontal
- Vertical
- Position Offset

---

# 6. Optical System

负责：

- Lens
- Sensor
- Shift
- Depth of Field
- Focus Target
- Focus Distance
- F-Stop

Optical System 只能影响：

```text
Camera Data
```

禁止修改：

```text
Camera Transform
```

特别是 Focus Target 必须严格与 Camera Transform 解耦。

---

# 7. Focus Target 强制独立规则

Focus Target 永远不能参与 Camera Transform 求解。

正确：

```text
Focus Target
      ↓
camera.data.dof.focus_object
```

或者未来使用：

```text
Focus Target
      ↓
Calculated Focus Distance
      ↓
camera.data.dof.focus_distance
```

错误：

```text
Focus Target
      ↓
Helper Transform
      ↓
Camera Transform
```

绝对禁止。

---

# 8. Focus Target P0 稳定性要求

以下任何操作：

- Bind Focus Target
- Unbind Focus Target
- Move Focus Target
- Rotate Focus Target
- Scale Focus Target
- Rename Focus Target
- Delete Focus Target
- Save File
- Reload File
- Reopen Blender

都不得改变：

- Camera matrix_world
- Origin
- Distance
- Horizontal
- Vertical
- Offset
- Pan
- Tilt
- Roll
- Aim Target
- Aim Influence

Focus Target 只能改变焦点相关结果。

---

# 9. Dependency Graph 是唯一实时求值系统

实时 Camera Motion 优先依赖：

- Parent Hierarchy
- Constraints
- Drivers
- Blender Dependency Graph

尽量禁止通过：

```python
frame_change_post
depsgraph_update_post
load_post
```

持续写回 Camera Transform。

尤其禁止以下逻辑：

```python
def update():
    camera.matrix_world = calculate_camera()
```

在多个 Handler 中重复执行。

原因：

- Viewport 与 Render 可能使用不同 Context。
- Dependency Graph 可能重复触发。
- Handler 执行顺序可能变化。
- File Load 后可能再次初始化。
- Render Depsgraph 与 Viewport Depsgraph 不是同一个 evaluated object。
- 可能出现一帧被计算两次导致 Offset 累加。
- Scrub、Playback、Render 的调用时序可能不同。

---

# 10. 不允许 Incremental Transform

插件内部 Transform 必须使用：

```text
Absolute Evaluation
```

禁止：

```text
Current Transform
+
Delta
=
New Transform
```

例如禁止：

```python
camera.location += offset
```

正确方式：

```text
Camera Final Transform
=
Function(
    Origin,
    Distance,
    Horizontal,
    Vertical,
    Offset,
    Aim,
    Pan,
    Tilt,
    Roll
)
```

每次求值都应该从参数直接得到同一个确定结果。

这样：

```text
Evaluate 1 次
Evaluate 10 次
```

结果应该完全一样。

---

# 11. 幂等性要求

核心求值逻辑必须满足：

```text
Evaluate(State) = Result
Evaluate(State) = Result
Evaluate(State) = Result
```

结果完全一致。

不能出现：

```text
第一次 Evaluate → Position A
第二次 Evaluate → Position A + Offset
第三次 Evaluate → Position A + 2 × Offset
```

所有 Initialization / Repair / Reload 逻辑也必须尽量满足幂等。

---

# 12. Local Space 与 World Space 必须统一

这是本插件最重要的工程约束之一。

所有 Helper 必须明确记录：

```text
这个节点使用 Local Space 还是 World Space。
```

禁止在不同函数中隐式混用。

建议：

```text
ROOT
World Position

YAW
Local Rotation

PITCH
Local Rotation

RADIUS
Local Translation

BASE
Local Rotation

OFFSET
Local Translation

AIM
Evaluated World Orientation via Constraint

LOCAL_ROT
Local Rotation

FINAL
World Evaluated Result
```

---

# 13. Camera World Matrix 是最终真相

当插件需要：

- Preserve Pose
- Set Origin
- Remove Controller
- Bake
- Validate Reload Result

必须优先读取：

```python
evaluated_camera.matrix_world
```

而不是简单读取：

```python
camera.location
camera.rotation_euler
```

原因：

Camera 最终结果可能包含：

- Parent
- Constraint
- Driver
- Helper Rig
- Animation
- Dependency Graph

因此：

```text
Object Local Transform
≠
Final Camera Transform
```

---

# 14. 必须使用 Evaluated Dependency Graph

获取最终 Camera Transform 时：

```python
depsgraph = context.evaluated_depsgraph_get()
camera_eval = camera.evaluated_get(depsgraph)
matrix = camera_eval.matrix_world.copy()
```

Bake、对比测试等都必须以 evaluated result 为准。

---

# 15. Viewport 与 Render 的统一原则

Cine Controller 不允许专门针对 Viewport 修改 Camera。

禁止依赖：

- Area
- Region
- SpaceView3D
- 当前 Editor 状态
- 当前选中对象
- 当前 3D View Camera Perspective 状态

来决定最终摄影机 Transform。

最终摄影机结果必须属于：

```text
Scene Dependency Graph
```

而不是：

```text
Viewport UI State
```

---

# 16. Render 不能执行另一套 Camera 更新逻辑

禁止：

```text
Viewport Handler → Camera Transform A

render_pre →
重新计算 →
Camera Transform B
```

Render 不应重新初始化 Cine Controller。

Render 只应该读取：

```text
Scene Camera Final Evaluated Transform
```

---

# 17. Viewport / Render 一致性验收

设置动画：

```text
Frame 1-100
```

随机测试至少：

```text
1
10
25
50
75
100
```

在每一帧记录：

```text
Viewport Evaluated Camera Matrix
```

随后执行正式 Render 前读取：

```text
Render Dependency Graph Camera Matrix
```

要求两者近似相等：

```text
M_viewport ≈ M_render
```

位置误差与旋转误差必须仅处于浮点容差。

---

# 18. Render 测试不能只肉眼判断

至少建立自动化 Matrix Test。

例如：

```python
assert_matrix_close(
    viewport_camera_matrix,
    render_camera_matrix,
    tolerance
)
```

后续还可以添加图像级测试，但 V1 优先 Matrix。

---

# 19. 文件保存 / 加载原则

保存 `.blend` 时：

必须依赖 Blender 自身保存：

- PropertyGroup Values
- Driver
- Constraint
- Object Relationship
- PointerProperty
- Helper Objects
- Camera Data

不要额外维护一份“Camera World Transform Cache”作为主要状态源。

---

# 20. 禁止 Load 时重新初始化 Camera

File Load 后：

禁止自动执行：

```text
Enable Controller
Set Origin
Reset Offset
Rebuild Camera Pose
Recalculate Initial Distance
```

除非：

```text
Rig 真正损坏
```

正常文件打开时应该：

```text
读取现有 Rig
↓
Dependency Graph 求值
↓
得到与保存前一致的 Camera
```

而不是：

```text
打开文件
↓
插件认为要重新初始化
↓
Camera 被重新求解
↓
出现漂移
```

---

# 21. load_post Handler 原则

V1 尽量不使用：

```python
bpy.app.handlers.load_post
```

修改 Camera Transform。

如果未来必须使用 `load_post`：

它只能做：

- Validation
- Reference Repair
- UI Cache Rebuild
- Missing Target Check

禁止：

```text
修改正常 Camera Rig Transform
重新求解 Camera Pose
重新绑定 Constraint 导致 Offset 改变
```

---

# 22. Reload 时不能依赖对象加载顺序

项目重新打开时：

不能假设：

```text
Origin Target 先加载
Camera 后加载
Helper 再加载
```

所有关系必须由 Blender ID Reference / PointerProperty / Constraint Target 保存。

不要通过：

```text
Object Name String
```

重新查找并重建关键关系。

---

# 23. UUID 只负责身份识别

UUID 用于：

- 确定一套 Cine Rig 属于哪个 Camera
- Repair
- Cleanup
- Duplicate Detection

但真正关系尽可能使用：

```text
PointerProperty
Constraint Target
Parent Relationship
```

不要在每次 File Load 时：

```python
bpy.data.objects.get(stored_name)
```

重新拼装整个 Rig。

---

# 24. Rename Stability

以下操作：

```text
Camera
→ Camera_Main

Freya
→ Freya_Final

CC_ROOT
→ 用户误改名称
```

不能直接让 Controller 失效。

名字不是身份。

---

# 25. Target 删除安全性

Origin / Aim / Focus Target 删除时：

不得产生未处理异常。

---

# 26. Focus Target 删除

结果：

```text
Focus Target = None
```

Camera Transform 完全不变。

---

# 27. Aim Target 删除

建议：

```text
Aim Target = None
Aim Constraint Influence = 0
```

Camera 当前 World Orientation 是否保持，需要明确处理。

推荐：

删除 Aim Target 时：

1. 记录删除前最后一个有效 Camera World Matrix。
2. 将当前最终 Orientation Bake 回 Local Rotation / Internal Orientation Offset。
3. Disable Aim。
4. 保持 Camera 当前画面。

如果 V1 难以自动捕获删除事件：

最低要求：

- 不崩溃。
- Camera 不出现 NaN / Infinity。
- UI 显示 Missing Aim Target。
- 提供 `Preserve Current Pose & Disable Aim`。

---

# 28. Origin Target 删除

Origin 比 Aim 更危险，因为 Origin 参与 Camera Position。

Origin Target 删除时：

目标：

```text
Camera 不跳
```

理想行为：

```text
OBJECT
→
STATIC
```

Static Origin：

使用 Target 删除前最后一个有效 World Position。

因此建议插件保存：

```text
last_valid_origin_world_position
```

注意这只是容错缓存，不是 Camera Transform 的主要状态源。

---

# 29. Rig Helper 被删除

不得自动静默创建一套新 Rig 并改变 Camera。

正确：

```text
Cine Rig Damaged
```

UI：

```text
[ Repair Rig ]
```

Repair 前：

记录：

```text
Current Camera Evaluated World Matrix
```

Repair 后：

必须保持：

```text
Camera Pose
```

---

# 30. Preserve Pose 是整个插件的基础算法

以下操作统一使用同一个底层：

```text
preserve_camera_pose()
```

适用：

- Enable Controller
- Set Origin
- Change Origin Mode
- Repair Rig
- Remove Controller
- Rebind Aim（如需要）
- Future Rig Upgrade

统一逻辑：

```text
1. 获取 Current Evaluated Camera World Matrix
2. 修改内部结构
3. 反解 / 设置 Controller Parameters
4. Force Dependency Graph Update
5. 再次读取 Evaluated Camera Matrix
6. 比较 Before / After
7. 超出容差则回滚或者报错
```

---

# 31. 不允许“看起来差不多”

Preserve Pose 必须使用 Matrix Comparison。

建议误差：

位置：

```text
<= 1e-5 Blender Unit
```

旋转：

可使用 Quaternion Angular Difference。

例如：

```text
<= 1e-5 radians
```

具体容差可根据 Blender Float Precision 调整。

---

# 32. Camera Matrix 不应该保存两份

避免：

```text
Camera Matrix
Rig Matrix
Cached Matrix
Plugin Matrix
```

四套互相同步。

推荐：

```text
Controller Parameters
→
Rig
→
Evaluated Camera Matrix
```

Cache 只用于：

- 临时操作
- Validation
- Error Recovery

而不是长期驱动状态。

---

# 33. Constraint 的 Transform Space 必须显式设置

所有 Constraint 创建时：

禁止依赖 Blender 默认值。

必须显式指定：

```text
owner_space
target_space
track_axis
up_axis
mix_mode
influence
```

否则 Blender 默认行为变化或不同 Constraint 类型默认值可能造成不可预测结果。

---

# 34. Driver 必须绝对驱动

例如：

```text
YAW.rotation_euler.z
```

Driver：

```text
= horizontal
```

而不是：

```text
= current_rotation + horizontal
```

Driver 结果必须是确定值。

---

# 35. Driver Namespace 谨慎使用

尽量不要依赖自定义 Python Driver Function。

优先简单 Driver Variable + Expression。

例如：

```text
distance
horizontal
vertical
```

原因：

自定义 Driver Namespace 在：

- File Load
- Background Render
- Render Farm
- Script Auto Run Security

场景中更容易产生额外问题。

---

# 36. Background Render 必须考虑

即使 V1 主要面向交互 Blender：

Controller 最终架构也必须能够在：

```bash
blender -b project.blend -f 1
```

这样的 Background Render 中正确求值。

因此不能依赖：

```text
3D Viewport Context
Active Area
Selected Camera
UI Panel 是否打开
```

---

# 37. Camera Active / Inactive 不影响求值

即使某个 Cine Camera 当前不是：

```text
scene.camera
```

它的 Rig 也应该保持数据完整。

切换：

```text
Scene Camera A
→
Scene Camera B
→
Scene Camera A
```

不能改变 Camera A Transform。

---

# 38. Camera Selection 不影响求值

选择：

```text
Cube
Light
Character
```

不能改变 Camera 结果。

Camera Controller 不允许依赖当前 Active Object 持续驱动。

Active Object 只允许用于用户点击 Operator 时取得输入。

---

# 39. Bake 是最终一致性基准

Bake 不是修复实时 Rig 的手段。

如果出现：

```text
Realtime Wrong
Bake Correct
```

必须修 Realtime。

不能接受：

> “反正最终 Bake 是对的。”

插件的设计目标是：

```text
Realtime = Render = Bake
```

---

# 40. Bake 的唯一数据来源

每帧：

```text
scene.frame_set(frame)

depsgraph = context.evaluated_depsgraph_get()

camera_eval = camera.evaluated_get(depsgraph)

M = camera_eval.matrix_world.copy()
```

然后：

```text
Baked Camera.matrix_world = M
```

再插关键帧。

不要使用：

```text
Distance
Horizontal
Vertical
```

再次独立求 Camera Position。

---

# 41. Bake 必须包含 Camera Optical Animation

除了 Transform：

如果下列数据存在动画：

- Lens
- Shift X
- Shift Y
- DOF Focus Distance
- F-Stop

需要：

- Copy Camera Data Animation
或
- 对这些属性逐帧 Bake

V1 最低要求：

Lens Animation 不得丢失。

---

# 42. Bake 与实时结果验收

每一帧：

```text
M_live(frame)
M_baked(frame)
```

要求：

```text
M_live ≈ M_baked
```

测试至少：

```text
Frame Start → Frame End
每帧比较
```

而不是只看第一帧和最后一帧。

---

# 43. Rotation Bake 使用 Quaternion

推荐：

```text
rotation_mode = 'QUATERNION'
```

从 Matrix 分解：

```python
location, rotation, scale = matrix.decompose()
```

写：

```text
location
rotation_quaternion
```

不要为了“方便查看曲线”强制转换 Euler。

最终一致性优先。

---

# 44. Reload 回归测试是 P0

必须建立真实 `.blend` Save / Reload 测试。

不是只：

```text
注册
注销
重新注册 Add-on
```

而是真正：

```text
创建场景
↓
保存 project.blend
↓
关闭当前文件状态
↓
重新打开 project.blend
↓
读取 Camera Matrix
```

---

# 45. Save / Reload 基础测试

流程：

```text
Camera
Origin
Aim
Focus
```

创建 Cine Controller。

Frame ：

```text
1
20
50
100
```

分别记录：

```text
Camera Evaluated Matrix
```

Save。

Reload。

重新记录。

要求：

```text
Before Save ≈ After Reload
```

所有测试帧均成立。

---

# 46. Focus Reload Bug 回归测试

专门针对已知 Camera Plugin 类型问题。

场景：

```text
Camera
Origin
Focus_Target
```

步骤：

```text
Enable Controller

Bind Focus Target

Frame 1:
记录 M1

Save
Reload

读取 M2
```

要求：

```text
M1 ≈ M2
```

然后：

```text
Move Focus Target

记录 Camera Transform
```

要求：

```text
Camera Transform 完全不变
```

继续：

```text
Save
Reload
```

仍然不变。

---

# 47. Aim Reload 测试

Aim 与 Focus 不同。

Aim 本来就应该改变 Rotation。

但同一帧、同一 Target 状态下：

```text
Before Save
After Reload
```

Camera Rotation 必须一致。

---

# 48. Moving Origin Reload 测试

Origin：

```text
Object Mode
```

Origin Target 有 Animation。

Camera 有：

- Distance Animation
- Horizontal Animation
- Vertical Animation

Save / Reload 后：

逐帧 Camera Matrix 必须一致。

---

# 49. Viewport vs Render 测试

场景：

- Moving Origin
- Aim Target
- Focus Target
- Horizontal 动画超过 360°
- Lens 动画

记录：

```text
Viewport evaluated matrix
```

再在 Render Depsgraph 中读取。

要求：

```text
Viewport ≈ Render
```

---

# 50. Render Image 验收场景

建议建立一个专门测试文件：

```text
tests/scenes/camera_consistency.blend
```

场景中：

- 地面 Grid
- 三个彩色或编号立方体
- 前景柱体
- Camera
- Origin
- Aim
- Focus

测试可以很容易肉眼识别 Camera 是否漂移。

---

# 51. 测试场景必须覆盖空间层级

至少测试 Camera 或 Target 存在 Parent 的情况。

例如：

```text
Character_ROOT
└── Freya
```

Origin Target：

```text
Freya
```

必须使用：

```text
Freya World Position
```

而不是 Local Location。

---

# 52. Scale 测试

如果 Target Parent 存在 Scale：

```text
0.5
2.0
```

Origin / Aim Target 的 World Transform 仍应正确。

Rig 本身尽量避免非 1 Scale。

Helper 默认：

```text
Scale = 1,1,1
```

不要用 Scale 表示 Distance。

---

# 53. Rig 不使用 Scale 表示摄影参数

Distance 使用：

```text
Translation
```

不要：

```text
Scale
```

原因：

Scale 会影响子节点 Transform、Constraint、Matrix Decompose，增加不可预测性。

---

# 54. Negative Scale

V1 可以明确：

Cine Rig 自身不支持 Negative Scale Parent。

如果 Camera 原本存在 Negative Scale Parent：

Enable 时：

- 检测
- Warning
- Preserve World Pose
- Camera 仍通过 World Space Copy Transforms 驱动

避免把负缩放传入内部 Rig。

---

# 55. Scene Unit 不应该改变算法

Distance 使用 Blender Unit。

UI：

```text
subtype='DISTANCE'
```

让 Blender 负责：

- Metric
- Imperial
- Unit Scale

内部不要硬编码：

```text
1 unit = 1 meter
```

---

# 56. FPS 不影响 Camera 求值

Camera Motion 由 Frame / F-Curve 驱动。

改变 FPS：

```text
24 → 30
```

不应改变同一个 Frame Index 上的 Camera Transform。

时间语义变化属于 Blender Animation 本身，不由插件自行补偿。

---

# 57. Evaluation Order 设计

建议 Rig 求值顺序逻辑明确为：

```text
Origin Translation
        ↓
Horizontal Orbit
        ↓
Vertical Orbit
        ↓
Distance
        ↓
Base Camera Orientation
        ↓
Position Offset
        ↓
Aim Orientation
        ↓
Pan / Tilt / Roll
        ↓
FINAL
        ↓
Actual Camera
```

这套顺序必须在：

- 代码
- 文档
- Unit Test

中保持一致。

---

# 58. 不允许不同模块自己猜 Axis

统一坐标定义。

建议文档明确：

```text
Blender World:
Z = Up

Blender Camera:
Local -Z = Forward
Local +Y = Up
Local +X = Right
```

Cine Controller 逻辑轴：

```text
Horizontal = Orbit around World / Origin Z

Vertical = Elevation around local orbit X

Offset X = Camera Right
Offset Y = Camera Up
Offset Z = Camera Forward
```

注意：

因为 Blender Camera Forward 是 `-Z`：

UI 的：

```text
Offset Z Positive = Forward
```

底层可能需要映射：

```text
local_z = -offset_z
```

这个映射只允许在一个统一函数处理。

---

# 59. 建立 Axis Utility

禁止各文件手写符号转换。

例如统一：

```python
cine_offset_to_blender_local()
blender_local_to_cine_offset()
camera_forward_world()
camera_up_world()
camera_right_world()
```

这样避免：

```text
rig_builder.py 认为 +Y 是 Forward
bake.py 认为 -Z 是 Forward
origin.py 又使用 +Z
```

造成长期漂移 Bug。

---

# 60. Matrix Utility 统一入口

建议：

```text
utils/math_utils.py
```

提供：

```python
matrix_close()
quaternion_angle_difference()
extract_camera_pose()
solve_orbit_from_pose()
compose_orbit_matrix()
```

所有模块使用同一套函数。

---

# 61. Set Origin 不重新累计 Offset

Set Origin：

```text
Old Origin
→
New Origin
```

要求：

当前 Camera Pose 保持。

建议策略：

1. 记录 Camera World Matrix。
2. 将 Offset 暂时归零或纳入反解。
3. 计算新 Origin 到 Camera 的 Vector。
4. 得到 Distance / Horizontal / Vertical。
5. 计算剩余 Local Rotation。
6. Re-evaluate。
7. Matrix Compare。

不能：

```text
New Origin
+
Old Offset
+
再次计算出来的 Offset
```

形成双重 Offset。

---

# 62. Aim Enable 不应该突然改变位置

Aim 只能修改 Orientation。

启用 Aim：

```text
Camera Position Before
=
Camera Position After
```

必须严格成立。

---

# 63. Aim Influence 0 → 1

当：

```text
Influence = 0
```

Camera 应保持原 Orientation。

当：

```text
Influence = 1
```

Camera 对准 Aim Target。

Constraint Blend 必须来自 Blender 求值系统。

不要 Python 每帧做：

```text
slerp
```

除非原生 Constraint 无法满足需求。

---

# 64. Optical 更新不能触发 Rig Rebuild

以下变化：

```text
Lens
F-Stop
Focus Target
Focus Distance
Sensor
```

不得调用：

```text
rebuild_rig()
preserve_pose()
set_origin()
```

这是严格禁止项。

---

# 65. UI 更新函数不能修改无关模块

例如：

```text
Focus Target PointerProperty update()
```

只允许：

```text
更新 DOF
```

不能：

```text
重新初始化 Camera
更新 Rig Root
重新计算 Orbit
```

减少隐式副作用。

---

# 66. 每个 Property Update 必须最小副作用

规则：

```text
Distance Change
→ 只影响 Radius

Horizontal Change
→ 只影响 Yaw

Vertical Change
→ 只影响 Pitch

Offset Change
→ 只影响 Offset Node

Focus Change
→ 只影响 Camera Data DOF
```

模块越独立，Save / Reload / Render 一致性越高。

---

# 67. Repair 不能静默覆盖动画

如果 Rig 损坏，但 Controller 参数已有 Animation：

Repair 时：

必须保留：

- F-Curves
- Property Values

只重新创建 Helper / Driver / Constraint。

不能：

```text
重置参数
```

---

# 68. Extension Upgrade 兼容

未来从：

```text
0.1
→
0.2
```

不要在注册插件时自动重建所有 Camera Rig。

如果数据结构需要迁移：

必须有：

```text
rig_version
```

例如：

```text
cine_controller.rig_version = 1
```

未来：

```text
Upgrade Rig
```

也必须 Preserve Pose。

---

# 69. Scene Duplicate / Append / Link

V1 可以不完整支持 Library Link。

但至少：

```text
Duplicate Scene
Append Object
```

不能让 UUID 冲突造成原 Camera Rig 被误删除。

---

# 70. Delete Controller 只删除自己的 Helper

Cleanup：

必须通过：

```text
rig UUID
+
Pointer References
```

确认 Helper。

禁止：

```text
删除所有名字以 CC_ 开头的 Object
```

---

# 71. Error 处理原则

发生异常时：

优先：

```text
保留用户 Camera
```

而不是：

```text
强制重建 Camera Rig
```

插件不能为了恢复自身状态而破坏已调好的镜头。

---

# 72. 操作事务化

对于高风险 Operator：

- Enable
- Set Origin
- Repair
- Remove

推荐：

```text
BEGIN
记录 Camera Pose / Controller State

执行修改

Validate

成功：
COMMIT

失败：
ROLLBACK
```

避免执行一半留下坏 Rig。

---

# 73. Debug Mode

建议 V1 提供隐藏开发选项：

```text
Developer Debug
```

输出：

- Camera evaluated matrix
- FINAL matrix
- Origin world position
- Distance
- Horizontal
- Vertical
- Current Dependency Graph frame
- Rig UUID

方便排查：

```text
Viewport 对
Render 错
```

这类问题。

正式 UI 默认隐藏。

---

# 74. 不在 Console 每帧 Spam

Debug 输出只能按需触发。

不要在 Dependency Graph 每次求值：

```python
print(...)
```

否则复杂场景几乎无法调试。

---

# 75. P0 自动化测试清单

V1 发布前必须通过：

## A. Enable Stability

```text
Before Matrix
≈
After Enable Matrix
```

---

## B. Set Origin Stability

```text
Before Matrix
≈
After Set Origin Matrix
```

---

## C. Focus Independence

绑定 / 移动 / 删除 Focus：

```text
Camera Transform 不变
```

---

## D. Save / Reload

保存前 / 重开后：

```text
Camera Matrix 一致
```

---

## E. Viewport / Render

```text
Viewport Matrix
≈
Render Matrix
```

---

## F. Bake

```text
Live Matrix
≈
Baked Matrix
```

每帧成立。

---

## G. Repeated Evaluation

相同 Frame 连续 Dependency Graph Update：

```text
Camera Matrix 不变化
```

---

## H. Target Rename

Rename：

- Origin
- Aim
- Focus

Controller 正常。

---

## I. Target Delete

无未处理异常。

Focus 删除尤其不能移动 Camera。

---

## J. Save / Reload + Focus

这是专门的 Bug Regression Test。

必须长期保留。

---

# 76. 最终一致性公式

整个插件最终必须满足：

```text
Camera(Viewport, Frame N)
=
Camera(Render, Frame N)
=
Camera(After Reload, Frame N)
=
Camera(Baked, Frame N)
```

允许的差异只有：

```text
Floating Point Tolerance
```

不允许存在肉眼可见变化。

---

# 77. 项目最高优先级

如果开发过程中出现：

```text
A. 新功能
B. Camera 稳定性
```

永远选择：

```text
B
```

宁可 V1 没有：

- Dolly Zoom
- Ghost Frame
- Lock Framing
- Multi Target
- 9:16 Overlay

也不能出现：

> 下次打开项目以后镜头变了。

---

# 78. Codex 开发硬规则

请严格遵守：

1. Camera 最终结果只能有一个 Source of Truth。
2. Dependency Graph 是实时求值核心。
3. Viewport / Render / Bake 共用同一个 evaluated Camera result。
4. Focus System 与 Transform System 完全解耦。
5. 禁止 Focus Target 修改或初始化 Camera Transform。
6. 禁止 File Load 正常状态下重新初始化 Camera。
7. 禁止 Incremental Transform。
8. 所有实时计算必须满足 Idempotent。
9. Local / World Space 必须显式定义。
10. Axis 转换必须集中在统一 Utility。
11. Preserve Pose 必须 Matrix 验证。
12. Bake 必须读取 evaluated Camera Matrix。
13. Camera Rename / Target Rename 不能破坏关系。
14. Pointer / Constraint Target 优先于 Name String。
15. Render 不允许重新计算另一套 Camera。
16. 任何失败优先保护用户已调好的 Camera。
17. Realtime Wrong / Bake Correct 仍然属于严重 Bug。
18. Save / Reload Matrix Regression Test 是 P0。
19. Focus Save / Reload Regression Test 是永久测试。
20. V1 不通过一致性测试，不进入 V1.1。

---

# 79. 第一开发里程碑

第一里程碑不以 UI 为判断标准。

必须建立一个最简单测试场景：

```text
Origin
Camera
Cube
Focus Target
Aim Target
```

实现：

- Enable Controller
- Distance
- Horizontal
- Vertical
- Aim
- Focus

然后验证：

```text
1. 当前 Camera Enable 后不跳
2. Horizontal 0 → 720° 正常
3. Focus Target 移动不会改变 Camera Transform
4. Save
5. Close / Reload
6. Camera 不漂
7. Viewport Matrix = Render Matrix
8. Bake
9. Live Matrix = Baked Matrix
```

只有这套测试完全通过，才继续开发：

- Offset
- Pan / Tilt / Roll
- UI Polish
- 其他 V1 功能

---

# 80. 产品质量标准

Cine Controller 最终要达到的用户预期：

> 我今天把 Camera 调好、绑定 Origin、Aim、Focus，保存 Blender 文件后关机。第二天打开这个项目，镜头必须和昨天完全一样。

以及：

> 我在 Camera View 里看到什么，正式 Render 就应该是什么。

以及：

> 我什么时候需要交付、导出、送 Houdini / Unreal / Alembic / FBX，只要 Bake Camera，得到的动画必须与实时 Cine Controller 完全一致。

这三条是整个插件最重要的质量标准。
