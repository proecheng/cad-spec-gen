# Phase 5 Provider 配置健康检查执行计划

## 目标

在 `PROJECT_GUIDE.json` 的 provider 选择向导中加入只读 `provider_health`，让普通用户和大模型能看到每个增强 provider 当前是“可用 / 需要配置 / 未知”，同时不运行增强、不扫描输出目录、不修改管线状态、不暴露密钥、URL、endpoint 或环境变量值。

## 范围

- 新增通用健康层 `tools/photo3d_provider_health.py`，由 provider preset 的公开元数据驱动。
- `project-guide` 只消费健康层的安全摘要，把 `provider_choice.provider_health`、`provider_choice.provider_health_summary` 和 `provider_wizard.options[].health` 写入报告。
- 检查仅限本地配置/依赖存在性：Gemini 配置文件存在性、fal 客户端依赖存在性、ComfyUI/Fal-Comfy 工作流模板和本地根目录存在性等。
- 不做网络探活，不执行增强，不读取/输出 secret 值，不把 URL/endpoint/base_url/api_key 这类字段带进公开报告。

## 测试

- 新增 provider 健康单元测试，覆盖默认无配置时的状态和已配置模拟环境时的状态。
- 扩展 `project-guide` 测试，验证 `provider_wizard` 嵌入健康状态，且健康对象不含 forbidden 字段。
- 扩展帮助文档和 metadata 契约测试，确保安装版 skill 也说明 `provider_health` 边界。
- 继续跑 `dev_sync.py --check`、Photo3D/project-guide 范围回归和空白检查。

## 完成定义

- `PROJECT_GUIDE.json` 在增强入口提供 provider 健康状态，普通用户无需读配置文件也能知道哪些选项可直接用。
- 所有健康输出保持只读、安全、可序列化，不泄漏 key、secret、URL、endpoint 或 arbitrary argv。
- 文档、metadata、安装版镜像同步，范围测试全绿。
