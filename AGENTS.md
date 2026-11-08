# 项目协作规则

- 使用中文沟通，说明与注释默认中文。
- 改代码前说明思路，优先最小改动，不增加未经同意的依赖。
- 修改后运行相关测试，明确实际验证范围。

## 使用 Blender MCP 操作镜头

本节仅针对 Blender 场景操作；源码开发不需要启动或连接 Blender MCP。

使用 `ahujasid/mcp-for-blender` 的 `execute_blender_code` 时，先执行：

```python
import bpy
bpy.ops.cine.automation(request_json='{"action":"describe"}')
bpy.ops.cine.automation(request_json='{"action":"list"}')
```

根据运行时说明，通过自动化 JSON 接口调用 Cine Controller。每次明确传镜头或控制器名称，角度统一为度，距离为场景单位。不要直接修改受控相机的基础变换、增量变换或内部驱动器。先切帧、再设值、再插帧，并以 JSON 中的 `ok` 判断业务是否成功。操作后读取最终位姿并观察画面。

完整规则与示例见 [MCP接入说明](docs/MCP接入说明.md)。插件未安装或 MCP 未连接时，说明缺失的环节；不要用其他云端 Blender 场景冒充用户本地工程，也不要改写用户全局配置。
