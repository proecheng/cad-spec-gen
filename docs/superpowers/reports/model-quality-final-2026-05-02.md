# Model Quality Final - 2026-05-02

## 结论

截至 `main` 基线 `78409fc`，当前仓库只有 2 个具备完整模型质量闭环的机械子系统：

- `end_effector`：`A=32`，无 missing STEP，无 review_required。
- `lifting_platform`：`A=11`，无 missing STEP，无 review_required。

这两个子系统都已达到本轮模型质量目标。早期报告中的 `lifting_platform D=8`、`end_effector` P3 小件 backlog 和 SW Toolbox 决策风险，已经被后续模型库映射、shared-cache STEP synthesizer、用户/示例 STEP 导入和生成器元数据闭环消化。

## 新鲜验证

本报告在隔离 worktree `codex/model-quality-final-docs` 中重新生成被 `.gitignore` 忽略的 geometry report 后审计：

```powershell
D:\Work\cad-spec-gen\.venv\Scripts\python.exe -c "from codegen.gen_std_parts import generate_std_part_files; generate_std_part_files('cad/lifting_platform/CAD_SPEC.md', 'cad/lifting_platform', mode='force'); generate_std_part_files('cad/end_effector/CAD_SPEC.md', 'cad/end_effector', mode='force')"
D:\Work\cad-spec-gen\.venv\Scripts\python.exe cad_pipeline.py model-audit --subsystem lifting_platform --json
D:\Work\cad-spec-gen\.venv\Scripts\python.exe cad_pipeline.py model-audit --subsystem end_effector --json
```

审计输出摘要：

| 子系统 | Total | Quality | Worst | Review required | Missing STEP | Status |
|---|---:|---|---|---:|---:|---|
| `end_effector` | 32 | `A=32` | `A` | 0 | 0 | pass |
| `lifting_platform` | 11 | `A=11` | `A` | 0 | 0 | pass |

生成器在本地会刷新 tracked `std_*.py` 文件头部或导入片段；这些生成痕迹不是本报告的交付内容，审计后已恢复，保留的证据来自 ignored `cad/<subsystem>/.cad-spec-gen/geometry_report.json`。

## 与旧报告的关系

旧报告仍保留为执行历史，但不再代表当前待办状态：

- `model-quality-audit-2026-04-29.md` 记录的是 `v2.23.3` 后的早期盘点，当时 `lifting_platform` 仍为 `D=8`。
- `model-quality-round1-2026-04-29.md` 和 `model-quality-round2-2026-04-29.md` 记录的是 `end_effector` 从 fallback/template 逐轮升级的过程。
- 当前事实以 `cad_pipeline.py model-audit` 读取的最新 geometry report 为准：两个可审计机械子系统均已全 A。

## 非当前模型质量债

仓库中其余 17 个 `cad/*/CAD_SPEC.md` 多为预算、软件、系统需求、集成说明或高层设计 spec 壳，当前没有可进入 resolver 的外购/标准件几何行，也没有完整 `build_all.py` 机械生成闭环。

这些目录不应被计入 D/E 模型质量债。若后续要继续扩展模型质量工作，应先确认它们是否需要被重新拆分为机械 CAD 子系统，并补齐有效 BOM、§6.4 包络和 codegen/build 产物，再进入模型库升级流程。

## 后续建议

1. 模型替换层面先停止追加零件升级 PR，避免围绕过期 backlog 重复施工。
2. 若要继续提高交付观感，下一步应转向全管线产物：重新 build/render/annotate 两个机械子系统，并检查输出图、GLB 和装配报告。
3. 若要扩大覆盖范围，先做新的机械子系统化需求澄清，而不是直接给 17 个非机械 spec 壳补占位模型。
