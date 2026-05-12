# SP1 §11 follow-up — B1 skill 描述 + B2 L4 smoke — 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 SP1 §11 两个收尾项落地：B1 = `/cad-enhance` skill.json 描述末尾追加 jury 自动重试闭环说明（+ dev_sync 同步 AGENTS.md）；B2 = L4 smoke 测试脚手架（3 case + `requires_jury_loop_e2e` marker + conftest skip hook + 合成 fixture），CI 默认 skip。零行为变更。

**Architecture:** 单 PR，分支 `feat/sp1-followup-skill-desc-l4-smoke`（已建，spec 在 `docs/superpowers/specs/2026-05-12-sp1-followup-skill-desc-l4-smoke-design.md`，2 个 docs commit `cd23cfe` + `a581d74`）。Task 0 确认剩余假设；Task 1 = B1；Task 2 = B2（marker + conftest hook + test 文件，1 commit）；Task 3 = 收尾验证 + code-review + push + PR。

**Tech Stack:** Python 3.10+ / `pytest`（marker + conftest `pytest_collection_modifyitems` skip hook）/ `PIL`（合成 fixture）/ `ruff` / `scripts/dev_sync.py`（skill.json → AGENTS.md 生成）/ `tools/jury_loop/orchestrator.run_loop_if_eligible` + `cmd_enhance_hook.run_loop_hook_for_view`（L4 驱动入口）。

设计文档：`docs/superpowers/specs/2026-05-12-sp1-followup-skill-desc-l4-smoke-design.md`

---

## 前置约定（所有 task 通用）

- 分支必须是 `feat/sp1-followup-skill-desc-l4-smoke`，**不是 main**。subagent 用 `git -C "D:\Work\cad-spec-gen"` 绝对路径 + 提交前 `git -C "D:\Work\cad-spec-gen" branch --show-current` 守卫（`feedback_subagent_cwd_drift.md`）。
- 提交用 `git -c commit.gpgsign=false commit`；commit message 描述部分用中文。
- 工作目录 `D:\Work\cad-spec-gen`；shell PowerShell；命令从 repo root 跑。
- 「全套件」= `python -m pytest tests/ -q`；基线 **3090 PASS / 11 skipped / 0 regression**（ruff/mypy cleanup 合并后；本 PR B2 加 3 个 conftest-skip 的 L4 case → 完工后 **3090 PASS / 14 skipped**）。
- B1 改 `skill.json` 后跑 `python scripts/dev_sync.py` + `python scripts/dev_sync.py --check` + `git diff --exit-code -- AGENTS.md`（`skill.json` 不在 `data/` 镜像里，但 dev_sync 顺带跑无害；AGENTS.md 多半不变——见 spec §3.2）。
- `LF→CRLF` git warning 是 noise，忽略。

---

## Task 0：确认剩余假设（无代码改动，无 commit）

spec §8 的 6 项调查——大部分已在 brainstorm 阶段 grep 解清（结论已写进本 plan 的 Task 1/2 代码块），Task 0 只做**确认**（发现不符就停下报告）+ 1 项仍开的 grep。

- [ ] **Step 1：B1 — 确认没有别的测试断言 "AI Enhancement (4 backends)" description 精确字符串**

Run: `grep -rn "AI Enhancement (4 backends)\|Phase 5: Enhance" tests/ 2>/dev/null`
Expected: 只命中 `tests/test_agents_md.py`（断言 `/cad-enhance` trigger，不断言描述文本）和可能的 collection-only 引用。**若有别的测试断言 description 的精确字符串 → 记下来，Task 1 要同步那个测试的期望值。**

- [ ] **Step 2：B2 — 确认 `run_loop_if_eligible` 只用 `rc.get("prompt")`、`base_params={}` trivial、`reference_mode` 取值**

Run: `grep -n "rc\[\|rc\.get(\|base_params\|reference_mode" tools/jury_loop/orchestrator.py tools/jury_loop/cmd_enhance_hook.py`
Expected: `orchestrator.py` 里 `rc` 只见 `rc.get("prompt", "")`（3 处）；`cmd_enhance_hook.py` 调 `run_loop_if_eligible(..., base_params={}, ...)`。看 `cmd_enhance_hook.run_loop_hook_for_view` 的 `reference_mode` 参数取值（grep `reference_mode ==` / `"v1_anchor"` / `"per_view"` / `"none"` in `cmd_enhance_hook.py` + `cad_pipeline.py`），记下 v1_anchor 模式的字符串值（plan 假设是 `"v1_anchor"`）。**不符就停下报告。**

- [ ] **Step 3：B2 — 确认 sidecar 字段 + `loop_status` "above_threshold" 值**

Run: `grep -n "retry_score_delta\|baseline_score\|loop_status\|above_threshold\|_enhance_meta" tools/jury_loop/metadata.py tools/jury_loop/orchestrator.py`
Expected: `metadata.write_sidecar` 写 `<render_dir>/<view>_enhance_meta.json`，字段含 `loop_status` / `retry_score_delta`（`int | None`，retry 发生则是 delta、没发生则 None）；`orchestrator.py` 里 `loop_status="above_threshold"` 是「baseline 分数 ≥ threshold、不 retry」的状态。确认 sidecar 里读 baseline 分数的字段名（可能在嵌套的 `baseline` dict 里——记下精确路径，如 `sidecar["baseline"]["photoreal_score"]`）。**不符就停下报告。**

- [ ] **Step 4：B2 — 确认 jury config 路径怎么传给 `photo3d-jury --single-view` 子进程 + 是否要 `--allow-external-config`**

Run: `grep -n "single-view\|--config\|allow-external\|allow_external\|jury_profile_path\|subprocess\|Popen" tools/jury_loop/orchestrator.py`
看 orchestrator 调 jury 子进程时把 `jury_profile_path` 怎么传（`--config <path>`？）、子进程对 config 路径有没有「必须在 ~/.claude/ 或当前项目」的限制 → 若有，L4 test 要么把临时 config 写到 `project_root`（当作「当前项目」）、要么传 `--allow-external-config`（看 orchestrator 支不支持透传）。记下结论，Task 2 的 test 据此放 config 文件位置。**这是 B2 最大的不确定点——若发现 orchestrator 不透传 config 路径、或限制太死无法绕 → 报告，可能要把 test 改成 mock jury 子进程（那就不是 e2e 了，降级；与用户确认）。**

- [ ] **Step 5：B2 — 确认 `_parse_profile` / `load_jury_config` 要的最小 config 字段**

已知（`docs/cad-jury-config.md` §2 + `tools/jury/config.py`）：`{"schema_version": 1, "active_profile_id": "<id>", "profiles": [{"id": "<id>", "kind": "openai_compat", "api_base_url": "https://...", "api_key": "...", "model": "..."}]}` 即可（`cost_per_call_usd` 可省）。Run `sed -n '63,160p' tools/jury/config.py` 复核 `_parse_profile` / `_parse_caps` 有没有别的必需字段（如 caps）。**不符就停下报告。**

- [ ] **Step 6：B2 — 确认 `pyproject.toml` 不是 skip-worktree + `tests/jury_loop/conftest.py` 现状**

Run: `git -C "D:\Work\cad-spec-gen" ls-files -v pyproject.toml` → 应是 `H pyproject.toml`（不是 `S`/`h`，可正常 stage）。`tests/jury_loop/conftest.py` 已存在（大量 mock fixture）——`_make_rough_render_png` 放 `test_l4_smoke.py` 自己的 module 函数即可（不进 conftest，避免与现有 fixture 混）。记下确认。

- [ ] **Step 7：汇总报告**

把 Step 1-6 的结论写一段。**任何 Step 发现实质不符（尤其 Step 4）→ 标红、停下、回报，不直接继续。**

---

## Task 1：B1 — `/cad-enhance` skill 描述提及 jury 自动重试闭环（1 commit）

**Files:**
- Modify: `src/cad_spec_gen/data/skill.json`（`skills[3]` = `"AI Enhancement (4 backends)"` 的 `description`）
- （可能）Modify: `AGENTS.md`（dev_sync 重生；多半无变化）

- [ ] **Step 1：改前快照**

Run: `python -m pytest tests/test_agents_md.py -q` → 全 PASS。
Run: `python scripts/dev_sync.py --check` → 通过（确认改前 AGENTS.md 已同步）。

- [ ] **Step 2：编辑 skill.json 的 "AI Enhancement (4 backends)" description**

`src/cad_spec_gen/data/skill.json` 里找到 `"name": "AI Enhancement (4 backends)"` 那个 skill 对象的 `"description"` 字段（一行长 JSON 字符串，当前以 `... Layout-aware prompt routing (radial/linear/custom).` 结尾）。在该字符串**末尾**（`.` 之后、闭引号之前）追加一空格 + 这句（保持单行、英文、JSON 转义正确——字符串里没有 `"` 不用转义；`/` 不用转义）：

```
 Auto-retry loop: when ~/.claude/cad_jury_config.json exists, each view's enhance output is scored by a vision-LLM jury; if below threshold the prompt is rebuilt from the jury feedback and the enhance retried once, keeping the higher-scoring image; disabled silently without the jury config; aggregated into ENHANCEMENT_REPORT.loop_summary.
```

即该字段从 `"...routing (radial/linear/custom)."` 变成 `"...routing (radial/linear/custom). Auto-retry loop: when ~/.claude/cad_jury_config.json exists, ... aggregated into ENHANCEMENT_REPORT.loop_summary."`。**只动这一个 description；不碰其它 4 个 skill。**

- [ ] **Step 3：JSON 仍合法 + dev_sync 同步**

Run: `python -c "import json; d=json.load(open('src/cad_spec_gen/data/skill.json',encoding='utf-8')); print('OK', repr(d['skills'][3]['description'][-120:]))"` → 打印末尾含 `aggregated into ENHANCEMENT_REPORT.loop_summary.`。
Run: `python scripts/dev_sync.py` → 成功（多半 `all mirrors up to date`，AGENTS.md 不变——描述追加到 100 字截断之后）。
Run: `python scripts/dev_sync.py --check` → 通过。
Run: `git -C "D:\Work\cad-spec-gen" status --porcelain` → 应只见 `M src/cad_spec_gen/data/skill.json`（若 AGENTS.md 也变了——理论上不会，但若变了——也一起；不应有别的文件变）。

- [ ] **Step 4：测试 + ruff**

Run: `python -m pytest tests/test_agents_md.py -q` → 全 PASS（描述改动不破它）。
Run: `python -m pytest tests/ -q` → **3090 PASS / 11 skipped / 0 regression**。
（skill.json 是 JSON，ruff 不检——无 ruff step。）
（若 Task 0 Step 1 发现别的测试断言 description 精确字符串 → 这里也跑那个测试 + 同步它的期望值。）

- [ ] **Step 5：commit**

```
git -C "D:\Work\cad-spec-gen" branch --show-current   # 必须是 feat/sp1-followup-skill-desc-l4-smoke
git -C "D:\Work\cad-spec-gen" add src/cad_spec_gen/data/skill.json
# 若 AGENTS.md 也变了：git add AGENTS.md
git -C "D:\Work\cad-spec-gen" -c commit.gpgsign=false commit -m "chore(skill): /cad-enhance 描述提及 jury 自动重试闭环（§11 B1）

AI Enhancement (4 backends) 的 skill.json description 末尾追加一句：jury_loop 自动
重试闭环（评分→低于阈值按反馈重试一次→选高分张交付；没配 cad_jury_config 静默禁用；
聚合到 ENHANCEMENT_REPORT.loop_summary）。dev_sync 同步（AGENTS.md 100 字截断下表格
不变）。零行为变更。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 2：B2 — L4 smoke 脚手架（marker + conftest hook + test 文件，1 commit）

**Files:**
- Modify: `pyproject.toml`（`[tool.pytest.ini_options].markers` 加 `requires_jury_loop_e2e`）
- Modify: `tests/conftest.py`（加 `import os` + 在 `pytest_collection_modifyitems` 里加 `requires_jury_loop_e2e` skip 段）
- Create: `tests/jury_loop/test_l4_smoke.py`（3 case + `_make_rough_render_png` helper）

注：B2 没有 RED→GREEN TDD 循环——3 个 L4 case 本身就是测试，但被 `requires_jury_loop_e2e` 门控、CI 无 `GEMINI_API_KEY` → 全 skip。本 task 的「验证」= 文件被正常收集 + 3 case 显示 skipped（reason 含 `requires_jury_loop_e2e`）+ 全套件不回归 + ruff clean。

- [ ] **Step 1：注册 marker**

`pyproject.toml` 的 `[tool.pytest.ini_options].markers` 列表（当前末项是 `regression: ...`）末尾追加一项：
```
requires_jury_loop_e2e: jury-loop L4 端到端 smoke；需 GEMINI_API_KEY（retry backend）+ jury LLM key（测试自带临时 jury config）；CI / 无 key 时自动 skip
```

- [ ] **Step 2：conftest.py 加 `import os` + skip hook 段**

`tests/conftest.py` 顶部 import 区（当前 `import hashlib` / `import importlib` / `import sys`）加一行 `import os`（按字母序放 `import importlib` 和 `import sys` 之间）。

在 `pytest_collection_modifyitems`（`@pytest.hookimpl(tryfirst=True)`，当前里面有 `_mark_photo3d_contract_tests(items)` + `requires_solidworks` skip 段）的**末尾**（`requires_solidworks` 段之后、函数 return 之前——其实 `requires_solidworks` 段里有早 return，所以新段要放在 `_mark_photo3d_contract_tests(items)` 之后、`requires_solidworks` 的 `needs_sw = ...` 之前，避免被早 return 跳过）加：
```python
    needs_jury_e2e = [it for it in items if it.get_closest_marker("requires_jury_loop_e2e")]
    if needs_jury_e2e and not os.environ.get("GEMINI_API_KEY"):
        skip_jury = pytest.mark.skip(reason="requires_jury_loop_e2e：GEMINI_API_KEY 未设")
        for it in needs_jury_e2e:
            it.add_marker(skip_jury)
```
（放在 `_mark_photo3d_contract_tests(items)` 调用之后、`needs_sw = [...]` 那行之前。`requires_solidworks` 段保持原样不动。）

- [ ] **Step 3：创建 `tests/jury_loop/test_l4_smoke.py`**

按 Task 0 的确认结果填具体值（`rc` 只放 `prompt`；`reference_mode` 用 Task 0 Step 2 确认的 v1_anchor 值；sidecar 字段名用 Task 0 Step 3 确认的；jury config 位置按 Task 0 Step 4 结论放）。骨架如下：

```python
"""L4 smoke — jury→prompt 闭环端到端（CP-8 Task 8.2 / §11 follow-up B2）。

CI 默认全 skip（conftest hook：无 GEMINI_API_KEY → skip）。本地手动跑需：
  - GEMINI_API_KEY            retry backend (gemini_chat_image) 的 key
  - CAD_JURY_LLM_API_KEY      vision-LLM jury 的 api_key（写进 test 自带的临时 cad_jury_config.json）
  - CAD_JURY_LLM_BASE_URL     vision-LLM jury 的 OpenAI 兼容 base url（如 https://你的中转.com/v1）
  - （可选）CAD_JURY_LLM_MODEL vision 模型名，默认 gemini-2.5-flash
跑：  $env:GEMINI_API_KEY="..."; $env:CAD_JURY_LLM_API_KEY="..."; $env:CAD_JURY_LLM_BASE_URL="..."
      python -m pytest tests/jury_loop/test_l4_smoke.py -v
要花真钱（每 case ~$0.1-4）；DRIFT-MINOR-8（git-LFS 验证过的真低分 render fixture）仍延期，本文件用合成图。
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from enhance_budget import LoopBudget
from tools.jury.config import load_jury_config
from tools.jury_loop import cmd_enhance_hook
from tools.jury_loop.config import DEFAULT_JURY_LOOP_DICT, load_jury_loop_config
from tools.jury_loop.orchestrator import run_loop_if_eligible

_SMOKE_RUNS = 3  # 原 plan 是 10（跑 10 次取均值抑制 jury 方差）；3 已够 smoke、调高更稳更贵
_BASE_PROMPT = "photorealistic product render, studio lighting, neutral background, high detail"

pytestmark = [pytest.mark.requires_jury_loop_e2e, pytest.mark.slow]


def _make_rough_render_png(path: Path, size: tuple[int, int] = (512, 512)) -> Path:
    """合成一张「未完成的 Blender 渲染」样子的低保真 PNG（平涂背景 + 单个简单几何体）。"""
    from PIL import Image, ImageDraw

    img = Image.new("RGB", size, (200, 200, 205))  # 平涂浅灰背景
    d = ImageDraw.Draw(img)
    cx, cy = size[0] // 2, size[1] // 2
    d.rectangle([cx - 90, cy - 60, cx + 90, cy + 60], fill=(120, 120, 130))  # 平涂方块，无着色/贴图/阴影
    img.save(path, "PNG")
    return path


def _require_jury_env() -> None:
    """conftest hook 已 gate GEMINI_API_KEY；这里再 runtime 检 jury LLM 的两个 env var。"""
    if not os.environ.get("CAD_JURY_LLM_API_KEY"):
        pytest.skip("CAD_JURY_LLM_API_KEY 未设")
    if not os.environ.get("CAD_JURY_LLM_BASE_URL"):
        pytest.skip("CAD_JURY_LLM_BASE_URL 未设")


def _write_temp_jury_config(dir_: Path) -> Path:
    """写 test 自带的临时 cad_jury_config.json（绕开 conftest 的 autouse home-fake）。

    放哪 = Task 0 Step 4 结论决定：若 orchestrator 限制 config 必须在「当前项目」→ 放 project_root；
    否则放 dir_ 即可（如需 --allow-external-config 透传则 Task 0 确认 orchestrator 支持）。
    """
    cfg = {
        "schema_version": 1,
        "active_profile_id": "l4_smoke",
        "profiles": [
            {
                "id": "l4_smoke",
                "kind": "openai_compat",
                "api_base_url": os.environ["CAD_JURY_LLM_BASE_URL"],
                "api_key": os.environ["CAD_JURY_LLM_API_KEY"],
                "model": os.environ.get("CAD_JURY_LLM_MODEL", "gemini-2.5-flash"),
            }
        ],
    }
    path = dir_ / "cad_jury_config.json"
    path.write_text(json.dumps(cfg), encoding="utf-8")
    return path


def _run_one_view_loop(*, render_dir: Path, project_root: Path, view: str, baseline_png: Path, threshold: int | None = None):
    """跑一遍单视角闭环 → 返 (LoopResult, sidecar_dict)。threshold=None 用 DEFAULT(75)。"""
    cfg_path = _write_temp_jury_config(project_root)  # 或 render_dir，按 Task 0 Step 4
    jury_profile, _caps = load_jury_config(cfg_path)
    loop_dict = dict(DEFAULT_JURY_LOOP_DICT)
    if threshold is not None:
        loop_dict = {**loop_dict, "advanced": {**loop_dict["advanced"], "threshold": threshold}}
    config = load_jury_loop_config(loop_dict)
    result = run_loop_if_eligible(
        view=view,
        backend_kind=config.backend.kind,           # "gemini_chat_image"
        rc={"prompt": _BASE_PROMPT},
        baseline_path=baseline_png,
        base_params={},
        budget=LoopBudget(n_views=1),               # cap_usd 默认 1.5
        project_root=project_root,
        config=config,
        jury_profile=jury_profile,
        jury_profile_path=cfg_path,
    )
    sidecar = json.loads((render_dir / f"{view}_enhance_meta.json").read_text(encoding="utf-8"))
    return result, sidecar


def test_l4_1_score_improves(tmp_path):
    """低分合成 baseline 跑 N 次闭环 → 平均 retry 提分 > 5。"""
    _require_jury_env()
    project_root = tmp_path
    render_dir = tmp_path / "render"
    render_dir.mkdir()
    deltas: list[int] = []
    for i in range(_SMOKE_RUNS):
        baseline = _make_rough_render_png(render_dir / "V1_enhanced_baseline.jpg")  # 文件名 = Task 0 Step 3 确认
        _result, sidecar = _run_one_view_loop(render_dir=render_dir, project_root=project_root, view="V1", baseline_png=baseline)
        delta = sidecar.get("retry_score_delta")  # 字段名 = Task 0 Step 3 确认
        assert delta is not None, f"第 {i+1} 次未触发 retry（合成图意外得高分？）：sidecar loop_status={sidecar.get('loop_status')}"
        deltas.append(int(delta))
        for f in render_dir.glob("V1_*"):  # 清理供下一轮
            f.unlink()
    mean_delta = sum(deltas) / len(deltas)
    assert mean_delta > 5, f"平均 retry 提分 {mean_delta:.1f} 不 > 5（deltas={deltas}）"


def test_l4_2_no_trigger_when_score_above_threshold(tmp_path):
    """threshold 调到 1 → baseline 真实 jury score（≥1 几乎必然）≥ threshold → loop_status == 'above_threshold'（无 retry）。"""
    _require_jury_env()
    project_root = tmp_path
    render_dir = tmp_path / "render"
    render_dir.mkdir()
    baseline = _make_rough_render_png(render_dir / "V1_enhanced_baseline.jpg")
    result, sidecar = _run_one_view_loop(render_dir=render_dir, project_root=project_root, view="V1", baseline_png=baseline, threshold=1)
    assert sidecar.get("loop_status") == "above_threshold", f"期望 above_threshold，得 {sidecar.get('loop_status')}"
    assert sidecar.get("retry_score_delta") is None, f"above_threshold 不该有 retry，但 retry_score_delta={sidecar.get('retry_score_delta')}"
    assert result.loop_status == "above_threshold"


def test_l4_3_v1_anchor_hook_returns_final_path(tmp_path):
    """v1_anchor 模式：run_loop_hook_for_view 跑完 V1 应返回 V1 的 final_path（== <render_dir>/V1_enhanced.jpg），
    供 cmd_enhance 拿去当 V2 的 anchor（BL-4 状态传递契约）。

    注：**不**走 `prepare_jury_loop_state`——它内部读 ~/.claude/cad_jury_config.json，被 conftest
    的 autouse home-fake 替成空假目录、会 fail。改为直接给 run_loop_hook_for_view 传 4 个参数
    （config / budget / profile / profile_path），test 自带临时 config。
    """
    _require_jury_env()
    project_root = tmp_path
    render_dir = tmp_path / "render"
    render_dir.mkdir()
    _make_rough_render_png(render_dir / "V1_enhanced_baseline.jpg")
    cfg_path = _write_temp_jury_config(project_root)
    jury_profile, _caps = load_jury_config(cfg_path)
    jury_loop_config = load_jury_loop_config(DEFAULT_JURY_LOOP_DICT)
    loop_budget = LoopBudget(n_views=2)
    final_path = cmd_enhance_hook.run_loop_hook_for_view(
        view_key="V1",
        new_path=str(render_dir / "V1_enhanced_baseline.jpg"),
        render_dir=render_dir,
        rc={"prompt": _BASE_PROMPT},
        rerun_loop=False,
        jury_loop_config=jury_loop_config,
        loop_budget=loop_budget,
        jury_profile=jury_profile,
        jury_profile_path=cfg_path,
        reference_mode="v1_anchor",   # 取值 = Task 0 Step 2 确认
        project_root=project_root,
    )
    assert final_path == str(render_dir / "V1_enhanced.jpg"), f"v1_anchor 模式 V1 hook 应返回 V1_enhanced.jpg 路径，得 {final_path!r}"
```

**Plan 注意**：`run_loop_hook_for_view` 的真签名（参数名 `view_key`/`new_path`/`render_dir`/`rc`/`rerun_loop`/`jury_loop_config`/`loop_budget`/`jury_profile`/`jury_profile_path`/`reference_mode`/`project_root` 已从源码确认）—— 实施前 `grep -n "def run_loop_hook_for_view" tools/jury_loop/cmd_enhance_hook.py` 复核一遍。`test_l4_3` 已避开 `prepare_jury_loop_state`（被 home-fake 阻断），直接构造 4 个参数传 hook。

- [ ] **Step 4：collection + skip 验证（无 env var）**

确保当前 shell 没设 `GEMINI_API_KEY`（`echo $env:GEMINI_API_KEY` 应空）。
Run: `python -m pytest tests/jury_loop/test_l4_smoke.py -v`
Expected: **3 skipped**，每个 reason 含 `requires_jury_loop_e2e：GEMINI_API_KEY 未设`（conftest hook 命中）。collection 无 error（module-level import 全 OK——`tools.jury_loop.*` / `tools.jury.config` / `enhance_budget` / 没 import `fal_client`）。

- [ ] **Step 5：ruff + 全套件**

Run: `python -m ruff check tests/jury_loop/test_l4_smoke.py tests/conftest.py` → `All checks passed!`（注意 test 文件里 `import os` 用了；`pytestmark` 用了；helper 用了——无未用 import）。
Run: `python -m pytest tests/ -q` → **3090 PASS / 14 skipped（11 + 3 新 L4）/ 0 regression**。conftest 加 `import os` + 新 skip 段不影响其它 marker（`requires_solidworks` 等照常）。

- [ ] **Step 6：commit**

```
git -C "D:\Work\cad-spec-gen" branch --show-current   # 必须是 feat/sp1-followup-skill-desc-l4-smoke
git -C "D:\Work\cad-spec-gen" add pyproject.toml tests/conftest.py tests/jury_loop/test_l4_smoke.py
git -C "D:\Work\cad-spec-gen" -c commit.gpgsign=false commit -m "test(jury-loop): L4 smoke 三 case + requires_jury_loop_e2e marker + conftest skip hook（§11 B2，CI skip）

L4 端到端 smoke 脚手架：test_l4_1（低分合成 baseline 跑 N 次平均提分>5）/ test_l4_2
（threshold 调 1 → above_threshold 不 retry）/ test_l4_3（v1_anchor hook 返回 V1
final_path）。requires_jury_loop_e2e marker（纠原 plan requires_fal_key 误名——闭环
retry backend 是 gemini_chat_image 不是 fal）；conftest hook 无 GEMINI_API_KEY → 全 skip。
合成 fixture（DRIFT-MINOR-8 git-LFS 真低分图仍延期）。CI 永不跑（要真 key + 真花钱）。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 3：收尾验证 + code-review + push + PR

**Files:** 无改动。

- [ ] **Step 1：最终验证**

Run: `python -m pytest tests/ -q` → **3090 PASS / 14 skipped / 0 regression**。
Run: `python -m pytest tests/jury_loop/test_l4_smoke.py -v` → 3 skipped（reason 含 `requires_jury_loop_e2e`）。
Run: `python -m ruff check tests/jury_loop/test_l4_smoke.py tests/conftest.py pyproject.toml` → `All checks passed!`（pyproject 是 toml，ruff 不检；列只为完整性）。
Run: `python scripts/dev_sync.py && python scripts/dev_sync.py --check && git -C "D:\Work\cad-spec-gen" diff --exit-code -- AGENTS.md` → 通过。
Run: `git -C "D:\Work\cad-spec-gen" status --porcelain` → clean。
Run: `python -m pytest tests/ -v -m "not mypy" -q`（CI 等价命令，系统 Python）→ 全 PASS。

- [ ] **Step 2：requesting-code-review**

按 CLAUDE.md，调 `superpowers:requesting-code-review` 对本分支相对 main 的 diff 做一次 review；按 `superpowers:receiving-code-review` 处理意见（本 PR 常见意见：B1 描述措辞 / B2 的 marker 名 / L4 test 的驱动路径选择 / conftest skip hook 位置——逐条核实，不盲改）。有阻断性问题就修完再继续。

- [ ] **Step 3：push + 开 PR（需用户确认）**

向用户确认后：
```
git -C "D:\Work\cad-spec-gen" push -u origin feat/sp1-followup-skill-desc-l4-smoke
gh pr create --base main --head feat/sp1-followup-skill-desc-l4-smoke --title "chore(sp1-followup): /cad-enhance 描述提及闭环 + L4 smoke 脚手架（§11 B1+B2）" --body "..."
```
PR body 要点：
- §11 follow-up 两项：B1 = skill.json "AI Enhancement" 描述末尾追加 jury 闭环说明（dev_sync 同步；AGENTS.md 100 字截断下表格不变）；B2 = L4 smoke 3 case + `requires_jury_loop_e2e` marker（纠原 plan `requires_fal_key` 误名）+ conftest skip hook + 合成 fixture，**CI 永不跑**（要真 GEMINI_API_KEY + jury LLM key + 真花钱）。
- 零行为变更；3090 PASS / 14 skipped / 0 regression。
- **手动验证 L4**（PR body 写明）：`$env:GEMINI_API_KEY="..."; $env:CAD_JURY_LLM_API_KEY="..."; $env:CAD_JURY_LLM_BASE_URL="..."; python -m pytest tests/jury_loop/test_l4_smoke.py -v`（要花钱）。
- 范围外：B3（N-16 命名统一）/ B4（N-15 跳过扩展）留后续；DRIFT-MINOR-8（git-LFS 真低分 fixture）仍延期。
- **注意 origin/main 比本地 main 落后**（本地 main 含未 push 的 ruff/mypy cleanup 10 commits）——开 PR 前看一眼 `git log origin/main..HEAD` 是不是包含了 cleanup 那批 + 本 PR 两批；若用户想先单独 push cleanup 那批再开本 PR，按用户意思来。
- 链接 spec：`docs/superpowers/specs/2026-05-12-sp1-followup-skill-desc-l4-smoke-design.md`
- 结尾：`🤖 Generated with [Claude Code](https://claude.com/claude-code)`

- [ ] **Step 4：盯 CI（PowerShell 用 `gh pr checks <PR#> --watch`，别用 bash `comm`/`watch` —— `feedback_monitor_windows_gnu_tools.md`）**

Expected: 8 checks 全 SUCCESS。L4 三 case 在 CI 上 skipped（无 GEMINI_API_KEY）。有红的 → 看日志、`superpowers:systematic-debugging` 修、push 修复 commit、再 watch。

---

## 自审（writing-plans skill 要求）

**1. Spec 覆盖**：spec §3 B1 → Task 1；spec §4.1 marker → Task 2 Step 1；§4.2 conftest hook → Task 2 Step 2；§4.3 绕 home-fake（自带临时 config）→ Task 2 Step 3 的 `_write_temp_jury_config`；§4.4 3 case → Task 2 Step 3 的三个 test 函数；§4.5 合成 fixture → `_make_rough_render_png`；§5 验证清单 → Task 1 Step 4 + Task 2 Step 4/5 + Task 3 Step 1；§8 调查 6 项 → Task 0 Step 1-6。无遗漏。

**2. Placeholder 扫描**：Task 0 的「确认」步不是 TBD——是「跑这个 grep，对照预期，不符就停」。Task 2 Step 3 的 test 代码块完整给出，里面标注「= Task 0 Step N 确认」的几处（`rc` prompt key 已确认 / `reference_mode` 值 / sidecar 字段名 / config 文件位置）是「从 Task 0 的实测结论填具体值」——不是空洞占位（每处都给了 plan 假设值 + 怎么确认）。`test_l4_3` 给了主路径 + 备选路径（直构 JuryLoopConfig）。无 "TODO/类似上文"。

**3. 类型/命名一致**：`requires_jury_loop_e2e` 全程同名（Task 2 Step 1/2/4，Task 3，commit msg，PR body）；`_make_rough_render_png` / `_run_one_view_loop` / `_write_temp_jury_config` / `_require_jury_env` 在 test 文件内引用一致；`GEMINI_API_KEY`（retry backend）/ `CAD_JURY_LLM_API_KEY` / `CAD_JURY_LLM_BASE_URL`（jury profile）三 env var 名全程一致；`run_loop_if_eligible` / `run_loop_hook_for_view` / `prepare_jury_loop_state` 参数名与 brainstorm 阶段 grep 确认的一致；分支名 `feat/sp1-followup-skill-desc-l4-smoke` 全程一致。

**4. 已知留给执行期判断的点**（Task 0 驱动，非 placeholder）：jury config 文件放哪（`project_root` vs `render_dir`，看 orchestrator 对 config 路径的限制——Task 0 Step 4，**这是最大不确定点**——若 orchestrator 不透传 config 路径或限制无法绕，B2 可能要降级成 mock jury 子进程，与用户确认）；`reference_mode` v1_anchor 的精确字符串值（Task 0 Step 2）；sidecar 里 baseline 分数 / `retry_score_delta` / `loop_status` 的精确字段路径（Task 0 Step 3）。`test_l4_3` 已定为直构 `JuryLoopConfig`/`LoopBudget`（不走 `prepare_jury_loop_state`——它读 ~/.claude，被 home-fake 阻断）。
