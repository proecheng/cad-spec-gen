# v2.37.7 §11-N3 + §11-N2 photo3d-jury CLI 改进 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 闭合 v2.37.x §11 follow-up 2 项 photo3d-jury CLI UX 改进：§11-N3 per-view 进度 stderr 输出（success+failure+crash 三态全覆盖）+ §11-N2 `--override-subsystem` alias flag（cli vs effective subsystem 分层 + 输入校验）。

**Architecture:** 小 patch PR：~50 行 production + 40 行测试 + 5 行 docs + 60 行 retro。TDD RED→GREEN 严格走（spec §11-N5 v2.37.6 实证 1 行 production 也走 TDD）。4 commit 拆分（feat per-view 进度 / feat --override-subsystem / docs / retro）。

**Tech Stack:** Python sys.stderr.write + argparse + pytest capsys + git tag-based release。

**Spec：** `docs/superpowers/specs/2026-05-15-v2-37-7-jury-cli-improvements-design.md`（298 行 / brainstorming F1+F2+F3+F4 + layer 6 E2+E3+E4+E5+E6+E8+E9 fix）

**分支：** `feat/v2-37-7-jury-cli-improvements`（已建 / HEAD `37fe4be`）

---

## File Structure

| 文件 | 用途 | 改动范围 |
|---|---|---|
| `tools/photo3d_jury.py` per-view 循环 (~line 620 try-success + ~line 644 except JuryLlmError + 新 except Exception) | 加 3 路径 stderr 进度行 | **+15 行 production** |
| `tools/photo3d_jury.py:_build_parser` (~line 111) | 加 `--override-subsystem` flag 解析 | +3 行 production |
| `tools/photo3d_jury.py:main()` | E3 输入校验 + 计算 effective_subsystem + 更新 path/report 使用 | +20 行 production |
| `tests/jury/test_photo3d_jury_*.py`（邻接 test_photo3d_jury_matches_spec.py 或新建）| 5 TDD 测试覆盖 success+failure+crash+override+input_validation | +60 行测试 |
| `docs/cad-jury-config.md` 附录 A cli flag 表 | 加 `--override-subsystem` 行 | +2 行 |
| `docs/superpowers/reports/2026-05-15-v2-37-7-jury-cli-improvements-retro.md`（新写）| retro | ~70 行 |

**总 diff** ≈ **~170 行**（含 retro）；有 production code 改 → 必发 v2.37.7 patch tag。

---

## Task 0: Scout + baseline

**Files:** Read only.

- [ ] **Step 1: 切到分支 + fetch + dev_sync**

```bash
cd D:/Work/cad-spec-gen
git fetch origin main
git checkout feat/v2-37-7-jury-cli-improvements
git log --oneline HEAD..origin/main
python scripts/dev_sync.py --check
echo "rc=$?"
```

Expected: HEAD..origin/main 空 / dev_sync rc=0。报告。

- [ ] **Step 2: baseline 测试**

```bash
pytest -q tests/jury/ tests/jury_loop/ 2>&1 | tail -3
pytest -q tests/test_agents_md.py tests/test_no_tracked_mirror.py 2>&1 | tail -3
ls tests/jury/test_photo3d_jury_*.py
```

Expected: jury 子集 504 PASS（v2.37.6 后）/ 元测试 5。**报告 + photo3d_jury 既有测试文件清单**（新测试加哪个文件参考）。

- [ ] **Step 3: 实测 per-view 循环结构（try-success + except JuryLlmError + 加 except Exception 位置）**

```bash
sed -n '595,665p' D:/Work/cad-spec-gen/tools/photo3d_jury.py
```

Expected: 看到 try → request_jury_verdict → parse_view_verdict → view_verdicts.append → except JuryLlmError → view_verdicts.append。**报告 try/except 实际行号 + view_verdicts.append 两处具体位置**（spec D1 snapshot line ~620/~644 验证）。

- [ ] **Step 4: 实测 _build_parser flag 顺序**

```bash
sed -n '105,135p' D:/Work/cad-spec-gen/tools/photo3d_jury.py
```

Expected: 看到 --subsystem (line 111) + 既有 flag 列表。**报告 --override-subsystem 插入位置**（紧邻 --subsystem 后；或末尾按 v2.37 series flag 风格）。

- [ ] **Step 5: 实测 args.subsystem 使用 11+ 处**

```bash
grep -n "args\.subsystem" D:/Work/cad-spec-gen/tools/photo3d_jury.py
```

Expected: 11+ 行命中（spec §3.2 D2 字段表声明各取谁）。**报告每行用途分类**：
- report 写（保留 args.subsystem）：line 687/745
- path 解析（改 effective_subsystem）：line 385/391/519/651
- Layer 0/cache 调用（改 effective_subsystem）：line 279/402/510

- [ ] **Step 6: 实测既有 `except Exception` 风格沿用**

```bash
grep -n "except Exception.*noqa" D:/Work/cad-spec-gen/tools/photo3d_jury.py
```

Expected: line 316/407/778 既有 `except Exception as exc: # noqa: BLE001` 模式。Task 1 加 except Exception 沿用此 noqa 注释。

- [ ] **Step 7: 实测 test_photo3d_jury_*.py fixture 风格**

```bash
ls D:/Work/cad-spec-gen/tests/jury/test_photo3d_jury_*.py
grep -n "^def test_\|enable_llm_for_test\|capsys\|capfd" D:/Work/cad-spec-gen/tests/jury/test_photo3d_jury_matches_spec.py 2>&1 | head -10
```

Expected: 既有测试用 `enable_llm_for_test` fixture + pytest 标准 capsys/capfd。**报告**新测试沿用风格。

- [ ] **Step 8: 汇总**

无 commit；report 汇总 7 步关键数据：行号、既有风格、新测试文件选择、effective_subsystem 用法分布。

---

## Task 1: §11-N3 TDD — per-view 进度 (success + failure + crash)

**Files:** Modify: `tools/photo3d_jury.py` per-view 循环；`tests/jury/test_photo3d_jury_*.py`（建议放 `test_photo3d_jury_matches_spec.py` 邻接或新建 `test_photo3d_jury_per_view_progress.py`）

**TDD 阶段**：RED → GREEN（3 路径 stderr 输出 + 3 测试）

- [ ] **Step 1: 写 3 个 RED 测试**

新建 `tests/jury/test_photo3d_jury_per_view_progress.py`（或追加既有 test_photo3d_jury_matches_spec.py）：

```python
"""§11-N3 per-view 进度 stderr 测试 (v2.37.7)。"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


def _setup_jury_env(tmp_path: Path) -> dict[str, Path]:
    """模拟 GISBOT-like 最小 layout: cad/<sub>/.cad-spec-gen/runs/<id>/ + 1 enhanced jpg + ENHANCEMENT_REPORT.json + render_manifest.json + jury config。
    
    返回 dict 含 project_root / config_path / run_dir 路径供测试用。
    """
    # 实施时按 GISBOT _setup_jury.py 镜像逻辑创建最小 layout
    # 占位实现：implementer 按 jury Layer 0 要求构造 minimal valid state
    raise NotImplementedError("Task 1 Step 1 实施时按 jury Layer 0 schema 写")


def test_per_view_progress_stderr_emit_success(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """v2.37.7 §11-N3 (F1 fix try-success path)：success 视角后 stderr 含 △ [V<n>/<total>] <model> photoreal=<score> verdict=<verdict> <latency>s。"""
    from tools import photo3d_jury

    env = _setup_jury_env(tmp_path)
    with patch("tools.jury.llm_client.urlopen") as m:
        # mock 200 success response
        resp = MagicMock()
        resp.status = 200
        resp.read.return_value = json.dumps({
            "id": "test-1",
            "choices": [{
                "message": {"content": json.dumps({
                    "semantic_checks": {
                        "geometry_preserved": True, "material_consistent": True,
                        "photorealistic": True, "no_extra_parts": True, "no_missing_parts": True,
                    },
                    "photoreal_score": 75, "reason": "ok",
                })},
                "finish_reason": "stop",
            }],
        }).encode("utf-8")
        resp.headers = {"Content-Type": "application/json"}
        cm = MagicMock()
        cm.__enter__.return_value = resp
        cm.__exit__.return_value = None
        m.return_value = cm

        photo3d_jury.main([
            "--subsystem", "end_effector",
            "--project-root", str(env["project_root"]),
            "--config", str(env["config_path"]),
        ])

    captured = capsys.readouterr()
    assert "△ [V1/" in captured.err
    assert "photoreal=75" in captured.err
    assert "verdict=" in captured.err


def test_per_view_progress_stderr_emit_failure(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """v2.37.7 §11-N3 (F1 fix except JuryLlmError path)：LLM 失败 stderr 含 ERROR <error_kind>。"""
    from tools import photo3d_jury
    from tools.jury.llm_client import JuryLlmError

    env = _setup_jury_env(tmp_path)
    with patch("tools.jury.llm_client.urlopen") as m:
        m.side_effect = JuryLlmError("auth_failed", 401, "")
        photo3d_jury.main([
            "--subsystem", "end_effector",
            "--project-root", str(env["project_root"]),
            "--config", str(env["config_path"]),
        ])

    captured = capsys.readouterr()
    assert "△ [V1/" in captured.err
    assert "ERROR auth_failed" in captured.err


def test_per_view_progress_stderr_emit_crash(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """v2.37.7 §11-N3 (E2 fix except Exception path)：non-JuryLlmError 异常 stderr 含 CRASH <exc_type> + re-raise（不吞）。"""
    from tools import photo3d_jury

    env = _setup_jury_env(tmp_path)
    with patch("tools.jury.llm_client.urlopen") as m:
        m.side_effect = OSError("network down")
        # E2 fix：OSError 通用兜底进度 + re-raise → main() 应捕获或 propagate
        with pytest.raises((OSError, SystemExit)):
            photo3d_jury.main([
                "--subsystem", "end_effector",
                "--project-root", str(env["project_root"]),
                "--config", str(env["config_path"]),
            ])

    captured = capsys.readouterr()
    assert "△ [V1/" in captured.err
    assert "CRASH OSError" in captured.err
```

注意：`_setup_jury_env` helper 实施时 implementer 按 jury Layer 0 schema 构造最小 valid state（参考 GISBOT `_setup_jury.py` 模板：mkdir + ENHANCEMENT_REPORT.json + render_manifest.json + ARTIFACT_INDEX.json + jury_config.json）。Step 1 占位 `NotImplementedError` 让 implementer 写完 helper 后 3 测试可跑。

- [ ] **Step 2: 跑 RED 验证 3 测试 FAIL（含 helper NotImplementedError）**

```bash
pytest tests/jury/test_photo3d_jury_per_view_progress.py -v 2>&1 | tail -15
```

Expected: 3 个 FAILED（含 NotImplementedError 或 missing stderr 内容）。

- [ ] **Step 3: 实现 _setup_jury_env helper（如 Step 1 还没实现）**

参考 GISBOT `D:/Work/cad-tests/GISBOT/_setup_jury.py` mirror 逻辑构造最小 jury Layer 0 state。注意：jury Layer 0 期望 `cad/<subsystem>/.cad-spec-gen/runs/<active_run_id>/{ENHANCEMENT_REPORT.json, render_manifest.json}` + ARTIFACT_INDEX.json + jury_config 含至少 1 vision profile。

具体实施 (放进 `_setup_jury_env`)：
```python
import shutil
SUB = "end_effector"
RUN_ID = "test-run-20260515"

cad_dir = tmp_path / "cad" / SUB / ".cad-spec-gen"
run_dir = cad_dir / "runs" / RUN_ID
renders_dir = tmp_path / "cad" / "output" / "renders"
run_dir.mkdir(parents=True, exist_ok=True)
renders_dir.mkdir(parents=True, exist_ok=True)

# 1 测试 JPG 写最小 PNG-bytes（jury 不解析图像内容，只 b64 编码上传 mock URL）
(renders_dir / "V1_test_enhanced.jpg").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)

# render_manifest.json（jury enhancement_semantic_review 校验需）
(renders_dir / "render_manifest.json").write_text(json.dumps({
    "schema_version": 2,
    "subsystem": SUB,
    "run_id": RUN_ID,
    "render_dir_rel_project": "cad/output/renders",
    "files": [{"view": "V1", "path_rel_project": "cad/output/renders/V1_test_enhanced.jpg"}],
}), encoding="utf-8")

# ENHANCEMENT_REPORT.json
(renders_dir / "ENHANCEMENT_REPORT.json").write_text(json.dumps({
    "schema_version": 1,
    "subsystem": SUB,
    "run_id": RUN_ID,
    "render_dir": "cad/output/renders",
    "render_manifest": "cad/output/renders/render_manifest.json",
    "view_count": 1,
    "views": [{
        "view": "V1",
        "source_image": "cad/output/renders/V1_test_enhanced.jpg",
        "enhanced_image": "cad/output/renders/V1_test_enhanced.jpg",
    }],
}), encoding="utf-8")

# ARTIFACT_INDEX.json
cad_dir.joinpath("ARTIFACT_INDEX.json").write_text(json.dumps({
    "schema_version": 1, "subsystem": SUB, "active_run_id": RUN_ID,
    "accepted_baseline_run_id": None,
    "runs": {RUN_ID: {"run_id": RUN_ID, "active": True, "artifacts": {
        "enhancement_report": "cad/output/renders/ENHANCEMENT_REPORT.json",
        "render_manifest": "cad/output/renders/render_manifest.json",
    }}},
}), encoding="utf-8")

# jury config（最小 vision profile）
config_path = tmp_path / "cad_jury_config.json"
config_path.write_text(json.dumps({
    "schema_version": 1,
    "active_profile_id": "test",
    "profiles": [{
        "id": "test", "kind": "openai_compat",
        "api_base_url": "https://api.example.com/v1",
        "api_key": "test-key", "model": "gpt-4o",
        "cost_per_call_usd": 0.001,
    }],
}), encoding="utf-8")

return {"project_root": tmp_path, "config_path": config_path, "run_dir": run_dir}
```

替换 Step 1 中 `raise NotImplementedError(...)` 为上述实现。

- [ ] **Step 4: 跑 3 测试 RED（helper 修后）**

```bash
pytest tests/jury/test_photo3d_jury_per_view_progress.py -v 2>&1 | tail -15
```

Expected: 3 FAILED（实际是 stderr 不含 △ 进度，因 production 还未加 stderr write）。

- [ ] **Step 5: 改 production — 加 try-success 进度行**

读 `tools/photo3d_jury.py:595-625` 找到 view_verdicts.append({...}) 第 1 处（try-success 后）。用 Edit 工具在 append 之后插入 stderr write。

`old_string`（找 try success append 的末 `}` 后），new_string 加：

```python
                    view_verdicts.append({...原内容...})
                    latency_s = round(resp.latency_ms / 1000, 1)
                    sys.stderr.write(
                        f"△ [{view_name}/{total_views}] {profile.model} "
                        f"photoreal={vv.photoreal_score} verdict={vv.verdict} {latency_s}s\n"
                    )
```

注：`total_views` 从 enhancement_report 取（既有 main() 已 load）；查具体 var 名。

- [ ] **Step 6: 改 production — 加 except JuryLlmError 失败进度行**

读 `tools/photo3d_jury.py:621-644` except JuryLlmError 块。在 view_verdicts.append 之后加：

```python
                    except JuryLlmError as exc:
                        # ... 既有 actual_cost += / view_verdicts.append({...needs_review...}) 不动 ...
                        sys.stderr.write(
                            f"△ [{view_name}/{total_views}] {profile.model} "
                            f"ERROR {exc.error_kind} 0.0s\n"
                        )
```

- [ ] **Step 7: 改 production — 加 except Exception 通用兜底（E2 fix）**

在 `except JuryLlmError as exc:` 块之后 加 `except Exception as exc:` 块：

```python
                    except JuryLlmError as exc:
                        # ... 既有 ...
                        sys.stderr.write(f"△ [{view_name}/{total_views}] {profile.model} ERROR {exc.error_kind} 0.0s\n")
                    except Exception as exc:  # noqa: BLE001 — v2.37.7 §11-N3 E2 fix：non-JuryLlmError 兜底 + re-raise
                        sys.stderr.write(
                            f"△ [{view_name}/{total_views}] {profile.model} "
                            f"CRASH {type(exc).__name__}\n"
                        )
                        raise  # 不吞异常，propagate 给 main 处理
```

- [ ] **Step 8: dev_sync + 跑 3 测试 GREEN**

```bash
cd D:/Work/cad-spec-gen
python scripts/dev_sync.py
python scripts/dev_sync.py --check
pytest tests/jury/test_photo3d_jury_per_view_progress.py -v 2>&1 | tail -15
```

Expected: dev_sync rc=0 + 3 测试全 PASS。

- [ ] **Step 9: 跑 jury 子集回归**

```bash
pytest -q tests/jury/ tests/jury_loop/ 2>&1 | tail -3
```

Expected: 504 + 3 = **507 PASS** / 0 regression。

- [ ] **Step 10: REFACTOR 步 + AC-4 grep 验证**

```bash
grep -cE "△ \[V" tools/photo3d_jury.py
```

Expected: ≥ 3（success / failure / crash 三处进度模板）。spec AC-4 floor 是 ≥ 2，实际 ≥ 3 更稳。

审视改动：进度行格式一致 / 沿用 `△` 既有风格 / except Exception 用 noqa 注释。Commit message 加 `REFACTOR: 3 处进度行格式统一，无可进一步抽取`。

- [ ] **Step 11: Commit (TDD RED+GREEN 一起)**

```bash
cd D:/Work/cad-spec-gen
git add tools/photo3d_jury.py tests/jury/test_photo3d_jury_per_view_progress.py
git -c commit.gpgsign=false commit -m "$(cat <<'EOF'
feat(jury): per-view 进度输出 stderr 三态全覆盖（§11-N3）

v2.37.x §11-N3 闭合：GISBOT e2e 实测 "jury 跑时 stderr 0 bytes 用户不知是否挂"
问题；本 commit 加 per-view 进度 stderr 输出。

设计决策（spec §3.1 D1 + layer 6 F1 + E2 fix）：
- try-success 路径：△ [V<n>/<total>] <model> photoreal=<score> verdict=<verdict> <latency>s
- except JuryLlmError 路径：△ [V<n>/<total>] <model> ERROR <error_kind> 0.0s
- except Exception 路径 (E2 fix non-JuryLlmError 兜底 + re-raise)：
  △ [V<n>/<total>] <model> CRASH <exc_type>
- 沿用既有 △/✗/✓ stderr 字符风格 (line 763 既有 △ 实证)

TDD RED → GREEN：
- 3 测试 (test_per_view_progress_stderr_emit_success/failure/crash)
- 测试 fixture _setup_jury_env 模拟 GISBOT-like 最小 layout

回归：jury 子集 504 → 507 PASS / 0 regression。

REFACTOR: 3 处进度行格式统一，无可进一步抽取。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: §11-N2 TDD — `--override-subsystem` flag + effective_subsystem + 输入校验

**Files:** Modify: `tools/photo3d_jury.py` _build_parser + main()；`tests/jury/test_photo3d_jury_per_view_progress.py`（追加 2 测试）

**TDD 阶段**：RED → GREEN

- [ ] **Step 1: 写 2 个 RED 测试**

追加到 `tests/jury/test_photo3d_jury_per_view_progress.py`：

```python
def test_override_subsystem_flag_used(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """v2.37.7 §11-N2：--override-subsystem ACTUAL → jury Layer 0 用 ACTUAL 解析 run_dir + report 含 effective_subsystem 字段；--subsystem 项目名保留为 report["subsystem"]。"""
    from tools import photo3d_jury

    env = _setup_jury_env(tmp_path)
    with patch("tools.jury.llm_client.urlopen") as m:
        resp = MagicMock()
        resp.status = 200
        resp.read.return_value = json.dumps({
            "id": "test", "choices": [{
                "message": {"content": json.dumps({
                    "semantic_checks": {
                        "geometry_preserved": True, "material_consistent": True,
                        "photorealistic": True, "no_extra_parts": True, "no_missing_parts": True,
                    },
                    "photoreal_score": 75, "reason": "ok",
                })}, "finish_reason": "stop",
            }],
        }).encode("utf-8")
        resp.headers = {"Content-Type": "application/json"}
        cm = MagicMock()
        cm.__enter__.return_value = resp
        cm.__exit__.return_value = None
        m.return_value = cm

        # cli --subsystem 项目名 GISBOT，override 到实际 end_effector
        photo3d_jury.main([
            "--subsystem", "GISBOT",
            "--override-subsystem", "end_effector",
            "--project-root", str(env["project_root"]),
            "--config", str(env["config_path"]),
        ])

    # report 写到 effective_subsystem path 下
    report_path = env["run_dir"] / "PHOTO3D_JURY_REPORT.json"
    assert report_path.is_file(), "report 应写到 effective_subsystem 解析的 run_dir"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["subsystem"] == "GISBOT", "report.subsystem 保 cli args.subsystem 不变"
    assert report["effective_subsystem"] == "end_effector", "report.effective_subsystem 仅 override 时存在"


def test_override_subsystem_input_validation(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """v2.37.7 §11-N2 (E3 fix)：--override-subsystem 输入校验：空字符串 / 路径遍历 → exit=2；合法值通过 + strip 空格。"""
    from tools import photo3d_jury

    env = _setup_jury_env(tmp_path)

    # 1. 空字符串 → exit=2
    rc = photo3d_jury.main([
        "--subsystem", "GISBOT",
        "--override-subsystem", "",
        "--project-root", str(env["project_root"]),
        "--config", str(env["config_path"]),
    ])
    assert rc == 2
    captured = capsys.readouterr()
    assert "✗ --override-subsystem 不能为空" in captured.err

    # 2. 路径遍历 → exit=2
    rc = photo3d_jury.main([
        "--subsystem", "GISBOT",
        "--override-subsystem", "../etc/passwd",
        "--project-root", str(env["project_root"]),
        "--config", str(env["config_path"]),
    ])
    assert rc == 2
    captured = capsys.readouterr()
    assert "含非法字符" in captured.err

    # 3. 合法值 + 末尾空格 → strip 通过 (实际 effective subsystem = "end_effector")
    # 此处不真跑 jury（不构造 mock），只验证 argparse 接受 + strip
    parser = photo3d_jury._build_parser()
    args = parser.parse_args([
        "--subsystem", "GISBOT", "--override-subsystem", "end_effector  ",
    ])
    assert args.override_subsystem == "end_effector  "  # argparse 不 strip；main 内 strip
```

- [ ] **Step 2: 跑 RED 验证 2 测试 FAIL**

```bash
pytest tests/jury/test_photo3d_jury_per_view_progress.py::test_override_subsystem_flag_used tests/jury/test_photo3d_jury_per_view_progress.py::test_override_subsystem_input_validation -v 2>&1 | tail -10
```

Expected: FAILED（argparse 不识别 --override-subsystem flag）。

- [ ] **Step 3: 改 production — argparse 加 flag**

读 `tools/photo3d_jury.py:111` `--subsystem` 行附近。在 `--subsystem` 之后插入：

```python
    p.add_argument("--subsystem")
    p.add_argument(
        "--override-subsystem",
        dest="override_subsystem",
        default=None,
        help="alias flag: cli --subsystem 项目名 + --override-subsystem 实际 subsystem；"
             "jury Layer 0 用 override 值解析 run_dir + report 加 effective_subsystem 字段；"
             "默认不指定时 effective = --subsystem（零行为变化）",
    )
```

- [ ] **Step 4: 改 production — main() 加输入校验 + effective_subsystem 计算**

读 `tools/photo3d_jury.py:464-510` 区域（args.subsystem 校验之后、Layer 0 之前）。插入：

```python
    # E3 fix：--override-subsystem 输入校验
    effective_subsystem = args.subsystem
    if args.override_subsystem is not None:
        override = args.override_subsystem.strip()
        if not override:
            sys.stderr.write("✗ --override-subsystem 不能为空字符串\n")
            return 2
        if "/" in override or "\\" in override or ".." in override:
            sys.stderr.write(
                f"✗ --override-subsystem={args.override_subsystem!r} 含非法字符 (/ \\ ..)\n"
            )
            return 2
        args.override_subsystem = override  # strip 写回
        effective_subsystem = override
```

- [ ] **Step 5: 改 production — 全文 path 解析改用 effective_subsystem**

Task 0 Step 5 实测的 `args.subsystem` 11+ 处用法。**注意只改 path 解析处**（spec §3.2 D2 字段表 row 3 "jury Layer 0 / run_dir 解析"+ row 4 "ARTIFACT_INDEX 字段"用 effective）；report 字段（line 687/745）保留 `args.subsystem` 不动（spec D2 row 1 forward-compat）。

具体改 path/cache 处：
- line 279: `_load_cached_features_for_subsystem(args.subsystem, ...)` → `_load_cached_features_for_subsystem(effective_subsystem, ...)`
- line 385: `project_root / "cad" / args.subsystem / "CAD_SPEC.md"` → `effective_subsystem`
- line 391: `project_root / "cad" / args.subsystem / ".cad-spec-gen"` → `effective_subsystem`
- line 402: `subsystem=args.subsystem` (Layer 0 调用) → `subsystem=effective_subsystem`
- line 510: `subsystem=args.subsystem` (Layer 1 调用) → `subsystem=effective_subsystem`
- line 519: `project_root / ... / args.subsystem / ...` (run_dir) → `effective_subsystem`
- line 651: `project_root / ... / args.subsystem / ...` (write report path) → `effective_subsystem`

**不改**（保 args.subsystem）：
- line 687: `"subsystem": args.subsystem` （report 顶层字段语义不变，F2 fix）
- line 745: `"subsystem": args.subsystem` （同上）

- [ ] **Step 6: 改 production — report 加 effective_subsystem 字段（仅 override 时）**

读 line 687/745 report dict 构造处。在 `"subsystem": args.subsystem,` 之后加：

```python
        report = {
            "subsystem": args.subsystem,
            # ... 既有字段 ...
        }
        if args.override_subsystem:
            report["effective_subsystem"] = effective_subsystem  # v2.37.7 §11-N2
```

两处都加（line 687 + line 745 报告写盘前）。

- [ ] **Step 7: dev_sync + 跑 2 测试 GREEN**

```bash
cd D:/Work/cad-spec-gen
python scripts/dev_sync.py
python scripts/dev_sync.py --check
pytest tests/jury/test_photo3d_jury_per_view_progress.py -v 2>&1 | tail -10
```

Expected: dev_sync rc=0 + 5 测试全 PASS（Task 1 的 3 + Task 2 的 2）。

- [ ] **Step 8: 全 jury 子集 + 既有测试回归**

```bash
pytest -q tests/jury/ tests/jury_loop/ 2>&1 | tail -3
```

Expected: 504 + 5 = **509 PASS** / 0 regression。

- [ ] **Step 9: AC grep strict**

```bash
grep -cE "△ \[V" tools/photo3d_jury.py
grep -c "override-subsystem" tools/photo3d_jury.py
grep -c "effective_subsystem" tools/photo3d_jury.py
```

Expected: △ 进度 ≥ 3 / override-subsystem ≥ 2 / effective_subsystem ≥ 3。

- [ ] **Step 10: REFACTOR 步**

审视：
- effective_subsystem 计算集中在 main() 入口一处 ✓
- args.subsystem 用法分两类清晰（report 字段 vs path 解析）✓
- Commit message 加 `REFACTOR: effective_subsystem 集中计算 + args.subsystem 用法二分清晰`

- [ ] **Step 11: Commit**

```bash
cd D:/Work/cad-spec-gen
git add tools/photo3d_jury.py tests/jury/test_photo3d_jury_per_view_progress.py
git -c commit.gpgsign=false commit -m "$(cat <<'EOF'
feat(jury): --override-subsystem alias flag + effective_subsystem 字段（§11-N2）

v2.37.x §11-N2 闭合：GISBOT e2e 实测跨项目跑 jury 时 --subsystem 必须匹配
report 内嵌 subsystem 的限制；本 commit 加 --override-subsystem alias flag。

设计决策（spec §3.2 D2 + layer 6 E3+E4+E5+E6 fix）：
- args.subsystem = cli 项目名（report 顶层 subsystem 字段保留语义不变 forward-compat）
- args.override_subsystem = effective subsystem（jury Layer 0 / run_dir / ARTIFACT_INDEX 用此值）
- effective_subsystem = args.override_subsystem or args.subsystem（默认零行为变化）
- report 加 effective_subsystem 字段仅 override 时存在
- E3 输入校验：空字符串 / 路径遍历 → exit=2 早返回
- 字段一致性（D2 字段表）：report subsystem = cli / run_dir + ARTIFACT_INDEX = effective

TDD RED → GREEN：
- 2 测试 (test_override_subsystem_flag_used + test_override_subsystem_input_validation)
- input_validation 3 子断言（空 / 路径遍历 / strip 通过）

回归：jury 子集 507 → 509 PASS / 0 regression。

REFACTOR: effective_subsystem 集中计算 + args.subsystem 用法二分清晰。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: cad-jury-config.md 附录 A 加 `--override-subsystem` 行

**Files:** Modify: `docs/cad-jury-config.md` 附录 A cli flag 表

- [ ] **Step 1: 找附录 A 表插入位置**

```bash
grep -nE "^\| .*--subsystem\b" D:/Work/cad-spec-gen/docs/cad-jury-config.md
```

Expected: 看到 `| --subsystem <name>` 行。新 `--override-subsystem` 紧邻插入。

- [ ] **Step 2: 用 Edit 插入新行**

`old_string` = `| \`--subsystem <name>\` | 必填（除 \`--list-profiles\` / \`--last-status\`） | 与 photo3d-* 一致 |`

（精确字符串以实测行内容为准）

`new_string` = `| \`--subsystem <name>\` | 必填（除 \`--list-profiles\` / \`--last-status\`） | 与 photo3d-* 一致 |
| \`--override-subsystem <name>\` | 可选 | alias flag (v2.37.7 §11-N2)：cli \`--subsystem\` 项目名 + override 实际 subsystem；jury Layer 0 用 override 解析 run_dir + report 加 \`effective_subsystem\` 字段；GISBOT-like 跨项目跑 jury 用例 |`

- [ ] **Step 3: 验证 + commit**

```bash
cd D:/Work/cad-spec-gen
grep -c "override-subsystem" docs/cad-jury-config.md
# Expected: ≥ 1
git add docs/cad-jury-config.md
git -c commit.gpgsign=false commit -m "docs(jury-config): 附录 A 加 --override-subsystem flag 描述（§11-N2）

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: retro 文档新写

**Files:** Create: `docs/superpowers/reports/2026-05-15-v2-37-7-jury-cli-improvements-retro.md`

- [ ] **Step 1: 写 retro**

新建 retro（utf-8，复用 v2.37.6 retro 风格）含：完工范围 / 数字 / 审查矩阵 / 6+ lessons / §11+§12 表 / 下次优化。

retro 模板：

```markdown
# Retro — v2.37.7 §11-N3 + §11-N2 photo3d-jury CLI 改进

**完工日期：** 2026-05-15
**Spec：** `docs/superpowers/specs/2026-05-15-v2-37-7-jury-cli-improvements-design.md`（298 行）
**Plan：** `docs/superpowers/plans/2026-05-15-v2-37-7-jury-cli-improvements.md`
**Baseline：** cad-spec-gen main@`184a7e1`（v2.37.6 merge）

## 一句话

闭合 §11-N3（jury 真跑 per-view stderr 进度 success+failure+crash 三态全覆盖）+ §11-N2（`--override-subsystem` alias flag + effective_subsystem 字段 + 输入校验）。

## 完工范围

- §11-N3 closed：tools/photo3d_jury.py per-view 循环 try-success + except JuryLlmError + except Exception 三处 stderr 进度行 + 3 TDD 测试
- §11-N2 closed：tools/photo3d_jury.py argparse 加 --override-subsystem + main() 计算 effective_subsystem + 输入校验 + report 加字段 + 2 TDD 测试
- docs/cad-jury-config.md 附录 A 加 flag 行

## 数字（实测）

- jury 子集 PASS：504 → 509（+5 新测试）
- 全套件 PASS：3194 → 3199 / 0 regression
- diff stat：~50 行 production + 60 行测试 + 2 行 docs + ~70 行 retro
- 4 commits（feat per-view / feat --override-subsystem / docs / retro）
- CI 8/8 SUCCESS（待 PR 后实测）

## 关键发现 — Layer 6 5 fix

| ID | 严重 | 修了什么 |
|---|---|---|
| F1 | 中-高 | spec D1 只 try-success 路径加进度；try-success + except-failure 双路径都加 |
| E2 | 中 | 加 except Exception 兜底 + re-raise（覆盖第三态"中途崩"）|
| E3 | 中 | --override-subsystem 输入校验（空 / 路径遍历 / strip）|
| E4+E5+E6 合 | 中 | 字段一致性表明示 cli_subsystem vs effective_subsystem 各组件取谁 |
| E8 + E9 | 低 | "ASCII △" 改 Unicode U+25B3 + grep 精度 △ [V |

## 沉淀 lessons

1. **try-success + except-failure 双覆盖**（F1 fix）— spec 写"插在 ... 之后"必明示两路径都加；漏 except 致用户看 6 行 success 误判"全跑了"，改完反更差
2. **except Exception 兜底 + re-raise**（E2 fix）— catch JuryLlmError 后必加 except Exception fallback；不吞异常 propagate；防"中途崩"第三态静默
3. **输入校验 CLI flag 不只 argparse 校 type**（E3 fix）— 空字符串 / 路径遍历 / 字符集白名单 必在 main() 早返回 exit=2
4. **字段一致性表是 schema 改动 spec 必备**（E4+E5+E6 fix）— "组件 × 字段 × 取值"对照表让 downstream consumer 一表看完
5. **Unicode vs ASCII 措辞精度**（E8 fix）— △ 是 U+25B3 Unicode 不是 ASCII；spec 措辞错可能让实施者错改字符
6. **grep AC 模式范围精度**（E9 fix）— `△ \[` vs `△ \[V` 精度差；spec AC 应明示 view 进度行限定

## §11 + §12 follow-up 表（本 PR 闭合后）

- §12 F1/F2/f3/f5/f6 + f2 closed（v2.37.3-v2.37.6）✓
- §12 f1 / f4 未闭合（batch 3）
- §11-N1 未闭合（batch 3 dev 工具）
- **§11-N2 closed v2.37.7** ✓
- **§11-N3 closed v2.37.7** ✓
- §11-N4 drop（非 bug，v2.37.6 重新评估）
- §11-N5 closed v2.37.6 ✓

## 下次类似 PR 优化

- try/except 多路径输出 spec 必明示每路径都覆盖
- catch specific exception 后必加 except Exception fallback + re-raise
- 输入校验 CLI flag 必 spec 化（不是 implementer 自由发挥）
- schema 改动加新字段必含字段一致性表（组件 × 字段 × 取值）
- spec 措辞 Unicode/ASCII / grep 模式精度等"小事"也要 layer 6 抓

[[project-v2-37-6-done]] 上游 v2.37.6 + §11-N4 重新评估教训追溯。
[[project-gisbot-jury-e2e-done]] §11-N3/§11-N2 来源（GISBOT e2e retro）。
```

- [ ] **Step 2: 元测试 + commit**

```bash
cd D:/Work/cad-spec-gen
pytest -q tests/test_agents_md.py tests/test_no_tracked_mirror.py 2>&1 | tail -3
git add docs/superpowers/reports/2026-05-15-v2-37-7-jury-cli-improvements-retro.md
git -c commit.gpgsign=false commit -m "docs(v2-37-7): retro 沉淀 — §11-N3+§11-N2 closed + 6 lessons

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

Expected: 元测试 5 PASS + commit 完成。

---

## Task 5: PR + CI + Merge + tag v2.37.7 + Release

### Task 5a: Push + 开 PR + 等 CI

- [ ] **Step 1: 验证无并行改动**

```bash
cd D:/Work/cad-spec-gen
git fetch origin main
git log --oneline HEAD..origin/main
```

Expected: 空。

- [ ] **Step 2: Push 分支**

```bash
git push origin feat/v2-37-7-jury-cli-improvements
```

- [ ] **Step 3: 开 PR**

```bash
gh pr create --title "feat(jury): v2.37.7 §11-N3 per-view 进度 + §11-N2 --override-subsystem flag" --body "$(cat <<'EOF'
## 概要

闭合 v2.37.x §11 follow-up 2 项 photo3d-jury CLI UX 改进：

- **§11-N3**：jury per-view 进度 stderr 输出 success + failure + crash 三态全覆盖（F1+E2 fix）
- **§11-N2**：`--override-subsystem` alias flag + effective_subsystem 字段 + 输入校验（E3 输入校验 + E4+E5+E6 字段一致性）

## 改动

- `tools/photo3d_jury.py` +~50 行 production（3 stderr 进度行 + argparse flag + main 输入校验 + effective_subsystem 计算 + report 字段）
- `tests/jury/test_photo3d_jury_per_view_progress.py` +60 行（5 新测试）
- `docs/cad-jury-config.md` 附录 A +2 行
- retro +70 行

## 测试

- jury 子集 504 → **509 PASS** / 0 regression
- 全套件 3194 → 3199

## 审查层数

brainstorming F1+F2+F3+F4 + layer 6 E2+E3+E4+E5+E6+E8+E9 fix = 11 findings / 9 inline 修 / 3 极低接受。

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Step 4: 等 CI 8/8**

```bash
gh pr checks --watch
```

Expected: 8/8 SUCCESS。Transient flake 同 v2.37.x 模板。

### Task 5b: Merge + Tag v2.37.7 + Release（用户授权后）

按 v2.37.6 Plan Task 6b 同模板：
- Step 5: `gh pr merge <PR#> --squash --delete-branch`
- Step 6: git pull main + 等 main CI
- Step 7: `git tag -a v2.37.7 $MAIN_SHA -m "v2.37.7 — §11-N3 per-view progress + §11-N2 --override-subsystem"` + push
- Step 8: `gh release create v2.37.7 --notes-file <D:/tmp/notes>`（注：v2.37.6 实证 `/tmp/` 在本机解析 `D:/tmp/` 应直接用绝对路径）
- Step 9: `gh release view v2.37.7` 验证
- Step 10: 写 `project_v2_37_7_done.md` memory + MEMORY.md 索引行

---

## Self-Review

**1. Spec coverage**:

| Spec 章节 | Plan Task | 备注 |
|---|---|---|
| §2.1 改动表 row 1 (per-view 3 stderr) | Task 1 Step 5/6/7 | ✓ |
| §2.1 改动表 row 2 (argparse flag) | Task 2 Step 3 | ✓ |
| §2.1 改动表 row 3 (main effective_subsystem + 输入校验 + report 字段) | Task 2 Step 4/5/6 | ✓ |
| §2.1 改动表 row 4 (5 TDD 测试) | Task 1 Step 1-3 (3 测试) + Task 2 Step 1 (2 测试) | ✓ |
| §2.1 改动表 row 5 (docs cad-jury-config 附录 A) | Task 3 | ✓ |
| §2.1 改动表 row 6 (retro) | Task 4 | ✓ |
| §3 D1 (per-view 3 路径) | Task 1 Step 5/6/7 | ✓ |
| §3 D2 (effective_subsystem 字段表) | Task 2 Step 4/5/6 | ✓ |
| §3 D3 (合 1 PR 4 commit) | Task 1+2+3+4 4 commit | ✓ |
| §4 AC-1..8 | Task 1 (AC-1) / Task 2 (AC-2/3) / Step 9 (AC-4) / Step 1 (AC-5) / Step 8 (AC-6) / Task 5a (AC-7) / Task 5b (AC-8) | ✓ |
| §5 风险表 layer 6 7 row | Task 1+2 全程维持（spec D1/D2 决策落地） | ✓ |
| §6 不变量 #1-7 | Task 1+2 全程维持 | ✓ |
| §7 流程 + 4 commit | Task 1+2+3+4 拆 4 commit | ✓ |
| §8 8 调查步 | Task 0 Step 1-7 全覆盖 | ✓ |
| §9 plan 必 cover | Task 0 实测 + Task 1+2 TDD + grep -cE + spec D1 except 双路径 | ✓ |
| §10 不写代码事项 | 全 task 不做 | ✓ |
| §11 §11+§12 表 | Task 4 retro | ✓ |
| §12 本 PR follow-up h1-h4 | Task 4 retro 末 | ✓ |

**所有 spec 章节有 task 覆盖。**

**2. Placeholder scan**: 无 TBD / TODO / implement later。Task 1 Step 1 `_setup_jury_env` 占位 `NotImplementedError` 是显式 TDD RED-driven placeholder（Step 3 实施完整 helper 实现）。

**3. Type consistency**: `args.subsystem` / `args.override_subsystem` / `effective_subsystem` 跨 Task 1+2 一致；`view_name` / `total_views` / `vv.photoreal_score` / `vv.verdict` / `resp.latency_ms` / `exc.error_kind` / `type(exc).__name__` 跨 spec 与 plan 一致；测试 fixture `_setup_jury_env` Task 1+2 共用。

**Plan 自检无问题 → ready for handoff。**

---

## 执行方式选择

Plan 完成保存到 `docs/superpowers/plans/2026-05-15-v2-37-7-jury-cli-improvements.md`。

1. **Subagent-Driven（推荐）** — v2.37.x 16 PR 连续一次过 CI 模板
2. **Inline 执行** — scope 中等，subagent-driven 仍最稳

建议 Subagent-Driven。
