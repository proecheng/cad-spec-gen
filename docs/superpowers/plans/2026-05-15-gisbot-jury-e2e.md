# GISBOT 端到端 photo3d-jury e2e Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 跑通 `D:/Work/cad-tests/GISBOT/`（v2.36 自制件质量大修测试归档，实际是 end_effector subsystem 物理复制）端到端 photo3d-jury 真金 e2e，验证跨项目结构兼容性 + photo3d-jury full pipeline + micuapi.ai gemini-2.5-flash 7 视角 vision 实测。

**Architecture:** 本地 setup 脚本（`D:/Work/cad-tests/GISBOT/_setup_jury.py` 不进 cad-spec-gen git）镜像 GISBOT 文件到 `cad/output/renders/` + `cad/end_effector/.cad-spec-gen/` 模拟 cad-spec-gen 项目根布局；用 **subsystem=end_effector + RUN_ID=20260513T115709Z**（既有报告内嵌值，spec D6）；path mirror 而非 rewrite（spec D7，保 sha256 不漂）；显式 cwd = `D:/Work/cad-tests/GISBOT/`（spec §7 + layer 6 E10）。

**Tech Stack:** Python `shutil.copy2` + 标准库 + `photo3d-jury` CLI（cad-spec-gen v2.37.5 既装）+ micuapi.ai gemini-2.5-flash（jury 评分 + retry backend）。

**Spec：** `docs/superpowers/specs/2026-05-15-gisbot-jury-e2e-design.md`（247 行 / brainstorming F1+F2 fix + layer 6 E7+E8+E10 fix）

**分支：** `feat/gisbot-jury-e2e`（已建 / HEAD `dd51929`）

---

## File Structure

| 文件 | 用途 | 落地 |
|---|---|---|
| `D:/Work/cad-tests/GISBOT/_setup_jury.py` | 一次性 setup 脚本（镜像 + ARTIFACT_INDEX 生成）| **本地不进 cad-spec-gen git** |
| `D:/Work/cad-tests/GISBOT/cad/output/renders/` | 镜像 04_render + 05_enhance 内容 | 本地（setup 创建）|
| `D:/Work/cad-tests/GISBOT/cad/end_effector/CAD_SPEC.md` | 镜像 01_spec/CAD_SPEC.md | 本地 |
| `D:/Work/cad-tests/GISBOT/cad/end_effector/.cad-spec-gen/ARTIFACT_INDEX.json` | setup 生成 active_run_id=20260513T115709Z | 本地 |
| `D:/Work/cad-tests/GISBOT/cad/end_effector/.cad-spec-gen/runs/20260513T115709Z/PHOTO3D_JURY_REPORT.json` | jury 跑完 evidence | 本地（retro 引）|
| `docs/superpowers/plans/2026-05-15-gisbot-jury-e2e.md` | 本 plan | **进 cad-spec-gen git** |
| `docs/superpowers/reports/2026-05-15-gisbot-jury-e2e-retro.md` | retro doc | 进 git |

**不动**：cad-spec-gen `tools/photo3d_jury.py` / 任何 production / 任何测试 / CI workflow / GISBOT/01_spec, 04_render, 05_enhance 既有文件。

---

## Task 0: Scout + 实测 schema + baseline

**Files:** Read only.

- [ ] **Step 1: 切到分支并 fetch 验证无并行改动**

```bash
cd D:/Work/cad-spec-gen
git fetch origin main
git checkout feat/gisbot-jury-e2e
git log --oneline HEAD..origin/main
```

Expected: 空。报告。

- [ ] **Step 2: baseline dev_sync --check + jury 测试**

```bash
python scripts/dev_sync.py --check
echo "rc=$?"
pytest -q tests/jury/ tests/jury_loop/ 2>&1 | tail -3
```

Expected: rc=0 + 503 jury PASS。

- [ ] **Step 3: 实测 GISBOT 内容清单**

```bash
ls D:/Work/cad-tests/GISBOT/01_spec/
ls D:/Work/cad-tests/GISBOT/04_render/
ls D:/Work/cad-tests/GISBOT/05_enhance/*.jpg | wc -l
ls D:/Work/cad-tests/GISBOT/cad/ 2>&1 | head -3  # 应不存在
du -sh D:/Work/cad-tests/GISBOT/05_enhance/  # 总大小
```

Expected:
- `01_spec/`: CAD_SPEC.md + DESIGN_REVIEW.{json,md}
- `04_render/`: 7 V*.png + render_manifest.json
- `05_enhance/`: 7 V*_enhanced.jpg = ~1 MB 总
- `cad/`: 不存在

**报告各 ls 输出 + 总大小。**

- [ ] **Step 4: 实测 ENHANCEMENT_REPORT.json schema 关键字段（layer 6 E7 验证）**

```bash
python -c "
import json
p = 'D:/Work/cad-tests/GISBOT/05_enhance/ENHANCEMENT_REPORT.json'
d = json.load(open(p, encoding='utf-8'))
print('subsystem:', d.get('subsystem'))
print('run_id:', d.get('run_id'))
print('render_dir:', d.get('render_dir'))
print('render_manifest:', d.get('render_manifest'))
print('view_count:', d.get('view_count'))
print('views[0].source_image:', d['views'][0].get('source_image'))
print('views[0].enhanced_image:', d['views'][0].get('enhanced_image'))
print('status:', d.get('status'))
"
```

Expected:
- subsystem: end_effector
- run_id: 20260513T115709Z
- render_dir: `cad/output/renders`
- render_manifest: `cad/output/renders/render_manifest.json`
- view_count: 7
- views[0].source_image: `cad/output/renders/V1_front_iso_20260513_1959.png`
- views[0].enhanced_image: `cad/output/renders/V1_front_iso_20260513_1959_20260513_2006_enhanced.jpg`
- status: accepted

**报告实际字段。如有偏差 spec assumption → BLOCKED 让 controller 重审。**

- [ ] **Step 5: 实测 render_manifest.json schema（layer 6 E8 验证）**

```bash
python -c "
import json
p = 'D:/Work/cad-tests/GISBOT/04_render/render_manifest.json'
d = json.load(open(p, encoding='utf-8'))
print('subsystem:', d.get('subsystem'))
print('run_id:', d.get('run_id'))
print('render_dir:', d.get('render_dir'))
print('render_dir_rel_project:', d.get('render_dir_rel_project'))
print('product_graph_path:', d.get('product_graph_path'))
print('files count:', len(d.get('files', [])))
"
```

Expected:
- subsystem: end_effector
- run_id: 20260513T115709Z
- render_dir: `D:\\Work\\cad-spec-gen\\cad\\output\\renders`（绝对路径 stale）
- render_dir_rel_project: `cad/output/renders`（相对路径，jury 主用此）
- product_graph_path: `cad/end_effector/PRODUCT_GRAPH.json`
- files count: 7

**报告。** 若 render_dir_rel_project 不存在 → spec D7 假设破，重审。

- [ ] **Step 6: 验证 jury config 可达**

```bash
python -c "
import json, os
p = os.path.expanduser('~/.claude/cad_jury_config.json')
d = json.load(open(p, encoding='utf-8'))
print('active_profile_id:', d.get('active_profile_id'))
for prof in d.get('profiles', []):
    print(f'  profile {prof[\"id\"]}: model={prof.get(\"model\")} url={prof.get(\"api_base_url\")[:50]}')
"
```

Expected: 至少 1 个 profile 含 micuapi.ai 或类似 vision-capable model。**报告。**

- [ ] **Step 7: 验证 photo3d-jury CLI 入口可达**

```bash
photo3d-jury --help 2>&1 | head -5
# 若失败：
# python -m tools.photo3d_jury --help 2>&1 | head -5
```

Expected: 显示帮助。**报告哪种入口可用** (Task 2 用同一形式)。

- [ ] **Step 8: 汇总数据**

无 commit；report 汇总：
- GISBOT 内容清单（jpg count / 总大小 / cad/ 不存在）
- ENHANCEMENT_REPORT.json + render_manifest.json 关键字段实测值（验证 spec D6/D7 假设）
- jury config 配置可达
- photo3d-jury CLI 入口形式
- baseline 503 jury PASS / dev_sync rc=0

---

## Task 1: 写 _setup_jury.py + 镜像 GISBOT/ 文件

**Files:**
- Create: `D:/Work/cad-tests/GISBOT/_setup_jury.py`（**本地不进 cad-spec-gen git**）

- [ ] **Step 1: 写 setup 脚本**

新建 `D:/Work/cad-tests/GISBOT/_setup_jury.py`（utf-8 编码显式）：

```python
"""GISBOT 端到端 photo3d-jury e2e setup 脚本（一次性）。

镜像 GISBOT/01_spec, 04_render, 05_enhance → cad-spec-gen 期望布局：
- cad/output/renders/  ← 04_render/* + 05_enhance/V*_enhanced.jpg + 05_enhance/ENHANCEMENT_REPORT.json
- cad/end_effector/CAD_SPEC.md  ← 01_spec/CAD_SPEC.md
- cad/end_effector/.cad-spec-gen/ARTIFACT_INDEX.json  ← 新生成（active_run_id=既有值）
- cad/end_effector/.cad-spec-gen/runs/20260513T115709Z/  ← jury 跑时自动创建 PHOTO3D_JURY_REPORT.json

subsystem=end_effector + RUN_ID=20260513T115709Z 用既有 ENHANCEMENT_REPORT 内嵌值
（spec §3.6 D6 + §3.7 D7：path mirror 不 rewrite，保 sha256 不漂）。
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

GISBOT = Path("D:/Work/cad-tests/GISBOT")
SUBSYSTEM = "end_effector"
RUN_ID = "20260513T115709Z"


def main() -> int:
    if not GISBOT.is_dir():
        print(f"✗ {GISBOT} 不存在", file=sys.stderr)
        return 1

    renders = GISBOT / "cad" / "output" / "renders"
    spec_target = GISBOT / "cad" / SUBSYSTEM / "CAD_SPEC.md"
    ag_dir = GISBOT / "cad" / SUBSYSTEM / ".cad-spec-gen"
    run_dir = ag_dir / "runs" / RUN_ID

    # 1. mkdir
    renders.mkdir(parents=True, exist_ok=True)
    ag_dir.mkdir(parents=True, exist_ok=True)
    run_dir.mkdir(parents=True, exist_ok=True)
    print(f"✓ 创建目录: {renders}, {ag_dir}, {run_dir}")

    # 2. 镜像 04_render（V*.png + render_manifest.json）
    for src in (GISBOT / "04_render").glob("V*.png"):
        shutil.copy2(src, renders / src.name)
    shutil.copy2(GISBOT / "04_render" / "render_manifest.json",
                 renders / "render_manifest.json")
    print(f"✓ 镜像 04_render → {renders}（V*.png + render_manifest.json）")

    # 3. 镜像 05_enhance（V*_enhanced.jpg + ENHANCEMENT_REPORT.json）
    for src in (GISBOT / "05_enhance").glob("V*_enhanced.jpg"):
        shutil.copy2(src, renders / src.name)
    shutil.copy2(GISBOT / "05_enhance" / "ENHANCEMENT_REPORT.json",
                 renders / "ENHANCEMENT_REPORT.json")
    print(f"✓ 镜像 05_enhance → {renders}（V*_enhanced.jpg + ENHANCEMENT_REPORT.json）")

    # 4. 镜像 01_spec/CAD_SPEC.md
    shutil.copy2(GISBOT / "01_spec" / "CAD_SPEC.md", spec_target)
    print(f"✓ 镜像 CAD_SPEC.md → {spec_target}")

    # 5. 写 ARTIFACT_INDEX.json（最小，jury 只读 active_run_id + artifacts dict）
    artifact_index = {
        "schema_version": 1,
        "subsystem": SUBSYSTEM,
        "active_run_id": RUN_ID,
        "accepted_baseline_run_id": None,
        "runs": {
            RUN_ID: {
                "run_id": RUN_ID,
                "active": True,
                "artifacts": {
                    "enhancement_report": "cad/output/renders/ENHANCEMENT_REPORT.json",
                    "render_manifest": "cad/output/renders/render_manifest.json",
                },
            },
        },
    }
    ag_dir.joinpath("ARTIFACT_INDEX.json").write_text(
        json.dumps(artifact_index, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"✓ 写 ARTIFACT_INDEX.json（active_run_id={RUN_ID}）")

    print("\n✓ setup 完成。下一步：")
    print(f"  cd {GISBOT}")
    print(f"  photo3d-jury --project-root . --subsystem {SUBSYSTEM} --budget 0.20")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: 跑 setup 脚本**

```bash
cd D:/Work/cad-tests/GISBOT
python _setup_jury.py
echo "exit=$?"
```

Expected: exit=0；7 个 "✓" 打印；目录骨架建好。

- [ ] **Step 3: 验证镜像结果**

```bash
ls D:/Work/cad-tests/GISBOT/cad/output/renders/ | wc -l       # 应 15 (7 png + 7 jpg + manifest)
ls D:/Work/cad-tests/GISBOT/cad/output/renders/ENHANCEMENT_REPORT.json
ls D:/Work/cad-tests/GISBOT/cad/end_effector/CAD_SPEC.md
cat D:/Work/cad-tests/GISBOT/cad/end_effector/.cad-spec-gen/ARTIFACT_INDEX.json | head -10
```

Expected:
- 镜像目录 15 文件（7 V*.png + 7 V*_enhanced.jpg + render_manifest.json）+ ENHANCEMENT_REPORT.json
- CAD_SPEC.md 存在
- ARTIFACT_INDEX.json 含 `active_run_id`: `20260513T115709Z`

任一不满足 → 改 _setup_jury.py 修复重跑。

- [ ] **Step 4: 验证 sha256 与原文件一致（shutil.copy2 保 metadata 但 sha 应等）**

```bash
python -c "
import hashlib
from pathlib import Path
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()[:16]
orig = Path('D:/Work/cad-tests/GISBOT/05_enhance/ENHANCEMENT_REPORT.json')
mirror = Path('D:/Work/cad-tests/GISBOT/cad/output/renders/ENHANCEMENT_REPORT.json')
print(f'orig:   {sha(orig)}')
print(f'mirror: {sha(mirror)}')
print('match:', sha(orig) == sha(mirror))
"
```

Expected: orig == mirror（spec D7 保 sha256 不漂证）。

- [ ] **Step 5: 不 commit**

`_setup_jury.py` 在 `D:/Work/cad-tests/GISBOT/` 不在 cad-spec-gen 仓；无 git 操作。

---

## Task 2: 跑 photo3d-jury 真金 e2e

**Files:** No file creation; CLI execution.

**Critical cwd 约定**（layer 6 E10）：必须先 `cd D:/Work/cad-tests/GISBOT/` 再跑 photo3d-jury。

- [ ] **Step 1: 预检 — 确认 jury env 不被 disable**

```bash
echo "CAD_JURY_DISABLE_LLM=$CAD_JURY_DISABLE_LLM"
```

Expected: 空字符串。**若非空**：`unset CAD_JURY_DISABLE_LLM`（Linux/Mac）或 `Remove-Item Env:CAD_JURY_DISABLE_LLM`（PowerShell）。

- [ ] **Step 2: dry-run 验证 Layer 0/1（不调 LLM 不花钱）**

```bash
cd D:/Work/cad-tests/GISBOT
photo3d-jury --project-root . --subsystem end_effector --budget 0.20 --dry-run 2>&1 | tee /tmp/jury_dry_run.log | tail -30
```

Expected: 
- 显示 "Layer 0 OK / Layer 1 OK / 估算 N.NN USD"
- exit=0
- **不**产 PHOTO3D_JURY_REPORT.json（dry-run 不写报告）

**若 Layer 0 fail**：读 log；常见 root cause:
- render_dir 绝对路径 mismatch → 看 jury 是否真用 render_dir_rel_project (Task 0 Step 5 实测应为是)；若不是 → fallback sed 改 render_dir 绝对值
- subsystem mismatch → spec D6 应已修；若仍 fail → re-verify Task 0 实测 subsystem 字段
- ARTIFACT_INDEX 路径错 → 验证 Task 1 Step 3 输出

**报告 dry-run 输出 + 估算 cost。**

- [ ] **Step 3: 真金 e2e 跑（dry-run pass 后）**

```bash
cd D:/Work/cad-tests/GISBOT
photo3d-jury --project-root . --subsystem end_effector --budget 0.20 2>&1 | tee /tmp/jury_real_run.log
echo "exit=$?"
```

Expected:
- exit ∈ {0, 3, 10, 11, 12}（spec AC-2）
- 产 `cad/end_effector/.cad-spec-gen/runs/20260513T115709Z/PHOTO3D_JURY_REPORT.json`
- 跑时 stderr 打 jury 进度（"Layer 2 V1/7..."）
- 用时约 30s-2min（7 视角 × LLM call latency）

**Transient flake 处理**：
- 网络挂 → 重试（jury 内部 max_retries=2 自动）
- 全 7 视角 fail → vendor issue；retro 沉淀 lesson
- cost_capped exit=3 → 看 stderr 报告哪些视角被 skip

**报告 jury 跑完 exit + log 末 20 行 + run_dir 路径**。

- [ ] **Step 4: 验证 PHOTO3D_JURY_REPORT.json 内容**

```bash
REPORT=D:/Work/cad-tests/GISBOT/cad/end_effector/.cad-spec-gen/runs/20260513T115709Z/PHOTO3D_JURY_REPORT.json
ls -la $REPORT
python -c "
import json
d = json.load(open('$REPORT', encoding='utf-8'))
print('status:', d.get('status'))
print('ordinary_user_message:', d.get('ordinary_user_message'))
print('first_blocking_reason:', d.get('first_blocking_reason'))
print('view_count:', d.get('view_count'))
print('estimated_cost_usd:', d.get('estimated_cost_usd'))
print('actual_cost_usd:', d.get('actual_cost_usd'))
print()
print('views:')
for v in d.get('view_verdicts', {}).items() if isinstance(d.get('view_verdicts'), dict) else []:
    print(f'  {v[0]}: ...')
print(json.dumps(d, indent=2, ensure_ascii=False)[:2000])
"
```

Expected:
- status 字段存在（accepted / preview / needs_review / blocked）
- view_count = 7
- estimated/actual cost 数字
- view-level verdicts 含 photoreal_score + semantic_checks

**报告 status + actual cost + 7 视角 verdict 摘要**。

- [ ] **Step 5: 验证 cost 在预算内**

```bash
# 从 Step 4 输出读 actual_cost_usd；若 > 0.20 → cost_capped 但仍算 AC-2 通过
```

Expected: ≤ $0.20（spec AC-5）；若超 → exit 应是 3。

- [ ] **Step 6: 不 commit**

evidence 在 `D:/Work/cad-tests/GISBOT/...` 本地；无 cad-spec-gen 仓改动。

---

## Task 3: 写 retro doc + commit plan/retro 进 git

**Files:**
- Create: `D:/Work/cad-spec-gen/docs/superpowers/reports/2026-05-15-gisbot-jury-e2e-retro.md`

- [ ] **Step 1: 写 retro 文档**

新建 `D:/Work/cad-spec-gen/docs/superpowers/reports/2026-05-15-gisbot-jury-e2e-retro.md`：

```markdown
# Retro — Tier 2 GISBOT 端到端 photo3d-jury e2e

**完工日期：** 2026-05-15
**Spec：** `docs/superpowers/specs/2026-05-15-gisbot-jury-e2e-design.md`（247 行 / brainstorming F1+F2 + layer 6 E7+E8+E10 fix）
**Plan：** `docs/superpowers/plans/2026-05-15-gisbot-jury-e2e.md`
**Baseline：** cad-spec-gen main@`27b2c5c`（v2.37.5 merge）

> **spec 标题 vs 实际 subsystem mapping**：本 PR spec/plan/retro 标题"GISBOT jury e2e"实际跑 subsystem **"end_effector"**（GISBOT 是 end_effector v2.36 测试归档物理复制目录，内部 metadata 未 rebrand；spec §3.6 D6 决策接受此 mapping）。

## 一句话

跑通 `D:/Work/cad-tests/GISBOT/` 端到端 photo3d-jury 真金 7 视角 e2e，验证跨项目结构兼容性（path mirror 模式 work）+ photo3d-jury full pipeline + micuapi.ai gemini-2.5-flash vendor。

## 完工范围

- `_setup_jury.py` 本地脚本（不进 git）镜像 GISBOT/ 到 cad-spec-gen 期望布局
- 跑 photo3d-jury 7 视角真金 e2e，产 PHOTO3D_JURY_REPORT.json
- spec/plan/retro 3 docs 进 cad-spec-gen git
- **0 production code 改 / 0 测试改 / 不发 patch tag**

## 数字（待实施期填）

- jury 子集 PASS：503 → 503 不变（无代码改）
- 全套件：3193 → 3193 / 0 regression
- PHOTO3D_JURY_REPORT.json status: <实测填>
- view_count: 7
- actual_cost_usd: <实测填>
- 7 视角 photoreal_score 均值：<实测填>
- LLM call 总数：<实测填>（feature_extractor + 7 verdict + 可能 retry）
- 跑时长：<实测填>

## 跑通的 evidence（本地路径）

- setup 脚本：`D:/Work/cad-tests/GISBOT/_setup_jury.py`
- 镜像布局：`D:/Work/cad-tests/GISBOT/cad/output/renders/` + `cad/end_effector/.cad-spec-gen/`
- jury 报告：`D:/Work/cad-tests/GISBOT/cad/end_effector/.cad-spec-gen/runs/20260513T115709Z/PHOTO3D_JURY_REPORT.json`
- 跑命令：`cd D:/Work/cad-tests/GISBOT && photo3d-jury --project-root . --subsystem end_effector --budget 0.20`

> evidence 在本仓主 maintainer 本机 `D:/Work/cad-tests/`；其他开发者本机路径相对应（layer 6 F1 教训）。

## 审查矩阵

| Layer | findings | inline 修 | 接受 |
|---|---|---|---|
| brainstorming 数据/漂移 | 2 (F1+F2) | 2 | 0 |
| layer 6 边界 + 闭环 | 10 | 3（E7+E8+E10）| 7 |
| per-task spec+quality review × 3 task | <待补> | <待补> | <待补> |
| **总** | **12+** | **5+** | **7+** |

## 沉淀 lessons

1. **spec cat 验证抓 metadata 漂移**（layer 6 E7+E8）：spec 写时凭印象假设"subsystem=GISBOT / 路径在 run_dir"；实测 cat ENHANCEMENT_REPORT.json + render_manifest.json **30 行**就证实纯 copy 100% 跑不通（subsystem=end_effector / 路径在 cad/output/renders/）。**lesson**：spec 涉及 JSON 数据 schema 假设时 brainstorming 阶段必 cat 实测，10 行命令救本 PR 免实施期 BLOCKED。

2. **测试归档 metadata 不 rebrand 陷阱**：GISBOT/ 是 end_effector 测试物理复制目录，但内部 metadata（subsystem / run_id / paths）未 rebrand。**lesson**：测试 evidence 归档应同步 rebrand metadata（subsystem + run_id + paths），否则下游工具用 metadata 字段 fail。**新登 §11 follow-up**（项目级）：建议未来 `tools/dev/rebrand_test_archive.py` 工具自动 rewrite metadata。

3. **path mirror 优于 path rewrite**（spec D7）：保 sha256/schema 不漂，jury Layer 0 freeze 仍 work；只物理布局变文件内容字面零改。**lesson**：跨项目兼容性 setup 优先用镜像策略而非 rewrite。

4. **cwd 显式声明**（layer 6 E10）：跨项目跑 photo3d-jury 时 `--project-root .` + `cd <target>` 双保险，避免 jury 内部 `Path.cwd()` 解析 ambiguity。

5. **<Task 2 实测填>**：跑实测如发现新 lesson（vendor cost 偏差 / Layer 0 校验异常 / feature_extractor 行为），写入这里。

## §11 follow-up（项目级，本 PR 新登）

| # | 严重度 | 内容 | 触发条件 |
|---|---|---|---|
| §11-N1 | LOW | 测试归档 rebrand 工具 `tools/dev/rebrand_test_archive.py` 自动 rewrite ENHANCEMENT_REPORT/render_manifest metadata | ≥ 2 个测试归档 e2e 跑过都遇 metadata 错位 |
| §11-N2 | LOW | photo3d-jury 接受 `--override-subsystem` flag 允许 cli vs report 内嵌 mismatch（softer 路径）| 用户多次需要跨 subsystem 测试 |

## 下次类似 PR 优化

- spec 涉及 JSON schema 假设时 brainstorming 阶段 cat 实测必跑
- 跨项目兼容性优先 path mirror 不 path rewrite
- cwd 跨项目场景必显式声明
- 测试归档不 rebrand metadata 是 anti-pattern，记得未来归档时 rebrand

[[project-v2-37-5-done]] 上游 §12 f3 cleanup 追溯。
[[project-v2-37-4-done]] 上游 §12 f5+f6 + layer 6 E10 行号 snapshot lesson 追溯。
```

- [ ] **Step 2: 元测试**

```bash
cd D:/Work/cad-spec-gen
pytest -q tests/test_agents_md.py tests/test_no_tracked_mirror.py 2>&1 | tail -3
```

Expected: 5 PASS。

- [ ] **Step 3: Commit plan + retro 进 git**

```bash
cd D:/Work/cad-spec-gen
git add docs/superpowers/plans/2026-05-15-gisbot-jury-e2e.md \
        docs/superpowers/reports/2026-05-15-gisbot-jury-e2e-retro.md
git -c commit.gpgsign=false commit -m "$(cat <<'EOF'
docs(gisbot-jury-e2e): plan + retro — Tier 2 GISBOT 端到端 photo3d-jury 真金 e2e

跑通 D:/Work/cad-tests/GISBOT/ 端到端 photo3d-jury 真金 7 视角 e2e。

3 task 实施：
- Task 0 scout 实测 ENHANCEMENT_REPORT/render_manifest schema (layer 6 E7+E8 验证)
- Task 1 _setup_jury.py 本地脚本（不进 git）镜像 GISBOT/ 到 cad-spec-gen 布局
- Task 2 cd D:/Work/cad-tests/GISBOT && photo3d-jury --subsystem end_effector
- Task 3 retro 沉淀 lesson + commit docs 进 git

subsystem=end_effector + RUN_ID=20260513T115709Z 用既有 ENHANCEMENT_REPORT
内嵌值（spec D6）；path mirror 不 rewrite（spec D7，保 sha256 不漂）。

spec 标题"GISBOT"实际跑 subsystem"end_effector"——GISBOT 是 end_effector v2.36
测试归档物理复制目录，内部 metadata 未 rebrand；retro 显式声明此 mapping。

0 production code 改 / 0 测试 / 不发 patch tag。

§11 follow-up 新登 2 项（项目级 rebrand 工具 + jury --override-subsystem）；
4 项 lesson 沉淀（cat 验证 metadata / 测试归档 rebrand 陷阱 / path mirror
优于 rewrite / cwd 显式声明）。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Push + 开 PR / 直接 commit main（plan 决定）

**Files:** 无文件改动；纯 git/GitHub。

由于本 PR **0 production code 改**仅 3 docs（spec/plan/retro），可选：
- A) 开 PR 走 CI 8/8（与 cleanup PR 一致工作流）
- B) 直接 commit/push main（无 production 改不需 CI gate）

**推荐 A**（一致性 + 走 review checklist）。

### Task 4a: Push + 开 PR + 等 CI

- [ ] **Step 1: PR push 前并行改动验证**

```bash
cd D:/Work/cad-spec-gen
git fetch origin main
git log --oneline HEAD..origin/main
```

Expected: 空。

- [ ] **Step 2: Push 分支**

```bash
git push origin feat/gisbot-jury-e2e
```

- [ ] **Step 3: 开 PR**

```bash
gh pr create --title "docs(gisbot-jury-e2e): Tier 2 GISBOT 端到端 photo3d-jury 真金 e2e + retro" --body "$(cat <<'EOF'
## 概要

Tier 2 GISBOT 端到端 photo3d-jury 真金 e2e（7 视角 micuapi.ai gemini-2.5-flash）跑通；3 docs 沉淀（spec/plan/retro）进 git。

## 改动

- `docs/superpowers/specs/2026-05-15-gisbot-jury-e2e-design.md`（spec / 247 行）
- `docs/superpowers/plans/2026-05-15-gisbot-jury-e2e.md`（plan / ~400 行）
- `docs/superpowers/reports/2026-05-15-gisbot-jury-e2e-retro.md`（retro / ~80 行）

**0 production code / 0 测试 / 0 schema / 0 env-config / 0 行为变化** —— pure docs。

## evidence（本地）

- setup: `D:/Work/cad-tests/GISBOT/_setup_jury.py`
- jury 报告: `D:/Work/cad-tests/GISBOT/cad/end_effector/.cad-spec-gen/runs/20260513T115709Z/PHOTO3D_JURY_REPORT.json`
- 实测 cost / verdict / status 见 retro

## 审查层数

brainstorming F1+F2 fix + layer 6 E7+E8+E10 fix + per-task spec+quality review × 3 = 12+ findings，5+ inline 修。

## 不发 v2.37.6 patch tag

0 production code 改无必要。

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Step 4: 等 PR CI 8/8 全绿**

```bash
gh pr checks --watch
```

Expected: 8/8 SUCCESS（docs 改不影响测试）。

### Task 4b: Merge（用户授权后；不发 tag）

按 v2.37.5 模板拆 5-merge步：

- Step 5: `gh pr merge <PR_NUM> --squash --delete-branch`
- Step 6: git checkout main + pull + 等 main CI 8/8 全绿
- Step 7: **不打 tag**（0 production 改无 release 需求）
- Step 8: **不发 GitHub Release**
- Step 9: 写 `project_gisbot_jury_e2e_done.md` memory + MEMORY.md 索引行

---

## Self-Review

**1. Spec coverage**:

| Spec 章节 | Plan Task | 备注 |
|---|---|---|
| §2.1 改动表 row 1 (_setup_jury.py 本地) | Task 1 | ✓ |
| §2.1 改动表 row 2-5 (镜像目录 + ARTIFACT_INDEX + run_dir + PHOTO3D_JURY_REPORT) | Task 1 + Task 2 | ✓ |
| §2.1 改动表 row 6-7 (plan/retro 进 git) | Task 3 + Task 4 | ✓ |
| §3 D1-D7 决策（含 D6+D7 layer 6 fix）| Task 1 Step 1 setup 代码 + Task 2 跑命令 | ✓ |
| §4 AC-1..7 | Task 1 Step 3 (AC-1) / Task 2 Step 3 (AC-2) / Task 2 Step 4 (AC-3/AC-4) / Task 2 Step 5 (AC-5) / Task 3 retro (AC-6) / Task 4 (AC-7) | ✓ |
| §5 风险表（含 E7/E8/E10 row）| Task 0 Step 4-5 实测 + Task 2 Step 2 dry-run + Task 2 cwd 显式 | ✓ |
| §6 不变量 #1-6 | Task 1-4 全程维持 | ✓ |
| §7 流程 + §7.1 Rollback | Task 3+4 + 本地 evidence | ✓ |
| §8 7 调查步 | Task 0 Step 1-7 全覆盖 | ✓ |
| §9 6 plan 必 cover | Task 0 实测填 + Task 1 utf-8 + Task 2 显式 env + cwd + Task 3 retro mapping disclaimer | ✓ |
| §10 不写代码事项 | 全 task 不做 | ✓ |
| §11 本 PR follow-up (h1/h2/h3) | Task 3 retro 末 §11 follow-up 新登 N1/N2 | ✓ |

**所有 spec 章节有 task 覆盖。**

**2. Placeholder scan**: 数字字段 retro 标 "<待实测填>" 是显式留白（Task 3 实施时补）；无 TBD/TODO/implement later 红旗。Task 2 Step 4 path 用 `$REPORT` shell 变量是正常 bash 用法。

**3. Type consistency**: SUBSYSTEM = "end_effector" / RUN_ID = "20260513T115709Z" 跨 Task 0/1/2/3 一致。setup 脚本 path 变量 `GISBOT` / `renders` / `ag_dir` / `run_dir` 命名 Task 1 内部一致。

**Plan 自检无问题 → ready for handoff。**

---

## 执行方式选择

Plan 完成保存到 `docs/superpowers/plans/2026-05-15-gisbot-jury-e2e.md`。两种执行模式：

1. **Subagent-Driven（推荐）** — v2.37.x 实证 14 PR 一次过 CI 模板可复用
2. **Inline 执行** — scope 中等（含真金 LLM 调用，~2-5 分钟跑时）可考虑

建议 Subagent-Driven。
