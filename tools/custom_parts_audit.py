"""
自制件审计工具 (CP-2 Task 6 of 2026-05-13 quality overhaul)

设计依据：docs/superpowers/specs/2026-05-13-quality-overhaul-design.md §5.1

做 5 件事：
  A. chain_of_custody       — BOM ↔ build_all ↔ STEP ↔ GLB instance 五段链对账
  B. envelope_vs_bbox       — §6.4 envelope (采购件) / scaffold docstring envelope (自制件) vs GLB bbox
  C. scaffold_marker_scan   — 检测残留 codegen 标记 (Auto-generated scaffold / ENRICHED_PLACEHOLDER / etc.)
  D. placement_collapse_detect — 件 bbox 中心两两最小距离 (装配坍塌检测)
  E. model_provenance_fill  — best-effort 摸 ~/.cad-spec-gen/sw_toolbox_index.json / step_cache

输出：
  cad/<sub>/.cad-spec-gen/CUSTOM_PARTS_AUDIT.md   人话报告 (中文)
  cad/<sub>/.cad-spec-gen/CUSTOM_PARTS_AUDIT.json 机器版报告 (下游 contract / CI gate)

Exit code:
  0 PASS  — 全部通过
  2 WARN  — 仅 marker 残留或采购件 envelope 偏差等"次要瑕疵"
  1 FAIL  — 几何错（自制件 envelope drift > 15% / placement 几乎全坍塌）→ 阻断 cad_pipeline.py build

CLI:
  python tools/custom_parts_audit.py <subsystem> [--project-root PATH]
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import math
import pathlib
import re
import sys

# ── 常量阈值（集中在文件顶端，便于审计本身被审计）──────────────────────────────
AUDIT_VERSION = "1.0.0"

# 任一轴上 (GLB bbox / declared envelope) 相对误差超过此阈值 → 触发
ENVELOPE_BBOX_REL_TOL = 0.15
# 任一轴上 (GLB bbox / declared envelope) 占比低于此阈值 → 触发"显著缺失特征"
# 0.60 阈值是反向推：bug A 法兰 disc-only bbox=90×90×30 vs envelope=160×160×20，
# axis_min_ratio = 90/160 = 0.56 < 0.60 → 命中 FAIL；其他已知边缘 case (001-08=0.95,
# 005-02=0.80) 都安全在阈值上方
ENVELOPE_BBOX_AXIS_MIN = 0.60
# 两件 bbox 中心欧氏距 (mm) — 低于此则认为发生"装配坍塌"
PLACEMENT_COLLAPSE_DIST_MM = 10.0
# < 0.1 mm 视为"全堆原点"病灶 → 升级为 FAIL
# (0.5-10 mm 区间常见于 O-ring/垫片等堆叠件，是 WARN 而非 FAIL)
PLACEMENT_HARD_COLLAPSE_MM = 0.1

# scaffold 标记 (regex)；任一文件命中即报"未完工"
SCAFFOLD_MARKER_PATTERNS: tuple[tuple[str, str], ...] = (
    ("auto_scaffold", r"Auto-generated scaffold"),
    ("enriched_placeholder", r"#\s*ENRICHED_PLACEHOLDER"),
    ("approximate_geom", r"Approximate geometry"),
    ("scaffold_default", r"Generated scaffold default"),
    ("refine_actual", r"Refine with actual geometry"),
)

# 不参与自制件审计的辅助/基础设施 .py (不属于"件" .py)
_AUX_PY_STEMS: frozenset[str] = frozenset({
    "build_all", "params", "__init__", "orientation_check", "render_3d",
    "cq_to_dxf", "draw_three_view",
})
_AUX_PY_PREFIXES: tuple[str, ...] = ("assembly", "draw_", "std_")


# ── 数据类 ─────────────────────────────────────────────────────────────────────
@dataclasses.dataclass
class PartRow:
    """BOM 表的一行（§5 BOM table）。"""
    part_no: str
    name: str
    category: str  # 自制 | 外购 | 标准件
    qty: int = 1


@dataclasses.dataclass
class AuditResult:
    subsystem: str
    overall: str        # PASS | WARN | FAIL
    exit_code: int      # 0 / 2 / 1
    findings: list[dict]
    chain: dict
    envelope: dict
    scaffold: dict
    placement: dict
    provenance: dict
    md_path: str | None = None
    json_path: str | None = None


# ── 解析器：CAD_SPEC.md §5 BOM + §6.4 envelope ─────────────────────────────────
def _read_text(p: pathlib.Path) -> str:
    return p.read_text(encoding="utf-8")


def _parse_bom_table(spec_md: str) -> list[PartRow]:
    """从 §5 BOM 表抽 PartRow 列。"""
    m = re.search(r"(?ms)^#+\s*5[^\n]*BOM[^\n]*\n(.+?)^#+", spec_md)
    if not m:
        return []
    rows: list[PartRow] = []
    for ln in m.group(1).splitlines():
        s = ln.strip()
        if not s.startswith("|"):
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if len(cells) < 5:
            continue
        part_no = cells[0]
        if not re.match(r"^(SLP|GIS|EE)-", part_no):
            continue
        try:
            qty = int(cells[3]) if len(cells) > 3 and cells[3] else 1
        except ValueError:
            qty = 1
        category = cells[4] if len(cells) > 4 else ""
        rows.append(PartRow(part_no=part_no, name=cells[1], category=category, qty=qty))
    return rows


def _parse_envelope_table(spec_md: str) -> dict[str, tuple[float, float, float]]:
    """从 §6.4 envelope 表抽 part_no → (a, b, c) mm。"""
    m = re.search(r"(?ms)^#+\s*6\.4[^\n]*\n(.+?)^#+", spec_md)
    if not m:
        return {}
    out: dict[str, tuple[float, float, float]] = {}
    for ln in m.group(1).splitlines():
        s = ln.strip()
        if not s.startswith("|"):
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if len(cells) < 4:
            continue
        part_no = cells[0]
        if not re.match(r"^(SLP|GIS|EE)-", part_no):
            continue
        env = _parse_dim_string(cells[3], cells[2])
        if env is not None:
            out[part_no] = env
    return out


def _parse_dim_string(dim: str, shape: str) -> tuple[float, float, float] | None:
    """'Φ90.0×25.0' / '12.0×50.0×1.0' / '不定' → 三轴 mm。"""
    s = dim.replace("×", "x").replace("*", "x").replace("Φ", "").replace("φ", "")
    nums = [float(p) for p in re.findall(r"[\d.]+", s)]
    shape_l = (shape or "").lower()
    if shape_l.startswith(("cylinder", "disc", "ring")):
        if len(nums) >= 2:
            d, h = nums[0], nums[1]
            return (d, d, h)
    elif shape_l.startswith("box"):
        if len(nums) >= 3:
            return (nums[0], nums[1], nums[2])
    if len(nums) >= 3:
        return (nums[0], nums[1], nums[2])
    return None


def _parse_scaffold_envelope(py_path: pathlib.Path) -> tuple[float, float, float] | None:
    """读 .py docstring 中的 `Envelope: A x B x C mm` (支持 x/×/* 分隔)。"""
    try:
        txt = py_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    m = re.search(
        r"Envelope:\s*([\d.]+)\s*[x×*]\s*([\d.]+)\s*[x×*]\s*([\d.]+)",
        txt,
    )
    if not m:
        return None
    return (float(m.group(1)), float(m.group(2)), float(m.group(3)))


def _scan_scaffold_markers(py_path: pathlib.Path) -> list[tuple[int, str]]:
    """返回 [(line_no, marker_label), ...]。"""
    try:
        txt = py_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    hits: list[tuple[int, str]] = []
    for ln_no, line in enumerate(txt.splitlines(), start=1):
        for label, pat in SCAFFOLD_MARKER_PATTERNS:
            if re.search(pat, line):
                hits.append((ln_no, label))
                break
    return hits


def _build_all_registered_modules(build_all_py: pathlib.Path) -> set[str]:
    """静态扫 _DXF_BUILDS / _STEP_BUILDS / _STD_STEP_BUILDS 等列表里的模块名。"""
    if not build_all_py.exists():
        return set()
    txt = build_all_py.read_text(encoding="utf-8")
    out: set[str] = set()
    for m in re.finditer(r'\(\s*"[^"]+"\s*,\s*"([^"]+)"', txt):
        out.add(m.group(1))
    return out


def _load_glb_instances(glb_path: pathlib.Path) -> dict[str, tuple[tuple[float, ...], tuple[float, ...]]]:
    """GLB scene → {node_name: (world_center, world_extents)}（应用 graph 中的 transform）。"""
    if not glb_path.exists():
        return {}
    try:
        import numpy as np
        import trimesh
    except ImportError:
        return {}
    scene = trimesh.load(glb_path, force="scene")
    if not hasattr(scene, "graph"):
        return {}
    out: dict[str, tuple[tuple[float, ...], tuple[float, ...]]] = {}
    for node in scene.graph.nodes_geometry:
        T, geom_name = scene.graph[node]
        g = scene.geometry[geom_name]
        local_min, local_max = g.bounds
        # 取八个角点，经 world transform 后求 axis-aligned world bbox
        corners = np.array([
            [local_min[0] if (i & 1) == 0 else local_max[0],
             local_min[1] if (i & 2) == 0 else local_max[1],
             local_min[2] if (i & 4) == 0 else local_max[2],
             1.0]
            for i in range(8)
        ])
        world = (T @ corners.T).T[:, :3]
        wmin = world.min(axis=0)
        wmax = world.max(axis=0)
        out[node] = (
            tuple(float(v) for v in (wmin + wmax) / 2.0),
            tuple(float(v) for v in (wmax - wmin)),
        )
    return out


_PART_NO_RE = re.compile(
    r"^(?:STD-)?(SLP-[A-Z0-9]+(?:-[A-Z0-9]+)*|(?:GIS-)?EE-[A-Z0-9]+(?:-[A-Z0-9]+)*)"
)


def _part_no_from_instance_name(name: str) -> str | None:
    """从 GLB node name 抽出 BOM 侧的 part_no（normalize 命名差异）。

    GLB 节点命名约定（codegen 历史遗留多个变体，都需要识别）：
      - 自制件：直接 part_no + 可选 '#NN' 实例号 (e.g. 'SLP-100#01')
      - 外购/标准件经 std 流程：前置 'STD-' 前缀 (e.g. 'STD-GIS-EE-005-01')
      - end_effector 自制件 GLB 端常省略 'GIS-' (e.g. 'EE-001-01' ↔ BOM 'GIS-EE-001-01')

    返回值：BOM 风格 part_no (含 GIS- 前缀)。
    """
    m = _PART_NO_RE.match(name)
    if not m:
        return None
    raw = m.group(1)
    # 把 GLB 端的 'EE-xxx' 归一化到 BOM 端的 'GIS-EE-xxx'
    if raw.startswith("EE-"):
        return "GIS-" + raw
    return raw


# ── 5 个 audit 模块 ────────────────────────────────────────────────────────────
def _candidate_module_names(part_no: str) -> list[str]:
    """根据件号给出 .py 模块名候选 (大小写敏感的项目惯例)。"""
    if part_no.startswith("SLP-"):
        num = part_no.removeprefix("SLP-").lower()
        return [f"p{num}", num, f"std_{num}"]
    if part_no.startswith("GIS-EE-"):
        num = part_no.removeprefix("GIS-EE-").replace("-", "_").lower()
        return [f"ee_{num}"]
    return []


def _expected_step_paths(part_no: str, category: str, output_dir: pathlib.Path) -> list[pathlib.Path]:
    """根据范畴给出可能的 STEP 文件路径。

    项目里两种命名：
      - 自制件：`<part_no>.step` (单独导出时)；多数情况下 build_all 不导自制件 STEP，
        几何来自 assembly.generated.py 内 make_pXXX()，仅 GLB 有
      - 外购/标准件：`<part_no>_std.step` (codegen 约定)
    """
    if category == "自制":
        return [output_dir / f"{part_no}.step"]
    # 外购 / 标准件 (或未标注的旧件) 通常带 _std 后缀
    return [
        output_dir / f"{part_no}_std.step",
        output_dir / f"{part_no}.step",
    ]


def chain_of_custody(
    sub_dir: pathlib.Path,
    bom: list[PartRow],
    glb_instances: dict,
    output_dir: pathlib.Path,
) -> dict:
    registered = _build_all_registered_modules(sub_dir / "build_all.py")
    glb_part_nos: set[str] = set()
    for inst_name in glb_instances:
        pn = _part_no_from_instance_name(inst_name)
        if pn:
            glb_part_nos.add(pn)

    findings: list[dict] = []
    rows: list[dict] = []
    for p in bom:
        mod_candidates = _candidate_module_names(p.part_no)
        # 模块文件本身存在 (源代码层)
        py_exists = any((sub_dir / f"{m}.py").exists() for m in mod_candidates)
        py_module = next((m for m in mod_candidates if (sub_dir / f"{m}.py").exists()), None)
        # build_all 是否登记了这个模块 (登记 → 跑 DXF/STEP 流程；自制件常只走 DXF)
        registered_match = next((m for m in mod_candidates if m in registered), None)
        # STEP 产物 (按范畴分支)
        step_candidates = _expected_step_paths(p.part_no, p.category, output_dir)
        step_found = next((s for s in step_candidates if s.exists()), None)
        in_glb = p.part_no in glb_part_nos

        rows.append({
            "part_no": p.part_no, "name": p.name, "category": p.category, "qty": p.qty,
            "py_module": py_module, "py_exists": py_exists,
            "build_all_module": registered_match,
            "step_path": str(step_found) if step_found else None,
            "step_exists": step_found is not None,
            "in_glb": in_glb,
        })

        # 检查规则（按范畴差异化）
        if p.category == "自制":
            # 必须有 .py（源码层缺 → FAIL）
            if not py_exists:
                findings.append({"severity": "FAIL", "part": p.part_no, "where": "chain.py_missing",
                                 "msg": f"自制件 .py 不存在 (候选: {mod_candidates})"})
            # GLB 缺实例 → WARN：可能是预存的"组件被漏挂"问题，不在 CP-2 critical 的"修过的 bug 反向回归"
            # 范围；critical 回归由 envelope.axis（bug A 模式）+ placement.collapse（bug B 模式）捕获
            if py_exists and not in_glb:
                findings.append({"severity": "WARN", "part": p.part_no, "where": "chain.glb_missing",
                                 "msg": "自制件未进 GLB 实例（assembly 漏挂或 make_*() 失败）"})
        elif p.category == "外购":
            # 外购件应有 _std.step（resolver 生成的代理几何）
            if step_found is None:
                findings.append({"severity": "WARN", "part": p.part_no, "where": "chain.step_missing",
                                 "msg": f"外购 STEP 未输出 (cad/output/{p.part_no}_std.step)"})
            if step_found is not None and not in_glb:
                findings.append({"severity": "WARN", "part": p.part_no, "where": "chain.glb",
                                 "msg": "STEP 存在但未进 GLB 实例 (assembly 漏挂)"})
        # 标准件 (螺栓 / 挡圈 / 销钉 / 螺母 / 销): 按 BOM-qty 大量存在，by-design 不逐件 render
        # → 既不查 STEP 也不查 GLB，避免 fastener bookkeeping 噪声淹没真正的 geometry findings
        # 其他范畴 (空 / 未标) — 不报，避免噪声

    return {
        "rows": rows,
        "glb_instance_count": len(glb_instances),
        "glb_unique_part_count": len(glb_part_nos),
        "findings": findings,
    }


def envelope_vs_bbox(
    sub_dir: pathlib.Path,
    spec_md: str,
    bom: list[PartRow],
    glb_instances: dict,
) -> dict:
    decl = _parse_envelope_table(spec_md)
    scaffold_decl: dict[str, tuple[float, float, float]] = {}
    for p in bom:
        if p.category != "自制":
            continue
        # 只查 ACTIVE 模块 (= _candidate_module_names 第一个存在的 .py)，
        # 避免误用旧 codegen 留下的 legacy 同号 .py (e.g. 201.py vs p201.py 都存在)
        active_module: str | None = next(
            (m for m in _candidate_module_names(p.part_no) if (sub_dir / f"{m}.py").exists()),
            None,
        )
        if active_module is None:
            continue
        env = _parse_scaffold_envelope(sub_dir / f"{active_module}.py")
        if env is not None:
            scaffold_decl[p.part_no] = env

    # GLB part_no → world extents (取第一个实例的 extents)
    glb_by_part: dict[str, tuple[float, float, float]] = {}
    for nm, (_c, e) in glb_instances.items():
        pn = _part_no_from_instance_name(nm)
        if pn is not None and pn not in glb_by_part:
            glb_by_part[pn] = e  # type: ignore[assignment]

    findings: list[dict] = []
    rows: list[dict] = []
    for p in bom:
        ext = glb_by_part.get(p.part_no)
        if ext is None:
            continue  # 不在 GLB → chain_of_custody 会单独报
        if p.part_no in decl:
            truth, src = decl[p.part_no], "§6.4"
        elif p.part_no in scaffold_decl:
            truth, src = scaffold_decl[p.part_no], "scaffold"
        else:
            rows.append({
                "part_no": p.part_no, "category": p.category, "src": "NONE",
                "truth": None, "bbox": list(ext),
            })
            if p.category == "自制":
                findings.append({"severity": "WARN", "part": p.part_no, "where": "envelope.missing_truth",
                                 "msg": "§6.4 和 scaffold docstring 都没有 envelope 数据"})
            continue

        # 按尺寸排序 axis-by-axis 比对（不假设朝向；最稳）
        t_sorted = sorted(truth)
        b_sorted = sorted(ext)
        rel_errors = [
            (abs(b - t) / t if t > 0 else (0.0 if b == 0 else float("inf")))
            for t, b in zip(t_sorted, b_sorted)
        ]
        axis_ratios = [(b / t) for t, b in zip(t_sorted, b_sorted) if t > 0]
        max_rel = max(rel_errors) if rel_errors else 0.0
        axis_min = min(axis_ratios) if axis_ratios else 0.0

        rows.append({
            "part_no": p.part_no, "category": p.category, "src": src,
            "truth": list(truth), "bbox": list(ext),
            "max_rel": max_rel, "axis_min_ratio": axis_min,
        })

        # 区分两类 envelope drift：
        #   a) axis_min_ratio < 阈值 = bbox 显著小于 truth → 缺失特征 (bug A 模式)。
        #      自制件 → FAIL；外购件 → WARN（resolver 可能合理）
        #   b) max_rel > 阈值 但 axis_min ≥ 阈值 = bbox 大于或匹配 truth → §6.4 过时
        #      或精度漂移，统一 WARN
        if axis_min < ENVELOPE_BBOX_AXIS_MIN:
            sev = "FAIL" if p.category == "自制" else "WARN"
            findings.append({
                "severity": sev, "part": p.part_no, "where": "envelope.axis",
                "msg": f"某轴 bbox 只有 {src} 真值的 {axis_min * 100:.0f}% (容忍 {ENVELOPE_BBOX_AXIS_MIN * 100:.0f}%) — 疑似缺失特征",
            })
        elif max_rel > ENVELOPE_BBOX_REL_TOL:
            findings.append({
                "severity": "WARN", "part": p.part_no, "where": "envelope.size",
                "msg": f"bbox 跨度与 {src} 差 {max_rel * 100:.0f}% (容忍 {ENVELOPE_BBOX_REL_TOL * 100:.0f}%) — bbox 大于或匹配 truth，可能 {src} 过时",
            })

    return {"rows": rows, "findings": findings}


def scaffold_marker_scan(sub_dir: pathlib.Path) -> dict:
    findings: list[dict] = []
    rows: list[dict] = []
    for py in sorted(sub_dir.glob("*.py")):
        if py.stem in _AUX_PY_STEMS:
            continue
        if any(py.stem.startswith(p) for p in _AUX_PY_PREFIXES):
            continue
        hits = _scan_scaffold_markers(py)
        if hits:
            rows.append({"file": py.name, "hits": [(ln, lbl) for ln, lbl in hits]})
            findings.append({
                "severity": "WARN", "part": py.stem, "where": "scaffold.marker",
                "msg": f"残留 scaffold/placeholder 标记 ({len(hits)} 处，首处 L{hits[0][0]}: {hits[0][1]})",
            })
    return {"rows": rows, "findings": findings}


def placement_collapse_detect(glb_instances: dict) -> dict:
    centers = [(n, c) for n, (c, _e) in glb_instances.items()]
    if len(centers) < 2:
        return {"closest_pair": None, "min_distance": float("inf"), "findings": []}
    min_d = float("inf")
    min_pair: tuple[str | None, str | None] = (None, None)
    for i in range(len(centers)):
        for j in range(i + 1, len(centers)):
            a, b = centers[i][1], centers[j][1]
            d = math.sqrt(sum((a[k] - b[k]) ** 2 for k in range(3)))
            if d < min_d:
                min_d = d
                min_pair = (centers[i][0], centers[j][0])
    findings: list[dict] = []
    if min_d < PLACEMENT_COLLAPSE_DIST_MM:
        sev = "FAIL" if min_d < PLACEMENT_HARD_COLLAPSE_MM else "WARN"
        findings.append({
            "severity": sev, "part": f"{min_pair[0]}↔{min_pair[1]}",
            "where": "placement.collapse",
            "msg": f"最近两件中心距 {min_d:.2f} mm (阈值 {PLACEMENT_COLLAPSE_DIST_MM:.1f} mm)",
        })
    return {
        "closest_pair": list(min_pair) if min_pair[0] else None,
        "min_distance": float(min_d) if math.isfinite(min_d) else None,
        "findings": findings,
    }


def model_provenance_fill() -> dict:
    """best-effort 摸用户主目录下的 SW Toolbox / step_cache 资源是否存在。"""
    home = pathlib.Path.home()
    index_path = home / ".cad-spec-gen" / "sw_toolbox_index.json"
    cache_dir = home / ".cad-spec-gen" / "step_cache" / "sw_toolbox"
    sw_index_entries = 0
    if index_path.exists():
        try:
            data = json.loads(index_path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                sw_index_entries = len(data)
            elif isinstance(data, list):
                sw_index_entries = len(data)
        except (json.JSONDecodeError, OSError):
            pass
    return {
        "sw_toolbox_index_path": str(index_path),
        "sw_toolbox_index_entries": sw_index_entries,
        "sw_step_cache_dir": str(cache_dir),
        "sw_step_cache_present": cache_dir.exists(),
    }


# ── 报告渲染（中文 MD + JSON）─────────────────────────────────────────────────
def _format_md(d: dict) -> str:
    import datetime

    lines: list[str] = [
        f"# 自制件审计报告 — {d['subsystem']}",
        "",
        f"- 日期：{datetime.date.today().isoformat()}",
        f"- 工具版本：{d['audit_version']}",
        f"- 总体判定：**{d['overall']}**（exit_code = {d['exit_code']}）",
        "",
        "## A · 五段链对账",
        "",
        f"BOM 声明 **{len(d['chain']['rows'])}** 件 → GLB 含 **{d['chain']['glb_unique_part_count']}** 件 / **{d['chain']['glb_instance_count']}** 实例",
        "",
        "| 件号 | 名称 | 范畴 | 数量 | build_all 模块 | STEP | GLB |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for r in d["chain"]["rows"]:
        lines.append(
            f"| {r['part_no']} | {r['name']} | {r['category']} | {r['qty']} "
            f"| {r['build_all_module'] or '—'} "
            f"| {'✓' if r['step_exists'] else '✗'} "
            f"| {'✓' if r['in_glb'] else '✗'} |"
        )

    lines += [
        "",
        "## B · envelope vs GLB bbox 比对",
        "",
        "采购件比对 CAD_SPEC §6.4；自制件比对自身 scaffold docstring `Envelope:` 行。",
        "",
        "| 件号 | 范畴 | 来源 | envelope (mm) | GLB bbox (mm) | 最大轴误差 | 最小轴占比 |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for r in d["envelope"]["rows"]:
        if r.get("truth"):
            t_str = "×".join(f"{v:.1f}" for v in r["truth"])
            b_str = "×".join(f"{v:.1f}" for v in r["bbox"])
            lines.append(
                f"| {r['part_no']} | {r['category']} | {r['src']} | {t_str} | {b_str} "
                f"| {r.get('max_rel', 0) * 100:.0f}% | {r.get('axis_min_ratio', 0) * 100:.0f}% |"
            )
        else:
            b_str = "×".join(f"{v:.1f}" for v in r["bbox"])
            lines.append(f"| {r['part_no']} | {r['category']} | — | (缺) | {b_str} | — | — |")

    lines += [
        "",
        "## C · scaffold 标记扫描",
        "",
    ]
    if not d["scaffold"]["rows"]:
        lines.append("无残留 scaffold/placeholder 标记。")
    else:
        lines += [
            "下列 .py 仍含 codegen 自标「未完工」标记（需要按 CAD_SPEC 行号继续手工补完）：",
            "",
            "| 文件 | 标记数 | 首处行号 |",
            "| --- | --- | --- |",
        ]
        for r in d["scaffold"]["rows"]:
            lines.append(f"| {r['file']} | {len(r['hits'])} | L{r['hits'][0][0]} ({r['hits'][0][1]}) |")

    pl = d["placement"]
    lines += [
        "",
        "## D · 装配坍塌检测",
        "",
        f"件 bbox 中心两两最小距离：**{pl['min_distance']:.2f} mm**"
        f" (阈值 {PLACEMENT_COLLAPSE_DIST_MM:.1f} mm，硬坍塌阈值 {PLACEMENT_HARD_COLLAPSE_MM:.1f} mm)",
    ]
    cp = pl.get("closest_pair")
    if cp:
        lines.append(f"最近对：`{cp[0]}` ↔ `{cp[1]}`")

    pv = d["provenance"]
    lines += [
        "",
        "## E · model_provenance 资源摸底",
        "",
        f"- `~/.cad-spec-gen/sw_toolbox_index.json` 条目数：**{pv['sw_toolbox_index_entries']}**",
        f"- `~/.cad-spec-gen/step_cache/sw_toolbox/` 存在：**{pv['sw_step_cache_present']}**",
        "",
        "> v1 仅摸底；富化 `geometry_report.json::decisions[*].model_provenance` 由 CP-3 任务做。",
        "",
        "## F · findings 汇总",
        "",
    ]
    if not d["findings"]:
        lines.append("（无）")
    else:
        lines += ["| 严重度 | 件 | 位置 | 说明 |", "| --- | --- | --- | --- |"]
        for f in d["findings"]:
            lines.append(f"| **{f['severity']}** | {f['part']} | {f['where']} | {f['msg']} |")

    lines.append("")
    return "\n".join(lines)


# ── 顶层入口 ───────────────────────────────────────────────────────────────────
def audit_subsystem(subsystem: str, *, project_root: str | pathlib.Path | None = None) -> AuditResult:
    """对 cad/<subsystem> 子系统跑完整审计；写双格式报告；返回 AuditResult。"""
    root = pathlib.Path(project_root) if project_root else pathlib.Path(__file__).resolve().parent.parent
    sub_dir = root / "cad" / subsystem
    if not sub_dir.exists():
        raise FileNotFoundError(f"子系统目录不存在: {sub_dir}")

    spec_md = _read_text(sub_dir / "CAD_SPEC.md")
    bom = _parse_bom_table(spec_md)

    output_dir = root / "cad" / "output"
    glb_name = (
        "SLP-000_assembly.glb" if subsystem == "lifting_platform"
        else "EE-000_assembly.glb"
    )
    glb_instances = _load_glb_instances(output_dir / glb_name)

    chain = chain_of_custody(sub_dir, bom, glb_instances, output_dir)
    envelope = envelope_vs_bbox(sub_dir, spec_md, bom, glb_instances)
    scaffold = scaffold_marker_scan(sub_dir)
    placement = placement_collapse_detect(glb_instances)
    provenance = model_provenance_fill()

    all_findings = (
        chain["findings"] + envelope["findings"]
        + scaffold["findings"] + placement["findings"]
    )
    has_fail = any(f["severity"] == "FAIL" for f in all_findings)
    has_warn = any(f["severity"] == "WARN" for f in all_findings)
    overall = "FAIL" if has_fail else ("WARN" if has_warn else "PASS")
    exit_code = 1 if has_fail else (2 if has_warn else 0)

    out_dir = sub_dir / ".cad-spec-gen"
    out_dir.mkdir(parents=True, exist_ok=True)

    data = {
        "audit_version": AUDIT_VERSION, "subsystem": subsystem,
        "overall": overall, "exit_code": exit_code,
        "chain": chain, "envelope": envelope,
        "scaffold": scaffold, "placement": placement,
        "provenance": provenance, "findings": all_findings,
    }
    json_path = out_dir / "CUSTOM_PARTS_AUDIT.json"
    json_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    md_path = out_dir / "CUSTOM_PARTS_AUDIT.md"
    md_path.write_text(_format_md(data), encoding="utf-8")

    return AuditResult(
        subsystem=subsystem, overall=overall, exit_code=exit_code,
        findings=all_findings, chain=chain, envelope=envelope,
        scaffold=scaffold, placement=placement, provenance=provenance,
        md_path=str(md_path), json_path=str(json_path),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="自制件审计：BOM→build_all→STEP→GLB 五段链 + envelope diff + scaffold scan + placement collapse",
    )
    parser.add_argument("subsystem", help="子系统名（end_effector / lifting_platform）")
    parser.add_argument("--project-root", default=None, help="项目根目录（默认推断为本脚本上一级）")
    args = parser.parse_args(argv)
    # Windows GBK 控制台不认 ✅/⚠️/❌ 等 emoji；尽力切到 utf-8，失败就用 ASCII fallback
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except (AttributeError, OSError):
        pass
    try:
        result = audit_subsystem(args.subsystem, project_root=args.project_root)
    except FileNotFoundError as e:
        print(f"审计失败：{e}", file=sys.stderr)
        return 1

    # ASCII fallback：如果 stdout encoding 不能编码 unicode badge，退回 [PASS]/[WARN]/[FAIL]
    enc = (getattr(sys.stdout, "encoding", None) or "ascii").lower()
    if enc.startswith("utf"):
        badge = {"PASS": "✅", "WARN": "⚠️", "FAIL": "❌"}.get(result.overall, "?")
    else:
        badge = {"PASS": "[PASS]", "WARN": "[WARN]", "FAIL": "[FAIL]"}.get(result.overall, "?")
    print(f"{badge} 自制件审计 [{args.subsystem}]：{result.overall} (exit={result.exit_code})")
    print(f"   报告：{result.md_path}")
    print(f"         {result.json_path}")
    if result.findings:
        print("   findings:")
        for f in result.findings[:10]:
            print(f"     [{f['severity']:4s}] {f['part']:30s} {f['where']:24s} {f['msg']}")
        if len(result.findings) > 10:
            print(f"     ... 余 {len(result.findings) - 10} 条详见报告")
    return result.exit_code


if __name__ == "__main__":
    sys.exit(main())
