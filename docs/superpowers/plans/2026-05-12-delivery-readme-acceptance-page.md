# `delivery/README.md` 验收页（队列 D）实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 `tools/photo3d_delivery_pack.py::_write_readme` 从「JSON-ish 项目符号 dump」重写成外行用户能直接读懂的验收页（头条状态 + 内嵌 enhanced 图 + 人话质量摘要 + 复核状态表 + 下一步 + 每视角实例计数 + 底部审计证据清单），并往 `DELIVERY_PACKAGE.json` / `report` dict 加一个可选 additive 的 `view_evidence` 字段（透出队列 C 的 `render_manifest.files[].visible_instance_ids`）。

**Architecture:** 零行为变更（除 README 内容更丰富 + DELIVERY_PACKAGE.json 多一个可选字段）。`_write_readme(path, report)` 拆成若干纯函数 section-builder（`_readme_*(report) -> list[str]`）+ 两个小工具（`_status_badge` / `_pkg_path_relative_to_delivery`），`_write_readme` 只负责按顺序拼接。`view_evidence` 由 `_view_evidence_summary(manifest)` 从已 load 的 `manifest` 提取，塞进 `run_photo3d_delivery_pack` 返回的 `report` dict（`write_json_atomic` 自动写进 DELIVERY_PACKAGE.json）。所有 section 在数据缺失时整段省略——graceful degradation。

**Tech Stack:** Python 3.11；纯标准库（`pathlib` / 字符串拼接）；测试 `pytest`（复用 `tests/test_photo3d_gate_contract.py::_contracts` fixture）；`scripts/dev_sync.py` 同步 gitignored 镜像。

**Spec:** `docs/superpowers/specs/2026-05-12-delivery-readme-acceptance-page-design.md`

**File structure:**
- Modify `tools/photo3d_delivery_pack.py`：
  - 加模块级常量 `_BADGE_POSITIVE` / `_BADGE_WARN` / `_BADGE_BLOCK` / `_BADGE_LABELS`、`_NEXT_ACTION_LABELS`。
  - 加纯工具 `_status_badge(status)` / `_pkg_path_relative_to_delivery(package_path, delivery_dir)` / `_view_evidence_summary(manifest)`。
  - 加 section-builder `_readme_headline` / `_readme_images_section` / `_readme_view_evidence_section` / `_readme_model_quality_section` / `_readme_review_status_section` / `_readme_next_step_section` / `_readme_blocking_section` / `_readme_evidence_appendix`（每个 `(report: dict[str, Any]) -> list[str]`）。
  - 重写 `_write_readme(path, report)` 为按顺序 `lines += _readme_*(report)`。
  - `run_photo3d_delivery_pack`：`report` dict 里在 `"deliverables": deliverables,` 之后插 `"view_evidence": _view_evidence_summary(manifest),`。
- Modify `tests/test_photo3d_delivery_pack.py`：更新 `test_photo3d_delivery_pack_includes_active_run_model_quality_summary` 的 README 断言；加 section-builder 单测；加 README 验收页集成测试 + view_evidence with/without 测试。
- 自动产物 `src/cad_spec_gen/data/tools/photo3d_delivery_pack.py`：gitignored 镜像，`scripts/dev_sync.py` 复制 canonical→镜像（**不 git add**，但本 PR 收尾要跑 dev_sync + `--check` + `git diff --exit-code -- AGENTS.md`）。
- **不改**：`run_photo3d_delivery_pack` 主流程 / `_copy_view_images` / `_model_quality_summary_from_source_reports` / `_build_jury_section` / `_semantic_material_review_summary` / 证据链 / hash 绑定 / `_reset_managed_delivery_dirs` / blocking 判定 / `cad_pipeline.py::cmd_photo3d_deliver` / `tools/render_visual_regression.py` / `tools/model_audit.py` / `render_manifest` schema / `DELIVERY_PACKAGE.json` schema_version（仍 1）/ `pyproject.toml` / `.github/workflows/`。

---

## Task 0: 起手 — 验证 spec 假设仍成立

**Files:** 只读，无改动。

- [ ] **Step 1: 跑下面的检查，确认 spec §7 的假设没漂移**

```bash
# 1. _write_readme 现状（应是项目符号 dump，约 35 行）
grep -n "def _write_readme" tools/photo3d_delivery_pack.py
# 2. report dict 字段（应含 delivery_dir / deliverables / view_evidence 待加）
sed -n '180,205p' tools/photo3d_delivery_pack.py
# 3. _image_item 给的是 project-relative package_path
grep -n "def _image_item" tools/photo3d_delivery_pack.py
# 4. enhanced 复制到 enhanced/（final）或 preview/（preview），labeled→labeled/
grep -n 'delivery_dir / ("enhanced" if final else "preview")\|delivery_dir / "labeled"' tools/photo3d_delivery_pack.py
# 5. manifest 是 run_photo3d_delivery_pack 的局部变量
grep -n 'manifest = load_json_required' tools/photo3d_delivery_pack.py
# 6. _build_jury_section 返回 dict 含 "status"
grep -n '"status": rep.get("status")' tools/photo3d_delivery_pack.py
# 7. semantic_material_review["required"] = bool(require_semantic_review)
grep -n 'semantic_material_review\["required"\] = bool' tools/photo3d_delivery_pack.py
# 8. _contracts fixture 的 assembly_signature 有 2 个 valid-bbox instances
grep -n '"instance_id": "P-100-0[12]#01"' tests/test_photo3d_gate_contract.py
# 9. photo3d_delivery_pack.py 不在 CI mypy-strict 那行
grep -n "mypy --strict" .github/workflows/tests.yml
# 10. 镜像是 gitignored
grep -n "src/cad_spec_gen/data/tools/" .gitignore
```

Expected：1=约第 794 行；3=约第 567 行；4=约第 508/516 行；5=约第 78 行；6=约第 365 行；7=约第 139 行；8=两行命中；9=mypy 行不含 `photo3d_delivery_pack`；10=`.gitignore` 命中 `src/cad_spec_gen/data/tools/`。若任一不符，停下来报告——spec 需修正。

- [ ] **Step 2: 确认没有别处硬断言 DELIVERY_PACKAGE.json 字段集**

```bash
grep -rn "DELIVERY_PACKAGE\|delivery_package" tests/ --include='*.py' | grep -v "test_photo3d_delivery_pack.py"
```

Expected：命中的只是 `.is_file()` / 路径断言 / `command_return_code_for_delivery_pack`，没有断言「dict 的 key 集合恰好等于 X」的——加 `view_evidence` additive 安全。若发现严格 key-set 断言，停下来报告。

无需 commit（只读 task）。

---

## Task 1: `_view_evidence_summary` helper + `view_evidence` report 字段

**Files:**
- Modify: `tools/photo3d_delivery_pack.py`（加 `_view_evidence_summary`；`report` dict 加 `view_evidence`）
- Test: `tests/test_photo3d_delivery_pack.py`（加 2 个集成测试）

- [ ] **Step 1: 写失败测试**

在 `tests/test_photo3d_delivery_pack.py` 末尾追加：

```python
# === 队列 D Task 1: view_evidence 字段 ===


def test_delivery_package_includes_view_evidence_when_manifest_has_visible_instance_ids(tmp_path):
    """render_manifest 带 evidence_method / visible_instance_ids（队列 C）时，
    DELIVERY_PACKAGE.json 与 report 都带 view_evidence（evidence_method + per_view）。"""
    from tools.photo3d_delivery_pack import run_photo3d_delivery_pack

    fixture = _contracts(tmp_path)
    _write_photo3d_run(fixture)
    _write_enhancement_report(fixture, "accepted")

    report = run_photo3d_delivery_pack(
        tmp_path, "demo", artifact_index_path=fixture["index_path"]
    )

    assert report["view_evidence"] == {
        "evidence_method": "instance_bbox_presence",
        "per_view": {"V1": ["P-100-01#01", "P-100-02#01"]},
    }
    pkg = json.loads(
        (tmp_path / report["artifacts"]["delivery_package"]).read_text(encoding="utf-8")
    )
    assert pkg["view_evidence"] == report["view_evidence"]


def test_delivery_package_view_evidence_is_none_when_manifest_lacks_evidence(tmp_path):
    """老 run / 缺 assembly_signature → render_manifest 无 evidence_method / visible_instance_ids
    → view_evidence 为 None（向后兼容）。"""
    from tools.photo3d_delivery_pack import run_photo3d_delivery_pack

    fixture = _contracts(tmp_path)
    _write_photo3d_run(fixture)
    _write_enhancement_report(fixture, "accepted")
    manifest_path = fixture["paths"]["render_manifest"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest.pop("evidence_method", None)
    for entry in manifest.get("files", []):
        entry.pop("visible_instance_ids", None)
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    report = run_photo3d_delivery_pack(
        tmp_path, "demo", artifact_index_path=fixture["index_path"]
    )

    assert report["view_evidence"] is None
    pkg = json.loads(
        (tmp_path / report["artifacts"]["delivery_package"]).read_text(encoding="utf-8")
    )
    assert pkg["view_evidence"] is None
```

- [ ] **Step 2: 跑测试，确认 fail**

Run: `python -m pytest tests/test_photo3d_delivery_pack.py -q -k view_evidence`
Expected: FAIL — `KeyError: 'view_evidence'`（report 里还没这个 key）。

- [ ] **Step 3: 实现**

在 `tools/photo3d_delivery_pack.py` 里，紧挨着 `_build_jury_section` 之前（或之后，位置不重要，放 helper 区即可）加：

```python
def _view_evidence_summary(manifest: dict[str, Any]) -> dict[str, Any] | None:
    """从 render_manifest 提取逐视角可见实例证据（队列 C 的 evidence_method / visible_instance_ids）。

    manifest 既没 evidence_method 也没任何 per-view visible_instance_ids → 返 None（向后兼容）。
    """
    method = manifest.get("evidence_method")
    per_view = {
        str(f.get("view")): list(f.get("visible_instance_ids"))
        for f in (manifest.get("files") or [])
        if isinstance(f, dict)
        and f.get("view")
        and isinstance(f.get("visible_instance_ids"), list)
    }
    if not method and not per_view:
        return None
    return {"evidence_method": method, "per_view": per_view}
```

在 `run_photo3d_delivery_pack` 的 `report = { ... }` 里，把

```python
        "deliverables": deliverables,
        "evidence_files": evidence_files,
```

改成

```python
        "deliverables": deliverables,
        "view_evidence": _view_evidence_summary(manifest),
        "evidence_files": evidence_files,
```

- [ ] **Step 4: 跑测试，确认 pass**

Run: `python -m pytest tests/test_photo3d_delivery_pack.py -q -k view_evidence`
Expected: PASS（2 passed）。

- [ ] **Step 5: 跑整个文件确认不回归**

Run: `python -m pytest tests/test_photo3d_delivery_pack.py tests/test_photo3d_gate_contract.py -q`
Expected: 全 PASS。

- [ ] **Step 6: Commit**

```bash
git add tools/photo3d_delivery_pack.py tests/test_photo3d_delivery_pack.py
git -c commit.gpgsign=false commit -m "$(cat <<'EOF'
feat(delivery): DELIVERY_PACKAGE.json 加 view_evidence 字段（队列 C 数据透出）

_view_evidence_summary(manifest) 从 render_manifest 提取 evidence_method + per-view
visible_instance_ids，塞进 report dict（缺数据时为 None，向后兼容）。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: `_status_badge` 工具

**Files:**
- Modify: `tools/photo3d_delivery_pack.py`（加常量 + `_status_badge`）
- Test: `tests/test_photo3d_delivery_pack.py`

- [ ] **Step 1: 写失败测试**

在 `tests/test_photo3d_delivery_pack.py` 末尾追加：

```python
# === 队列 D Task 2: _status_badge ===


def test_status_badge_positive_warn_block():
    from tools.photo3d_delivery_pack import _status_badge

    assert _status_badge("delivered") == "✓ 已交付"
    assert _status_badge("accepted") == "✓ 已验收"
    assert _status_badge("preview") == "⚠ 预览"
    assert _status_badge("not_run") == "⚠ 未做"
    assert _status_badge("needs_review") == "⚠ 建议复核"
    assert _status_badge("blocked") == "✗ 阻断"
    assert _status_badge("not_deliverable") == "✗ 未交付"


def test_status_badge_unknown_is_neutral_never_block():
    from tools.photo3d_delivery_pack import _status_badge

    assert _status_badge("weird_state") == "· weird_state"
    assert _status_badge("") == "· 未知"
    assert _status_badge(None) == "· 未知"
```

- [ ] **Step 2: 跑测试，确认 fail**

Run: `python -m pytest tests/test_photo3d_delivery_pack.py -q -k status_badge`
Expected: FAIL — `ImportError: cannot import name '_status_badge'`。

- [ ] **Step 3: 实现**

在 `tools/photo3d_delivery_pack.py` 顶部常量区（`RUN_REPORTS = { ... }` 之后）加：

```python
_BADGE_POSITIVE = {"delivered", "accepted", "ready", "continue_photo3d"}
_BADGE_WARN = {"preview", "preview_package", "needs_review", "unknown", "not_run"}
_BADGE_BLOCK = {"not_deliverable", "blocked", "not_available"}
_BADGE_LABELS = {
    "delivered": "已交付",
    "accepted": "已验收",
    "ready": "就绪",
    "continue_photo3d": "可继续",
    "preview": "预览",
    "preview_package": "预览包",
    "needs_review": "建议复核",
    "unknown": "未知",
    "not_run": "未做",
    "not_deliverable": "未交付",
    "blocked": "阻断",
    "not_available": "无数据",
}
```

在 helper 区（`_write_readme` 之前）加：

```python
def _status_badge(status: object) -> str:
    """状态枚举值 → 「图标 中文」徽章。未知值用中性「·」+原值，绝不误判成 ✗。"""
    key = str(status or "").strip()
    label = _BADGE_LABELS.get(key, key or "未知")
    if key in _BADGE_POSITIVE:
        return f"✓ {label}"
    if key in _BADGE_WARN:
        return f"⚠ {label}"
    if key in _BADGE_BLOCK:
        return f"✗ {label}"
    return f"· {key}" if key else "· 未知"
```

- [ ] **Step 4: 跑测试，确认 pass**

Run: `python -m pytest tests/test_photo3d_delivery_pack.py -q -k status_badge`
Expected: PASS（2 passed）。

- [ ] **Step 5: Commit**

```bash
git add tools/photo3d_delivery_pack.py tests/test_photo3d_delivery_pack.py
git -c commit.gpgsign=false commit -m "$(cat <<'EOF'
feat(delivery): _status_badge — 状态枚举值映射成图标+中文徽章

正向/告警/阻断三集 + 未知值退化中性「· <原值>」（不误判成 ✗）。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: `_pkg_path_relative_to_delivery` 工具

**Files:**
- Modify: `tools/photo3d_delivery_pack.py`（加 `_pkg_path_relative_to_delivery`）
- Test: `tests/test_photo3d_delivery_pack.py`

- [ ] **Step 1: 写失败测试**

在 `tests/test_photo3d_delivery_pack.py` 末尾追加：

```python
# === 队列 D Task 3: _pkg_path_relative_to_delivery ===


def test_pkg_path_relative_to_delivery_strips_delivery_prefix():
    from tools.photo3d_delivery_pack import _pkg_path_relative_to_delivery

    delivery_dir = "cad/demo/.cad-spec-gen/runs/RUN001/delivery"
    assert (
        _pkg_path_relative_to_delivery(
            "cad/demo/.cad-spec-gen/runs/RUN001/delivery/enhanced/V1_enhanced.jpg",
            delivery_dir,
        )
        == "enhanced/V1_enhanced.jpg"
    )
    assert (
        _pkg_path_relative_to_delivery(
            "cad/demo/.cad-spec-gen/runs/RUN001/delivery/labeled/V1_labeled.jpg",
            delivery_dir,
        )
        == "labeled/V1_labeled.jpg"
    )


def test_pkg_path_relative_to_delivery_falls_back_to_basename_on_bad_path():
    from tools.photo3d_delivery_pack import _pkg_path_relative_to_delivery

    # package_path 不在 delivery_dir 内 → 不抛，退化为 basename
    assert (
        _pkg_path_relative_to_delivery(
            "some/other/place/img.jpg", "cad/demo/.cad-spec-gen/runs/RUN001/delivery"
        )
        == "img.jpg"
    )
```

- [ ] **Step 2: 跑测试，确认 fail**

Run: `python -m pytest tests/test_photo3d_delivery_pack.py -q -k pkg_path_relative`
Expected: FAIL — `ImportError: cannot import name '_pkg_path_relative_to_delivery'`。

- [ ] **Step 3: 实现**

在 `tools/photo3d_delivery_pack.py` helper 区（`_status_badge` 旁边）加：

```python
def _pkg_path_relative_to_delivery(package_path: str, delivery_dir: str) -> str:
    """把 project-relative 的 package_path 转成相对 delivery_dir 的 posix 路径。

    README 写在 delivery/ 下，所以图链接要相对 delivery_dir。两个入参都是 project-relative；
    正常情况 package_path 在 delivery_dir 内（cad/.../runs/RUN001/delivery/enhanced/V1.jpg →
    enhanced/V1.jpg）。路径异常（不在 delivery_dir 内）时退化为 basename，绝不抛异常。
    """
    try:
        return Path(package_path).relative_to(Path(delivery_dir)).as_posix()
    except ValueError:
        return Path(package_path).name
```

- [ ] **Step 4: 跑测试，确认 pass**

Run: `python -m pytest tests/test_photo3d_delivery_pack.py -q -k pkg_path_relative`
Expected: PASS（2 passed）。

- [ ] **Step 5: Commit**

```bash
git add tools/photo3d_delivery_pack.py tests/test_photo3d_delivery_pack.py
git -c commit.gpgsign=false commit -m "$(cat <<'EOF'
feat(delivery): _pkg_path_relative_to_delivery — 图链接相对 delivery_dir

project-relative package_path → 相对 delivery_dir 的 posix；路径异常退化 basename。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: README section-builder 之一 — headline / 渲染图 / 完整性证据

**Files:**
- Modify: `tools/photo3d_delivery_pack.py`（加 `_readme_headline` / `_readme_images_section` / `_readme_view_evidence_section`）
- Test: `tests/test_photo3d_delivery_pack.py`

- [ ] **Step 1: 写失败测试**

在 `tests/test_photo3d_delivery_pack.py` 末尾追加：

```python
# === 队列 D Task 4: README section builders（headline / images / view_evidence）===


def test_readme_headline_basic():
    from tools.photo3d_delivery_pack import _readme_headline

    lines = _readme_headline(
        {
            "subsystem": "demo",
            "run_id": "RUN001",
            "status": "delivered",
            "enhancement_status": "accepted",
            "final_deliverable": True,
            "ordinary_user_message": "最终交付包已生成。",
        }
    )
    text = "\n".join(lines)
    assert text.startswith("# 交付包验收 — demo / RUN001")
    assert "**状态**：✓ 已交付  ·  增强：✓ 已验收  ·  最终交付物：是" in text
    assert "> 最终交付包已生成。" in text


def test_readme_images_section_embeds_relative_path_and_part_count_and_labeled():
    from tools.photo3d_delivery_pack import _readme_images_section

    report = {
        "delivery_dir": "cad/demo/.cad-spec-gen/runs/RUN001/delivery",
        "deliverables": {
            "enhanced_images": [
                {
                    "view": "V1",
                    "package_path": "cad/demo/.cad-spec-gen/runs/RUN001/delivery/enhanced/V1_e.jpg",
                }
            ],
            "labeled_images": [
                {
                    "view": "V1",
                    "package_path": "cad/demo/.cad-spec-gen/runs/RUN001/delivery/labeled/V1_l.jpg",
                }
            ],
        },
        "view_evidence": {"evidence_method": "instance_bbox_presence", "per_view": {"V1": ["A", "B", "C"]}},
    }
    text = "\n".join(_readme_images_section(report))
    assert "## 渲染图（增强后）" in text
    assert "### V1" in text
    assert "![V1 增强图](enhanced/V1_e.jpg)" in text
    assert "- 本图标着含 3 个零件" in text
    assert "[带标注版](labeled/V1_l.jpg)" in text


def test_readme_images_section_empty_when_no_enhanced_images():
    from tools.photo3d_delivery_pack import _readme_images_section

    assert _readme_images_section({"deliverables": {"enhanced_images": []}}) == []
    assert _readme_images_section({}) == []


def test_readme_images_section_omits_part_count_when_no_view_evidence():
    from tools.photo3d_delivery_pack import _readme_images_section

    report = {
        "delivery_dir": "cad/demo/.cad-spec-gen/runs/RUN001/delivery",
        "deliverables": {
            "enhanced_images": [
                {"view": "V1", "package_path": "cad/demo/.cad-spec-gen/runs/RUN001/delivery/enhanced/V1_e.jpg"}
            ]
        },
        "view_evidence": None,
    }
    text = "\n".join(_readme_images_section(report))
    assert "![V1 增强图](enhanced/V1_e.jpg)" in text
    assert "本图标着含" not in text


def test_readme_view_evidence_section_counts_and_none():
    from tools.photo3d_delivery_pack import _readme_view_evidence_section

    text = "\n".join(
        _readme_view_evidence_section(
            {
                "view_evidence": {
                    "evidence_method": "instance_bbox_presence",
                    "per_view": {"V2": ["A"], "V1": ["A", "B"]},
                }
            }
        )
    )
    assert "## 完整性证据" in text
    assert "证据方式：instance_bbox_presence" in text
    assert "各视角实例计数：V1=2、V2=1" in text  # 按 view 名排序
    assert "RENDER_VISUAL_REGRESSION.json" in text
    assert _readme_view_evidence_section({"view_evidence": None}) == []
    assert _readme_view_evidence_section({}) == []
```

- [ ] **Step 2: 跑测试，确认 fail**

Run: `python -m pytest tests/test_photo3d_delivery_pack.py -q -k "readme_headline or readme_images or readme_view_evidence"`
Expected: FAIL — `ImportError: cannot import name '_readme_headline'`。

- [ ] **Step 3: 实现**

在 `tools/photo3d_delivery_pack.py` 里、`_write_readme` 之前加这三个 section builder：

```python
def _readme_headline(report: dict[str, Any]) -> list[str]:
    subsystem = report.get("subsystem") or "?"
    run_id = report.get("run_id") or "?"
    final = "是" if report.get("final_deliverable") is True else "否"
    lines = [
        f"# 交付包验收 — {subsystem} / {run_id}",
        "",
        f"**状态**：{_status_badge(report.get('status'))}  ·  "
        f"增强：{_status_badge(report.get('enhancement_status'))}  ·  "
        f"最终交付物：{final}",
    ]
    message = report.get("ordinary_user_message") or ""
    if message:
        lines += ["", f"> {message}"]
    return lines


def _readme_images_section(report: dict[str, Any]) -> list[str]:
    deliverables = report.get("deliverables") or {}
    enhanced = deliverables.get("enhanced_images") or []
    if not enhanced:
        return []
    delivery_dir = str(report.get("delivery_dir") or "")
    labeled_by_view = {
        str(item.get("view")): item
        for item in (deliverables.get("labeled_images") or [])
        if isinstance(item, dict) and item.get("view")
    }
    per_view = (report.get("view_evidence") or {}).get("per_view") or {}
    lines = ["", "## 渲染图（增强后）"]
    for item in enhanced:
        if not isinstance(item, dict):
            continue
        view = str(item.get("view") or "")
        rel = _pkg_path_relative_to_delivery(str(item.get("package_path") or ""), delivery_dir)
        lines += ["", f"### {view}", f"![{view} 增强图]({rel})"]
        ids = per_view.get(view)
        if isinstance(ids, list):
            lines.append(f"- 本图标着含 {len(ids)} 个零件")
        labeled = labeled_by_view.get(view)
        if isinstance(labeled, dict):
            lab_rel = _pkg_path_relative_to_delivery(str(labeled.get("package_path") or ""), delivery_dir)
            lines.append(f"- [带标注版]({lab_rel})")
    return lines


def _readme_view_evidence_section(report: dict[str, Any]) -> list[str]:
    view_evidence = report.get("view_evidence")
    if not view_evidence:
        return []
    method = view_evidence.get("evidence_method") or "?"
    per_view = view_evidence.get("per_view") or {}
    counts = "、".join(
        f"{view}={len(ids)}"
        for view, ids in sorted(per_view.items())
        if isinstance(ids, list)
    )
    lines = ["", "## 完整性证据", f"- 证据方式：{method}"]
    if counts:
        lines.append(f"- 各视角实例计数：{counts}")
    lines.append(
        "- 详细逐视角实例清单见 `DELIVERY_PACKAGE.json` 的 `view_evidence` 字段 / "
        "`render_manifest.json`；完整性 PASS/BLOCKED 判定见 `RENDER_VISUAL_REGRESSION.json`"
        "（若已跑过 `photo3d-render-check`）"
    )
    return lines
```

- [ ] **Step 4: 跑测试，确认 pass**

Run: `python -m pytest tests/test_photo3d_delivery_pack.py -q -k "readme_headline or readme_images or readme_view_evidence"`
Expected: PASS（5 passed）。

- [ ] **Step 5: Commit**

```bash
git add tools/photo3d_delivery_pack.py tests/test_photo3d_delivery_pack.py
git -c commit.gpgsign=false commit -m "$(cat <<'EOF'
feat(delivery): README section builders 1/2 — headline / 渲染图 / 完整性证据

_readme_headline（头条状态徽章 + 通用人话句）/ _readme_images_section（内嵌 enhanced
图相对路径 + 每图零件数 + 带标注版链接，无 enhanced 图整段省略）/ _readme_view_evidence_section
（证据方式 + 各视角实例计数，view_evidence 为 None 整段省略）。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: README section-builder 之二 — 模型质量 / 复核状态 / 下一步 / 阻断项 / 证据清单

**Files:**
- Modify: `tools/photo3d_delivery_pack.py`（加 `_readme_model_quality_section` / `_readme_review_status_section` / `_readme_next_step_section` / `_readme_blocking_section` / `_readme_evidence_appendix` + 常量 `_NEXT_ACTION_LABELS`）
- Test: `tests/test_photo3d_delivery_pack.py`

- [ ] **Step 1: 写失败测试**

在 `tests/test_photo3d_delivery_pack.py` 末尾追加：

```python
# === 队列 D Task 5: README section builders（model_quality / review_status / next_step / blocking / appendix）===


def test_readme_model_quality_section():
    from tools.photo3d_delivery_pack import _readme_model_quality_section

    text = "\n".join(
        _readme_model_quality_section(
            {
                "model_quality_summary": {
                    "ordinary_user_message": "模型质量摘要发现 2 个零件建议复核。",
                    "readiness_status": "needs_review",
                    "photoreal_risk": "high",
                    "review_recommended_count": 2,
                    "blocking_count": 0,
                }
            }
        )
    )
    assert "## 模型质量" in text
    assert "> 模型质量摘要发现 2 个零件建议复核。" in text
    assert "就绪状态：needs_review  ·  照片级风险：high" in text
    assert "建议复核 2 个零件  ·  阻断 0 个" in text
    assert _readme_model_quality_section({"model_quality_summary": None}) == []
    assert _readme_model_quality_section({}) == []


def test_readme_review_status_section_semantic_required_and_jury_none():
    from tools.photo3d_delivery_pack import _readme_review_status_section

    text = "\n".join(
        _readme_review_status_section(
            {
                "quality_summary": {"status": "accepted"},
                "enhancement_status": "accepted",
                "semantic_material_review": {"status": "not_run", "required": True},
                "jury": None,
            }
        )
    )
    assert "## 复核状态" in text
    assert "| 增强图质量（quality_summary）| ✓ 已验收 |" in text
    assert "| AI 增强（enhancement）| ✓ 已验收 |" in text
    assert "| 语义/材质复核（semantic_material_review）| ⚠ 必需但未做 |" in text
    assert "| AI 视觉评分（jury）| ⚠ 未运行 |" in text


def test_readme_review_status_section_semantic_not_required_and_jury_accepted():
    from tools.photo3d_delivery_pack import _readme_review_status_section

    text = "\n".join(
        _readme_review_status_section(
            {
                "quality_summary": {"status": "unknown"},
                "enhancement_status": "preview",
                "semantic_material_review": {"status": "not_run", "required": False},
                "jury": {"status": "accepted", "actual_cost_usd": 0.02},
            }
        )
    )
    assert "| 增强图质量（quality_summary）| ⚠ 未知 |" in text
    assert "| AI 增强（enhancement）| ⚠ 预览 |" in text
    assert "| 语义/材质复核（semantic_material_review）| ⚠ 未做（非强制）|" in text
    assert "| AI 视觉评分（jury）| ✓ 已验收（成本 $0.02）|" in text


def test_readme_review_status_section_semantic_blocked_shows_report_path():
    from tools.photo3d_delivery_pack import _readme_review_status_section

    text = "\n".join(
        _readme_review_status_section(
            {
                "quality_summary": {"status": "accepted"},
                "enhancement_status": "accepted",
                "semantic_material_review": {
                    "status": "blocked",
                    "required": False,
                    "review_report": "cad/x/ENHANCEMENT_REVIEW_REPORT.json",
                },
                "jury": None,
            }
        )
    )
    assert "✗ 阻断（见 `cad/x/ENHANCEMENT_REVIEW_REPORT.json`）" in text


def test_readme_next_step_section_three_branches():
    from tools.photo3d_delivery_pack import _readme_next_step_section

    # 1. 有阻断项
    text = "\n".join(_readme_next_step_section({"blocking_reasons": [{"code": "x"}]}))
    assert "## 下一步" in text
    assert "✗ 当前有阻断项" in text
    # 2. recommended_next_action.kind == review_models
    text = "\n".join(
        _readme_next_step_section(
            {
                "blocking_reasons": [],
                "model_quality_summary": {"recommended_next_action": {"kind": "review_models"}},
                "status": "preview_package",
            }
        )
    )
    assert "⚠ 建议先复核标黄的零件，再交付。" in text
    # 3. delivered 且无阻断、无建议动作
    text = "\n".join(
        _readme_next_step_section(
            {
                "blocking_reasons": [],
                "model_quality_summary": {"recommended_next_action": {"kind": "continue_photo3d"}},
                "status": "delivered",
            }
        )
    )
    assert "✓ 交付完成，无需进一步动作。" in text


def test_readme_blocking_section():
    from tools.photo3d_delivery_pack import _readme_blocking_section

    text = "\n".join(
        _readme_blocking_section({"blocking_reasons": [{"code": "photo_quality_not_accepted", "message": "质量未验收"}]})
    )
    assert "## 阻断项" in text
    assert "- photo_quality_not_accepted: 质量未验收" in text
    assert _readme_blocking_section({"blocking_reasons": []}) == []
    assert _readme_blocking_section({}) == []


def test_readme_evidence_appendix():
    from tools.photo3d_delivery_pack import _readme_evidence_appendix

    text = "\n".join(
        _readme_evidence_appendix(
            {
                "source_reports": {
                    "render_manifest": "cad/.../render_manifest.json",
                    "artifact_index": "cad/.../ARTIFACT_INDEX.json",
                },
                "deliverables": {
                    "source_images": [{"view": "V1"}],
                    "enhanced_images": [{"view": "V1"}],
                    "labeled_images": [],
                },
                "evidence_files": [{"package_path": "cad/.../delivery/evidence/x.json"}],
                "delivery_dir": "cad/.../delivery",
            }
        )
    )
    assert "## 证据清单（供审计）" in text
    assert "- artifact_index: `cad/.../ARTIFACT_INDEX.json`" in text
    assert "- render_manifest: `cad/.../render_manifest.json`" in text
    assert "- 源渲染：1 张" in text
    assert "- 增强图：1 张" in text
    assert "- 标注图：0 张" in text
    assert "- `cad/.../delivery/evidence/x.json`" in text
    assert "cad/.../delivery" in text  # 末尾说明里有 delivery_dir
```

- [ ] **Step 2: 跑测试，确认 fail**

Run: `python -m pytest tests/test_photo3d_delivery_pack.py -q -k "readme_model_quality or readme_review_status or readme_next_step or readme_blocking or readme_evidence_appendix"`
Expected: FAIL — `ImportError: cannot import name '_readme_model_quality_section'`。

- [ ] **Step 3: 实现**

在 `tools/photo3d_delivery_pack.py` 顶部常量区（紧挨 `_BADGE_LABELS` 之后）加：

```python
_NEXT_ACTION_LABELS = {
    "import_missing_models": "先导入缺失的 3D 模型",
    "review_models": "先复核标黄的零件",
}
```

在 `_write_readme` 之前加这五个 section builder：

```python
def _readme_model_quality_section(report: dict[str, Any]) -> list[str]:
    summary = report.get("model_quality_summary")
    if not summary:
        return []
    lines = ["", "## 模型质量"]
    message = summary.get("ordinary_user_message") or ""
    if message:
        lines.append(f"> {message}")
    lines += [
        f"- 就绪状态：{summary.get('readiness_status') or '?'}  ·  "
        f"照片级风险：{summary.get('photoreal_risk') or '?'}",
        f"- 建议复核 {summary.get('review_recommended_count') or 0} 个零件  ·  "
        f"阻断 {summary.get('blocking_count') or 0} 个",
        "（来源：`MODEL_CONTRACT.json`，与本 run 绑定）",
    ]
    return lines


def _readme_review_status_section(report: dict[str, Any]) -> list[str]:
    quality_status = (report.get("quality_summary") or {}).get("status")
    semantic = report.get("semantic_material_review") or {}
    semantic_status = semantic.get("status")
    if semantic_status == "accepted":
        semantic_cell = _status_badge("accepted")
    elif semantic_status == "not_run":
        semantic_cell = "⚠ 必需但未做" if semantic.get("required") else "⚠ 未做（非强制）"
    else:
        semantic_cell = _status_badge(semantic_status)
        review_report = semantic.get("review_report")
        if review_report:
            semantic_cell += f"（见 `{review_report}`）"
    jury = report.get("jury")
    if not jury:
        jury_cell = "⚠ 未运行"
    else:
        jury_status = jury.get("status")
        jury_cell = _status_badge(jury_status)
        if jury_status == "accepted":
            cost = jury.get("actual_cost_usd")
            if cost is not None:
                jury_cell += f"（成本 ${cost}）"
    return [
        "",
        "## 复核状态",
        "| 项 | 状态 |",
        "|---|---|",
        f"| 增强图质量（quality_summary）| {_status_badge(quality_status)} |",
        f"| AI 增强（enhancement）| {_status_badge(report.get('enhancement_status'))} |",
        f"| 语义/材质复核（semantic_material_review）| {semantic_cell} |",
        f"| AI 视觉评分（jury）| {jury_cell} |",
    ]


def _readme_next_step_section(report: dict[str, Any]) -> list[str]:
    lines = ["", "## 下一步"]
    if report.get("blocking_reasons"):
        lines.append("✗ 当前有阻断项（见下方「阻断项」），处理后重新运行 `photo3d-deliver`。")
        return lines
    summary = report.get("model_quality_summary") or {}
    kind = str((summary.get("recommended_next_action") or {}).get("kind") or "").strip()
    if kind in _NEXT_ACTION_LABELS:
        lines.append(f"⚠ 建议{_NEXT_ACTION_LABELS[kind]}，再交付。")
        return lines
    if report.get("status") == "delivered":
        lines.append("✓ 交付完成，无需进一步动作。")
        return lines
    lines.append("⚠ 见上方各项状态。")
    return lines


def _readme_blocking_section(report: dict[str, Any]) -> list[str]:
    reasons = report.get("blocking_reasons") or []
    if not reasons:
        return []
    lines = ["", "## 阻断项"]
    for reason in reasons:
        if not isinstance(reason, dict):
            lines.append(f"- {reason}")
            continue
        code = reason.get("code") or "unknown"
        message = reason.get("message") or ""
        lines.append(f"- {code}: {message}" if message else f"- {code}")
    return lines


def _readme_evidence_appendix(report: dict[str, Any]) -> list[str]:
    lines = ["", "---", "## 证据清单（供审计）", "", "**报告**"]
    for kind, rel_path in sorted((report.get("source_reports") or {}).items()):
        lines.append(f"- {kind}: `{rel_path}`")
    deliverables = report.get("deliverables") or {}
    lines += [
        "",
        "**交付物**",
        f"- 源渲染：{len(deliverables.get('source_images') or [])} 张",
        f"- 增强图：{len(deliverables.get('enhanced_images') or [])} 张",
        f"- 标注图：{len(deliverables.get('labeled_images') or [])} 张",
        "",
        "**证据文件**",
    ]
    for item in report.get("evidence_files") or []:
        package_path = item.get("package_path") if isinstance(item, dict) else None
        if package_path:
            lines.append(f"- `{package_path}`")
    lines += [
        "",
        f"*本文件由 `photo3d-deliver` 自动生成于交付包目录"
        f"（`{report.get('delivery_dir') or ''}`）。"
        "`DELIVERY_PACKAGE.json` 是机器可读的完整证据清单。*",
    ]
    return lines
```

- [ ] **Step 4: 跑测试，确认 pass**

Run: `python -m pytest tests/test_photo3d_delivery_pack.py -q -k "readme_model_quality or readme_review_status or readme_next_step or readme_blocking or readme_evidence_appendix"`
Expected: PASS（6 passed）。

- [ ] **Step 5: Commit**

```bash
git add tools/photo3d_delivery_pack.py tests/test_photo3d_delivery_pack.py
git -c commit.gpgsign=false commit -m "$(cat <<'EOF'
feat(delivery): README section builders 2/2 — 模型质量 / 复核状态 / 下一步 / 阻断项 / 证据清单

_readme_model_quality_section（透出 model_quality_summary.ordinary_user_message + 枚举）/
_readme_review_status_section（quality/enhancement/semantic/jury 四行表，semantic 区分
「必需但未做 / 非强制」，jury None → 未运行）/ _readme_next_step_section（阻断 → 建议动作 →
delivered → 兜底 决策树）/ _readme_blocking_section / _readme_evidence_appendix（报告 + 交付物
计数 + 证据文件）。所有 section 数据缺失整段省略。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: 重写 `_write_readme` 组合所有 section + 更新/新增集成测试

**Files:**
- Modify: `tools/photo3d_delivery_pack.py`（重写 `_write_readme`）
- Modify: `tests/test_photo3d_delivery_pack.py`（改 `test_photo3d_delivery_pack_includes_active_run_model_quality_summary` 的 README 断言；加 2 个集成测试）

- [ ] **Step 1: 改现有测试 + 加集成测试（先让它们 fail）**

把 `tests/test_photo3d_delivery_pack.py` 里 `test_photo3d_delivery_pack_includes_active_run_model_quality_summary` 末尾的：

```python
    readme = (tmp_path / report["artifacts"]["delivery_readme"]).read_text(
        encoding="utf-8"
    )
    assert "model_quality_summary" in readme
    assert "needs_review" in readme
```

改成：

```python
    readme = (tmp_path / report["artifacts"]["delivery_readme"]).read_text(
        encoding="utf-8"
    )
    assert "## 模型质量" in readme
    assert summary["ordinary_user_message"] in readme
    assert "就绪状态：needs_review" in readme
```

在 `tests/test_photo3d_delivery_pack.py` 末尾追加两个集成测试：

```python
# === 队列 D Task 6: _write_readme 验收页集成 ===


def test_delivery_readme_is_acceptance_page(tmp_path):
    """accepted run → README 是结构化验收页：头条 / 内嵌 enhanced 图 / 完整性证据 /
    模型质量 / 复核状态 / 下一步 / 证据清单；DELIVERY_PACKAGE.json 带 view_evidence。"""
    from tools.photo3d_delivery_pack import run_photo3d_delivery_pack

    fixture = _contracts(tmp_path)
    _write_photo3d_run(fixture)
    _write_enhancement_report(fixture, "accepted")

    report = run_photo3d_delivery_pack(
        tmp_path, "demo", artifact_index_path=fixture["index_path"]
    )
    readme = (tmp_path / report["artifacts"]["delivery_readme"]).read_text(encoding="utf-8")

    # 头条
    assert readme.startswith("# 交付包验收 — demo / RUN001")
    assert "**状态**：✓ 已交付" in readme
    assert report["ordinary_user_message"] in readme
    # 渲染图段（内嵌 enhanced 图相对路径 + 零件数 + 带标注版）
    assert "## 渲染图（增强后）" in readme
    assert "### V1" in readme
    assert "![V1 增强图](enhanced/V1_front_20260505_1200_enhanced.jpg)" in readme
    assert "- 本图标着含 2 个零件" in readme
    assert "[带标注版](labeled/V1_front_20260505_1200_enhanced_labeled_en.jpg)" in readme
    # 完整性证据段
    assert "## 完整性证据" in readme
    assert "证据方式：instance_bbox_presence" in readme
    assert "各视角实例计数：V1=2" in readme
    # 模型质量段
    assert "## 模型质量" in readme
    assert report["model_quality_summary"]["ordinary_user_message"] in readme
    assert "就绪状态：needs_review" in readme
    # 复核状态段
    assert "## 复核状态" in readme
    assert "增强图质量（quality_summary）" in readme
    assert "AI 视觉评分（jury）| ⚠ 未运行" in readme  # jury 未跑
    # 下一步段（recommended_next_action.kind == review_models）
    assert "## 下一步" in readme
    assert "先复核标黄的零件" in readme
    # 证据清单（供审计）
    assert "## 证据清单（供审计）" in readme
    assert "render_manifest:" in readme
    assert "- 增强图：1 张" in readme
    assert "DELIVERY_PACKAGE.json" in readme
    # DELIVERY_PACKAGE.json 的 view_evidence
    pkg = json.loads(
        (tmp_path / report["artifacts"]["delivery_package"]).read_text(encoding="utf-8")
    )
    assert pkg["view_evidence"]["per_view"]["V1"] == ["P-100-01#01", "P-100-02#01"]


def test_delivery_readme_degrades_gracefully_on_blocked_and_missing_evidence(tmp_path):
    """blocked run（无 enhanced 图）+ 剥去 render_manifest 逐视角证据 → README 仍是合法 markdown：
    无「渲染图」段、无「完整性证据」段、有「阻断项」段、「下一步」指向阻断项。"""
    from tools.photo3d_delivery_pack import run_photo3d_delivery_pack

    fixture = _contracts(tmp_path)
    _write_enhancement_report(fixture, "blocked")
    manifest_path = fixture["paths"]["render_manifest"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest.pop("evidence_method", None)
    for entry in manifest.get("files", []):
        entry.pop("visible_instance_ids", None)
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    report = run_photo3d_delivery_pack(
        tmp_path, "demo", artifact_index_path=fixture["index_path"]
    )
    assert report["view_evidence"] is None
    readme = (tmp_path / report["artifacts"]["delivery_readme"]).read_text(encoding="utf-8")

    assert readme.startswith("# 交付包验收 — demo / RUN001")
    assert "**状态**：✗ 未交付" in readme
    assert "## 渲染图（增强后）" not in readme  # 无 enhanced 图
    assert "## 完整性证据" not in readme        # 无 view_evidence
    assert "## 阻断项" in readme
    assert "- blocked_reason" in readme
    assert "## 下一步" in readme
    assert "✗ 当前有阻断项" in readme
    assert "## 证据清单（供审计）" in readme   # 底部清单总在
```

- [ ] **Step 2: 跑测试，确认 fail**

Run: `python -m pytest tests/test_photo3d_delivery_pack.py -q -k "includes_active_run_model_quality_summary or delivery_readme_is_acceptance_page or delivery_readme_degrades_gracefully"`
Expected: FAIL — 旧 `_write_readme` 产的是 `# Photo3D Delivery Package` 项目符号 dump，不含 `# 交付包验收` / `## 模型质量` 等。

- [ ] **Step 3: 重写 `_write_readme`**

把 `tools/photo3d_delivery_pack.py` 里整个 `_write_readme` 函数体替换成：

```python
def _write_readme(path: Path, report: dict[str, Any]) -> None:
    """把交付包 report 渲染成外行用户可读的验收页 README.md。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    lines += _readme_headline(report)
    lines += _readme_images_section(report)
    lines += _readme_view_evidence_section(report)
    lines += _readme_model_quality_section(report)
    lines += _readme_review_status_section(report)
    lines += _readme_next_step_section(report)
    lines += _readme_blocking_section(report)
    lines += _readme_evidence_appendix(report)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
```

- [ ] **Step 4: 跑测试，确认 pass**

Run: `python -m pytest tests/test_photo3d_delivery_pack.py tests/test_photo3d_gate_contract.py -q`
Expected: 全 PASS（含改过的 + 新加的）。

- [ ] **Step 5: Commit**

```bash
git add tools/photo3d_delivery_pack.py tests/test_photo3d_delivery_pack.py
git -c commit.gpgsign=false commit -m "$(cat <<'EOF'
feat(delivery): 把 delivery/README.md 重写成外行用户验收页

_write_readme 改为按序拼接 8 个 section builder：头条状态徽章 + 内嵌 enhanced 图 +
完整性证据（每视角实例计数）+ 模型质量人话摘要 + 复核状态表 + 下一步动作 + 阻断项 +
底部审计证据清单。零行为变更（只 README 内容变丰富）；blocked / 缺数据 run graceful
degradation 仍是合法 markdown。同步更新 model_quality_summary README 断言 +
加验收页 / 降级 两个集成测试。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: 镜像同步 + ruff + 全套件 + 收尾

**Files:** 无新改动；跑校验脚本。

- [ ] **Step 1: 同步 gitignored 镜像**

Run: `python scripts/dev_sync.py && python scripts/dev_sync.py --check && git diff --exit-code -- AGENTS.md`
Expected: dev_sync 成功；`--check` 通过；`AGENTS.md` 无 diff。（镜像 `src/cad_spec_gen/data/tools/photo3d_delivery_pack.py` 是 gitignored，不会出现在 `git status`；如果 `--check` 失败说明没跑第一条 `dev_sync.py`。）

- [ ] **Step 2: ruff**

Run: `python -m ruff check tools/photo3d_delivery_pack.py tests/test_photo3d_delivery_pack.py`
Expected: `All checks passed!`。若报错，修掉（典型：行过长 → 拆字符串；未用 import → 删）。

- [ ] **Step 3: 全套件不回归**

Run: `python -m pytest tests/ -q`
Expected: ≥ 3096 passed / 0 failed（队列 C 后基线 3096；本 PR 新增约 17 个测试 → 约 3113 passed）。若个别 flaky（如 `test_backend_packaging_contract`），重跑确认是环境抖动而非本 PR 引入。

- [ ] **Step 4: 北极星 5 gate 自查**

确认（口头核对，无需命令）：零配置 ✓（无新配置项）/ 稳定可靠 ✓（不动交付/证据/hash 逻辑）/ 结果准确 ✓（README 只反映已有 report 数据）/ SW 装即用 ✓（不涉及 SW）/ 傻瓜式 ✓（外行打开 `delivery/README.md` 就能看懂结果 + 下一步）；Windows-only ✓（纯字符串拼接 + markdown，无平台特定 API）。

- [ ] **Step 5: 若 Step 1-3 有任何额外文件改动（如 ruff 自动修），补 commit**

```bash
git status --short
# 若有改动：
git add -A
git -c commit.gpgsign=false commit -m "$(cat <<'EOF'
chore(delivery): ruff 修复 + 镜像同步

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

否则跳过（无改动则不 commit）。

---

## Self-Review（计划作者自查）

**1. Spec 覆盖：**
- §2 README 头条（subsystem/run_id + 状态徽章 + ordinary_user_message）→ Task 4 `_readme_headline` + Task 6 集成测试 ✓
- §2 渲染图段（内嵌 enhanced 图相对路径 + N 个零件 + 带标注版）→ Task 4 `_readme_images_section` ✓
- §2 完整性证据段（evidence_method + 各视角计数 + 指向 JSON）→ Task 4 `_readme_view_evidence_section` ✓
- §2 模型质量段（ordinary_user_message + readiness/risk + 复核/阻断计数）→ Task 5 `_readme_model_quality_section` ✓
- §2 复核状态表（quality / enhancement / semantic（必需但未做 vs 非强制）/ jury（None → 未运行））→ Task 5 `_readme_review_status_section` ✓
- §2 下一步决策树（阻断 → recommended_next_action → delivered → 兜底）→ Task 5 `_readme_next_step_section` ✓
- §2 阻断项段 → Task 5 `_readme_blocking_section` ✓
- §2 证据清单（供审计）→ Task 5 `_readme_evidence_appendix` ✓
- §2 `_status_badge`（正向/告警/阻断集 + 未知中性）→ Task 2 ✓
- §3 `_pkg_path_relative_to_delivery`（含 ValueError 退化 basename）→ Task 3 ✓
- §3 `_view_evidence_summary` + `report` 加 `view_evidence` → Task 1 ✓
- §3 不改交付逻辑 / cad_pipeline / schema / CI mypy gate → 各 Task「Files」明确列「Modify」范围 ✓
- §3 canonical/mirror dev_sync → Task 7 Step 1 ✓
- §4 TDD（先改 `test_..._model_quality_summary` 断言再重写）→ Task 6 Step 1-4 ✓
- §4 测试①-⑥ → Task 1/4/6 覆盖（① `![](enhanced/...)` Task 4+6；② 复核状态段 Task 5+6；③ 下一步段 Task 5+6；④ N 个零件 + view_evidence Task 1+4+6；⑤ 不带 visible_instance_ids → 段省略 + view_evidence None Task 1+6；⑥ 现有 packages_accepted + blocked-path 仍过 Task 6 Step 4 全套件）✓
- §5 验证清单 → Task 7 ✓
- §6 范围外 → 计划全程未触及 ✓
- §7 调查项 → Task 0 ✓

**2. Placeholder 扫描：** 无 TBD / 「类似 Task N」/ 空 code block；每个改 code 的 step 都给了完整代码。✓

**3. 类型/命名一致性：**
- `_status_badge(status: object) -> str` — Task 2 定义、Task 4/5 用，签名一致 ✓
- `_pkg_path_relative_to_delivery(package_path: str, delivery_dir: str) -> str` — Task 3 定义、Task 4 用，一致 ✓
- `_view_evidence_summary(manifest: dict[str, Any]) -> dict[str, Any] | None` — Task 1 定义、用于 `report["view_evidence"]` ✓
- `_readme_*` 八个 builder 全签名 `(report: dict[str, Any]) -> list[str]`，Task 4/5 定义、Task 6 `_write_readme` 调用，名字逐一对上（`_readme_headline` / `_readme_images_section` / `_readme_view_evidence_section` / `_readme_model_quality_section` / `_readme_review_status_section` / `_readme_next_step_section` / `_readme_blocking_section` / `_readme_evidence_appendix`）✓
- 常量 `_BADGE_POSITIVE/_WARN/_BLOCK/_LABELS`（Task 2）+ `_NEXT_ACTION_LABELS`（Task 5）名字在定义与使用处一致 ✓
- `report` 加 `view_evidence` 的位置（`deliverables` 之后、`evidence_files` 之前）在 Task 1 Step 3 明确 ✓

无发现需修正项。
