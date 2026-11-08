# 通过 MCP 使用 Cine Controller

适配项目：<https://github.com/ahujasid/mcp-for-blender>。该项目的 `execute_blender_code` 在 Blender 中执行 Python，并将标准输出返回给 AI。本插件提供原生操作 `bpy.ops.cine.automation` 作为 JSON 入口，不需要修改 MCP 服务端或启动新的通信端口。

## 安装与识别

1. 将 Cine Controller 更新到 1.0.0，重新启用插件。
2. 保持现有 Blender MCP 的安装和连接方式。
3. 在插件齿轮设置中点击“复制 MCP 接入指令”，粘贴到 AI 客户端的项目指令或会话中。支持 `AGENTS.md` 的客户端在本仓库工作时也可读取根目录规则；详细规则见下文。
4. 让 AI 先执行发现脚本，再根据返回的接口版本操作。MCP 本身的 `get_addon_status` 主要检查它自己的桥接和资产功能，不会自动注入本插件的业务规则。

发现脚本，通过 MCP 的 `execute_blender_code` 执行：

```python
import bpy

try:
    bpy.ops.cine.automation.get_rna_type()
except Exception:
    raise RuntimeError("请先安装并启用 Cine Controller 1.0.0")

bpy.ops.cine.automation(request_json='{"action":"describe"}')
bpy.ops.cine.automation(request_json='{"action":"list"}')
```

入口只需导入 `bpy` 和标准库 `json`。插件模块名可以不同，不必猜安装目录或导入 `CineController`。它也避免在 MCP 提交的代码中注册属性、生成驱动器或访问网络；相关功能由已经启用的插件完成。不同版本 MCP 的安全模式如有额外限制，以实际错误为准，不要要求 AI 绕过限制。

## 客户端规则

以下文字可以整段复制到 AI 客户端的项目指令：

> 通过 Blender MCP 进行镜头工作时，优先使用已经启用的 Cine Controller。先调用 `bpy.ops.cine.automation(request_json='{"action":"describe"}')` 和 `list`，读取当前接口规则与镜头清单，再用 `get` 读取目标镜头。通过现有 MCP 的 `execute_blender_code` 发送 Python，不要另起服务。
>
> 每次修改明确传 `camera`，可以是摄像机名或其曲线控制器名。禁止绕过插件直接写受控相机的基础位置、旋转、增量变换和内部驱动器。使用 describe 返回的操作和字段，不猜参数名；角度字段以 `_deg` 结尾，单位是度，距离使用 Blender 场景单位。
>
> 插件控制器负责整体空间变换，距离、环绕、偏移、摇摄、俯仰和翻滚是相对控制器及空间原点的参数。主面板不使用瞄准功能。轨迹进度作用于控制器中心，相机保留自己的距离和偏移；要让相机本身在路径上，须由用户意图决定是否清零这些参数。
>
> 用 `set` 设置镜头参数，`move_control` 设置整体变换，`import_pose` 匹配参考相机。轨迹和希区柯克使用专用操作，启停为幂等请求。希区柯克启用后，`distance` 仍可使用：减小推进、增大后退，自动补偿焦距；实体主体按投影包围盒高度保持。`set` 不插帧；制作动画时先传 `frame` 设置帧，再设置参数，最后 `keyframe`。已有关键帧在切帧时会重新求值，因此顺序必须是先切帧、再设值、再插帧。
>
> 以返回 JSON 中的 `ok` 判断成功，不以操作返回的 FINISHED 或 MCP 的“代码执行成功”判断业务成功。失败时读取 `error.message`，不要通过直接改内部数据绕过保护。成功后读取最终参数和世界位姿，并用 MCP 的观察或截图工具核对画面。位姿匹配不等于焦距、景深和构图一致。
>
> 用户没有要求时，不自动烘焙、切换渲染相机、保存或覆盖工程。该规则只约束镜头场景操作，不要求修改 MCP 服务端或用户全局配置。

## 请求与返回

请求是 JSON 对象，包含 `action`；除 `describe`、`list`、`create` 外，必须传 `camera`。运行时 `describe` 的返回是操作和字段的权威定义。

```python
import bpy
import json

request = {
    "action": "set",
    "camera": "Cine_Camera",
    "values": {"distance": 6, "pan_deg": 15, "tilt_deg": -10}
}
bpy.ops.cine.automation(request_json=json.dumps(request, ensure_ascii=False))
```

成功返回 `ok: true`、接口版本、操作名及 `data`。失败返回 `ok: false` 和 `error`。`get` 返回参数、控制器、轨迹与希区柯克状态、当前帧、单位换算比例，以及最终世界位置、四元数和矩阵。对象指针使用对象名，清空目标使用 JSON `null`，不要传字符串 `"None"`。

## 常见调用

以下每个对象都是一次 `request_json` 请求内容。实际镜头名请使用 `create`、`list` 的返回值，不假定 Blender 自动命名没有后缀。

```json
{"action":"create","name":"产品主镜头"}
```

```json
{"action":"get","camera":"产品主镜头"}
```

```json
{"action":"move_control","camera":"产品主镜头","location":[0,0,2],"rotation_deg":[0,0,30]}
```

```json
{"action":"set","camera":"产品主镜头","frame":1,"values":{"distance":8,"lens_mm":50,"pan_deg":0}}
```

```json
{"action":"keyframe","camera":"产品主镜头"}
```

```json
{"action":"set","camera":"产品主镜头","frame":60,"values":{"distance":4,"pan_deg":20}}
```

```json
{"action":"keyframe","camera":"产品主镜头"}
```

```json
{"action":"import_pose","camera":"产品主镜头","source":"自由相机"}
```

```json
{"action":"bind_path","camera":"产品主镜头","target":"镜头轨迹"}
```

```json
{"action":"set","camera":"产品主镜头","values":{"path_progress":0.5,"path_follow":true}}
```

```json
{"action":"pause_path","camera":"产品主镜头"}
```

```json
{"action":"resume_path","camera":"产品主镜头"}
```

```json
{"action":"enable_dolly","camera":"产品主镜头","target":"产品"}
```

```json
{"action":"set","camera":"产品主镜头","values":{"dolly_travel":1}}
```

```json
{"action":"disable_dolly","camera":"产品主镜头"}
```

`bake` 使用场景帧范围并解除相机控制器，属于显式输出操作；`render_camera` 显式切换场景渲染镜头。镜头副本出现共享计算数据时使用 `make_independent`，共享相机光学数据需在 Blender 中先独立化。

## 验证范围

`tests/automation_test.py` 使用与上游相同的 `exec(code, {"bpy": bpy})` 和标准输出收集方式，在真实 Blender 中验证发现、创建、读写、明确目标、角度单位、插帧、完整反推、轨迹、希区柯克、烘焙和错误回滚。此测试不等于已连接用户当前运行的 MCP 服务；首次接入还需在 AI 客户端实际执行发现脚本，再核对 `list` 返回的镜头清单。

上游依据：[执行工具](https://github.com/ahujasid/mcp-for-blender/blob/main/src/blender_mcp/server.py)、[Blender 端代码执行与输出收集](https://github.com/ahujasid/mcp-for-blender/blob/main/addon.py)。


## 高级震动接口

`enable_shake`／`disable_shake` 为幂等启停；`get` 的 `shake.events` 返回稳定 `event_id`。`shake_event` 的 `operation` 为 `add`、`update`、`duplicate`、`remove`，操作已有事件时必须传 `event_id`。`values` 可包含名称 `label`、开关 `enabled`、模式 `kind`（`IMPACT`／`CONTINUOUS`）、开始帧 `start`、持续帧数 `duration`、强度 `strength`、频率 `frequency`、衰减 `decay`、种子 `seed`、位移向量 `position` 与旋转向量 `rotation_deg`。位移顺序是右／上／前，旋转顺序是俯仰／摇摄／翻滚，旋转单位为度。

```json
{"action":"shake_event","camera":"产品主镜头","operation":"add","values":{"label":"第一次落地","start":30,"duration":12,"strength":1,"frequency":8}}
```

```json
{"action":"shake_event","camera":"产品主镜头","operation":"add","values":{"label":"再次落地","start":48,"duration":8,"strength":0.5,"frequency":10}}
```

```json
{"action":"enable_shake","camera":"产品主镜头"}
```

添加事件本身不自动启用震动。通过 `set` 的 `shake_strength` 设置整组总强度；该字段可在希区柯克运行期间使用。震动与希区柯克的面板入口都在默认折叠的高级效果中，自动化无需展开界面。
