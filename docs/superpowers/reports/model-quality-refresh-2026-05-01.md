# Model Quality Refresh — 2026-05-01

## 结论

本轮刷新使用当前 `main` 合并后的产品命令重新确认模型质量状态。4/29 报告中的
`end_effector` D/C 级 backlog 与 `lifting_platform D=8` 已被后续工作覆盖：

- `end_effector`：`A=32`，无 D/E、无缺失 STEP、无 review-required 项。
- `lifting_platform`：`A=3, B=5`，无 D/E、无缺失 STEP、无 review-required 项。

因此下一步不再是清理历史 TODO 或 D 级占位，而是决定 `lifting_platform`
剩余 5 个 B 级半参数模板是否需要升级为 A 级真实 STEP。

## 证据

命令：

```powershell
.venv/Scripts/python.exe cad_pipeline.py model-audit --subsystem end_effector --json
.venv/Scripts/python.exe cad_pipeline.py model-audit --subsystem lifting_platform --json
```

结果：

| 子系统 | status | total | quality | worst | review_required | missing_step |
|---|---|---:|---|---|---:|---:|
| `end_effector` | pass | 32 | `A=32` | A | 0 | 0 |
| `lifting_platform` | pass | 8 | `A=3, B=5` | B | 0 | 0 |

本轮没有运行 `codegen --force`、`build` 或 `render`，也没有导出新的 STEP。
审计命令只读取当前 `.cad-spec-gen/geometry_report.json` 产品快照并输出摘要。

## 被覆盖的历史结论

| 文档 | 原结论 | 当前判定 |
|---|---|---|
| `model-quality-audit-2026-04-29.md` | `lifting_platform D=8` 是下一轮主目标 | 已覆盖；当前为 `A=3, B=5` |
| `model-quality-round1-2026-04-29.md` | `end_effector` 有 23 个 D 级 fallback | 已覆盖；当前为 `A=32` |
| `model-quality-round2-2026-04-29.md` | `end_effector` 仍有 10 个 D 级 fallback | 已覆盖；当前为 `A=32` |

上述文件保留为历史执行记录；后续规划以本刷新报告为准。

## `lifting_platform` 剩余 B 级项

| 优先级 | 料号 | 名称 | 当前来源 | 当前尺寸 | 建议动作 | 验收口径 |
|---|---|---|---|---|---|---|
| P1 | `SLP-C03` | KFL001 | `parametric_template:pillow_block_bearing_kfl001` | `60×36×16` | 替换为 KFL001 真实 STEP 或标准带座轴承模型 | `model-audit` 显示该项 `geometry_quality=A`、`validated=true` |
| P1 | `SLP-C06` | L070 联轴器 | `parametric_template:clamping_coupling_l070` | `25×25×30` | 替换为 L070 夹紧联轴器真实 STEP | `step_path` 为 project/shared STEP，hash 非空 |
| P2 | `SLP-C08` | CL57T 闭环驱动器 | `parametric_template:cl57t_stepper_driver` | `118×75×34` | 若渲染需要控制器外观，补厂商 STEP；否则接受 B 级盒体模板 | 若升级，A 级；若不升级，在后续报告中标记为 B-accepted |
| P3 | `SLP-F11` | PU 缓冲垫 20×20×3 | `parametric_template:pu_buffer_pad` | `20×20×3` | 当前包络漂移已修正；仅在 close-up 渲染需要时补真实垫片 STEP | 保持 `20×20×3`，不得回退到旧 `80×80×5` |
| P3 | `SLP-F13` | 导向轴保护帽 φ10 | `parametric_template:guide_shaft_protective_cap` | `10×10×8` | 小件，可延后；有 vendor STEP 时升级 | 不产生 D/E，不触发 review-required |

## 推荐下一轮

建议下一轮开 `codex/lifting-platform-a-grade-models`：

1. 先处理 `SLP-C03` 与 `SLP-C06`，它们是最显眼的机械传动/支撑件。
2. 再决定 `SLP-C08` 是否需要 A 级真实 STEP；如果仅作为电控盒背景件，可明确接受 B 级。
3. `SLP-F11` 与 `SLP-F13` 保持低优先级，除非目标输出是局部 close-up 渲染。
4. 每轮升级后运行：

```powershell
.venv/Scripts/python.exe cad_pipeline.py model-audit --subsystem lifting_platform --json
.venv/Scripts/python.exe cad_pipeline.py build --subsystem lifting_platform
```

验收目标：`lifting_platform` 无 D/E、无 missing STEP、无新增 GATE-3.5 warning；
若推进 A 级升级，则 `A` 数量增加且 B 级 accepted 项有明确理由。
