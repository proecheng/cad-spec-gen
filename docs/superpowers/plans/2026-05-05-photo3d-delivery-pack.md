# Phase 6 最终交付包执行计划

## 目标

把已经通过增强验收的 Photo3D 结果从“散落在 render/run 目录里的文件”收敛成一个可审计、可交给普通用户或其他大模型继续处理的交付目录。最终包必须只绑定当前 active run，不能通过扫描最新目录、相似文件名或手工复制图片来决定交付内容。

## 范围

- 新增 `photo3d-deliver` 命令和 `tools/photo3d_delivery_pack.py`。
- 输入只来自 `ARTIFACT_INDEX.json.active_run_id`、当前 run 目录、当前 render dir 的 `render_manifest.json` 和 `ENHANCEMENT_REPORT.json`。
- 默认只有 `accepted` 才复制最终增强图、源渲染图和可唯一识别的标注图；`preview` / `blocked` 只写证据报告，不标记 `final_deliverable`。
- 输出固定在 `cad/<subsystem>/.cad-spec-gen/runs/<run_id>/delivery/`，包含 `DELIVERY_PACKAGE.json`、`README.md`、`evidence/`、`source/`、`enhanced/` 和按需 `labeled/`。
- `--include-preview` 只用于显式预览包；仍不把结果标成最终交付。

## 数据契约

- `DELIVERY_PACKAGE.json.run_id` / `subsystem` 必须等于 active run。
- `source_reports` 记录 `ARTIFACT_INDEX.json`、`render_manifest.json`、`ENHANCEMENT_REPORT.json`、`PHOTO3D_RUN.json` 和存在的契约证据。
- `deliverables.source_images` / `enhanced_images` / `labeled_images` 记录每张复制图片的 view、原路径、包内路径和 sha256。
- `evidence_files` 记录复制到 `delivery/evidence/` 的所有报告文件及 sha256。
- `final_deliverable == true` 只允许出现在增强验收为 `accepted` 且所有图片路径、哈希、manifest 绑定都通过时。

## 测试

- 红绿覆盖 accepted run 生成交付包、复制源图/增强图/标注图和证据报告。
- 覆盖 `ENHANCEMENT_REPORT.json.run_id` 与 active run 不一致时阻断。
- 覆盖 blocked 报告只写 `DELIVERY_PACKAGE.json`，不复制最终增强图，返回非零。
- 覆盖 CLI `cmd_photo3d_deliver`。
- 扩展帮助文档、metadata 和打包镜像同步测试，保证安装版 skill 能看到 `photo3d-deliver`。

## 完成定义

- `photo3d-deliver --subsystem <name>` 能把 accepted 增强结果打成可读、可审计的最终包。
- 文档明确普通用户/大模型在 `enhancement_accepted` 后运行 `photo3d-deliver`，不要手工复制图片或扫描 render 目录。
- `scripts/dev_sync.py --check`、目标回归和空白检查通过。
