# Phase 5 -> Phase 6 增强执行与验收闭环计划

## 目标

把“执行增强”和“验收增强”从两条需要用户或大模型手工拼接的命令，收敛到 `photo3d-handoff --confirm` 的确认式闭环里。普通用户在 `PHOTO3D_RUN.json` 停到 `ready_for_enhancement` 后，只需要确认 handoff；系统必须在同一 active run、同一 render dir 内完成增强、`enhance-check`、再回读一次 `photo3d-run`，让结果直接显示为 accepted / preview / blocked 和下一步。

## 范围

- `photo3d-run` 保持非执行增强入口：它只报告下一步，不运行 `enhance`，不运行 `enhance-check`。
- `photo3d-handoff --confirm` 在当前 `next_action.kind == run_enhancement` 且增强 subprocess 成功后，自动运行同一 active run 的 `enhance-check`。
- `enhance-check` 的 argv 必须由 `ARTIFACT_INDEX.json`、`active_run_id`、subsystem 和白名单 provider preset 重构；不能信任 JSON 里的任意 argv，不能扫描最新目录。
- `enhance-check` 返回非零但写出了有效 blocked `ENHANCEMENT_REPORT.json` 时，handoff 仍应回读 `photo3d-run`，把 blocked 交付状态作为可理解的下一步暴露出来。
- 若增强 subprocess 失败，不运行 follow-up；若 follow-up 阶段发现 `active_run_id` 漂移、报告缺失或回读失败，写入 `PHOTO3D_HANDOFF.json` 的 `execution_failed` 和 `followup_action.stderr`，不要无报告退出。

## 数据契约

- `PHOTO3D_HANDOFF.json.executed_action`：增强命令本身的安全 argv、stdout/stderr、returncode。
- `PHOTO3D_HANDOFF.json.followup_action`：自动 `run_enhance_check` 的安全 argv、stdout/stderr、returncode；增强失败时为 `null`。
- `PHOTO3D_HANDOFF.json.post_handoff_photo3d_run`：follow-up 后无确认重跑一次 `photo3d-run` 的摘要，包含 `status`、`enhancement_summary`、`next_action` 和 artifacts。
- `status == executed_with_followup`：增强执行成功，且同 run 的验收复查和回读已完成；其中 `post_handoff_photo3d_run.status` 可以是 `enhancement_accepted`、`enhancement_preview` 或 `enhancement_blocked`。
- `status == execution_failed`：增强命令失败，或增强后 follow-up/回读阶段失败；普通用户应看 `executed_action` / `followup_action`。

## 测试

- 红绿覆盖增强成功后自动执行 `enhance-check` 并回读 `photo3d-run`。
- 覆盖增强失败时跳过 `enhance-check`。
- 覆盖 `enhance-check` blocked 返回码为 1 但写出有效报告时，handoff 仍返回 0 并暴露 `enhancement_blocked` 下一步。
- 覆盖增强成功后 `active_run_id` 漂移时，handoff 写出 `execution_failed` 报告，不无报告退出。
- 扩展帮助文档和 metadata 契约，保证普通用户/大模型知道读取 `followup_action` 与 `post_handoff_photo3d_run`，而不是继续手拼命令或扫描目录。

## 完成定义

- `photo3d-handoff --confirm` 能把 provider 选择后的增强执行自然推进到验收复查，并在同一 run 报告中给出 accepted / preview / blocked。
- 不增加新 provider，不把 `gpt-image-2-pro` 或任意未来模型名加入白名单。
- 文档、metadata、安装版镜像同步，范围回归和空白检查通过。
