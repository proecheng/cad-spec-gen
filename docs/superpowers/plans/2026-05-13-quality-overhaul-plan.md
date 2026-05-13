# Quality Overhaul — Execution Plan

**Spec:** `docs/superpowers/specs/2026-05-13-quality-overhaul-design.md`
**Status doc:** `docs/superpowers/QUALITY_OVERHAUL_STATUS.md` ← always update after each task
**Date:** 2026-05-13

---

## 怎么用这份 plan

- 每个 task 有：**目标 / 做什么 / 验收 / 影响文件 / 时长估计**
- Task 序号是连续的，跨 CP 不重置
- 任务粒度 **2–10 分钟**（render 任务除外，那些是 Blender 限速）
- 完成一个 task → 在 task 标题前打 `✅`、在 STATUS doc §五 CURRENT TASK 更新指针；FAIL → 打 `❌` 加 1–2 行原因，再决定是回头修还是 skip
- 任何一个 task 卡住超过 30 分钟 → 停下来，把卡点记在 STATUS doc，等下一次会话/人接手
- 改任何 tracked file **必须**先 `git status` 确认当前没有别的脏文件混进来（除了已知的：`tools/render_qa.py` `cad/end_effector/render_config.json` `docs/系统全景图.html`）
- 任何 task 不许触发被列入 spec §8 "不变量" 的操作

---

# CP-1 · 自制件几何手工补完到"看上去对"

## Task 0 · 把每个自制件该长什么样摘出来（2-table）

**目标：** 写一份 `tmp/_custom_parts_spec.md`，对 9 个待修自制件（1 个 end_effector + 8 个 lifting_platform）逐件列：件号、文件名、CAD_SPEC 行号、关键尺寸/孔位/特征、引用的设计文档章节。后续所有 task 的工作基础。

**做什么：**
1. 读 `cad/end_effector/CAD_SPEC.md` 找 `GIS-EE-001-01` 的全部参数（FLANGE_*, ARM_*, ROT_RANGE 等）+ 设计文档 `examples/04-末端执行机构设计.md` 关于"法兰本体（含十字悬臂）"的描述
2. 读 `cad/lifting_platform/CAD_SPEC.md` 找 `SLP-100, 200, 201, 300, 400, 403, 404, 500` 的描述 + `D:/Work/cad-tests/19-液压钳升降平台设计.md`
3. 同时读 `cad/lifting_platform/draw_top_plate.py` `draw_motor_bracket.py` 等 — 它们是为 DXF 工程图准备的几何，里面有正确的孔位 + 尺寸，可以用来推断 3D
4. 写出 `tmp/_custom_parts_spec.md`：每件一节，含尺寸表 + 孔位列表 + 引用行号

**验收：** 9 件每件至少 1 段中文描述 + 关键尺寸表 + 设计文档引用；没有"未知"或"待定"

**影响文件：** 仅创建 `tmp/_custom_parts_spec.md`（gitignored）

**时长：** 15–25 min

---

## Task 1 · 修 `ee_001_01.py` 加 4 条十字悬臂

**目标：** `make_ee_001_01()` 返回的实体 bbox 跨度变成 `~160×160×~30 mm`（含臂），4 条径向臂沿 +X/+Y/-X/-Y 伸出。

**做什么：**
1. 读 Task 0 输出里关于该件的小节
2. 在 `cad/end_effector/ee_001_01.py::make_ee_001_01()` 的圆盘 + 螺栓孔逻辑之后，加 4 个臂的 union：
   - 单臂参数：`arm_l = 40 mm`（CAD_SPEC ARM_L_2）、`arm_w = 12 mm`（ARM_SEC_W）、`arm_t = 8 mm`（ARM_SEC_THICK）
   - 4 个方向：0°/90°/180°/270°；每条臂从圆盘外缘（r=45）向外伸 arm_l，z 方向与圆盘顶面齐平、厚度 arm_t（位于 disc 顶面下方 8mm 范围内，不超过圆盘总厚 30mm）
   - 用 `.box(arm_l, arm_w, arm_t).translate((45 + arm_l/2, 0, 30 - arm_t/2))` 然后旋转 union 进 body
   - 加 chamfer 0.5mm 或 fillet 1mm 收边（v2.8.2 changelog 提的"chamfer/fillet polish"）
3. 更新 `_orientation_spec()` 的 `min_ratio` 如果需要（现在是 1.0，加臂后仍是 z 主轴，min_ratio 仍合适）
4. 局部测试：`python cad/end_effector/ee_001_01.py` 应在 `cad/output/GIS-EE-001-01.step` 写出新 STEP

**验收：**
- `python -c "from cad.end_effector.ee_001_01 import make_ee_001_01; b=make_ee_001_01().val(); bb=b.BoundingBox(); print(bb.xmin,bb.xmax,bb.ymin,bb.ymax,bb.zmin,bb.zmax)"` 输出 x/y 跨度 ≥150 mm
- `cad/output/GIS-EE-001-01.step` 文件 size 比之前大（带臂的 step 比纯圆盘大）

**影响文件：** `cad/end_effector/ee_001_01.py`（tracked，会污染 git status — 这是预期改动）

**时长：** 15–25 min

---

## Task 2 · `end_effector` 重 build + 验法兰

**目标：** 重新跑 build → 生成新 GLB → 验证 `EE-001-01` 在 GLB 里 bbox ≈160×160 而不是 90×90。

**做什么：**
1. `python cad_pipeline.py build --subsystem end_effector 2>&1 | tail -15`
2. 用证据 4 的 GLB 探针脚本（见 spec/plan 仓库历史）确认 `EE-001-01` 跨度
3. 如果跨度对了 → 继续；如果还不对 → 回到 Task 1 修

**验收：** GLB 里 `EE-001-01` mesh bbox 跨度 x ≥ 150 mm, y ≥ 150 mm（即臂确实建出来了）

**影响文件：** `cad/output/*` （gitignored）

**时长：** 5–10 min（含 build 时间）

---

## Task 3 · 找出 `lifting_platform` 装配坍塌的根因

**目标：** 弄清为什么 36 个 mesh 都在世界原点附近（应该有 transform）。锁定到具体哪个文件 / 哪一段逻辑。

**做什么：**
1. `wc -l cad/lifting_platform/assembly*.py` 看 4 个 assembly 文件大小
2. `cat cad/lifting_platform/build_all.py` 看它 import 谁来做 assembly
3. 读 `assembly.py` `assembly.generated.py` `assembly_legacy.py` `assembly_layout.py` 4 个 —— 找哪个里有 `translate` `transformed` `rotate` 这种放置逻辑、哪个又是空的或 stub
4. `git log --oneline -20 cad/lifting_platform/assembly*.py` 看哪份是最近被改的（可能是被静默覆盖了）
5. 用 `git show <commit>:cad/lifting_platform/assembly.py` 跟当前对比，确认是否回归
6. 把结论写进 STATUS doc §五，并决定 Task 4 是 (a) 从 git history 恢复 (b) 修 codegen 让它别再覆盖 还是 (c) 重写 placement

**验收：** 一段 ≤5 行的诊断，含「问题在 X 文件 Y 行，做法是 Z」

**影响文件：** 仅读 + 写 STATUS doc

**时长：** 15–25 min

---

## Task 4 · 修 lifting_platform 装配 placement

**目标：** assembly 实际给每个 part 加上正确的 translate / rotate，让 GLB 里件 bbox 中心散开（两两距离 ≥10 mm 这种正常装配水平）。

**做什么（按 Task 3 结论分支）：**
- 分支 a（从 git history 恢复）：`git checkout <good-commit> -- cad/lifting_platform/<file>` 然后微调
- 分支 b（修 codegen）：找到覆盖来源，加 guard，然后 a
- 分支 c（重写 placement）：参考 CAD_SPEC §6.3 的 zone_offsets 表 + `assembly_layout.py` 现有结构，写 placement table（顶板 z=350、底板 z=0、动板 z=动态 / 0~300、电机座 z=0 等等）

**验收：**
- `python cad_pipeline.py build --subsystem lifting_platform`
- 读新 GLB 后探针确认：bbox 中心两两最小距离 ≥10 mm；整体 z 跨度 ≥ 350 mm；x 跨度 ≥ 150 mm（说明上下板在不同高度、左右导向轴分开）

**影响文件：** `cad/lifting_platform/assembly*.py`（可能多个）

**时长：** 30–60 min

---

## Task 5 · 修 lifting_platform 8 个结构件的 .py（顶板 / 底板 / 动板 / 电机座 / …）

**目标：** 8 个 .py（`100/200/201/300/400/403/404/500.py` 或者 `p100/...p500.py`，按 Task 3 结论确认实际用的那一组）从 box 占位升级到带正确特征的几何。

**做什么（每件一个迷你 task）：**

| 子任务 | 件 | 关键特征要画上 |
| --- | --- | --- |
| 5a | 顶板 `SLP-100` | 矩形板 + 4 个 LM10UU 沉孔 / 导向轴孔 φ10H7 + M5 安装孔 + 倒角 |
| 5b | 底板 `SLP-300` | 矩形板 + 4 个 KFL001 螺栓孔 + 导向轴孔 φ10H7 + 电机座连接孔 |
| 5c | 动板（含 LM10UU 沉孔 + 螺母法兰沉台）`SLP-200` 或类似 | 矩形板 + 4 个 LM10UU 沉孔 φ19H7 + 中心 φ32 沉台（T16 螺母法兰用）+ M4 螺纹孔 |
| 5d | 电机座 `SLP-400` 系列 | L 形板或方块 + NEMA23 螺栓孔 + 顶部联轴器避让槽 |
| 5e | 丝杠端支撑 `SLP-403/404` 之一 | 看 CAD_SPEC 决定 |
| 5f | 限位/挡块 `SLP-500` 或 `SLP-201` | 看 CAD_SPEC 决定 |
| 5g | 余下 1 件 | 看 Task 0 表 |
| 5h | 余下 1 件 | 看 Task 0 表 |

每件流程：
1. 读 Task 0 spec 表的对应行
2. 读对应的 `draw_*.py`（如果有）抄孔位
3. 编辑相应的 `.py`，把 `.box(...)` 换成 `.box(...).cut(holes).cut(counterbores).fillet(...)`
4. `python <file>` 单跑测试，看是否能 export 不抛异常

**验收：** 每件局部测试通过；文件不再含 scaffold 自标记字符串（删 docstring 里那几行）

**影响文件：** 8 个 `.py`，全部 tracked

**时长：** 8 件 × 10–20 min = ~2 小时（可拆 2-3 个 session）

---

## ✋ CHECKPOINT 1 完成条件

- ✅ Task 1-5 全部 ✅
- ✅ `python cad_pipeline.py build --subsystem end_effector` 成功；GLB 里法兰跨度 ≈160×160
- ✅ `python cad_pipeline.py build --subsystem lifting_platform` 成功；GLB 整体 bbox z 跨度 ≥350、x/y 跨度合理、件 bbox 中心散开
- ✅ STATUS doc §三 表里 CP-1 标 ✅

---

# CP-2 · 自制件审计工具 + 接进 build 后做强制门禁

## Task 6 · 写 `tools/custom_parts_audit.py`

**目标：** 单文件可独立运行的审计工具，做 spec §5.1 列的 5 件事，输出双格式报告。

**做什么：**
1. 创建 `tools/custom_parts_audit.py`，签名按 spec §5.1
2. 实现 5 个检查模块：
   - `chain_of_custody(sub)` — BOM ↔ build_all ↔ STEP ↔ GLB
   - `envelope_vs_bbox(sub)` — §6.4 envelope vs GLB
   - `scaffold_marker_scan(sub)` — grep marker
   - `placement_collapse_detect(sub)` — bbox 中心两两距离最小值
   - `model_provenance_fill(sub)` — 反查 sw_toolbox_index / step_cache，富化 geometry_report
3. 写 `CUSTOM_PARTS_AUDIT.md`（中文人话）+ `CUSTOM_PARTS_AUDIT.json`（机器版）到 `cad/<sub>/.cad-spec-gen/`
4. exit code: 0 PASS / 2 WARN / 1 FAIL

**验收：**
- `python tools/custom_parts_audit.py end_effector` 退出 0；MD 报告里没有 "未通过" / "FAIL" 字样
- `python tools/custom_parts_audit.py lifting_platform` 退出 0

**影响文件：** 新建 `tools/custom_parts_audit.py`、运行后写 `.cad-spec-gen/CUSTOM_PARTS_AUDIT.*`（gitignored）

**时长：** 40–60 min

---

## Task 7 · 写 audit 工具的回归测试（确认它能反向抓 CP-1 修过的 bug）

**目标：** TDD — 至少 4 个测试 case 证明审计能抓住相应 bug 类型。

**做什么：**
1. `tests/test_custom_parts_audit.py`：
   - case A：fake subsystem 缺一个 BOM 件 → chain_of_custody 报错
   - case B：fake GLB 某件 bbox 比 envelope 小 60% → envelope_vs_bbox 报错
   - case C：fake `.py` 含 `Auto-generated scaffold` → scaffold_scan 报警
   - case D：fake GLB 所有件 bbox 中心 < 1mm 距离 → placement_collapse 报错
   - case E：`end_effector` 在 CP-1 之前（用 `git stash` 的 ee_001_01.py）→ envelope_vs_bbox FAIL；CP-1 之后 → PASS
2. `pytest tests/test_custom_parts_audit.py -v` 全绿

**验收：** 全部测试通过；其中 case E 是端到端的"反向回归"证据

**影响文件：** 新建 `tests/test_custom_parts_audit.py`

**时长：** 30–40 min

---

## Task 8 · 接进 `cad_pipeline.py` 做强制门禁

**目标：** `cad_pipeline.py build --subsystem <s>` 完成后自动跑审计；FAIL 时阻断后续；同时暴露 `cad_pipeline.py custom-parts-audit --subsystem <s>` 独立子命令。

**做什么：**
1. 改 `cad_pipeline.py::cmd_build`：在 GATE-3.5 之后调 `tools.custom_parts_audit.audit_subsystem`；exit code 1 抛 SystemExit(1)
2. 加 `add_parser("custom-parts-audit", ...)`
3. 加 `cmd_custom_parts_audit`
4. 在 `dispatch` 字典加映射

**验收：**
- `python cad_pipeline.py build --subsystem end_effector` 跑完最后一段日志含 "自制件审计：PASS"
- `python cad_pipeline.py custom-parts-audit --subsystem end_effector` 单独可跑
- 故意把 ee_001_01.py 改坏（删一行 union arm）→ `build` 退出非零，提示 "自制件审计：FAIL — 见 `cad/end_effector/.cad-spec-gen/CUSTOM_PARTS_AUDIT.md`"

**影响文件：** `cad_pipeline.py`

**时长：** 20–30 min

---

## ✋ CHECKPOINT 2 完成条件

- ✅ Task 6-8 全部 ✅；CP-2 反向回归（Task 7 case E）实证有效
- ✅ STATUS doc §三 表里 CP-2 标 ✅

---

# CP-3 · 端到端重跑 + 出最终交付图

## Task 9 · 重新清空 `D:\Work\cad-tests\GISBOT\` 和 `\jiehuo\`

**做什么：** 用 PowerShell `Remove-Item -Recurse -Force` 清两个目录再创空，跟 session 5 一致

**时长：** 1 min

---

## Task 10 · `end_effector` 端到端跑 + 归档

**做什么：**
1. `python cad_pipeline.py codegen --subsystem end_effector`（不带 --force，CP-1 改动保留）
2. `python cad_pipeline.py build --subsystem end_effector`（含新审计）→ 应 PASS
3. `python cad_pipeline.py render --subsystem end_effector --timestamp`
4. `python cad_pipeline.py enhance --subsystem end_effector --backend engineering`（gemini 代理修好的话改 `--backend gemini`）
5. `python cad_pipeline.py enhance-check --subsystem end_effector --dir cad/output/renders`
6. `python cad_pipeline.py annotate --subsystem end_effector --lang cn,en --dir cad/output/renders`
7. `python tmp/_copy_pipeline_outputs.py end_effector D:/Work/cad-tests/GISBOT`
8. 检查 `D:\Work\cad-tests\GISBOT\04_render\V4_exploded*.png` 视觉验法兰 4 臂

**验收：** 视觉上能看到法兰有 4 臂；ENHANCEMENT_REPORT delivery_status=accepted；CUSTOM_PARTS_AUDIT PASS

**时长：** 15–25 min（含 Blender render ~7 min）

---

## Task 11 · `lifting_platform` 端到端跑 + 归档

**做什么：** 同 Task 10 模式，subsystem 换 lifting_platform；归档到 `D:\Work\cad-tests\jiehuo\`

**验收：** 视觉上能看到上下板、动板、导向轴、电机座、丝杠 ≥6 件分离；ENHANCEMENT_REPORT accepted；CUSTOM_PARTS_AUDIT PASS

**时长：** 15–25 min

---

## Task 12 · 更新 _README.md 把"SW 模型/材质 provenance"链摊开

**做什么：** 两个 `_README.md` 里加一节「SW Toolbox / SW 材质 的使用证据」：
- 列 `model_provenance.source_kind` 统计
- 引用 `geometry_report.json` 行号
- 列渲染日志中 `SW_TEXTURES_DIR` 注入那一句
- 列 runtime_materials.json 里这次实际用到的预设和它们的 SW 纹理路径

**时长：** 10 min

---

## ✋ CHECKPOINT 3 完成条件

- ✅ Task 9-12 ✅
- ✅ 用户 5 条验收（spec §6）逐条人工核对通过
- ✅ STATUS doc §三 CP-3 ✅

---

# CP-4 · 跨会话文档收尾

## Task 13 · 全景图 §10 更新 + 新增 §11「自制件审计层」

**做什么：**
- §10 实测跑通板块换成 CP-3 的 6 张新缩略图 + 文案改成"两类 bug 修复后的真实输出"
- 新增 §11「自制件审计层 · 防止这类 bug 再回归」简介

**时长：** 15 min

---

## Task 14 · memory + retrospective

**做什么：**
- 更新 `memory/project_quality_overhaul.md` 标 v1 done
- 在 `memory/MEMORY.md` 加一行 retrospective pointer
- 写 `docs/superpowers/reports/2026-05-13-quality-overhaul-retro.md`（≤30 行）

**验收：** memory + report 一致；任何新 session 读 MEMORY.md 就知道这件事完成了

**时长：** 10 min

---

## ✋ CHECKPOINT 4 完成条件

- ✅ Task 13-14 ✅
- ✅ STATUS doc §三 CP-4 ✅
- ✅ STATUS doc §五 CURRENT TASK 改成"全部完成，下一个 session 可以接新工作了"
