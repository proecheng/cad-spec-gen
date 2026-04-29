# Model Quality Audit — 2026-04-29

## 结论

本轮在 `v2.23.3` 发布后的 `main` 基线上执行跨子系统模型质量盘点。仓库共有 19 个 `cad/*/CAD_SPEC.md`，其中只有 2 个子系统当前具备可审计的外购/标准件几何行：

- `end_effector`：已达当前阶段目标，`A=9, C=23, D=0, E=0`。
- `lifting_platform`：下一轮优先目标，`D=8`，全部来自 `JINJA_PRIMITIVE` fallback。

其余 17 个 `CAD_SPEC.md` 可解析，但没有可进入模型 resolver 的外购/标准件几何行，且无 `build_all.py`。这些目录当前不是模型质量优化入口；除非重新从机械设计文档生成有效 BOM / §6.4 包络，否则不应把它们计入 D/E 模型质量债。

## 方法

本轮采用只读审计方式：

- 扫描 `cad/*/CAD_SPEC.md`。
- 使用 `parse_bom_tree()` 与 `parse_envelopes()` 解析 BOM 和 §6.4 包络。
- 仅对 `外购` / `标准件` 且非 `fastener` / `cable` 的行调用 `PartsResolver.resolve(..., mode="inspect")`。
- 未运行 `codegen --force`，未批量改写 `std_*.py`，未提交 `.cad-spec-gen/geometry_report.json`。
- 本机已刷新两个被 `.gitignore` 忽略的 inspect 快照：
  - `cad/end_effector/.cad-spec-gen/geometry_report.json`
  - `cad/lifting_platform/.cad-spec-gen/geometry_report.json`

注意：`lifting_platform` 的 `SLP-F06` 在 inspect 阶段触发一次 SolidWorks 配置列表探测并超时 15s；未导出 STEP，未修改模型库。

## 子系统总览

| 子系统 | CAD_SPEC | build_all.py | 外购/标准几何行 | 质量分布 | 判定 |
|---|---:|---:|---:|---|---|
| `end_effector` | yes | yes | 32 | `A=9, C=23` | 已达标，保留少量 SW 配置决策风险 |
| `lifting_platform` | yes | yes | 8 | `D=8` | 下一轮模型质量主目标 |
| `budget` | yes | no | 0 | n/a | 非当前模型质量目标 |
| `charging` | yes | no | 0 | n/a | 非当前模型质量目标 |
| `communication` | yes | no | 0 | n/a | 非当前模型质量目标 |
| `couplant` | yes | no | 0 | n/a | 非当前模型质量目标 |
| `detection` | yes | no | 0 | n/a | 非当前模型质量目标 |
| `electrical` | yes | no | 0 | n/a | 非当前模型质量目标 |
| `integration` | yes | no | 0 | n/a | 非当前模型质量目标 |
| `motion_ctrl` | yes | no | 0 | n/a | 非当前模型质量目标 |
| `navigation` | yes | no | 0 | n/a | 非当前模型质量目标 |
| `patent` | yes | no | 0 | n/a | 非当前模型质量目标 |
| `plan` | yes | no | 0 | n/a | 非当前模型质量目标 |
| `power` | yes | no | 0 | n/a | 非当前模型质量目标 |
| `robot_platform` | yes | no | 0 | n/a | 非当前模型质量目标 |
| `safety` | yes | no | 0 | n/a | 非当前模型质量目标 |
| `software` | yes | no | 0 | n/a | 非当前模型质量目标 |
| `sys_arch` | yes | no | 0 | n/a | 非当前模型质量目标 |
| `sys_req` | yes | no | 0 | n/a | 非当前模型质量目标 |

## `end_effector`

审计结果：

- BOM leaf parts：48
- resolver 几何行：32
- 跳过非几何行：2
- quality：`A=9, C=23`
- source：`REAL_STEP=9`, `JINJA_TEMPLATE=23`
- D/E：0

仍需关注的 inspect warning：

| 料号 | 名称 | 风险 |
|---|---|---|
| `GIS-EE-001-03` | O型圈 | SW Toolbox 候选需要用户决策 |
| `GIS-EE-001-12` | 定位销 | SW Toolbox 候选需要用户决策 |
| `GIS-EE-004-11` | 微型轴承 | SW Toolbox 候选需要用户决策 |

这些不是当前 D/E 质量债，但说明真实 SW/Toolbox 路由仍可能在全自动 codegen 中进入用户决策分支。后续可通过显式 `parts_library.yaml` 规则或用户 `model_choices` 固化。

## `lifting_platform`

审计结果：

- BOM leaf parts：32
- resolver 几何行：8
- 跳过非几何行：13
- quality：`D=8`
- source：`JINJA_PRIMITIVE=8`
- D/E：D=8，E=0

当前 D 级零件：

| 料号 | 名称 | 当前来源 | 当前尺寸 | 建议升级路径 |
|---|---|---|---|---|
| `SLP-C02` | LM10UU | `jinja_primitive:bearing` | `19×19×29` | 优先真实 STEP 或标准直线轴承参数模板 |
| `SLP-C03` | KFL001 | `jinja_primitive:bearing` | `12×12×4` | 优先真实 STEP；若无则做带座轴承半参数模板 |
| `SLP-C06` | L070 联轴器 | `jinja_primitive:connector` | `10×10×25` | 优先真实 STEP；次选夹紧联轴器半参数模板 |
| `SLP-C07` | NEMA23 闭环步进 ≥1.0Nm | `jinja_primitive:motor` | `22×22×50` | 优先 NEMA23 电机 STEP；次选方形机身+法兰+轴伸模板 |
| `SLP-C08` | CL57T 闭环驱动器 | `jinja_primitive:other` | `15×15×10` | 控制器盒体半参数模板，或不参与 3D 机械装配 |
| `SLP-F11` | PU 缓冲垫 20×20×3 | `jinja_primitive:seal` | `80×80×5` | 修正 §6.4 包络后做弹性缓冲垫模板 |
| `SLP-F12` | M8 电感接近开关 NPN-NO | `jinja_primitive:sensor` | `15×15×12` | M8 圆柱传感器半参数模板或 vendor STEP |
| `SLP-F13` | 导向轴保护帽 φ10 | `jinja_primitive:other` | `15×15×10` | 保护帽半参数模板 |

额外 warning：

| 料号 | 名称 | 风险 |
|---|---|---|
| `SLP-F06` | φ5×20 定位销 | SW Toolbox 候选需要用户决策；inspect 阶段配置列表探测超时 15s |

## 优先级建议

1. **P1：`lifting_platform` 真实 STEP / 半参数模板升级。** 先处理 `SLP-C07`、`SLP-C02`、`SLP-C03`、`SLP-C06`、`SLP-F12`，这些在机械视觉中最显眼；目标是把 `D=8` 降到 0。
2. **P1：修正 `SLP-F11` 包络漂移。** BOM 名称写明 `20×20×3`，resolver 当前报告 `80×80×5`，应先查 §6.4 / 材料解析来源，再决定模板。
3. **P2：固化 SW Toolbox 需要决策的标准件。** `SLP-F06`、`GIS-EE-001-03`、`GIS-EE-001-12`、`GIS-EE-004-11` 应通过显式模型选择或 registry rule 避免交互式漂移。
4. **P2：补一个可复用审计命令。** 目前审计脚本是临时执行；建议新增 `cad_pipeline.py model-audit` 或 `tools/model_quality_audit.py`，把 `inspect` 模式、Markdown 报告和 JSON 快照固定为产品能力。
5. **P3：17 个无几何行 CAD_SPEC 暂缓。** 这些目录多为预算、软件、系统需求或高层文档生成的 spec 壳；下一步不是补模型，而是先确认是否需要机械 CAD 子系统化。

## 下一轮推荐 PR

建议下一轮开 `codex/lifting-platform-model-quality`：

- 为 `lifting_platform` 新增 5-8 个半参数模板或 STEP 映射。
- 更新 `cad/lifting_platform/CAD_SPEC.md` §6.4 中对应来源、粒度和理由。
- 运行 `gen_std_parts.py` / `cad_pipeline.py build --subsystem lifting_platform`。
- 验证目标：`lifting_platform` 几何质量从 `D=8` 提升到 `C/B/A`，且装配构建无新增 GATE-3.5 warning。
