# Assembly Positioning Enhancement — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate part separation/floating in 3D assembly rendering by extracting rich positioning data from source design documents instead of heuristic stacking.

**Architecture:** Four priority levels (P0→P1a/P1b→P2) modify 8 skill code files. P0 adds exclude marking to prevent orphan assemblies. P1a extracts serial stacking chains + computes Z offsets. P1b extracts part envelopes from multiple sources. P2 integrates all data into CAD_SPEC.md rendering and gen_assembly consumption. All changes target pipeline code only — no intermediate product files are touched.

**Tech Stack:** Python 3.12, CadQuery, Jinja2, pytest

**Design Document:** `docs/assembly_positioning_enhancement_plan.md` (1142 lines, 4 rounds of review)

---

## Task 1: P0 — Exclude Marking in Assembly Layers (extractors + gen + gen_assembly)

**Files:**
- Modify: `cad_spec_extractors.py:620-667` — `extract_assembly_pose()`
- Modify: `cad_spec_extractors.py:545-618` — `extract_connection_matrix()`
- Modify: `cad_spec_extractors.py:722-795` — `extract_render_plan()` constraint classification
- Modify: `cad_spec_gen.py:207-214` — `render_spec()` §6.2 table
- Modify: `codegen/gen_assembly.py:492-718` — `generate_assembly()` skip excluded
- Test: `tests/test_gen_assembly.py`

- [ ] **Step 1: Modify `extract_assembly_pose()` — keep excluded parts with marker instead of dropping**

Replace the BUG-10 hardcoded `continue` (lines 654-657) with an `exclude` field. Also parse `offset` and `axis_dir` into structured fields (`offset_parsed`, `axis_dir_parsed`).

```python
# In extract_assembly_pose(), replace:
#   if "GIS-EE-006" in part_name or "信号调理" in part_name:
#       continue
# With:
exclude = False
exclude_reason = ""
# Check negative constraints for assembly_exclude
# (will be populated by extract_render_plan constraints later)
# For now, keep all parts, mark exclude via post-processing

result["layers"].append({
    "level": ...,
    "part": ...,
    "fixed_moving": ...,
    "connection": ...,
    "offset": ...,           # raw text preserved
    "offset_parsed": _parse_offset(offset_text),  # NEW structured
    "axis_dir": ...,         # raw text preserved
    "axis_dir_parsed": _parse_axis_dir(axis_dir_text),  # NEW structured
    "exclude": exclude,
    "exclude_reason": exclude_reason,
})
```

Add helper functions `_parse_offset()` and `_parse_axis_dir()` at module level:
```python
def _parse_offset(text: str) -> dict:
    """Parse 'Z=+73mm(向上)' → {z: 73.0, r: None, theta: None, is_origin: False}"""
    result = {"z": None, "r": None, "theta": None, "is_origin": False}
    if not text:
        return result
    if "基准" in text or "原点" in text:
        result["z"] = 0.0
        result["is_origin"] = True
    m = re.search(r"Z\s*=\s*([+-]?\d+(?:\.\d+)?)", text)
    if m:
        result["z"] = float(m.group(1))
    m = re.search(r"R\s*[=≈]\s*(\d+(?:\.\d+)?)", text)
    if m:
        result["r"] = float(m.group(1))
    m = re.search(r"θ\s*=\s*(\d+(?:\.\d+)?)", text)
    if m:
        result["theta"] = float(m.group(1))
    return result

def _parse_axis_dir(text: str) -> list:
    """Parse multi-clause axis_dir into structured list."""
    if not text:
        return []
    clauses = re.split(r"[，,]", text)
    parsed = []
    for clause in clauses:
        clause = clause.strip()
        if not clause:
            continue
        entry = {"keyword": "", "direction": (0,0,-1), "rotation": None}
        # Extract keyword (first 2-3 Chinese chars before 轴/面)
        kw_m = re.match(r"([\u4e00-\u9fff]{1,4})[轴面]", clause)
        if kw_m:
            entry["keyword"] = kw_m.group(1)
        # Determine direction
        if any(k in clause for k in ["盘面∥XY", "环∥XY", "弧形∥XY"]):
            entry["direction"] = (0, 0, 1)
        elif any(k in clause for k in ["沿-Z", "-Z", "向下", "垂直向下"]):
            entry["direction"] = (0, 0, -1)
        elif any(k in clause for k in ["沿+Z", "+Z", "向上"]):
            entry["direction"] = (0, 0, 1)
        elif any(k in clause for k in ["沿Z", "垂直", "⊥法兰"]):
            entry["direction"] = (0, 0, -1)
        elif any(k in clause for k in ["∥XY", "水平", "径向外伸", "径向"]):
            entry["direction"] = (1, 0, 0)
            entry["rotation"] = {"axis": (1, 0, 0), "angle": 90}
        parsed.append(entry)
    return parsed
```

- [ ] **Step 2: Add exclude post-processing using negative constraints**

In `cad_spec_gen.py:process_doc()`, after extracting render_plan and assembly, cross-reference constraints to mark excluded assemblies:

```python
# After line 394 (data dict assembled), add:
_apply_exclude_markers(data)
```

New function in `cad_spec_gen.py`:
```python
def _apply_exclude_markers(data: dict):
    """Cross-reference negative constraints to mark excluded assemblies in layers."""
    constraints = data.get("render_plan", {}).get("constraints", [])
    layers = data.get("assembly", {}).get("layers", [])
    
    exclude_keywords = ["不在", "不画", "排除", "不属于", "not on", "exclude"]
    
    for constraint in constraints:
        desc = constraint.get("description", "")
        if not any(kw in desc for kw in exclude_keywords):
            continue
        # Extract part numbers from description
        pnos = re.findall(r"[A-Z]+-[A-Z]+-\d+", desc)
        for layer in layers:
            part_text = layer.get("part", "")
            for pno in pnos:
                if pno in part_text:
                    layer["exclude"] = True
                    layer["exclude_reason"] = desc[:80]
```

- [ ] **Step 3: Update `extract_connection_matrix()` to skip excluded layers**

In `extract_connection_matrix()`, filter out excluded layers before generating connections:

```python
# At line 557, change:
#   for i in range(1, len(assembly_layers)):
# To:
active_layers = [l for l in assembly_layers if not l.get("exclude", False)]
for i in range(1, len(active_layers)):
    b = active_layers[i]
    ...
```

- [ ] **Step 4: Update `render_spec()` §6.2 table to include exclude column**

In `cad_spec_gen.py`, modify the §6.2 rendering (lines 207-214):

```python
sections.append("### 6.2 装配层叠")
sections.append("")
sections.append(_md_table(
    ["层级", "零件/模块", "固定/运动", "连接方式", "偏移(Z/R/θ)", "轴线方向", "排除"],
    [[l["level"], l["part"], l["fixed_moving"], l["connection"],
      l["offset"], l["axis_dir"],
      "exclude" if l.get("exclude") else ""]
     for l in assembly.get("layers", [])]
))
```

- [ ] **Step 5: Update `gen_assembly.py` to skip excluded assemblies**

In `generate_assembly()` (around line 546), skip excluded assemblies:

```python
# In the loop: for i, assy in enumerate(assemblies):
# Add at the start of the loop body:
# Check if this assembly is excluded via §6.2 exclude column
if _is_excluded(assy["part_no"], spec_path):
    continue
```

Add helper:
```python
def _is_excluded(part_no: str, spec_path: str) -> bool:
    """Check if assembly is marked as excluded in §6.2."""
    text = Path(spec_path).read_text(encoding="utf-8")
    # Look for the part_no in §6.2 table rows with 'exclude' marker
    for line in text.splitlines():
        if part_no in line and "exclude" in line.lower():
            return True
    return False
```

- [ ] **Step 6: Test P0 changes**

Run: `python cad_spec_gen.py D:/Work/cad-tests/04-末端执行机构设计.md --review-only`
Expected: DESIGN_REVIEW should no longer have B1 warning about EE-006 "悬空零件"

Run: `python codegen/gen_assembly.py cad/end_effector/CAD_SPEC.md --mode force`
Expected: Generated assembly.py should NOT contain EE-006 parts

- [ ] **Step 7: Commit P0**

```bash
git add cad_spec_extractors.py cad_spec_gen.py codegen/gen_assembly.py
git commit -m "feat(P0): add exclude marking for non-local assemblies in §6.2"
```

---

## Task 2: P1b — Extract Part Envelopes + Expand STD_PART_DIMENSIONS

**Files:**
- Modify: `cad_spec_extractors.py` — add `extract_part_envelopes()`
- Modify: `cad_spec_defaults.py:130-178` — expand `STD_PART_DIMENSIONS`, add `MATERIAL_PROPS`

- [ ] **Step 1: Expand STD_PART_DIMENSIONS in cad_spec_defaults.py**

Add after line 167 (before generic fallbacks):

```python
# --- Linear Bearings ---
"LM6UU":   {"od": 12, "id": 6, "w": 19},
"LM8UU":   {"od": 15, "id": 8, "w": 24},
"LM10UU":  {"od": 19, "id": 10, "w": 29},
"LM12UU":  {"od": 21, "id": 12, "w": 30},
# --- More Deep Groove Bearings (ISO 15) ---
"6000ZZ":  {"od": 26, "id": 10, "w": 8},
"6001ZZ":  {"od": 28, "id": 12, "w": 8},
"6200ZZ":  {"od": 30, "id": 10, "w": 9},
"6201ZZ":  {"od": 32, "id": 12, "w": 10},
# --- NEMA Stepper Motors ---
"NEMA 17": {"w": 42.3, "h": 42.3, "l": 48, "shaft_d": 5, "shaft_l": 24},
"NEMA 23": {"w": 57, "h": 57, "l": 56, "shaft_d": 6.35, "shaft_l": 24},
# --- Additional Tanks ---
"_tank_small": {"d": 25, "l": 110},
```

- [ ] **Step 2: Add MATERIAL_PROPS dict in cad_spec_defaults.py**

Add after STD_PART_DIMENSIONS:

```python
MATERIAL_PROPS = {
    "7075-T6":  {"density": 2.81, "color": (0.15, 0.15, 0.15), "ra_default": 3.2, "material_type": "al"},
    "6063":     {"density": 2.69, "color": (0.20, 0.20, 0.20), "ra_default": 3.2, "material_type": "al"},
    "6061-T6":  {"density": 2.70, "color": (0.18, 0.18, 0.18), "ra_default": 3.2, "material_type": "al"},
    "PEEK":     {"density": 1.31, "color": (0.85, 0.65, 0.13), "ra_default": 3.2, "material_type": "peek"},
    "SUS316L":  {"density": 7.98, "color": (0.82, 0.82, 0.85), "ra_default": 1.6, "material_type": "steel"},
    "SUS304":   {"density": 7.93, "color": (0.80, 0.80, 0.83), "ra_default": 1.6, "material_type": "steel"},
    "SUS303":   {"density": 7.90, "color": (0.78, 0.78, 0.80), "ra_default": 1.6, "material_type": "steel"},
    "FKM":      {"density": 1.80, "color": (0.08, 0.08, 0.08), "ra_default": 6.3, "material_type": "rubber"},
    "PA66":     {"density": 1.14, "color": (0.10, 0.10, 0.10), "ra_default": 3.2, "material_type": "plastic"},
    "POM":      {"density": 1.41, "color": (0.90, 0.88, 0.85), "ra_default": 1.6, "material_type": "plastic"},
    "硅橡胶":   {"density": 1.10, "color": (0.75, 0.60, 0.45), "ra_default": 6.3, "material_type": "rubber"},
}
```

- [ ] **Step 3: Add `extract_part_envelopes()` in cad_spec_extractors.py**

Add new function after `extract_part_features()`:

```python
def extract_part_envelopes(lines: list, bom_data: Optional[dict] = None,
                           visual_ids: list = None, params: list = None) -> dict:
    """从多来源提取零件包络尺寸，按优先级合并。

    Priority: P1(零件级参数表) > P2(叙述包络) > P3(BOM材质列) > P4(视觉标识) > P5(全局参数)

    Returns: {part_no: {"type": "cylinder"|"box"|"disc"|"ring",
                         "d"|"w": float, "h"|"l": float, "source": str}}
    """
    result = {}

    # P3: BOM 材质列
    if bom_data:
        for assy in bom_data.get("assemblies", []):
            for part in assy.get("parts", []):
                pno = part.get("part_no", "")
                material = part.get("material", "")
                dims = _parse_dims_from_text(material)
                if dims and pno:
                    result[pno] = _dims_to_envelope(dims, f"P3:BOM")

    # P4: 视觉标识表 size 列
    if visual_ids:
        for v in visual_ids:
            part_name = v.get("part", "")
            size_text = v.get("size", "")
            if not size_text or size_text == "[待定]":
                continue
            dims = _parse_dims_from_text(size_text)
            if dims:
                # Match to BOM part_no by name
                pno = _match_visual_to_bom(part_name, bom_data)
                if pno:
                    result[pno] = _dims_to_envelope(dims, "P4:visual")

    # P2: 叙述文字中"模块包络尺寸：W×D×H"
    text = "\n".join(lines)
    for m in re.finditer(r"模块包络尺寸[：:]\s*(\d+(?:\.\d+)?)\s*[×xX]\s*(\d+(?:\.\d+)?)\s*[×xX]\s*(\d+(?:\.\d+)?)\s*mm", text):
        w, d, h = float(m.group(1)), float(m.group(2)), float(m.group(3))
        # Find nearest assembly context
        pos = m.start()
        context = text[max(0, pos-200):pos]
        pno = _find_nearest_part_no(context, bom_data)
        if pno:
            result[pno] = {"type": "box", "w": w, "d": d, "h": h, "source": "P2:narrative"}

    # P1: 零件级参数表（含"外形"/"尺寸"列的子表格）
    part_tables = extract_tables(lines, column_keywords=["外形", "尺寸参数"])
    for tbl in part_tables:
        cols = [c.lower() for c in tbl["columns"]]
        name_i = next((i for i, c in enumerate(cols) if "零件" in c), 0)
        dim_i = next((i for i, c in enumerate(cols) if "设计值" in c or "尺寸" in c), -1)
        if dim_i < 0:
            continue
        for row in tbl["rows"]:
            part_name = row[name_i].strip() if name_i < len(row) else ""
            dim_text = row[dim_i].strip() if dim_i < len(row) else ""
            dims = _parse_dims_from_text(dim_text)
            if dims:
                pno = _match_name_to_bom(part_name, bom_data)
                if pno:
                    result[pno] = _dims_to_envelope(dims, "P1:part_table")

    return result


def _dims_to_envelope(dims: dict, source: str) -> dict:
    """Convert raw dims dict to envelope format."""
    if "d" in dims and "l" in dims:
        return {"type": "cylinder", "d": dims["d"], "h": dims["l"], "source": source}
    elif "w" in dims and "h" in dims and "l" in dims:
        return {"type": "box", "w": dims["w"], "d": dims.get("h", dims["w"]), "h": dims["l"], "source": source}
    elif "od" in dims:
        return {"type": "ring", "d": dims["od"], "h": dims.get("w", dims.get("h", 5)), "source": source}
    elif "d" in dims:
        return {"type": "disc", "d": dims["d"], "h": max(5, dims["d"] * 0.25), "source": source}
    return {"type": "box", "w": 20, "d": 20, "h": 20, "source": source + "(fallback)"}


def _match_name_to_bom(name: str, bom_data: Optional[dict]) -> Optional[str]:
    """Match a Chinese part name to BOM part_no by prefix matching."""
    if not bom_data or not name:
        return None
    keywords = [name[:n] for n in (4, 3, 2) if len(name) >= n]
    for assy in bom_data.get("assemblies", []):
        for part in assy.get("parts", []):
            pname = part.get("name", "")
            for kw in keywords:
                if kw in pname:
                    return part.get("part_no")
    return None


def _match_visual_to_bom(name: str, bom_data: Optional[dict]) -> Optional[str]:
    """Match visual ID part name to BOM."""
    return _match_name_to_bom(name, bom_data)


def _find_nearest_part_no(context: str, bom_data: Optional[dict]) -> Optional[str]:
    """Find nearest part_no mentioned in text context."""
    if not bom_data:
        return None
    # Try to find a part number pattern
    m = re.search(r"[A-Z]+-[A-Z]+-\d+", context)
    if m:
        # Find in BOM assemblies
        prefix = m.group(0)
        for assy in bom_data.get("assemblies", []):
            if assy.get("part_no", "").startswith(prefix[:prefix.rfind("-")]):
                return assy["part_no"]
    return None
```

- [ ] **Step 4: Wire `extract_part_envelopes()` into `process_doc()`**

In `cad_spec_gen.py`, after line 369 (visual_ids extraction):

```python
# Part envelopes (multi-source)
part_envelopes = extract_part_envelopes(lines, bom, visual_ids, params)
print(f"  §6.4 Envelopes: {len(part_envelopes)} parts")
```

Add to data dict (line 386+):
```python
data["part_envelopes"] = part_envelopes
```

- [ ] **Step 5: Commit P1b**

```bash
git add cad_spec_extractors.py cad_spec_defaults.py cad_spec_gen.py
git commit -m "feat(P1b): extract part envelopes from multiple sources + expand STD_PART_DIMENSIONS"
```

---

## Task 3: P1a — Extract Serial Stacking Chains + Compute Offsets

**Files:**
- Modify: `cad_spec_extractors.py` — add chain extraction in `extract_part_placements()`
- Modify: `cad_spec_defaults.py` — add `compute_serial_offsets()`

- [ ] **Step 1: Add `extract_part_placements()` to cad_spec_extractors.py**

This function scans for → chain syntax in fenced code blocks and narrative text:

```python
def extract_part_placements(lines: list, bom_data: Optional[dict] = None,
                             assembly_layers: list = None) -> list:
    """提取零件级定位信息：串联堆叠链 + 非轴向定位描述。

    Returns: list of placement dicts:
      [{"assembly": str, "anchor": str, "direction": tuple,
        "mode": "axial_stack"|"radial_extend"|...,
        "chain": [{part_name, part_no, dims, connection, sub_assembly}]}]
    """
    placements = []
    text = "\n".join(lines)

    # --- Part 1: Extract axial_stack chains from → syntax ---
    # Find fenced code blocks and narrative text with → chains
    chain_pattern = re.compile(
        r"(?:```[^\n]*\n)((?:.*?→.*?\n)+)(?:```)|"  # fenced code block
        r"((?:^[ \t]*→.*$\n?){2,})",                  # inline → lines
        re.MULTILINE
    )

    for match in chain_pattern.finditer(text):
        block = match.group(1) or match.group(2)
        if not block:
            continue

        chain_lines_raw = [l.strip() for l in block.strip().splitlines() if "→" in l or l.strip()]
        if len(chain_lines_raw) < 2:
            continue

        # Detect assembly context from preceding text
        ctx_start = max(0, match.start() - 500)
        context = text[ctx_start:match.start()]
        assembly_pno = _detect_assembly_context(context, bom_data)

        # Parse anchor (first node before first →)
        anchor = ""
        first_line = chain_lines_raw[0] if chain_lines_raw else ""
        anchor_m = re.match(r"^([^→]+?)(?:\s*→|$)", first_line)
        if anchor_m:
            anchor = anchor_m.group(1).strip()

        # Parse chain nodes
        nodes = []
        # Flatten all → separated items
        full_text = " ".join(chain_lines_raw)
        items = re.split(r"→", full_text)

        for item in items[1:]:  # skip anchor
            item = item.strip()
            if not item:
                continue
            node = _parse_chain_node(item, bom_data)
            nodes.append(node)

        if nodes:
            # Determine direction from assembly layers
            direction = (0, 0, -1)  # default
            if assembly_layers and assembly_pno:
                for layer in assembly_layers:
                    if assembly_pno in layer.get("part", ""):
                        parsed = layer.get("axis_dir_parsed", [])
                        if parsed:
                            direction = parsed[0].get("direction", (0, 0, -1))

            placements.append({
                "assembly": assembly_pno or "",
                "anchor": anchor,
                "direction": direction,
                "mode": "axial_stack",
                "chain": nodes,
            })

    # --- Part 2: Extract non-axial placements from narrative ---
    placements.extend(_extract_non_axial_placements(lines, bom_data))

    return placements


def _parse_chain_node(text: str, bom_data) -> dict:
    """Parse a single → chain node like '力传感器KWR42(Φ42×20mm, 70g)'."""
    node = {"part_name": "", "part_no": None, "dims": None,
            "connection": None, "sub_assembly": None}

    # Strip connection prefix: [4×M3螺栓] → actual part
    conn_m = re.match(r"\[([^\]]+)\]\s*", text)
    if conn_m:
        node["connection"] = conn_m.group(1)
        text = text[conn_m.end():]

    # Extract dimensions from parentheses
    dim_m = re.search(r"\(([^)]+)\)", text)
    if dim_m:
        dim_text = dim_m.group(1)
        from cad_spec_defaults import _parse_dims_from_text
        dims = _parse_dims_from_text(dim_text)
        if dims:
            node["dims"] = _dims_to_envelope(dims, "chain")
        # Remove dims from name
        name = text[:dim_m.start()].strip()
    else:
        name = text.strip()

    node["part_name"] = name

    # Match to BOM
    if bom_data:
        node["part_no"] = _match_name_to_bom(name, bom_data)

    return node


def _detect_assembly_context(context: str, bom_data) -> Optional[str]:
    """Detect which assembly a chain belongs to from surrounding text."""
    if not bom_data:
        return None
    # Look for part numbers
    pnos = re.findall(r"([A-Z]+-[A-Z]+-\d{3})", context)
    if pnos:
        return pnos[-1]  # nearest
    # Look for assembly names
    for assy in bom_data.get("assemblies", []):
        name = assy.get("name", "")
        if name and name[:4] in context:
            return assy.get("part_no")
    return None


def _extract_non_axial_placements(lines: list, bom_data) -> list:
    """Extract radial_extend, side_mount, coaxial, lateral_array from narrative."""
    placements = []
    text = "\n".join(lines)

    patterns = [
        (r"(沿.{0,4}径向|轴线与悬臂共线).{0,6}(向外|外伸|延伸)", "radial_extend"),
        (r"(安装于|位于).{0,4}(侧壁|侧面|外侧).{0,10}(竖直|并排)", "side_mount"),
        (r"(压入|嵌入|过盈配合)", "coaxial"),
        (r"(并列|并排).{0,6}间距\s*(\d+)\s*mm", "lateral_array"),
        (r"(安装于|位于).{0,4}(顶部|底部|末端|端部)", "extremity"),
    ]

    for pattern, mode in patterns:
        for m in re.finditer(pattern, text):
            ctx_start = max(0, m.start() - 300)
            context = text[ctx_start:m.start() + 100]
            # Find associated part
            pno_m = re.search(r"([A-Z]+-[A-Z]+-\d+-\d+)", context)
            if not pno_m and bom_data:
                # Try name matching
                for assy in bom_data.get("assemblies", []):
                    for part in assy.get("parts", []):
                        if part.get("name", "")[:3] in context:
                            pno_m_val = part.get("part_no")
                            break

            params = {}
            if mode == "radial_extend":
                params["rotation"] = {"axis": (1, 0, 0), "angle": 90}
            elif mode == "lateral_array":
                pitch_m = re.search(r"间距\s*(\d+)", m.group(0))
                if pitch_m:
                    params["pitch"] = float(pitch_m.group(1))

            placements.append({
                "assembly": "",
                "part_no": pno_m.group(1) if pno_m else None,
                "mode": mode,
                "params": params,
                "source": f"text:{mode}",
                "confidence": "medium",
            })

    return placements
```

- [ ] **Step 2: Add `compute_serial_offsets()` to cad_spec_defaults.py**

```python
def compute_serial_offsets(placements: list, envelopes: dict,
                           connections: list = None) -> dict:
    """从串联堆叠链计算零件底面 Z 偏移（工位局部坐标）。

    Direction-aware: supports (0,0,-1), (0,0,+1), (1,0,0), etc.

    Returns: {part_no: {"z": float, "mode": str, "source": str, "confidence": str}}
    """
    result = {}

    for placement in placements:
        if placement.get("mode") != "axial_stack":
            continue
        chain = placement.get("chain", [])
        if not chain:
            continue

        d = placement.get("direction", (0, 0, -1))
        # Determine primary axis and sign
        if abs(d[2]) >= abs(d[0]) and abs(d[2]) >= abs(d[1]):
            sign = -1 if d[2] < 0 else 1
            axis = "z"
        elif abs(d[0]) >= abs(d[1]):
            sign = -1 if d[0] < 0 else 1
            axis = "x"
        else:
            sign = -1 if d[1] < 0 else 1
            axis = "y"

        cursor = 0.0

        # Sub-assembly merging: group consecutive same-sub_assembly nodes
        merged_chain = _merge_sub_assemblies(chain)

        for i, node in enumerate(merged_chain):
            pno = node.get("part_no")
            if not pno:
                # Skip nodes that couldn't be matched to BOM
                # but still accumulate height
                h = _get_node_height(node, envelopes)
                if sign < 0:
                    cursor -= h
                else:
                    cursor += h
                continue

            h = _get_node_height(node, envelopes)

            # axial_gap from connections
            gap = 0.0
            if connections and i > 0:
                prev_pno = merged_chain[i - 1].get("part_no")
                if prev_pno:
                    for conn in connections:
                        if ((prev_pno in conn.get("partA", "") and pno in conn.get("partB", "")) or
                            (pno in conn.get("partA", "") and prev_pno in conn.get("partB", ""))):
                            gap = conn.get("axial_gap", 0.0)
                            break

            if sign < 0:
                cursor -= abs(gap)
                bottom = cursor - h
                result[pno] = {
                    axis: bottom,
                    "h": h,
                    "mode": "axial_stack",
                    "source": "serial_chain",
                    "confidence": "high",
                }
                cursor = bottom
            else:
                cursor += abs(gap)
                bottom = cursor
                result[pno] = {
                    axis: bottom,
                    "h": h,
                    "mode": "axial_stack",
                    "source": "serial_chain",
                    "confidence": "high",
                }
                cursor += h

    return result


def _merge_sub_assemblies(chain: list) -> list:
    """Merge consecutive nodes with same sub_assembly into single unit."""
    merged = []
    i = 0
    while i < len(chain):
        node = chain[i]
        sa = node.get("sub_assembly")
        if sa:
            # Collect consecutive nodes with same sub_assembly
            group = [node]
            j = i + 1
            while j < len(chain) and chain[j].get("sub_assembly") == sa:
                group.append(chain[j])
                j += 1
            # Merge: total height = sum, part_no = sub_assembly value
            total_h = sum(_get_node_height_raw(n) for n in group)
            merged.append({
                "part_name": f"{sa}(合并)",
                "part_no": sa,
                "dims": {"type": "cylinder", "h": total_h},
                "connection": group[0].get("connection"),
                "sub_assembly": None,
            })
            i = j
        else:
            merged.append(node)
            i += 1
    return merged


def _get_node_height(node: dict, envelopes: dict) -> float:
    """Get height from node dims, then envelope, then default."""
    h = _get_node_height_raw(node)
    if h > 0:
        return h
    pno = node.get("part_no")
    if pno and pno in envelopes:
        return envelopes[pno].get("h", 20.0)
    return 20.0  # fallback


def _get_node_height_raw(node: dict) -> float:
    """Get height from node dims only."""
    dims = node.get("dims")
    if not dims:
        return 0.0
    return dims.get("h", dims.get("l", 0.0))
```

- [ ] **Step 3: Wire into process_doc()**

In `cad_spec_gen.py`, add after part_envelopes extraction:

```python
# Part placements (serial chains + non-axial)
from cad_spec_extractors import extract_part_placements
placements = extract_part_placements(lines, bom, assembly.get("layers", []))
print(f"  §6.3 Placements: {len(placements)} chains/modes")

# Compute serial offsets
from cad_spec_defaults import compute_serial_offsets
part_offsets = compute_serial_offsets(placements, part_envelopes, connections)
print(f"  §6.3 Offsets: {len(part_offsets)} parts positioned")

data["placements"] = placements
data["assembly"]["part_offsets"] = part_offsets
```

- [ ] **Step 4: Commit P1a**

```bash
git add cad_spec_extractors.py cad_spec_defaults.py cad_spec_gen.py
git commit -m "feat(P1a): extract serial stacking chains + compute part-level Z offsets"
```

---

## Task 4: P2 — Integration (Rendering §6.3/§6.4/§9 + gen_assembly Consumption + Reviewer B10-B16)

**Files:**
- Modify: `cad_spec_gen.py:194-269` — render new sections
- Modify: `codegen/gen_assembly.py:397-490` — consume §6.3 data
- Modify: `cad_spec_reviewer.py:248-534` — add B10-B16 checks
- Modify: `templates/assembly.py.j2` — confidence comments

- [ ] **Step 1: Add §6.3, §6.4, §9 rendering in render_spec()**

After the §6.2 block (line 214) in `cad_spec_gen.py`:

```python
# §6.3 零件级定位
part_offsets = assembly.get("part_offsets", {})
if part_offsets:
    sections.append("### 6.3 零件级定位")
    sections.append("")
    # Group by assembly
    assy_groups = {}
    for pno, off in part_offsets.items():
        prefix = "-".join(pno.split("-")[:3])
        assy_groups.setdefault(prefix, []).append((pno, off))
    for prefix, items in sorted(assy_groups.items()):
        sections.append(f"#### {prefix}")
        sections.append("")
        sections.append(_md_table(
            ["料号", "零件名", "模式", "高度(mm)", "底面Z(mm)", "XY偏移", "旋转", "来源", "置信度"],
            [[pno,
              _lookup_part_name(pno, data.get("bom")),
              off.get("mode", "axial_stack"),
              f"{off.get('h', '')}", f"{off.get('z', '')}", 
              off.get("xy_offset", "—"),
              off.get("rotation", "—"),
              off.get("source", ""),
              off.get("confidence", "")]
             for pno, off in sorted(items)]
        ))

# §6.4 零件包络尺寸
envelopes = data.get("part_envelopes", {})
if envelopes:
    sections.append("### 6.4 零件包络尺寸")
    sections.append("")
    sections.append(_md_table(
        ["料号", "零件名", "类型", "尺寸(mm)", "来源"],
        [[pno,
          _lookup_part_name(pno, data.get("bom")),
          env.get("type", ""),
          _format_dims(env),
          env.get("source", "")]
         for pno, env in sorted(envelopes.items())]
    ))

# §9 装配约束 (from classified constraints)
constraints = data.get("render_plan", {}).get("constraints", [])
excludes = [l for l in assembly.get("layers", []) if l.get("exclude")]
if excludes or constraints:
    sections.append("## 9. 装配约束")
    sections.append("")
    if excludes:
        sections.append("### 9.1 装配排除")
        sections.append("")
        sections.append(_md_table(
            ["零件/模块", "原因"],
            [[l["part"], l.get("exclude_reason", "")] for l in excludes]
        ))
```

Add helpers:
```python
def _lookup_part_name(pno: str, bom) -> str:
    if not bom:
        return ""
    for assy in bom.get("assemblies", []):
        if assy.get("part_no") == pno:
            return assy.get("name", "")
        for part in assy.get("parts", []):
            if part.get("part_no") == pno:
                return part.get("name", "")
    return ""

def _format_dims(env: dict) -> str:
    t = env.get("type", "")
    if t in ("cylinder", "disc"):
        return f"Φ{env.get('d', '')}×{env.get('h', '')}"
    elif t == "box":
        return f"{env.get('w', '')}×{env.get('d', '')}×{env.get('h', '')}"
    elif t == "ring":
        return f"Φ{env.get('d', '')}×{env.get('h', '')}"
    return ""
```

- [ ] **Step 2: Update gen_assembly.py to consume §6.3**

Add `_parse_part_positions()` function and modify `_resolve_child_offsets()`:

```python
def _parse_part_positions(spec_path: str) -> dict:
    """Parse §6.3 part-level positioning table from CAD_SPEC.md."""
    text = Path(spec_path).read_text(encoding="utf-8")
    positions = {}
    in_section = False
    for line in text.splitlines():
        if "### 6.3" in line and "零件级定位" in line:
            in_section = True
            continue
        if in_section and line.startswith("### ") and "6.3" not in line:
            break
        if not in_section or not line.startswith("|") or "---" in line:
            continue
        cells = [c.strip() for c in line.split("|") if c.strip()]
        if len(cells) >= 5 and re.match(r"[A-Z]+-", cells[0]):
            pno = cells[0]
            mode = cells[2] if len(cells) > 2 else "axial_stack"
            try:
                z = float(cells[4]) if cells[4] not in ("", "—") else None
            except ValueError:
                z = None
            positions[pno] = {"z": z, "mode": mode}
    return positions
```

In `_resolve_child_offsets()`, add §6.3 lookup at the beginning:

```python
# At the top of _resolve_child_offsets():
part_positions = _parse_part_positions(spec_path) if spec_path else {}

# In the loop where offsets are assigned, add before auto_queue:
for child in children:
    cpno = child["part_no"]
    if cpno in part_positions:
        pos = part_positions[cpno]
        if pos.get("z") is not None:
            result[cpno] = (0, 0, pos["z"])
            continue  # Skip auto-stacking for this part
    # ... existing auto-queue logic
```

- [ ] **Step 3: Add B10-B16 review checks in cad_spec_reviewer.py**

In `review_assembly()`, after existing B-series checks:

```python
# --- B10: 孤儿总成 (BOM assembly not in layers and not excluded) ---
layers = data.get("assembly", {}).get("layers", [])
layer_pnos = set()
excluded_pnos = set()
for l in layers:
    m = re.search(r"([A-Z]+-[A-Z]+-\d+)", l.get("part", ""))
    if m:
        if l.get("exclude"):
            excluded_pnos.add(m.group(1))
        else:
            layer_pnos.add(m.group(1))

bom = data.get("bom")
if bom:
    orphans = []
    for assy in bom.get("assemblies", []):
        apno = assy.get("part_no", "")
        if apno and apno not in layer_pnos and apno not in excluded_pnos:
            orphans.append(apno)
    if orphans:
        idx += 1
        items.append({
            "id": f"B{idx}", "item": f"孤儿总成 ({len(orphans)}项)",
            "detail": f"BOM中以下总成在§6.2中无定位且未标记排除: {', '.join(orphans)}",
            "verdict": "CRITICAL",
            "suggestion": "在§6.2中添加定位或标记为exclude",
        })

# --- B11: 零件缺少包络尺寸 ---
envelopes = data.get("part_envelopes", {})
if bom:
    missing_env = []
    for assy in bom.get("assemblies", []):
        for part in assy.get("parts", []):
            if "自制" in part.get("make_buy", "") and part["part_no"] not in envelopes:
                missing_env.append(part["part_no"])
    if missing_env:
        idx += 1
        items.append({
            "id": f"B{idx}", "item": f"零件缺少包络尺寸 ({len(missing_env)}项)",
            "detail": f"自制件缺少包络: {', '.join(missing_env[:5])}{'...' if len(missing_env)>5 else ''}",
            "verdict": "WARNING",
            "suggestion": "在源文档中补充零件尺寸表或BOM材质列中的尺寸信息",
        })

# --- B12: 总成缺少零件级定位 ---
part_offsets = data.get("assembly", {}).get("part_offsets", {})
if bom and part_offsets:
    for assy in bom.get("assemblies", []):
        apno = assy.get("part_no", "")
        if apno in excluded_pnos:
            continue
        children = [p for p in assy.get("parts", []) if not p.get("is_assembly")]
        positioned = sum(1 for p in children if p["part_no"] in part_offsets)
        total = len(children)
        if total > 0 and positioned / total < 0.5:
            idx += 1
            items.append({
                "id": f"B{idx}", "item": f"总成 {apno} 零件级定位不足",
                "detail": f"{positioned}/{total} 零件有定位 ({positioned/total*100:.0f}%)",
                "verdict": "WARNING",
                "suggestion": "在源文档中添加串联堆叠链（→语法）",
            })
```

- [ ] **Step 4: Update DESIGN_REVIEW.md rendering with E section**

In `cad_spec_reviewer.py` `render_review()`, add section E:

```python
# After section D, add:
md.append("## E. 装配定位审查")
md.append("")
part_offsets = data.get("assembly", {}).get("part_offsets", {})
if part_offsets:
    # Coverage stats
    total = sum(len(a.get("parts", [])) for a in data.get("bom", {}).get("assemblies", []))
    positioned = len(part_offsets)
    md.append(f"- 定位覆盖: {positioned}/{total} 零件")
    md.append("")
```

- [ ] **Step 5: Commit P2**

```bash
git add cad_spec_gen.py codegen/gen_assembly.py cad_spec_reviewer.py
git commit -m "feat(P2): render §6.3/§6.4/§9 + gen_assembly consumes part-level positions + reviewer B10-B16"
```

---

## Task 5: Update Enhancement Plan Document

**Files:**
- Modify: `docs/assembly_positioning_enhancement_plan.md` — update status

- [ ] **Step 1: Update plan status to "实施完成"**

- [ ] **Step 2: Run full pipeline on GISBOT to verify**

```bash
python cad_pipeline.py spec --subsystem end_effector --mode force
python cad_pipeline.py codegen --subsystem end_effector --mode force
```

- [ ] **Step 3: Commit all**

```bash
git add docs/
git commit -m "docs: update assembly positioning enhancement plan status"
```
