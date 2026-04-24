# Track C — LLM 驱动几何生成 + 多视角一致增强 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 BOM 自制件增加 LLM 驱动几何层（L1 参数提取 / L2 CadQuery 代码生成 / L3 富化 Envelope），并将多视角一致增强（v1_anchor）扩展到 FAL/ComfyUI 后端。

**Architecture:** 激活 `route()`（`parts_routing.py`）取代 `_match_template()`；L1/L2 LLM 函数封装在新模块 `llm_codegen.py`；L3 富化 Envelope 封装在 `enriched_envelope.py`；多视角一致性通过向 `enhance_cfg` dict 注入 `hero_image` 键实现，不改动 `_enhance_fn` 签名。

**Tech Stack:** Python 3.11+, CadQuery, Gemini REST API (`GEMINI_API_KEY`), `uv run pytest`

---

## 文件结构

### 新建文件

| 文件 | 职责 |
|---|---|
| `templates/parts/cantilever_arm.py` | route() 可匹配"悬臂"的路由描述符存根 |
| `templates/parts/circular_cover.py` | route() 可匹配"盖/端盖"的路由描述符存根 |
| `templates/parts/cylindrical_sleeve.py` | route() 可匹配"套筒"的路由描述符存根 |
| `templates/parts/spring_unit.py` | route() 可匹配"弹簧"的路由描述符存根 |
| `src/cad_spec_gen/data/codegen/llm_codegen.py` | L1 `_llm_extract_params` + L2 `_llm_generate_cadquery` / `_classify_error` / `_llm_fix` |
| `src/cad_spec_gen/data/codegen/enriched_envelope.py` | L3 `_ENRICH_*` 常量 + `_make_enriched_envelope` |
| `tests/test_track_c_routing.py` | 路由激活单元测试 |
| `tests/test_track_c_llm.py` | L1/L2/L3 单元测试 |
| `tests/test_track_c_multiview.py` | 多视角一致性单元测试 |

### 修改文件

| 文件 | 改动 |
|---|---|
| `templates/parts/iso_9409_flange.py` | MATCH_KEYWORDS 加中文关键词 |
| `templates/parts/l_bracket.py` | MATCH_KEYWORDS 加中文关键词 |
| `templates/parts/cylindrical_housing.py` | MATCH_KEYWORDS 加中文关键词 |
| `templates/parts/rectangular_housing.py` | MATCH_KEYWORDS 加中文关键词 |
| `templates/parts/fixture_plate.py` | MATCH_KEYWORDS 加中文关键词 |
| `src/cad_spec_gen/data/codegen/gen_parts.py` | 激活 route()、加 `_ROUTE_TO_FACTORY_TYPE`、wire L1/L2/L3 |
| `src/cad_spec_gen/data/python_tools/fal_enhancer.py` | hero_image 注入 + seed |
| `src/cad_spec_gen/data/python_tools/comfyui_enhancer.py` | hero_image 上传 + workflow 节点替换 + seed |
| `src/cad_spec_gen/data/python_tools/cad_pipeline.py` | hero_image 注入 enhance_cfg + FAL V1 后设置 hero_image |

---

## CHECKPOINT 1 — 路由基础设施

### Task 1: templates/parts/ 中文关键词 + 4 个存根模板

**Files:**
- Modify: `templates/parts/iso_9409_flange.py`
- Modify: `templates/parts/l_bracket.py`
- Modify: `templates/parts/cylindrical_housing.py`
- Modify: `templates/parts/rectangular_housing.py`
- Modify: `templates/parts/fixture_plate.py`
- Create: `templates/parts/cantilever_arm.py`
- Create: `templates/parts/circular_cover.py`
- Create: `templates/parts/cylindrical_sleeve.py`
- Create: `templates/parts/spring_unit.py`
- Test: `tests/test_track_c_routing.py`

- [ ] **Step 1: 写失败测试（route() 匹配中文法兰名）**

```python
# tests/test_track_c_routing.py
import pytest
from cad_spec_gen.parts_routing import GeomInfo, route, discover_templates, locate_builtin_templates_dir


def _make_geom(gtype="cylinder", w=90.0, d=90.0, h=20.0):
    return GeomInfo(type=gtype, envelope_w=w, envelope_d=d, envelope_h=h, extras={})


def test_route_chinese_flange():
    tier1 = locate_builtin_templates_dir()
    templates = discover_templates([tier1] if tier1 else [])
    decision = route("法兰盘", _make_geom("cylinder"), templates)
    assert decision.outcome in ("HIT_BUILTIN", "HIT_PROJECT"), decision.reason
    assert decision.template is not None
    assert "flange" in decision.template.name


def test_route_chinese_bracket():
    tier1 = locate_builtin_templates_dir()
    templates = discover_templates([tier1] if tier1 else [])
    decision = route("安装支架", _make_geom("l_bracket"), templates)
    assert decision.outcome in ("HIT_BUILTIN", "HIT_PROJECT"), decision.reason
    assert decision.template is not None
    assert "bracket" in decision.template.name


def test_route_chinese_arm():
    tier1 = locate_builtin_templates_dir()
    templates = discover_templates([tier1] if tier1 else [])
    decision = route("悬臂件", _make_geom("box", 120, 30, 15), templates)
    assert decision.outcome in ("HIT_BUILTIN", "HIT_PROJECT"), decision.reason
    assert "arm" in decision.template.name


def test_route_unknown_falls_back():
    tier1 = locate_builtin_templates_dir()
    templates = discover_templates([tier1] if tier1 else [])
    decision = route("弹簧限力机构", _make_geom("cylinder"), templates)
    # After Task 1, spring_unit.py exists, so this should HIT
    # Before Task 1: FALLBACK
    assert decision.outcome in ("HIT_BUILTIN", "HIT_PROJECT", "FALLBACK")
```

- [ ] **Step 2: 运行确认失败**

```
uv run pytest tests/test_track_c_routing.py::test_route_chinese_flange -v
```
预期：FAIL（MATCH_KEYWORDS 中无中文）

- [ ] **Step 3: 在 5 个现有模板中追加中文关键词**

`templates/parts/iso_9409_flange.py` — 找到 `MATCH_KEYWORDS: list[str] = [` 行，在列表末尾追加：
```python
    # 中文 BOM 关键词（Track C routing activation）
    "法兰", "法兰盘", "工具法兰", "安装法兰", "连接法兰",
```

`templates/parts/l_bracket.py` — 追加：
```python
    "支架", "L型支架", "角支架", "安装支架",
```

`templates/parts/cylindrical_housing.py` — 追加：
```python
    "壳体", "圆柱壳体", "圆筒壳体",
```

`templates/parts/rectangular_housing.py` — 追加：
```python
    "壳体", "矩形壳体", "方形壳体", "箱体",
```

`templates/parts/fixture_plate.py` — 追加：
```python
    "板", "安装板", "夹具板", "底板",
```

- [ ] **Step 4: 创建 4 个存根模板**

`templates/parts/cantilever_arm.py`:
```python
"""templates/parts/cantilever_arm.py — 悬臂/连杆路由描述符（Track C）。

几何由 codegen/part_templates/arm.py make_arm() 实现；
此文件仅为 route() 提供关键词发现入口。
"""
from __future__ import annotations

MATCH_KEYWORDS: list[str] = [
    "cantilever", "arm", "connecting rod",
    "悬臂", "臂", "连杆", "摇臂",
]
MATCH_PRIORITY: int = 10
TEMPLATE_CATEGORY: str = "bracket"
TEMPLATE_VERSION: str = "1.0"


def example_params() -> dict:
    return {"length": 100.0, "width": 20.0, "thickness": 5.0}


def make(params: dict):  # pragma: no cover
    raise NotImplementedError("Use codegen/part_templates/arm.py make_arm()")
```

`templates/parts/circular_cover.py`:
```python
"""templates/parts/circular_cover.py — 圆形端盖路由描述符（Track C）。"""
from __future__ import annotations

MATCH_KEYWORDS: list[str] = [
    "cover", "end cap", "circular cover",
    "盖", "端盖", "封盖", "盖板",
]
MATCH_PRIORITY: int = 10
TEMPLATE_CATEGORY: str = "mechanical_interface"
TEMPLATE_VERSION: str = "1.0"


def example_params() -> dict:
    return {"od": 60.0, "thickness": 8.0}


def make(params: dict):  # pragma: no cover
    raise NotImplementedError("Use codegen/part_templates/cover.py make_cover()")
```

`templates/parts/cylindrical_sleeve.py`:
```python
"""templates/parts/cylindrical_sleeve.py — 套筒路由描述符（Track C）。"""
from __future__ import annotations

MATCH_KEYWORDS: list[str] = [
    "sleeve", "cylindrical sleeve", "bushing",
    "套筒", "套管", "衬套",
]
MATCH_PRIORITY: int = 10
TEMPLATE_CATEGORY: str = "mechanical_interface"
TEMPLATE_VERSION: str = "1.0"


def example_params() -> dict:
    return {"od": 40.0, "length": 60.0}


def make(params: dict):  # pragma: no cover
    raise NotImplementedError("Use codegen/part_templates/sleeve.py make_sleeve()")
```

`templates/parts/spring_unit.py`:
```python
"""templates/parts/spring_unit.py — 弹簧机构路由描述符（Track C）。"""
from __future__ import annotations

MATCH_KEYWORDS: list[str] = [
    "spring", "spring mechanism", "spring unit",
    "弹簧", "弹簧机构", "压簧", "弹力",
]
MATCH_PRIORITY: int = 10
TEMPLATE_CATEGORY: str = "mechanical_interface"
TEMPLATE_VERSION: str = "1.0"


def example_params() -> dict:
    return {"od": 20.0, "free_length": 50.0}


def make(params: dict):  # pragma: no cover
    raise NotImplementedError("Use codegen/part_templates/spring_mechanism.py make_spring_mechanism()")
```

- [ ] **Step 5: 运行确认通过**

```
uv run pytest tests/test_track_c_routing.py -v
```
预期：4/4 PASS

- [ ] **Step 6: Commit**

```bash
git add templates/parts/
git add tests/test_track_c_routing.py
git commit -m "feat(c1-routing): templates/parts 加中文关键词 + 4 个存根模板"
```

---

### Task 2: gen_parts.py — 激活 route() 取代 _match_template()

**Files:**
- Modify: `src/cad_spec_gen/data/codegen/gen_parts.py`
- Test: `tests/test_track_c_routing.py`（追加测试）

- [ ] **Step 1: 写失败测试（gen_parts 使用 route() 路由法兰件）**

在 `tests/test_track_c_routing.py` 末尾追加：

```python
def test_gen_parts_route_to_factory_type(tmp_path):
    """route() 命中 iso_9409_flange → _ROUTE_TO_FACTORY_TYPE 映射到 'flange'"""
    from cad_spec_gen.data.codegen.gen_parts import _ROUTE_TO_FACTORY_TYPE
    assert _ROUTE_TO_FACTORY_TYPE["iso_9409_flange"] == "flange"
    assert _ROUTE_TO_FACTORY_TYPE["l_bracket"] == "bracket"
    assert _ROUTE_TO_FACTORY_TYPE["cantilever_arm"] == "arm"
    assert _ROUTE_TO_FACTORY_TYPE["spring_unit"] == "spring_mechanism"


def test_gen_parts_imports_pick_best():
    """gen_parts 可导入 _pick_best（routing activation 需要）"""
    from cad_spec_gen.parts_routing import _pick_best
    from cad_spec_gen.parts_routing import TemplateDescriptor
    from pathlib import Path
    a = TemplateDescriptor("a", ("kw",), priority=10, category="bracket", tier="builtin", source_path=Path("."))
    b = TemplateDescriptor("b", ("kw",), priority=20, category="bracket", tier="builtin", source_path=Path("."))
    assert _pick_best([a, b]).name == "b"
```

- [ ] **Step 2: 运行确认失败**

```
uv run pytest tests/test_track_c_routing.py::test_gen_parts_route_to_factory_type -v
```
预期：FAIL（`_ROUTE_TO_FACTORY_TYPE` 未定义）

- [ ] **Step 3: 在 gen_parts.py 导入块末尾添加映射常量**

在 `gen_parts.py` 中，找到 `_PARTS_ROUTING_AVAILABLE` 赋值块之后（约第 57 行），添加：

```python
# Track C: route() 模板名 → _apply_template_decision() 工厂类型字符串
_ROUTE_TO_FACTORY_TYPE: dict[str, str] = {
    "iso_9409_flange": "flange",
    "l_bracket": "bracket",
    "cylindrical_housing": "housing",
    "rectangular_housing": "housing",
    "fixture_plate": "plate",
    "cantilever_arm": "arm",
    "circular_cover": "cover",
    "cylindrical_sleeve": "sleeve",
    "spring_unit": "spring_mechanism",
}
```

同时在 `try: from cad_spec_gen.parts_routing import ...` 块中添加 `_pick_best`：

```python
from cad_spec_gen.parts_routing import (
    GeomInfo,
    route,
    discover_templates,
    locate_builtin_templates_dir,
    _pick_best,          # Track C: resolve AMBIGUOUS
)
```

- [ ] **Step 4: 替换 generate_part_files() 中的路由逻辑**

找到 `generate_part_files()` 内（约第 683 行）从 `# Spec 1: log routing preview` 开始到 `if _tpl_type:` 块结束的代码段，替换为：

```python
        # Track C: route() 为唯一路由入口（取代 _match_template）
        _tpl_type: str | None = None
        _fallback_reason: str | None = None

        if _PARTS_ROUTING_AVAILABLE:
            try:
                _geom = GeomInfo(
                    type=geom.get("type", "unknown"),
                    envelope_w=float(geom.get("envelope_w") or 0),
                    envelope_d=float(geom.get("envelope_d") or 0),
                    envelope_h=float(geom.get("envelope_h") or 0),
                    extras={
                        k: v for k, v in geom.items()
                        if k not in {"type", "envelope_w", "envelope_d", "envelope_h"}
                    },
                )
                _tier1 = locate_builtin_templates_dir()
                _search = [_tier1] if _tier1 else []
                _templates = discover_templates(_search)
                _decision = route(p["name_cn"] or "", _geom, _templates)

                if _decision.outcome in ("HIT_BUILTIN", "HIT_PROJECT"):
                    _route_name = _decision.template.name
                    _tpl_type = _ROUTE_TO_FACTORY_TYPE.get(_route_name)
                    if _tpl_type is None:
                        print(f"  WARNING: 未知模板映射 '{_route_name}'，跳过模板")
                    else:
                        print(f"  [routing] {p['name_cn']} -> {_decision.outcome} ({_route_name} -> {_tpl_type})")
                elif _decision.outcome == "AMBIGUOUS":
                    _best = _pick_best(list(_decision.ambiguous_candidates))
                    _tpl_type = _ROUTE_TO_FACTORY_TYPE.get(_best.name)
                    print(f"  [routing] {p['name_cn']} -> AMBIGUOUS resolved: {_best.name} -> {_tpl_type}")
                else:  # FALLBACK
                    _fallback_reason = _decision.reason
                    print(f"  [routing] {p['name_cn']} -> FALLBACK ({_fallback_reason})")
            except Exception as _err:
                print(f"  [routing] {p['name_cn']} -> error: {_err}")
        else:
            # parts_routing 不可用时降级到旧系统
            _tpl_type = _match_template(p["name_cn"], _user_mapping)

        if _tpl_type:
            geom = _apply_template_decision(
                geom, _tpl_type, part_meta, envelope,
                part_no=p.get("part_no", ""),
                output_dir=str(output_dir),
            )
```

- [ ] **Step 5: 运行全量测试**

```
uv run pytest tests/test_track_c_routing.py -v
```
预期：PASS

```
uv run pytest -x -q
```
预期：所有现有测试通过（≥1126）

- [ ] **Step 6: Commit**

```bash
git add src/cad_spec_gen/data/codegen/gen_parts.py
git add tests/test_track_c_routing.py
git commit -m "feat(c1-routing): 激活 route() 取代 _match_template()，加 _ROUTE_TO_FACTORY_TYPE 映射"
```

---

## CHECKPOINT 2 — L1 参数提取

### Task 3: 创建 llm_codegen.py — _llm_extract_params()

**Files:**
- Create: `src/cad_spec_gen/data/codegen/llm_codegen.py`
- Test: `tests/test_track_c_llm.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_track_c_llm.py
import json
import pytest
from unittest.mock import patch, MagicMock


def test_llm_extract_params_returns_populated_list(monkeypatch):
    """mock LLM 返回合法 JSON → 返回 dim_tolerances 列表"""
    # 模拟 _call_gemini_text 返回法兰参数 JSON
    mock_json = json.dumps([
        {"name": "FLANGE_BODY_OD", "nominal": "90"},
        {"name": "FLANGE_BODY_ID", "nominal": "45"},
        {"name": "FLANGE_TOTAL_THICK", "nominal": "20"},
        {"name": "FLANGE_BOLT_PCD", "nominal": "65"},
    ])
    import sys
    sys.path.insert(0, "src/cad_spec_gen/data/codegen")
    from llm_codegen import _llm_extract_params
    with patch("llm_codegen._call_gemini_text", return_value=mock_json):
        result = _llm_extract_params(
            part_name="法兰盘",
            spec_text="法兰外径 90mm，中心孔 45mm，厚度 20mm，螺栓孔中心距 65mm",
            template_name="flange",
            required_tol_keys=["FLANGE_BODY_OD", "FLANGE_BODY_ID", "FLANGE_TOTAL_THICK", "FLANGE_BOLT_PCD"],
            existing_dim_tols=[],
        )
    assert result is not None
    by_name = {d["name"]: float(d["nominal"]) for d in result}
    assert abs(by_name["FLANGE_BODY_OD"] - 90) < 1
    assert abs(by_name["FLANGE_BODY_ID"] - 45) < 1


def test_llm_extract_params_json_fail_returns_none(monkeypatch):
    """LLM 返回非法 JSON → 返回 None，不抛异常"""
    import sys
    sys.path.insert(0, "src/cad_spec_gen/data/codegen")
    from llm_codegen import _llm_extract_params
    with patch("llm_codegen._call_gemini_text", return_value="not valid json"):
        result = _llm_extract_params("法兰盘", "spec", "flange", ["FLANGE_BODY_OD"], [])
    assert result is None


def test_llm_extract_params_skips_existing_keys():
    """existing_dim_tols 中已有的键不被覆盖"""
    import sys
    sys.path.insert(0, "src/cad_spec_gen/data/codegen")
    from llm_codegen import _llm_extract_params
    existing = [{"name": "FLANGE_BODY_OD", "nominal": "90"}]
    mock_json = json.dumps([
        {"name": "FLANGE_BODY_ID", "nominal": "45"},
        {"name": "FLANGE_TOTAL_THICK", "nominal": "20"},
        {"name": "FLANGE_BOLT_PCD", "nominal": "65"},
    ])
    with patch("llm_codegen._call_gemini_text", return_value=mock_json):
        result = _llm_extract_params("法兰盘", "spec", "flange",
                                     ["FLANGE_BODY_OD", "FLANGE_BODY_ID", "FLANGE_TOTAL_THICK", "FLANGE_BOLT_PCD"],
                                     existing)
    assert result is not None
    # OD 应保留原值 90，不被新值覆盖
    by_name = {d["name"]: d["nominal"] for d in result}
    assert by_name["FLANGE_BODY_OD"] == "90"
```

- [ ] **Step 2: 运行确认失败**

```
uv run pytest tests/test_track_c_llm.py -v
```
预期：FAIL（`llm_codegen` 模块不存在）

- [ ] **Step 3: 创建 llm_codegen.py**

```python
# src/cad_spec_gen/data/codegen/llm_codegen.py
"""LLM 辅助几何生成：L1 参数提取 / L2 CadQuery 代码生成 / L2 自我修正。

依赖：GEMINI_API_KEY 环境变量（text-only，不走 gemini_image_config.json）。
所有公开函数失败时返回 None，不抛异常。
"""
from __future__ import annotations

import json
import logging
import os
import re
import urllib.error
import urllib.request

log = logging.getLogger(__name__)

_GEMINI_TEXT_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-2.0-flash:generateContent"
)
_TIMEOUT_L1 = 10   # L1 参数提取超时秒数
_TIMEOUT_L2 = 30   # L2 代码生成超时秒数


def _call_gemini_text(prompt: str, timeout: int = 10) -> str | None:
    """向 Gemini 2.0 Flash 发送纯文本请求，返回模型第一条文本回复；失败返回 None。"""
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        log.warning("GEMINI_API_KEY 未设置，跳过 LLM 调用")
        return None
    payload = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.2},
    }).encode()
    url = f"{_GEMINI_TEXT_URL}?key={api_key}"
    req = urllib.request.Request(url, data=payload, method="POST",
                                  headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read())
        return data["candidates"][0]["content"]["parts"][0]["text"]
    except (urllib.error.URLError, KeyError, json.JSONDecodeError) as exc:
        log.warning("Gemini text call failed: %s", exc)
        return None


# ── L1: 参数提取 ─────────────────────────────────────────────────────────────

_L1_PROMPT_TEMPLATE = """\
你是 CAD 参数提取助手。从以下零件描述中提取指定尺寸参数。

零件名称：{part_name}
模板类型：{template_name}
描述文本：
{spec_text}

需要提取的参数键（已存在的键已列出，只需提取缺失的）：
{missing_keys}

已存在参数（不要修改这些）：
{existing_json}

请严格按以下 JSON 格式输出，不含任何说明文字、Markdown 代码块或注释：
[{{"name": "KEY_NAME", "nominal": "数值"}}, ...]

只输出缺失键的提取结果。若某键在描述中找不到数值，忽略它（不输出）。
"""


def _llm_extract_params(
    part_name: str,
    spec_text: str,
    template_name: str,
    required_tol_keys: list[str],
    existing_dim_tols: list[dict],
) -> list[dict] | None:
    """从 spec_text 补全 dim_tolerances 中缺失的参数条目。

    返回合并后的完整 dim_tolerances 列表（已有 + 新提取）；
    解析失败返回 None，不抛异常。
    """
    existing_names = {d["name"] for d in existing_dim_tols}
    missing = [k for k in required_tol_keys if k not in existing_names]
    if not missing:
        return list(existing_dim_tols)  # 全部已有，不调 LLM

    prompt = _L1_PROMPT_TEMPLATE.format(
        part_name=part_name,
        template_name=template_name,
        spec_text=spec_text[:2000],  # 截断避免超长
        missing_keys=", ".join(missing),
        existing_json=json.dumps(existing_dim_tols, ensure_ascii=False),
    )
    raw = _call_gemini_text(prompt, timeout=_TIMEOUT_L1)
    if raw is None:
        return None

    # 提取 JSON 数组（去掉可能包裹的 ```json ... ``` 或多余文字）
    match = re.search(r"\[.*\]", raw, re.DOTALL)
    if not match:
        log.warning("L1: LLM 返回无法解析为 JSON 数组: %s", raw[:200])
        return None
    try:
        new_entries: list[dict] = json.loads(match.group())
    except json.JSONDecodeError as exc:
        log.warning("L1: JSON 解析失败: %s", exc)
        return None

    # 过滤掉已有键（LLM 有时会重复输出）
    merged = list(existing_dim_tols)
    for entry in new_entries:
        if isinstance(entry, dict) and "name" in entry and "nominal" in entry:
            if entry["name"] not in existing_names:
                merged.append(entry)
    return merged
```

- [ ] **Step 4: 运行确认通过**

```
uv run pytest tests/test_track_c_llm.py::test_llm_extract_params_returns_populated_list tests/test_track_c_llm.py::test_llm_extract_params_json_fail_returns_none tests/test_track_c_llm.py::test_llm_extract_params_skips_existing_keys -v
```
预期：3/3 PASS

- [ ] **Step 5: Commit**

```bash
git add src/cad_spec_gen/data/codegen/llm_codegen.py
git add tests/test_track_c_llm.py
git commit -m "feat(c1-l1): llm_codegen.py 新增 _llm_extract_params()"
```

---

### Task 4: Wire L1 into _apply_template_decision()

**Files:**
- Modify: `src/cad_spec_gen/data/codegen/gen_parts.py:529-531`
- Test: `tests/test_track_c_llm.py`（追加测试）

- [ ] **Step 1: 写失败测试**

在 `tests/test_track_c_llm.py` 末尾追加：

```python
def test_apply_template_decision_calls_l1_when_code_none():
    """_apply_template_decision: factory 返回 None 时调用 _llm_extract_params"""
    import sys
    sys.path.insert(0, "src/cad_spec_gen/data/codegen")
    # 构造一个缺少必填参数的 part_meta（id 缺失 → make_flange 返回 None）
    geom = {"type": "cylinder", "envelope_w": 90.0, "envelope_d": 90.0, "envelope_h": 20.0}
    part_meta = {"dim_tolerances": [{"name": "FLANGE_BODY_OD", "nominal": "90"}]}
    filled = [
        {"name": "FLANGE_BODY_OD", "nominal": "90"},
        {"name": "FLANGE_BODY_ID", "nominal": "45"},
        {"name": "FLANGE_TOTAL_THICK", "nominal": "20"},
        {"name": "FLANGE_BOLT_PCD", "nominal": "65"},
    ]
    with patch("gen_parts._llm_extract_params", return_value=filled) as mock_l1:
        from gen_parts import _apply_template_decision
        result = _apply_template_decision(geom, "flange", part_meta, (90.0, 90.0, 20.0))
    mock_l1.assert_called_once()
    assert result.get("template_code") is not None, "L1 应补参后生成代码"
```

- [ ] **Step 2: 运行确认失败**

```
uv run pytest tests/test_track_c_llm.py::test_apply_template_decision_calls_l1_when_code_none -v
```
预期：FAIL

- [ ] **Step 3: 修改 gen_parts.py _apply_template_decision() 第 529-531 行**

找到：
```python
    if code is None:
        print(f"  [template] {tpl_type}: 必填主尺寸缺失，退回 envelope primitive")
        return geom
```

替换为：
```python
    if code is None:
        # Track C L1: 尝试 LLM 参数提取补全缺失必填键
        _l1_result = None
        try:
            from llm_codegen import _llm_extract_params as _l1_fn
            _REQUIRED_KEYS: dict[str, list[str]] = {
                "flange":           ["FLANGE_BODY_OD", "FLANGE_BODY_ID", "FLANGE_TOTAL_THICK", "FLANGE_BOLT_PCD"],
                "housing":          ["HOUSING_W", "HOUSING_D", "HOUSING_H"],
                "bracket":          ["BRACKET_W", "BRACKET_H", "BRACKET_T"],
                "spring_mechanism": ["SPRING_OD", "SPRING_L"],
                "sleeve":           ["SLEEVE_OD", "SLEEVE_L"],
                "plate":            ["PLATE_W", "PLATE_D", "PLATE_T"],
                "arm":              ["ARM_L", "ARM_W", "ARM_T"],
                "cover":            ["COVER_OD", "COVER_T"],
            }
            _req_keys = _REQUIRED_KEYS.get(tpl_type, [])
            if _req_keys:
                _spec_text = part_meta.get("_spec_text", "") or str(part_meta)
                _l1_result = _l1_fn(
                    part_name=part_meta.get("name_cn", ""),
                    spec_text=_spec_text,
                    template_name=tpl_type,
                    required_tol_keys=_req_keys,
                    existing_dim_tols=part_meta.get("dim_tolerances", []),
                )
        except ImportError:
            pass  # llm_codegen 未安装，跳过 L1

        if _l1_result is not None:
            # 用补全后的 dim_tolerances 重试 factory
            _patched_meta = dict(part_meta)
            _patched_meta["dim_tolerances"] = _l1_result
            print(f"  [L1] {tpl_type}: LLM 补全参数，重试工厂函数")
            return _apply_template_decision(
                geom, tpl_type, _patched_meta, envelope, part_no, output_dir
            )

        # L1 失败或无结果 → 调用方将触发 L2（由 generate_part_files 中的 _fallback_reason 处理）
        print(f"  [template] {tpl_type}: 必填主尺寸缺失，L1 无结果，退回")
        return geom
```

- [ ] **Step 4: 运行全量测试**

```
uv run pytest tests/test_track_c_llm.py -v
uv run pytest -x -q
```
预期：全部通过

- [ ] **Step 5: Commit**

```bash
git add src/cad_spec_gen/data/codegen/gen_parts.py
git commit -m "feat(c1-l1): wire L1 into _apply_template_decision() code=None 分支"
```

---

## CHECKPOINT 3 — L3 富化 Envelope

### Task 5: 创建 enriched_envelope.py

**Files:**
- Create: `src/cad_spec_gen/data/codegen/enriched_envelope.py`
- Test: `tests/test_track_c_llm.py`（追加测试）

- [ ] **Step 1: 写失败测试**

在 `tests/test_track_c_llm.py` 末尾追加：

```python
def test_enriched_envelope_flange_has_more_faces_than_cylinder():
    """法兰富化 envelope 面数 > 裸圆柱（3 面）"""
    pytest.importorskip("cadquery")
    import sys
    sys.path.insert(0, "src/cad_spec_gen/data/codegen")
    from enriched_envelope import _make_enriched_envelope
    wp = _make_enriched_envelope("flange", 90.0, 90.0, 20.0)
    assert wp is not None
    assert len(wp.val().Faces()) >= 15


def test_enriched_envelope_unknown_type_returns_box():
    """未知 tpl_type → 返回带圆角的 box，不返回 None"""
    pytest.importorskip("cadquery")
    import sys
    sys.path.insert(0, "src/cad_spec_gen/data/codegen")
    from enriched_envelope import _make_enriched_envelope
    wp = _make_enriched_envelope("unknown_xyz", 50.0, 40.0, 30.0)
    assert wp is not None


def test_enriched_envelope_exports_valid_step(tmp_path):
    """富化 envelope 可导出为合法 STEP 文件（文件大小 > 1KB）"""
    pytest.importorskip("cadquery")
    import cadquery as cq
    import sys
    sys.path.insert(0, "src/cad_spec_gen/data/codegen")
    from enriched_envelope import _make_enriched_envelope
    wp = _make_enriched_envelope("bracket", 60.0, 40.0, 50.0)
    out = tmp_path / "test.step"
    cq.exporters.export(wp, str(out))
    assert out.stat().st_size > 1000
```

- [ ] **Step 2: 运行确认失败**

```
uv run pytest tests/test_track_c_llm.py::test_enriched_envelope_flange_has_more_faces_than_cylinder -v
```
预期：FAIL（`enriched_envelope` 不存在）

- [ ] **Step 3: 创建 enriched_envelope.py**

```python
# src/cad_spec_gen/data/codegen/enriched_envelope.py
"""L3 富化 Envelope：为无模板或 L2 失败的自制件生成比裸 box 更真实的几何。

所有比例为命名常量，tpl_type 复用 _BUILTIN_KEYWORDS 键名。
"""
from __future__ import annotations

import math

# ── 比例常量 ──────────────────────────────────────────────────────────────────
_ENRICH_FLANGE_ID_RATIO   = 0.50   # 中心孔 id = od × 此值
_ENRICH_FLANGE_PCD_RATIO  = 0.75   # 螺栓孔 PCD = od × 此值
_ENRICH_HOUSING_SLOT_W    = 0.30   # 侧面开口宽 = w × 此值
_ENRICH_HOUSING_SLOT_H    = 0.40   # 侧面开口高 = h × 此值
_ENRICH_DEFAULT_FILLET    = 3.0    # mm，通用圆角
_ENRICH_DEFAULT_CBORE_D   = 10.0   # mm，默认沉孔直径
_ENRICH_DEFAULT_CBORE_H   = 5.0    # mm，默认沉孔深度
_ENRICH_BOLT_COUNT        = 6      # 默认螺栓孔数


def _make_enriched_envelope(
    tpl_type: str,
    w: float,
    d: float,
    h: float,
) -> "cq.Workplane":
    """生成比裸 envelope 更真实的近似几何。

    tpl_type 对应 _BUILTIN_KEYWORDS 键名（flange/housing/bracket/plate/arm/cover/sleeve/spring_mechanism）。
    所有操作包裹在 try/except，OCCT 失败时回退到带圆角的 box。
    """
    import cadquery as cq

    od = max(w, d)

    try:
        if tpl_type == "flange":
            return _enrich_flange(cq, od, h)
        elif tpl_type == "housing":
            return _enrich_housing(cq, w, d, h)
        elif tpl_type in ("bracket", "plate", "arm"):
            return _enrich_plate_like(cq, w, d, h)
        else:
            return _enrich_default(cq, w, d, h)
    except Exception:
        return _enrich_default(cq, w, d, h)


def _enrich_flange(cq, od: float, h: float):
    id_ = round(od * _ENRICH_FLANGE_ID_RATIO, 2)
    pcd = round(od * _ENRICH_FLANGE_PCD_RATIO, 2)
    bolt_r = round(pcd * 0.04, 2)
    body = (
        cq.Workplane("XY")
        .circle(od / 2).extrude(h)
        .cut(cq.Workplane("XY").circle(id_ / 2).extrude(h))
    )
    for i in range(_ENRICH_BOLT_COUNT):
        ang = math.radians(360 / _ENRICH_BOLT_COUNT * i)
        bx = round(pcd / 2 * math.cos(ang), 4)
        by = round(pcd / 2 * math.sin(ang), 4)
        body = body.cut(
            cq.Workplane("XY")
            .transformed(offset=cq.Vector(bx, by, 0))
            .circle(bolt_r).extrude(h)
        )
    try:
        body = body.edges("|Z").chamfer(min(_ENRICH_DEFAULT_FILLET, od * 0.02))
    except Exception:
        pass
    return body


def _enrich_housing(cq, w: float, d: float, h: float):
    wall = min(w, d) * 0.12
    body = (
        cq.Workplane("XY").box(w, d, h)
        .cut(cq.Workplane("XY")
             .box(w - wall * 2, d - wall * 2, h - wall)
             .translate((0, 0, wall / 2)))
    )
    slot_w = round(w * _ENRICH_HOUSING_SLOT_W, 2)
    slot_h = round(h * _ENRICH_HOUSING_SLOT_H, 2)
    body = body.cut(
        cq.Workplane("XZ")
        .transformed(offset=cq.Vector(0, d / 2, 0))
        .rect(slot_w, slot_h).extrude(wall + 1)
    )
    try:
        body = body.edges("|Z").fillet(_ENRICH_DEFAULT_FILLET)
    except Exception:
        pass
    return body


def _enrich_plate_like(cq, w: float, d: float, h: float):
    body = cq.Workplane("XY").box(w, d, h)
    hole_r = min(w, d) * 0.04
    for sx in (-1, 1):
        for sy in (-1, 1):
            hx = sx * w * 0.35
            hy = sy * d * 0.35
            body = body.cut(
                cq.Workplane("XY")
                .transformed(offset=cq.Vector(hx, hy, 0))
                .circle(hole_r).extrude(h)
            )
    try:
        body = body.edges("|Z").fillet(_ENRICH_DEFAULT_FILLET)
    except Exception:
        pass
    return body


def _enrich_default(cq, w: float, d: float, h: float):
    body = cq.Workplane("XY").box(w, d, h)
    cbore_r = _ENRICH_DEFAULT_CBORE_D / 2
    cbore_h = min(_ENRICH_DEFAULT_CBORE_H, h * 0.4)
    body = body.cut(
        cq.Workplane("XY")
        .transformed(offset=cq.Vector(0, 0, h / 2 - cbore_h))
        .circle(cbore_r).extrude(cbore_h + 1)
    )
    try:
        body = body.edges("|Z").fillet(_ENRICH_DEFAULT_FILLET)
    except Exception:
        pass
    return body
```

- [ ] **Step 4: 运行确认通过**

```
uv run pytest tests/test_track_c_llm.py::test_enriched_envelope_flange_has_more_faces_than_cylinder tests/test_track_c_llm.py::test_enriched_envelope_unknown_type_returns_box tests/test_track_c_llm.py::test_enriched_envelope_exports_valid_step -v
```
预期：3/3 PASS（需要 cadquery 环境）

- [ ] **Step 5: Commit**

```bash
git add src/cad_spec_gen/data/codegen/enriched_envelope.py
git commit -m "feat(c2-l3): enriched_envelope.py — _ENRICH_* 常量 + _make_enriched_envelope()"
```

---

### Task 6: Wire L3 into gen_parts.py FALLBACK 路径

**Files:**
- Modify: `src/cad_spec_gen/data/codegen/gen_parts.py`
- Test: `tests/test_track_c_llm.py`（追加测试）

- [ ] **Step 1: 写失败测试**

在 `tests/test_track_c_llm.py` 末尾追加：

```python
def test_enriched_placeholder_comment_in_py_file(tmp_path):
    """L3 生成的 .py 文件首行包含 ENRICHED_PLACEHOLDER 注释"""
    pytest.importorskip("cadquery")
    import sys
    sys.path.insert(0, "src/cad_spec_gen/data/codegen")
    # 构造触发 L3 的场景：FALLBACK reason = "no keyword match"
    # 直接测试 _write_enriched_placeholder 辅助函数
    from gen_parts import _write_enriched_placeholder
    out_py = tmp_path / "test_part.py"
    _write_enriched_placeholder(out_py, "test_part", "flange", 90.0, 90.0, 20.0)
    content = out_py.read_text(encoding="utf-8")
    assert "ENRICHED_PLACEHOLDER" in content
    step_out = tmp_path / "test_part.step"
    assert step_out.exists()
```

- [ ] **Step 2: 运行确认失败**

```
uv run pytest tests/test_track_c_llm.py::test_enriched_placeholder_comment_in_py_file -v
```
预期：FAIL

- [ ] **Step 3: 在 gen_parts.py 中添加 _write_enriched_placeholder() 辅助函数**

在 `_apply_template_decision()` 之前添加：

```python
def _write_enriched_placeholder(
    py_path: "Path",
    func_name: str,
    tpl_type: str | None,
    env_w: float,
    env_d: float,
    env_h: float,
) -> None:
    """生成 L3 富化 Envelope 的 .py 文件 + .step 文件。

    .py 首行写入 ENRICHED_PLACEHOLDER 标记供下游识别。
    """
    import cadquery as cq
    from pathlib import Path as _Path

    _codegen_dir = os.path.join(_PROJECT_ROOT, "codegen")
    if _codegen_dir not in sys.path:
        sys.path.insert(0, _codegen_dir)
    from enriched_envelope import _make_enriched_envelope

    tpl = tpl_type or "unknown"
    wp = _make_enriched_envelope(tpl, env_w, env_d, env_h)

    step_path = _Path(py_path).with_suffix(".step")
    cq.exporters.export(wp, str(step_path))

    py_content = (
        f"# ENRICHED_PLACEHOLDER — geometry approximated, not dimensionally accurate\n"
        f"# tpl_type={tpl} envelope=({env_w},{env_d},{env_h})\n"
        f"import cadquery as cq\n\n"
        f"def {func_name}():\n"
        f"    # 此件由 L3 富化 Envelope 生成，精度有限\n"
        f"    return cq.importers.importStep(r'{step_path}')\n"
    )
    _Path(py_path).write_text(py_content, encoding="utf-8")
```

- [ ] **Step 4: 在 generate_part_files() 中 FALLBACK 分支触发 L3**

在 Task 2 修改的路由代码块之后（`if _tpl_type:` 块之后），添加 FALLBACK 处理：

```python
        # L3: FALLBACK 且 no keyword match / disc_arms → 富化 Envelope
        elif _fallback_reason and _fallback_reason.startswith((
            "no keyword match", "disc_arms"
        )):
            if not os.path.exists(out_file) or mode == "force":
                print(f"  [L3] {p['name_cn']}: FALLBACK ({_fallback_reason})，生成富化 Envelope")
                try:
                    _write_enriched_placeholder(
                        _Path(out_file), func_name, None,
                        geom.get("envelope_w", 0), geom.get("envelope_d", 0), geom.get("envelope_h", 0),
                    )
                    generated.append(out_file)
                except Exception as _l3_err:
                    print(f"  ERROR L3: {_l3_err}")
                    failed.append(out_file)
            continue  # 跳过后续 Jinja 渲染
        elif _fallback_reason:
            print(f"  WARNING: {p['name_cn']} FALLBACK ({_fallback_reason})，跳过 L3（空名/退化几何）")
```

- [ ] **Step 5: 运行全量测试**

```
uv run pytest tests/test_track_c_llm.py -v
uv run pytest -x -q
```
预期：全部通过

- [ ] **Step 6: Commit**

```bash
git add src/cad_spec_gen/data/codegen/gen_parts.py
git commit -m "feat(c2-l3): wire L3 富化 Envelope 到 FALLBACK 路径"
```

---

## CHECKPOINT 4 — L2 CadQuery 生成

### Task 7: llm_codegen.py — _classify_error() + _llm_fix()

**Files:**
- Modify: `src/cad_spec_gen/data/codegen/llm_codegen.py`
- Test: `tests/test_track_c_llm.py`（追加测试）

- [ ] **Step 1: 写失败测试**

在 `tests/test_track_c_llm.py` 末尾追加：

```python
def test_classify_error_syntax():
    import sys; sys.path.insert(0, "src/cad_spec_gen/data/codegen")
    from llm_codegen import _classify_error
    try:
        exec("def f(:\n    pass")
    except SyntaxError as e:
        assert _classify_error(e) == "SYNTAX_ERROR"


def test_classify_error_import():
    import sys; sys.path.insert(0, "src/cad_spec_gen/data/codegen")
    from llm_codegen import _classify_error
    try:
        exec("import nonexistent_lib_xyz")
    except ImportError as e:
        assert _classify_error(e) == "IMPORT_OR_NAME_ERROR"


def test_llm_fix_extracts_code_block():
    """_llm_fix: 若 LLM 返回包含 ```python 块则提取其中代码"""
    import sys; sys.path.insert(0, "src/cad_spec_gen/data/codegen")
    from llm_codegen import _llm_fix
    response = "修复说明\n```python\ndef make_part():\n    return 1\n```"
    with patch("llm_codegen._call_gemini_text", return_value=response):
        result = _llm_fix("original_code", "SYNTAX_ERROR", "SyntaxError: ...")
    assert "def make_part():" in result


def test_llm_fix_fallback_to_original_on_no_code_block():
    """_llm_fix: LLM 不返回代码块时原样返回原始代码"""
    import sys; sys.path.insert(0, "src/cad_spec_gen/data/codegen")
    from llm_codegen import _llm_fix
    with patch("llm_codegen._call_gemini_text", return_value="just text, no code"):
        result = _llm_fix("def make_part(): pass", "API_SIGNATURE", "TypeError")
    assert result == "def make_part(): pass"
```

- [ ] **Step 2: 运行确认失败**

```
uv run pytest tests/test_track_c_llm.py::test_classify_error_syntax -v
```
预期：FAIL

- [ ] **Step 3: 在 llm_codegen.py 末尾追加**

```python
# ── L2: 错误分类与修复 ────────────────────────────────────────────────────────

_CLASSIFY_HINT: dict[str, str] = {
    "SYNTAX_ERROR":         "代码存在语法错误，请检查括号、缩进、引号是否配对，不得有 Markdown 标记",
    "IMPORT_OR_NAME_ERROR": "执行环境仅提供 `cq`（cadquery），不得 import 其他库，所有变量须在 make_part() 内定义",
    "INVALID_GEOMETRY":     "几何体存在自相交或零厚面，请检查 cut/union 顺序",
    "API_SIGNATURE":        "CadQuery API 签名错误，常见用法：cq.Workplane('XY').circle(r).extrude(h)",
    "DIMENSION_OVERFLOW":   "尺寸参数越界，请检查 id < od，thickness > 0，所有数值 > 0",
    "TOPOLOGY_ERROR":       "拓扑构造失败，建议拆分为多步 union 而非单步复合操作",
}


def _classify_error(exc: Exception) -> str:
    """将异常分类为 6 类之一，供 _llm_fix 选择修复提示。"""
    name = type(exc).__name__
    msg = str(exc).lower()
    if name == "SyntaxError":
        return "SYNTAX_ERROR"
    if name in ("ImportError", "ModuleNotFoundError", "NameError", "AttributeError"):
        return "IMPORT_OR_NAME_ERROR"
    if name == "TypeError" or "unexpected keyword" in msg or "argument" in msg:
        return "API_SIGNATURE"
    if "stdfail" in msg or "brepface" in msg or "null" in msg or "notdone" in msg:
        return "INVALID_GEOMETRY"
    if name == "ValueError" or "overflow" in msg or "negative" in msg:
        return "DIMENSION_OVERFLOW"
    if "constructionerror" in msg or "standard_" in msg:
        return "TOPOLOGY_ERROR"
    return "INVALID_GEOMETRY"  # 默认归类为几何无效


_L2_FIX_PROMPT_TEMPLATE = """\
你是 CadQuery 代码修复助手。以下代码运行时出错，错误类型：{error_class}。

错误信息：
{error_msg}

修复方向：{hint}

原代码：
```python
{code}
```

请返回修正后的完整 make_part() 函数，不含任何 import 语句、不含说明文字，仅 Python 代码。
"""


def _llm_fix(code: str, error_class: str, error_msg: str) -> str:
    """向 LLM 发送修复请求，返回修正后的代码字符串。

    LLM 不响应或返回格式无效时，原样返回 code（由上层 loop 继续重试）。
    """
    hint = _CLASSIFY_HINT.get(error_class, _CLASSIFY_HINT["INVALID_GEOMETRY"])
    prompt = _L2_FIX_PROMPT_TEMPLATE.format(
        error_class=error_class,
        error_msg=error_msg[:500],
        hint=hint,
        code=code,
    )
    raw = _call_gemini_text(prompt, timeout=_TIMEOUT_L2)
    if raw is None:
        return code

    # 提取第一个 ```python ... ``` 块
    match = re.search(r"```python\s*(.*?)```", raw, re.DOTALL)
    if match:
        return match.group(1).strip()
    # 若无代码块但有 def make_part 行，直接返回
    if "def make_part" in raw:
        return raw.strip()
    return code  # 提取失败，原样返回
```

- [ ] **Step 4: 运行确认通过**

```
uv run pytest tests/test_track_c_llm.py::test_classify_error_syntax tests/test_track_c_llm.py::test_classify_error_import tests/test_track_c_llm.py::test_llm_fix_extracts_code_block tests/test_track_c_llm.py::test_llm_fix_fallback_to_original_on_no_code_block -v
```
预期：4/4 PASS

- [ ] **Step 5: Commit**

```bash
git add src/cad_spec_gen/data/codegen/llm_codegen.py
git commit -m "feat(c4-l2): _classify_error() + _CLASSIFY_HINT + _llm_fix()"
```

---

### Task 8: llm_codegen.py — _llm_generate_cadquery() Step 1 + Step 2 + Step 3

**Files:**
- Modify: `src/cad_spec_gen/data/codegen/llm_codegen.py`
- Test: `tests/test_track_c_llm.py`（追加测试）

- [ ] **Step 1: 写失败测试**

在 `tests/test_track_c_llm.py` 末尾追加：

```python
def test_llm_generate_step1_json_fail_returns_none():
    """Step 1 JSON 解析失败 → 直接返回 None，不进入 Step 2"""
    import sys; sys.path.insert(0, "src/cad_spec_gen/data/codegen")
    from llm_codegen import _llm_generate_cadquery
    # Step 1 returns invalid JSON, Step 2 should never be called
    call_count = {"n": 0}
    def mock_call(prompt, timeout=10):
        call_count["n"] += 1
        return "not valid json at all"
    with patch("llm_codegen._call_gemini_text", side_effect=mock_call):
        result = _llm_generate_cadquery("弹簧", "弹簧机构", (50, 50, 80))
    assert result is None
    assert call_count["n"] == 1  # 只调用 1 次（Step 1），Step 2 未调用


def test_llm_generate_with_template_hint_includes_hint_in_prompt():
    """template_hint 传入时 Step 1 Prompt 应包含该提示"""
    import sys; sys.path.insert(0, "src/cad_spec_gen/data/codegen")
    from llm_codegen import _llm_generate_cadquery
    prompts_seen = []
    def mock_call(prompt, timeout=10):
        prompts_seen.append(prompt)
        return "not valid json"
    with patch("llm_codegen._call_gemini_text", side_effect=mock_call):
        _llm_generate_cadquery("法兰盘", "spec", (90, 90, 20), template_hint="flange")
    assert "flange" in prompts_seen[0]


def test_llm_generate_self_correction_retries_on_exec_fail(tmp_path):
    """自我修正：exec 失败后调 _llm_fix，最多 3 次"""
    pytest.importorskip("cadquery")
    import sys; sys.path.insert(0, "src/cad_spec_gen/data/codegen")
    from llm_codegen import _llm_generate_cadquery

    step1_json = '{"base_shape":"cylinder","dimensions":{"od":50,"h":80},"features":[],"principal_axis":"Z"}'
    bad_code = "def make_part():\n    return UNDEFINED_VAR"
    call_count = {"n": 0}
    def mock_call(prompt, timeout=10):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return step1_json  # Step 1 feature extraction
        return f"```python\n{bad_code}\n```"  # Step 2 + fix calls
    with patch("llm_codegen._call_gemini_text", side_effect=mock_call):
        result = _llm_generate_cadquery("弹簧限力机构", "spec", (50, 50, 80))
    assert result is None  # 3 次仍失败
    assert call_count["n"] == 4  # Step1(1) + Step2(1) + fix×2(2) = 4
```

- [ ] **Step 2: 运行确认失败**

```
uv run pytest tests/test_track_c_llm.py::test_llm_generate_step1_json_fail_returns_none -v
```
预期：FAIL

- [ ] **Step 3: 在 llm_codegen.py 末尾追加**

```python
# ── L2: CadQuery 代码生成（两步 + 自我修正） ──────────────────────────────────

_L2_STEP1_PROMPT = """\
你是机械 CAD 特征分析助手。分析以下零件描述，提取几何特征。
{hint_line}

零件名称：{part_name}
描述文本：{spec_text}
包络尺寸：宽 {w}mm × 深 {d}mm × 高 {h}mm

请严格按以下 JSON 格式输出（不含说明文字，不含 Markdown 代码块）：
{{"base_shape":"cylinder|box|ring|l_bracket","dimensions":{{"od":0,"h":0}},"features":[{{"type":"hole_array","count":6,"pcd":65,"dia":8,"face":"top"}}],"principal_axis":"Z"}}
"""

_L2_STEP2_PROMPT = """\
你是 CadQuery 代码生成助手。根据以下特征 JSON 生成 CadQuery 代码。

特征：{feature_json}
包络尺寸：宽 {w}mm × 深 {d}mm × 高 {h}mm

要求：
- 输出一个 Python 函数 make_part() -> cq.Workplane
- 不含任何 import 语句（执行环境已注入 cq = cadquery）
- 不含任何说明文字，仅 Python 代码
- 所有变量在函数体内定义

```python
def make_part():
    ...
```
"""


def _llm_generate_cadquery(
    part_name: str,
    spec_text: str,
    envelope: tuple[float, float, float],
    template_hint: str | None = None,
) -> str | None:
    """两步生成 + 自我修正（≤3 次）。

    返回可执行的代码字符串（含 make_part() 函数定义）；失败返回 None。
    """
    import tempfile
    import cadquery as cq

    w, d, h = envelope
    hint_line = f"已知零件类型提示：{template_hint}" if template_hint else ""

    # Step 1: 特征提取
    step1_prompt = _L2_STEP1_PROMPT.format(
        hint_line=hint_line, part_name=part_name,
        spec_text=spec_text[:1500], w=w, d=d, h=h,
    )
    raw1 = _call_gemini_text(step1_prompt, timeout=_TIMEOUT_L2)
    if raw1 is None:
        return None
    match1 = re.search(r"\{.*\}", raw1, re.DOTALL)
    if not match1:
        log.warning("L2 Step 1: 无法解析特征 JSON，跳过 Step 2")
        return None
    try:
        feature_json = json.loads(match1.group())
    except json.JSONDecodeError:
        log.warning("L2 Step 1: JSON 解析失败")
        return None

    # Step 2: 代码生成
    step2_prompt = _L2_STEP2_PROMPT.format(
        feature_json=json.dumps(feature_json, ensure_ascii=False), w=w, d=d, h=h,
    )
    raw2 = _call_gemini_text(step2_prompt, timeout=_TIMEOUT_L2)
    if raw2 is None:
        return None
    match2 = re.search(r"```python\s*(.*?)```", raw2, re.DOTALL)
    code = match2.group(1).strip() if match2 else (raw2.strip() if "def make_part" in raw2 else None)
    if code is None:
        log.warning("L2 Step 2: 未提取到代码块")
        return None

    # Step 3: 自我修正循环（≤3 次，含首次）
    with tempfile.NamedTemporaryFile(suffix=".step", delete=False) as _tf:
        tmp_path = _tf.name

    for attempt in range(3):
        try:
            ns: dict = {}
            exec(code, {"cq": cq}, ns)  # noqa: S102
            wp = ns["make_part"]()
            cq.exporters.export(wp, tmp_path)
            return code  # 成功
        except Exception as exc:
            error_class = _classify_error(exc)
            log.warning("L2 attempt %d/%d: %s — %s", attempt + 1, 3, error_class, exc)
            code = _llm_fix(code, error_class, str(exc))

    return None  # 3 次均失败
```

- [ ] **Step 4: 运行确认通过**

```
uv run pytest tests/test_track_c_llm.py::test_llm_generate_step1_json_fail_returns_none tests/test_track_c_llm.py::test_llm_generate_with_template_hint_includes_hint_in_prompt tests/test_track_c_llm.py::test_llm_generate_self_correction_retries_on_exec_fail -v
```
预期：3/3 PASS

- [ ] **Step 5: 运行全量测试**

```
uv run pytest -x -q
```
预期：全部通过

- [ ] **Step 6: Commit**

```bash
git add src/cad_spec_gen/data/codegen/llm_codegen.py
git commit -m "feat(c4-l2): _llm_generate_cadquery() Step1+Step2+Step3 自我修正"
```

---

### Task 9: Wire L2 into gen_parts.py FALLBACK 路径（L3 之前）

**Files:**
- Modify: `src/cad_spec_gen/data/codegen/gen_parts.py`
- Test: `tests/test_track_c_llm.py`（追加测试）

- [ ] **Step 1: 写失败测试**

在 `tests/test_track_c_llm.py` 末尾追加：

```python
def test_gen_parts_l2_called_before_l3_on_fallback():
    """FALLBACK 路径：先调 L2，L2 失败才调 L3"""
    import sys; sys.path.insert(0, "src/cad_spec_gen/data/codegen")
    call_order = []
    with patch("gen_parts._llm_generate_cadquery", side_effect=lambda *a, **kw: call_order.append("L2") or None) as mock_l2, \
         patch("gen_parts._write_enriched_placeholder", side_effect=lambda *a, **kw: call_order.append("L3")) as mock_l3:
        # 触发 FALLBACK 场景（通过直接调 _handle_fallback 辅助函数）
        from gen_parts import _handle_l2_l3_fallback
        from pathlib import Path
        _handle_l2_l3_fallback(
            part_name="弹簧限力机构",
            spec_text="弹簧限力机构",
            tpl_type_hint=None,
            fallback_reason="no keyword match",
            envelope=(50.0, 50.0, 80.0),
            out_py=Path("/tmp/test.py"),
            func_name="test_fn",
        )
    assert call_order == ["L2", "L3"], f"实际顺序: {call_order}"
```

- [ ] **Step 2: 运行确认失败**

```
uv run pytest tests/test_track_c_llm.py::test_gen_parts_l2_called_before_l3_on_fallback -v
```
预期：FAIL（`_handle_l2_l3_fallback` 不存在）

- [ ] **Step 3: 在 gen_parts.py 中添加 _handle_l2_l3_fallback() 辅助函数**

在 `_write_enriched_placeholder()` 之后添加：

```python
def _handle_l2_l3_fallback(
    part_name: str,
    spec_text: str,
    tpl_type_hint: str | None,
    fallback_reason: str,
    envelope: tuple,
    out_py: "Path",
    func_name: str,
) -> bool:
    """FALLBACK 路径：先尝试 L2，失败才退到 L3。

    返回 True 表示成功写入文件（L2 或 L3），False 表示全部失败。
    """
    from pathlib import Path as _Path
    env_w, env_d, env_h = (envelope or (0.0, 0.0, 0.0))

    # L2: LLM CadQuery 生成
    code: str | None = None
    try:
        from llm_codegen import _llm_generate_cadquery
        code = _llm_generate_cadquery(
            part_name=part_name,
            spec_text=spec_text,
            envelope=(env_w, env_d, env_h),
            template_hint=tpl_type_hint,
        )
    except ImportError:
        pass

    if code is not None:
        print(f"  [L2] {part_name}: CadQuery 代码生成成功，写入 {out_py.name}")
        _Path(out_py).write_text(code, encoding="utf-8")
        return True

    # L3: 富化 Envelope
    print(f"  [L3] {part_name}: L2 失败，退回富化 Envelope")
    try:
        _write_enriched_placeholder(out_py, func_name, tpl_type_hint, env_w, env_d, env_h)
        return True
    except Exception as _l3_err:
        print(f"  ERROR L3: {_l3_err}")
        return False
```

- [ ] **Step 4: 将 Task 6 中的 L3 代码替换为调用 _handle_l2_l3_fallback()**

找到 Task 6 添加的 FALLBACK 分支，将 `_write_enriched_placeholder(...)` 替换为：

```python
        elif _fallback_reason and _fallback_reason.startswith((
            "no keyword match", "disc_arms"
        )):
            if not os.path.exists(out_file) or mode == "force":
                _spec_text = part_meta.get("_spec_text", "") or p.get("name_cn", "")
                ok = _handle_l2_l3_fallback(
                    part_name=p["name_cn"],
                    spec_text=_spec_text,
                    tpl_type_hint=None,
                    fallback_reason=_fallback_reason,
                    envelope=(geom.get("envelope_w", 0), geom.get("envelope_d", 0), geom.get("envelope_h", 0)),
                    out_py=_Path(out_file),
                    func_name=func_name,
                )
                if ok:
                    generated.append(out_file)
                else:
                    failed.append(out_file)
            continue
```

- [ ] **Step 5: 运行全量测试**

```
uv run pytest tests/test_track_c_llm.py -v
uv run pytest -x -q
```
预期：全部通过

- [ ] **Step 6: Commit**

```bash
git add src/cad_spec_gen/data/codegen/gen_parts.py
git commit -m "feat(c4-l2): wire L2 → L3 fallback chain into generate_part_files()"
```

---

## CHECKPOINT 5 — 多视角一致增强

### Task 10: fal_enhancer.py — hero_image 注入 + seed

**Files:**
- Modify: `src/cad_spec_gen/data/python_tools/fal_enhancer.py:251-291`
- Test: `tests/test_track_c_multiview.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_track_c_multiview.py
import pytest
from unittest.mock import patch, MagicMock


def test_fal_canny_replaced_with_hero_image(tmp_path):
    """fal_cfg 含 hero_image 时，controlnets[0].control_image_url 被替换为 V1 参考 URL"""
    hero = tmp_path / "v1_hero.jpg"
    hero.write_bytes(b"fake_image_bytes")

    captured = {}
    def mock_subscribe(endpoint, arguments, with_logs=False):
        captured["args"] = arguments
        return {"images": [{"url": "https://mock/out.jpg"}]}

    def mock_upload(path, **kw):
        return f"https://mock/uploaded/{path.split('/')[-1]}"

    png = tmp_path / "V2_render.png"
    png.write_bytes(b"fake_png")

    import sys
    sys.path.insert(0, "src/cad_spec_gen/data/python_tools")
    from fal_enhancer import enhance_image

    fal_cfg = {
        "model": "fal-ai/flux-general",
        "hero_image": str(hero),
    }
    with patch("fal_enhancer._upload_with_retry", side_effect=mock_upload), \
         patch("fal_client.subscribe", side_effect=mock_subscribe), \
         patch("fal_enhancer._find_depth_for_png", return_value=(None, False)), \
         patch("urllib.request.urlretrieve"):
        enhance_image(str(png), "test prompt", fal_cfg, "V2", {})

    controlnets = captured["args"]["controlnets"]
    assert controlnets[0]["control_image_url"] == "https://mock/uploaded/v1_hero.jpg"


def test_fal_seed_injected_when_set(tmp_path):
    """fal_cfg 含 seed 整数时，api_args 包含 seed 键"""
    png = tmp_path / "V2.png"
    png.write_bytes(b"x")
    captured = {}
    def mock_subscribe(endpoint, arguments, with_logs=False):
        captured["args"] = arguments
        return {"images": [{"url": "https://mock/out.jpg"}]}

    import sys
    sys.path.insert(0, "src/cad_spec_gen/data/python_tools")
    from fal_enhancer import enhance_image

    with patch("fal_enhancer._upload_with_retry", return_value="https://mock/img.jpg"), \
         patch("fal_client.subscribe", side_effect=mock_subscribe), \
         patch("fal_enhancer._find_depth_for_png", return_value=(None, False)), \
         patch("urllib.request.urlretrieve"):
        enhance_image(str(png), "prompt", {"seed": 42}, "V2", {})

    assert captured["args"].get("seed") == 42
```

- [ ] **Step 2: 运行确认失败**

```
uv run pytest tests/test_track_c_multiview.py::test_fal_canny_replaced_with_hero_image -v
```
预期：FAIL

- [ ] **Step 3: 修改 fal_enhancer.py enhance_image() 函数**

找到构建 `controlnets` 列表后（约第 251 行），在 `# Determine endpoint` 之前，插入：

```python
    # Track C C-7: v1_anchor — 将 V1 增强结果替换 canny 参考图
    hero = fal_cfg.get("hero_image")
    if hero and os.path.isfile(hero):
        hero_url = _upload_with_retry(hero)
        controlnets[0]["control_image_url"] = hero_url
        log.info("  v1_anchor: canny 参考替换为 hero_image %s", os.path.basename(hero))
```

找到 `api_args = {` 块末尾（约第 282 行），在 `if use_img2img:` 之前插入：

```python
    # Track C C-7: 固定 seed（None 时不传，保持随机）
    _seed = fal_cfg.get("seed")
    if _seed is not None:
        api_args["seed"] = int(_seed)
```

- [ ] **Step 4: 运行确认通过**

```
uv run pytest tests/test_track_c_multiview.py::test_fal_canny_replaced_with_hero_image tests/test_track_c_multiview.py::test_fal_seed_injected_when_set -v
```
预期：2/2 PASS

- [ ] **Step 5: Commit**

```bash
git add src/cad_spec_gen/data/python_tools/fal_enhancer.py
git add tests/test_track_c_multiview.py
git commit -m "feat(c3-multiview): fal_enhancer hero_image 注入 + seed 支持"
```

---

### Task 11: comfyui_enhancer.py — hero_image 上传 + workflow 节点替换

**Files:**
- Modify: `src/cad_spec_gen/data/python_tools/comfyui_enhancer.py:182-252`
- Test: `tests/test_track_c_multiview.py`（追加测试）

- [ ] **Step 1: 写失败测试**

在 `tests/test_track_c_multiview.py` 末尾追加：

```python
def test_comfyui_hero_image_replaces_input_node(tmp_path):
    """comfyui_cfg 含 hero_image 时，workflow input_image 节点被替换为 hero 上传名"""
    hero = tmp_path / "v1_hero.jpg"
    hero.write_bytes(b"hero_bytes")
    png = tmp_path / "V2.png"
    png.write_bytes(b"render_bytes")

    uploaded_names = []
    def mock_post(url, **kwargs):
        resp = MagicMock()
        resp.raise_for_status = lambda: None
        if "upload" in url:
            fname = list(kwargs.get("files", {}).values())[0][0]
            uploaded_names.append(fname)
            resp.json.return_value = {"name": fname}
        elif "/prompt" in url:
            resp.ok = True
            resp.json.return_value = {"prompt_id": "pid1"}
        return resp

    def mock_get(url, **kwargs):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"pid1": {"outputs": {"12": {"images": [{"filename": "out.png", "subfolder": "", "type": "output"}]}}}}
        return resp

    import sys
    sys.path.insert(0, "src/cad_spec_gen/data/python_tools")
    from comfyui_enhancer import enhance_image

    cfg = {"hero_image": str(hero), "host": "127.0.0.1", "port": 8188}
    with patch("requests.post", side_effect=mock_post), \
         patch("requests.get", side_effect=mock_get), \
         patch("comfyui_enhancer._download_image", return_value=None):
        try:
            enhance_image(str(png), "prompt", cfg, "V2", {})
        except Exception:
            pass  # 下载失败不影响断言

    # hero 文件名应出现在上传队列中
    assert "v1_hero.jpg" in uploaded_names
```

- [ ] **Step 2: 运行确认失败**

```
uv run pytest tests/test_track_c_multiview.py::test_comfyui_hero_image_replaces_input_node -v
```
预期：FAIL

- [ ] **Step 3: 修改 comfyui_enhancer.py enhance_image()**

在 `# Load and patch workflow` 之前（约第 229 行），插入：

```python
    # Track C C-7: v1_anchor — 上传 hero_image 供 workflow 使用
    _hero_uploaded = None
    _hero = comfyui_cfg.get("hero_image")
    if _hero and os.path.isfile(_hero):
        with open(_hero, "rb") as _hf:
            _hr = _req.post(
                f"http://{_host}:{_port}/upload/image",
                files={"image": (os.path.basename(_hero), _hf, "image/jpeg")},
                data={"overwrite": "true"},
                timeout=30,
            )
        _hr.raise_for_status()
        _hero_uploaded = _hr.json()["name"]
        log.info("  [comfyui] v1_anchor hero_image uploaded as %s", _hero_uploaded)
```

在 `workflow = _patch_workflow(...)` 行之后插入：

```python
    # 若有 hero_image，替换 input_image 节点（使 V2-V4 参考 V1 风格）
    if _hero_uploaded:
        for node in workflow.values():
            if node.get("_title") == "input_image":
                node["inputs"]["image"] = _hero_uploaded
                break
    # seed 支持
    _comfyui_seed = comfyui_cfg.get("seed")
    if _comfyui_seed is not None:
        for node in workflow.values():
            if node.get("_title") == "ksampler":
                node["inputs"]["seed"] = int(_comfyui_seed)
                break
```

- [ ] **Step 4: 运行确认通过**

```
uv run pytest tests/test_track_c_multiview.py::test_comfyui_hero_image_replaces_input_node -v
```
预期：PASS

- [ ] **Step 5: Commit**

```bash
git add src/cad_spec_gen/data/python_tools/comfyui_enhancer.py
git commit -m "feat(c3-multiview): comfyui_enhancer hero_image 上传 + workflow 节点替换 + seed"
```

---

### Task 12: cad_pipeline.py — hero_image cfg 注入 + FAL V1 后设置 hero_image

**Files:**
- Modify: `src/cad_spec_gen/data/python_tools/cad_pipeline.py:1935-1940` 和 `2010-2016` 和 `2028-2029`
- Test: `tests/test_track_c_multiview.py`（追加测试）

- [ ] **Step 1: 写失败测试**

在 `tests/test_track_c_multiview.py` 末尾追加：

```python
def test_cad_pipeline_injects_hero_image_into_fal_cfg():
    """cad_pipeline: reference_mode=v1_anchor + FAL 后端，V2 调用时 enhance_cfg 含 hero_image"""
    import sys
    sys.path.insert(0, "src/cad_spec_gen/data/python_tools")
    # 直接测试注入逻辑的辅助函数
    from cad_pipeline import _build_enhance_cfg_with_hero
    cfg = {"model": "fal-ai/flux-general"}
    hero = "/tmp/v1_hero.jpg"
    result = _build_enhance_cfg_with_hero(cfg, hero)
    assert result["hero_image"] == hero
    # 原始 cfg 不应被修改（浅拷贝）
    assert "hero_image" not in cfg
```

- [ ] **Step 2: 运行确认失败**

```
uv run pytest tests/test_track_c_multiview.py::test_cad_pipeline_injects_hero_image_into_fal_cfg -v
```
预期：FAIL

- [ ] **Step 3: 在 cad_pipeline.py 中添加 _build_enhance_cfg_with_hero() 辅助函数**

在 `_pixel_seed()` 内嵌函数之前（约第 1857 行附近，module level），在文件中找到合适的 module-level 位置添加：

```python
def _build_enhance_cfg_with_hero(cfg: dict, hero_image: str) -> dict:
    """返回注入了 hero_image 键的 cfg 浅拷贝，不修改原 cfg。"""
    result = dict(cfg)
    result["hero_image"] = hero_image
    return result
```

- [ ] **Step 4: 在 _enhance_fn 调用处注入 hero_image**

找到约第 2010 行的 `_enhance_fn` 调用：

```python
                    raw_path = _enhance_fn(
                        png,
                        prompt,
                        _pcfg.get("enhance", {}).get(_enhance_cfg_key, {}),
                        view_key,
                        rc,
                    )
```

替换为：

```python
                    _ecfg = _pcfg.get("enhance", {}).get(_enhance_cfg_key, {})
                    # Track C C-7: v1_anchor 扩展到 FAL/ComfyUI
                    if (
                        _ref_mode == "v1_anchor"
                        and hero_image
                        and view_key != "V1"
                        and backend in ("fal", "comfyui", "fal_comfy")
                    ):
                        _ecfg = _build_enhance_cfg_with_hero(_ecfg, hero_image)
                    raw_path = _enhance_fn(png, prompt, _ecfg, view_key, rc)
```

- [ ] **Step 5: 在 FAL V1 完成后设置 hero_image**

找到约第 2028 行的 `if view_key == "V1": v1_done = True` 块，在其之后追加：

```python
                if view_key == "V1" and _ref_mode == "v1_anchor" and raw_path:
                    # Track C: FAL/ComfyUI 后端也需设置 hero_image（Gemini 在第 2199 行设置）
                    if backend in ("fal", "comfyui", "fal_comfy"):
                        hero_image = new_path
                        log.info("  Hero image set (FAL/ComfyUI): %s", os.path.basename(new_path))
```

注意：此处 `new_path` 的赋值在约第 2037 行，确保插入位置在 `new_path` 定义之后。找到 `log.info("  Saved: %s", new_path)` 行之后插入。

- [ ] **Step 6: 运行全量测试**

```
uv run pytest tests/test_track_c_multiview.py -v
uv run pytest -x -q
```
预期：全部通过

- [ ] **Step 7: Commit**

```bash
git add src/cad_spec_gen/data/python_tools/cad_pipeline.py
git commit -m "feat(c3-multiview): cad_pipeline hero_image cfg 注入 + FAL V1 后设置"
```

---

## CHECKPOINT 6 — 集成测试

### Task 13: 集成测试 — ee_001_08 法兰件 L1 路径端对端

**Files:**
- Test: `tests/test_track_c_integration.py`

- [ ] **Step 1: 写集成测试**

```python
# tests/test_track_c_integration.py
"""Track C 集成测试：routing + L1 端对端验证（不需要真实 LLM API Key）"""
import json
import pytest
from pathlib import Path
from unittest.mock import patch


def _get_ee_spec():
    """定位 end_effector 规格文件路径"""
    repo = Path(__file__).parent.parent
    spec = repo / "cad" / "end_effector" / "CAD_SPEC.md"
    if not spec.exists():
        pytest.skip("CAD_SPEC.md not found")
    return spec


def test_route_finds_flange_in_end_effector_bom():
    """routing 层：ee BOM 中的法兰件能被 route() 命中（不需要 LLM）"""
    from cad_spec_gen.parts_routing import GeomInfo, route, discover_templates, locate_builtin_templates_dir
    geom = GeomInfo(type="cylinder", envelope_w=90.0, envelope_d=90.0, envelope_h=20.0, extras={})
    tier1 = locate_builtin_templates_dir()
    templates = discover_templates([tier1] if tier1 else [])
    # ee_001_08 是法兰件
    decision = route("法兰盘", geom, templates)
    assert decision.outcome in ("HIT_BUILTIN", "HIT_PROJECT")
    assert decision.template is not None


def test_l1_param_extraction_flange_mock():
    """L1 层：mock LLM 返回法兰参数，_apply_template_decision 生成含螺栓孔几何"""
    pytest.importorskip("cadquery")
    import sys
    sys.path.insert(0, "src/cad_spec_gen/data/codegen")

    filled = [
        {"name": "FLANGE_BODY_OD", "nominal": "90"},
        {"name": "FLANGE_BODY_ID", "nominal": "45"},
        {"name": "FLANGE_TOTAL_THICK", "nominal": "20"},
        {"name": "FLANGE_BOLT_PCD", "nominal": "65"},
    ]
    geom = {"type": "cylinder", "envelope_w": 90.0, "envelope_d": 90.0, "envelope_h": 20.0}
    part_meta = {"name_cn": "法兰盘", "dim_tolerances": [{"name": "FLANGE_BODY_OD", "nominal": "90"}]}

    with patch("gen_parts._llm_extract_params", return_value=filled):
        from gen_parts import _apply_template_decision
        result = _apply_template_decision(geom, "flange", part_meta, (90.0, 90.0, 20.0))

    assert result.get("template_code") is not None, "L1 应使 factory 返回代码"
    assert "bolt" in result["template_code"].lower() or "circle" in result["template_code"].lower()


def test_l3_enriched_placeholder_written_for_unknown_part(tmp_path):
    """L3 层：无模板件生成带 ENRICHED_PLACEHOLDER 注释的 .py 文件"""
    pytest.importorskip("cadquery")
    import sys
    sys.path.insert(0, "src/cad_spec_gen/data/codegen")
    from gen_parts import _write_enriched_placeholder
    out_py = tmp_path / "ee_unknown.py"
    _write_enriched_placeholder(out_py, "ee_unknown", None, 50.0, 40.0, 30.0)
    content = out_py.read_text(encoding="utf-8")
    assert "ENRICHED_PLACEHOLDER" in content
    step_file = tmp_path / "ee_unknown.step"
    assert step_file.exists()
    assert step_file.stat().st_size > 500
```

- [ ] **Step 2: 运行集成测试**

```
uv run pytest tests/test_track_c_integration.py -v
```
预期：3/3 PASS

- [ ] **Step 3: 运行全量回归**

```
uv run pytest -x -q
```
预期：≥1139 测试全部通过（原 1126 + Track C 新增 ≥13）

- [ ] **Step 4: Final commit**

```bash
git add tests/test_track_c_integration.py
git commit -m "test(track-c): 集成测试 routing + L1 + L3 端对端验证"
```

---

## 实施顺序速查

```
CHECKPOINT 1: Task 1 → Task 2   (路由基础设施)
CHECKPOINT 2: Task 3 → Task 4   (L1 参数提取)
CHECKPOINT 3: Task 5 → Task 6   (L3 富化 Envelope)
CHECKPOINT 4: Task 7 → Task 8 → Task 9  (L2 CadQuery 生成)
CHECKPOINT 5: Task 10 → Task 11 → Task 12  (多视角一致增强)
CHECKPOINT 6: Task 13  (集成测试)
```

各 CHECKPOINT 完成后暂停确认，验证 `uv run pytest -x -q` 全通过后再进入下一 CHECKPOINT。
