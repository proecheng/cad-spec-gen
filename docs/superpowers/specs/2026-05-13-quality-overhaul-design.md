# Quality Overhaul — Design Spec

**Date:** 2026-05-13
**Status:** v1 / approved by user (user delegated all technical decisions)
**Entry point doc:** `docs/superpowers/QUALITY_OVERHAUL_STATUS.md`
**Plan doc:** `docs/superpowers/plans/2026-05-13-quality-overhaul-plan.md`

---

## 1 · Goal

让外行用户在 `D:\Work\cad-tests\GISBOT\` 和 `D:\Work\cad-tests\jiehuo\` 里看到**满足 5 条验收标准**的交付包：

1. 法兰像法兰（4 条十字悬臂可见）
2. 升降平台元件齐全、装配不坍塌
3. 多视角几何一致
4. SW 模型与 SW 材质有据可查地被用上了
5. 照片级（engineering 后端达标作为兜底，gemini 代理恢复即可升级）

## 2 · Context — 这次发现了什么

### 2.1 两个直接 bug

**Bug A — `end_effector` 法兰只有圆盘没有 4 条十字悬臂**

- 件号：`GIS-EE-001-01 法兰本体（含十字悬臂）`，BOM 标"自制"、7075-T6 铝合金
- 模块：`cad/end_effector/ee_001_01.py::make_ee_001_01()`
- 现状：只生成 Φ90×30 mm 圆盘 + 6×M3 PCD70 螺栓孔 + 沉孔；**完全没建 ARM_SEC_W=12 / ARM_SEC_THICK=8 / ARM_L_2=40 的 4 条径向臂**
- 铁证：GLB 里 `EE-001-01` mesh bbox `min=[-45,-45,0] max=[45,45,32]` → 跨度 90×90×32 mm；设计文档 §6.4 给的 envelope 是 160×160×20 mm。**多出来的每边 35mm 就是失踪的臂**
- 文件自标 `"Auto-generated scaffold by codegen/gen_parts.py"` + `"Refine with actual geometry citing design-doc lines"`

**Bug B — `lifting_platform` 整个装配坍塌成一根丝杠**

- GLB 整体 bbox 跨度 170×80×360 mm，z 跨度 360mm 全靠丝杠 `SLP-P01`（参数化 350mm）撑着
- **36 个 mesh node 的 bbox 全部以世界原点 (0,0,0) 为中心** → 装配 transform 全部丢失或没生成 → 所有零件挤在原点重叠
- **8 个自制结构件**（`100.py / 200.py / 201.py / 300.py / 400.py / 403.py / 404.py / 500.py` 还有 `p100/p300/p400/p403/p404.py`）一字排开都是 106 行、全部 `.box()` 占位、全部带 scaffold 自标记
- 这 8 个件按设计文档应该是：上板、下板、中间动板、电机座、丝杠端支撑、限位支撑等结构件，每个件都有特定的孔位、加强筋、安装边 —— 现在全部沦为生成 60×40×10 或 50×40×25 的方块

### 2.2 同一种病

两 bug 不是孤立的，是同一个架构漏洞的两个症状：

> **cad-spec-gen 的所有评分/门禁/审计都建在「采购件 + 渲染像素 + AI 增强忠实度」这条链上；自制件这条链从来没有任何评分。**

详细映射（每条都有证据，session 5/6 调查纪录）：

| 现有评分/门禁 | 它实际在评什么 | 对 Bug A/B 的判断 |
| --- | --- | --- |
| `geometry_report.json` A–E 质量分级 | 只评采购件（resolver 决策）| 自制件不在 scope，根本不评 |
| GATE-3.5 `assembly_validator.py` | F1 重叠 / F2 断连 / F3 紧凑 / F4 尺寸比 / F5 排除 | 形状对错看不出来；F1 重叠对"全在原点"应该报警但本次 ASSEMBLY_REPORT 未生成 |
| `render_qa.py` | 像素层 occupancy / cropped / blank | ✅ pass，不知道件应该长什么样 |
| `render-visual-check` | `visible_instance_ids` 集合相等 | 36 个 id 都"可见"哪怕全堆一块 → 集合相等 → ✅ |
| `enhance-check.quality_summary` | 画布 / 亮度 / 对比度 / 饱和度 | 像素层 → ✅ |
| `jury` (vision LLM) | 5 boolean 含 `geometry_preserved` | `geometry_preserved` = AI 没破坏源 PNG ≠ 源 PNG 符合设计文档 |
| `enhance-review.semantic_material_review` | 同样 5 boolean | 无 "matches_spec" 维度 |

**11 个 `ee_*.py` + 13 个 `lifting_platform` 自制件 .py 自标 `Auto-generated scaffold`，仓库里没有任何工具 grep 这行。**

### 2.3 LLM 操作员（之前的 session）的失误

我手里同时握着 GLB bbox（90×90） 和设计文档 envelope（160×160） 两个数，**没去 diff**。把"管线门禁全 ✅"当成了"输出对得起 spec"。`superpowers:verification-before-completion` 这条该跑的没跑。

## 3 · Decisions（用户授权我替他做的技术决策）

| # | 决策 | 一句话理由 |
| --- | --- | --- |
| D1 | **自制件用手写 CadQuery 引用设计文档行号修，不靠 `codegen --force`** | 用户原话「目前法兰的模型经过那么多次的重修改进，仍然不像真正的法兰」—— 旧 codegen 启发式不是答案。手写 + 行号引用是项目自己的纪律（README 已写明） |
| D2 | **审计做成 `cad_pipeline.py custom-parts-audit` 一级子命令，强制接在 `build` 之后，不通过阻断后续阶段** | 用户原话「应该是你做出来不好或者评分低的一个必要环节」—— 必须是流程内置门禁，不是事后跑 |
| D3 | **AI 后端默认 `engineering`，gemini 代理恢复后由用户一行命令升级** | 不让 503 拖住交付。engineering 用了 SW 纹理 + PBR，效果已达"工程展示级"，外行也能看 |
| D4 | **新增 `model_provenance` 字段到 `geometry_report.json` 标注 SW Toolbox 溯源** | 用户想要"SW 模型用上了"的证据；现状是 SW Toolbox 被 sw-warmup 间接用过、resolver 直接命中缓存，这个链条对外不可见 —— 加字段透明化 |
| D5 | **v1 不做 LLM 设计对话 CLI；审计触发"无法自动决策"时写一份 `CUSTOM_PART_TODO.md` 列纯中文问题，用户/下一会话答完再继续** | 用户是外行不要交互式 Q&A；plain-text TODO 文件最低门槛 |
| D6 | **修自制件时优先复用 `draw_*.py` 已有的 2D 投影几何（如果可用）作为参考** | lifting_platform 已经有 `draw_top_plate.py` `draw_motor_bracket.py` 等做 DXF 工程图的脚本，里面有正确的尺寸与孔位 |
| D7 | **lifting_platform 装配坍塌的修复优先于结构件单件几何** | 即使每个件画得多漂亮，如果都堆在原点也没用。先把 transform 修对，再补单件几何 |
| D8 | **审计写出来的报告必须人类可读**（plain Chinese, 不要全是 JSON）+ 同时写一份机器可读的 JSON（供下游契约用） | 外行能看；下一个 CI gate / LLM 能读 |

## 4 · Scope

### In Scope (v1)

- 修 `ee_001_01.py` 加 4 条十字悬臂
- 修 lifting_platform 装配坍塌（找到 assembly placement 丢失的根因再修；优先看 `assembly.py` `assembly.generated.py` `assembly_layout.py` `assembly_legacy.py` 4 选 1 的逻辑）
- 修 lifting_platform 8 个结构件的 `.py`（顶板 / 底板 / 动板 / 电机座系列 / 等）从 box 占位到带正确特征的几何
- 新工具 `tools/custom_parts_audit.py`，做 5 件事：
  - (a) BOM ↔ build_all PARTS ↔ STEP files ↔ GLB instance 五段链对账（少一节就报警）
  - (b) §6.4 envelope vs GLB per-part bbox 比对（误差 > 15% 或某一轴 < 50% 报警）
  - (c) 扫所有 `cad/<sub>/*.py` 的 `Auto-generated scaffold` / `Approximate geometry` / `scaffold default` marker（有就报告"未完成"）
  - (d) 装配坍塌检测：所有 mesh bbox 中心两两距离 < 阈值（如 10mm） → 报警"placement 可能丢失"
  - (e) 输出双格式报告：`CUSTOM_PARTS_AUDIT.md`（中文人类版）+ `CUSTOM_PARTS_AUDIT.json`（机器版）
- 接进 cad_pipeline：`build` 完成后自动跑审计；非零 exit 阻断后续；可显式 `cad_pipeline.py custom-parts-audit --subsystem <name>` 单独跑
- `geometry_report.json` 加 `model_provenance` 字段（每件标注"是否来自 sw-warmup 缓存 / 来自用户 STEP / 来自参数化模板"）
- 端到端重跑两个子系统 + 归档到 `D:\Work\cad-tests\<sub>\` + 更新全景图 §10

### Out of Scope (v2 or later)

- LLM 设计对话 CLI（`project-guide --custom-part-clarify ...`）
- jury 加 `matches_spec` 维度（需要给 vision LLM 喂设计文档片段）
- "评分低 → 自动 re-codegen → 再审计" 全自动闭环（v1 是"评分低 → 写 TODO + 阻断 + 等人/LLM 接手"半闭环）
- `parts_library.yaml` 优先级改造（让 sw_toolbox 在某些类别下优于 step_pool）
- 修 gemini 代理 / 配 fal / 装 ComfyUI（用户运维侧，不是管线侧）
- 全仓 ruff/mypy 历史债剩余清理（已在别处跟踪）
- 任何 LLM 操作员（我）的自动化纪律工具（如 pre-commit hook 检查 verify-before-completion 是否跑过）

## 5 · Architecture

### 5.1 新工具 `tools/custom_parts_audit.py`

签名：

```python
def audit_subsystem(subsystem: str, *, project_root: str | None = None) -> AuditResult:
    """五段链 + envelope diff + scaffold scan + collapse detect。
    写 cad/<subsystem>/.cad-spec-gen/CUSTOM_PARTS_AUDIT.{md,json}。
    返回 exit_code: 0 = PASS, 2 = WARN（有 marker 但几何 OK）, 1 = FAIL（阻断后续阶段）。
    """
```

报告骨架（md）：

```markdown
# 自制件审计报告 — <subsystem>
日期：YYYY-MM-DD · run_id: <…>
总体判定：PASS / WARN / FAIL

## A · 五段链对账
BOM 声明 N 个自制件 → build_all.py 登记 M 个 → 实际写出 K 个 STEP → GLB 实例 L 个 → 渲染 R 个视角覆盖 S 个 instance
| 件号 | BOM | build_all | STEP | GLB | 状态 |

## B · §6.4 envelope vs GLB bbox 比对
| 件号 | 设计文档 envelope | GLB bbox | 误差% | 判定 |

## C · scaffold 标记扫描
| 文件 | scaffold marker 命中行 | 自标"需精修"次数 |

## D · 装配坍塌检测
件 bbox 中心两两最小距离：X mm（阈值 10mm）；触发：是 / 否

## E · 该处理什么（人话）
- 修 `<file>` 第 X 行：…
- 用户需要回答：…（如有，会同时写入 CUSTOM_PART_TODO.md）
```

### 5.2 接入点

```
cad_pipeline.py build --subsystem <s>
  ↓ build_all.py 跑完
  ↓ consolidate_glb 跑完
  ↓ render_dxf.py 跑完
  ↓ GATE-3.5 assembly_validator 跑完
  ↓ [新] custom_parts_audit.audit_subsystem(<s>)
       PASS → 继续
       WARN → 打印警告 + 继续（仅 marker 没几何错）
       FAIL → exit ≠ 0 阻断 render / enhance / deliver
```

`cad_pipeline.py custom-parts-audit --subsystem <s>` 独立子命令，方便人手动跑。

### 5.3 model_provenance 字段（geometry_report.json）

每个 `decisions` 行追加：

```json
"model_provenance": {
  "source_kind": "sw_toolbox_warmup" | "user_provided_step" | "vendor_synthesizer" | "parametric_template" | "jinja_fallback",
  "sw_toolbox_source": "GB/T 17463-2007 Tr16x4 / din2093" | null,
  "sw_warmup_run_log": "sw_warmup_run3.log" | null,
  "imported_at": "2026-05-06T..." | null
}
```

来源信息从 `~/.cad-spec-gen/sw_toolbox_index.json` + `step_cache/{sw_toolbox,…}` 目录结构反查得到。

## 6 · Acceptance Criteria

对应 STATUS doc 的 5 条用户验收标准 + 内部 CI-级别条件：

| # | 验收 | 怎么验 |
| --- | --- | --- |
| 1 | 法兰像法兰 | `D:\Work\cad-tests\GISBOT\04_render\V4_exploded*.png` 视觉检查 4 臂；GLB bbox 跨度 ≈160×160 |
| 2 | 升降平台元件齐全 | `D:\Work\cad-tests\jiehuo\04_render\V5_exploded*.png` 视觉 ≥6 件分离可辨；装配坍塌检测 PASS |
| 3 | 多视角一致 | `render_manifest.status=pass`、视角间 visible_instance_ids 集合稳定 |
| 4 | SW 模型 + 材质 | `geometry_report.json` `model_provenance.source_kind` 至少有一个 `sw_toolbox_warmup`；渲染日志含 `SW_TEXTURES_DIR` 注入 |
| 5 | 照片级 | engineering 后端 `enhance-check delivery_status=accepted` + `quality_summary=accepted`；gemini 可用时再跑一次 |
| 6 | 审计能反向抓 bug | `git stash` 一个 CP-1 修改 → 审计应 FAIL；恢复 → 应 PASS |
| 7 | 跨会话顺滑 | 把这份 spec + plan + status 给一个新 session，它能从 CURRENT TASK 指针接着干 |

## 7 · Risks & Mitigations

| 风险 | 缓解 |
| --- | --- |
| 装配坍塌的根因可能是 `assembly.py` 被某次 codegen 静默覆盖；如果 git log 没记录，不好恢复 | 先看 git history；如果丢了，参考 `assembly_legacy.py` `assembly_layout.py` 重写。最坏情况：根据 CAD_SPEC §6.3 zone_offsets 重写 placement table |
| 8 个自制件手工补完工作量大，单 session 可能干不完 | 任务粒度按"一个件一个 task"切；CP-1 内 4 件做完就可以提前进 CP-2 验证审计能 work，剩余 4 件并行 |
| 新审计的 envelope diff 阈值（15%）可能误报或漏报 | 阈值在 spec 里写明、在 audit 工具开头作为常量；先跑两个子系统校准；不通过的件人工 review 后再决定阈值微调 |
| Blender 重渲染慢（end_effector 7 视角 ~7min；lifting_platform 6 视角 ~4min）| 单 session 内只跑必要的；多 session 时把 render 任务放在 session 末，下次 session 直接接 enhance |
| `codegen --force` 在 v1 之外被误触发会冲掉 CP-1 改动 | STATUS doc §六 明确禁用 `--force`；plan 文档每个修文件的任务前都重复这条警告 |

## 8 · 不变量（任何 session 改代码都不许碰）

1. **不许动 `tools/render_qa.py` 的 `MIN_OBJECT_OCCUPANCY`**（之前已改到 0.004，再改会破坏 fixture 测试）
2. **不许动 `cad/end_effector/render_config.json` 的 V5/V6 相机**（之前已经调好，再改会回归 cropped）
3. **不许把 `cad/output/` 加进 git tracked**（gitignored 已有）
4. **不许跑 `codegen --force --subsystem *`**
5. **不许跑 `cad_pipeline.py full`**（这个命令绕开 STATUS doc 的检查点，不可控）
6. **不许在没跑新审计的情况下声称"跑通了"**
