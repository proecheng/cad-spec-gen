# SP1 Jury→Prompt 反馈闭环实施 Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 enhance 跑出来的 photoreal_score 提分——baseline 跑完 → jury 评分 → score 低于阈值时按规则表+LLM 改 prompt+ControlNet 参数 → retry 一次 → 二轮 jury 选高分张。

**Architecture:** 9 个新模块 + 1 个 backends/ 子包（4 文件：Protocol + 3 内置 adapter）+ 1 个跨 SP 通用 budget 模块；唯一副作用持有者是 `orchestrator.py`；BackendAdapter Protocol 让用户任意 vendor（gemini banana / gpt-image-2 / fal_comfy / 自定义 plugin）只需 config 写 backend_kind + base_url + api_key_env + model_name；`cmd_enhance` 内嵌视角级 hook + try/except 异常隔离 + LoopBudget 跨视角累计；photo3d-jury CLI 扩 `--single-view --image` 支持 single-image 评分；ENHANCEMENT_REPORT.json 条件性追加 `loop_summary` 顶层段。

**Tech Stack:** Python 3.11+ / pyyaml (safe_load) / hypothesis / pytest / argparse / threading.Lock / pathlib.Path / importlib.resources

**Spec:** `docs/superpowers/specs/2026-05-10-jury-prompt-loop-design.md` (804 行，过 5 层审查)

---

## 文件结构总览

### 新增文件
```
enhance_budget.py       # M-1 跨 SP 通用 LoopBudget
tools/jury_loop/
├── __init__.py
├── reason_parser.py        # 纯函数：reason 文本 → tag set
├── rule_table.py           # 纯函数 + yaml safe_load：tags+backend_kind → (addons, params)
├── llm_fallback.py         # 复用 jury llm_client，miss tags → addons
├── score_select.py         # ScoreSelectStrategy Protocol + Pick* 实现
├── secrets_scrubber.py     # SEC-MINOR-2 净化 errors + payload
├── metadata.py             # sidecar JSON schema + write_sidecar / write_degraded
├── orchestrator.py         # 视角级 hook 主入口
├── backends/               # ★ 新增：BackendAdapter 抽象与 3 内置实现
│   ├── __init__.py         # BACKEND_REGISTRY + register_backend()
│   ├── protocol.py         # BackendAdapter Protocol + Request/Response NamedTuple + 4 类异常
│   ├── gemini_chat_image.py        # chat-completions 传图（gemini banana / openai gpt-4o vision）
│   ├── openai_images_edit.py       # /v1/images/edits REST（gpt-image-2 / stability.ai）
│   └── comfyui_workflow_cloud.py   # 包装现有 fal_comfy_enhancer.py（baseline 模块名保留）；base_url 默认 fal.ai 但用户可改 RunComfy/Comfy Cloud/自部署；保 ControlNet hard lock
└── rules/
    └── photoreal_v1.yaml   # 内置规则表

tests/jury_loop/
├── __init__.py
├── conftest.py
├── test_secrets_scrubber.py
├── test_reason_parser.py
├── test_rule_table.py
├── test_llm_fallback.py
├── test_score_select.py
├── test_enhance_budget.py
├── test_metadata.py
├── test_orchestrator.py
├── test_jury_cli_single_view.py
├── test_cmd_enhance_integration.py
├── test_l3_contract.py
├── test_l4_smoke.py        # marker requires_fal_key
└── fixtures/
    ├── sample_jury_verdicts.json
    ├── user_rule_yaml_valid.yaml
    ├── user_rule_yaml_unknown_field.yaml
    └── user_rule_yaml_wrong_schema.yaml
```

### 修改文件
- `cad_pipeline.py:cmd_enhance` (line 2504-2700+) — 视角级 hook + try/except 异常隔离 + LoopBudget 实例化 + hero_image 状态传递 + `--rerun-loop` flag + 条件写 `loop_summary`
- `pipeline_config.json` — 加 `enhance.jury_loop` 段（顶层 enabled + cost_cap_usd + advanced 子段）
- `tools/photo3d_jury.py:_build_parser` — 加 `--single-view` + `--image` flags（SUPPRESS 隐藏 help）

---

## CP-0：包结构 + 测试基建（≈30 min）

### Task 0.1：创建 jury_loop 包骨架

**Files:**
- Create: `tools/jury_loop/__init__.py`
- Create: `tools/jury_loop/rules/.gitkeep`
- Create: `tests/jury_loop/__init__.py`
- Create: `tests/jury_loop/conftest.py`

- [ ] **Step 1：创建包目录与空 __init__.py**

```python
# tools/jury_loop/__init__.py
"""SP1 Jury→Prompt 反馈闭环。

模块布局：reason_parser / rule_table / llm_fallback / score_select /
secrets_scrubber / metadata / orchestrator。规则资源在 rules/。
"""
```

```python
# tests/jury_loop/__init__.py
```

- [ ] **Step 2：写 conftest.py（公共 fixture）**

```python
# tests/jury_loop/conftest.py
"""jury_loop 包测试公共 fixture。"""
from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def fixture_dir() -> Path:
    """测试 fixtures 目录。"""
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def sample_reason_plastic_flat() -> str:
    """jury reason 含 plastic_look + flat_light 两 tag。"""
    return "plastic look, flat lighting"


@pytest.fixture
def builtin_yaml_path() -> Path:
    """内置 photoreal_v1.yaml 路径。"""
    from importlib.resources import files

    return Path(str(files("tools.jury_loop.rules") / "photoreal_v1.yaml"))
```

- [ ] **Step 3：验证 import 不抛**

Run: `python -c "from cad_spec_gen.data.tools import jury_loop; print(jury_loop.__doc__)"`
Expected: 输出 docstring，不抛 ImportError

- [ ] **Step 4：commit**

```bash
git add tools/jury_loop/__init__.py \
        tools/jury_loop/rules/.gitkeep \
        tests/jury_loop/__init__.py \
        tests/jury_loop/conftest.py
git commit -m "feat(jury-loop): 创建 SP1 闭环包骨架"
```

---

## CP-1：纯函数基础 — secrets_scrubber + reason_parser（≈45 min）

### Task 1.1：secrets_scrubber 失败测试 + 实现

**Files:**
- Create: `tools/jury_loop/secrets_scrubber.py`
- Test: `tests/jury_loop/test_secrets_scrubber.py`

- [ ] **Step 1：写 RED 测试**

```python
# tests/jury_loop/test_secrets_scrubber.py
from __future__ import annotations

import pytest

from tools.jury_loop.secrets_scrubber import scrub_secrets


class TestScrubSecrets:
    def test_redacts_fal_key_envvar(self) -> None:
        text = "Error: FAL_KEY=sk-abc123 expired"
        assert scrub_secrets(text) == "Error: FAL_KEY=[REDACTED] expired"

    def test_redacts_bearer_token(self) -> None:
        text = "Authorization: Bearer eyJhbGc.payload.signature"
        assert "[REDACTED]" in scrub_secrets(text)
        assert "eyJhbGc" not in scrub_secrets(text)

    def test_redacts_authorization_header_quoted(self) -> None:
        text = '{"Authorization": "Bearer abc123"}'
        out = scrub_secrets(text)
        assert "abc123" not in out

    def test_redacts_openai_gemini_anthropic_keys(self) -> None:
        text = "OPENAI_API_KEY=sk-foo GEMINI_API_KEY=ai-bar ANTHROPIC_API_KEY=sk-ant-baz"
        out = scrub_secrets(text)
        assert "sk-foo" not in out
        assert "ai-bar" not in out
        assert "sk-ant-baz" not in out

    def test_passthrough_when_no_secrets(self) -> None:
        text = "rule_table miss tag plastic_look"
        assert scrub_secrets(text) == text

    def test_handles_nested_dict(self) -> None:
        payload = {"api_key": "sk-secret", "model": "gemini-1.5"}
        out = scrub_secrets(payload)
        assert out["api_key"] == "[REDACTED]"
        assert out["model"] == "gemini-1.5"

    def test_handles_list_of_dicts(self) -> None:
        payload = [{"api_key": "k1"}, {"FAL_KEY": "k2"}]
        out = scrub_secrets(payload)
        assert all(d.get("api_key") == "[REDACTED]" or d.get("FAL_KEY") == "[REDACTED]" for d in out)

    def test_truncate_at_200_chars(self) -> None:
        text = "x" * 500
        out = scrub_secrets(text, max_len=200)
        assert len(out) == 200
```

- [ ] **Step 2：跑测试确认 RED**

Run: `python -m pytest tests/jury_loop/test_secrets_scrubber.py -v`
Expected: 8 测试全 fail，ImportError "No module named ... secrets_scrubber"

- [ ] **Step 3：实现 secrets_scrubber.py**

```python
# tools/jury_loop/secrets_scrubber.py
"""SEC-MINOR-2 净化器：去除 errors[] 与 backend_payload 里的 API key 与 token。"""
from __future__ import annotations

import re
from typing import Any

REDACTED = "[REDACTED]"

_ENV_KEY_PATTERNS = [
    re.compile(r"(?i)(FAL_KEY|FAL_API_KEY)=([^\s,;\"']+)"),
    re.compile(r"(?i)(OPENAI_API_KEY|OPENAI_KEY)=([^\s,;\"']+)"),
    re.compile(r"(?i)(GEMINI_API_KEY|GOOGLE_API_KEY)=([^\s,;\"']+)"),
    re.compile(r"(?i)(ANTHROPIC_API_KEY|CLAUDE_API_KEY)=([^\s,;\"']+)"),
]
_BEARER_PATTERN = re.compile(r"(?i)Bearer\s+[A-Za-z0-9\-\._~+/=]+")
_AUTH_HEADER_PATTERN = re.compile(r'"Authorization"\s*:\s*"[^"]+"')

_SECRET_DICT_KEYS = {
    "api_key", "apikey", "fal_key", "fal_api_key",
    "openai_api_key", "gemini_api_key", "anthropic_api_key",
    "authorization", "bearer", "token",
}


def scrub_secrets(value: Any, max_len: int | None = None) -> Any:
    """递归净化 value 中的已知 secret 模式。

    支持 str / dict / list / 其他原样返回。max_len 仅对 str 生效。
    """
    if isinstance(value, str):
        return _scrub_str(value, max_len=max_len)
    if isinstance(value, dict):
        return {k: (REDACTED if k.lower() in _SECRET_DICT_KEYS else scrub_secrets(v, max_len=max_len))
                for k, v in value.items()}
    if isinstance(value, list):
        return [scrub_secrets(v, max_len=max_len) for v in value]
    return value


def _scrub_str(text: str, max_len: int | None) -> str:
    out = text
    for pat in _ENV_KEY_PATTERNS:
        out = pat.sub(lambda m: f"{m.group(1)}={REDACTED}", out)
    out = _BEARER_PATTERN.sub(f"Bearer {REDACTED}", out)
    out = _AUTH_HEADER_PATTERN.sub(f'"Authorization": "{REDACTED}"', out)
    if max_len is not None and len(out) > max_len:
        out = out[:max_len]
    return out
```

- [ ] **Step 4：跑测试确认 GREEN**

Run: `python -m pytest tests/jury_loop/test_secrets_scrubber.py -v`
Expected: 8 测试全 pass

- [ ] **Step 5：commit**

```bash
git add tools/jury_loop/secrets_scrubber.py tests/jury_loop/test_secrets_scrubber.py
git commit -m "feat(jury-loop): secrets_scrubber 净化 errors 与 payload（SEC-MINOR-2）"
```

---

### Task 1.2：reason_parser 纯函数

**Files:**
- Create: `tools/jury_loop/reason_parser.py`
- Test: `tests/jury_loop/test_reason_parser.py`

- [ ] **Step 1：写 RED 测试（含 hypothesis property）**

```python
# tests/jury_loop/test_reason_parser.py
from __future__ import annotations

import string

import pytest
from hypothesis import given, strategies as st

from tools.jury_loop.reason_parser import (
    BUILTIN_TAGS,
    parse_reason,
    reason_sanitized,
)


class TestReasonSanitized:
    def test_preserves_ascii_printable(self) -> None:
        assert reason_sanitized("plastic look, flat lighting") == "plastic look, flat lighting"

    def test_strips_control_chars(self) -> None:
        assert reason_sanitized("plastic\x00look\x1b[31m") == "plasticlook31m"

    def test_truncates_at_200(self) -> None:
        out = reason_sanitized("x" * 500)
        assert len(out) <= 200

    def test_strips_non_ascii(self) -> None:
        assert "中文" not in reason_sanitized("plastic 中文 look")


class TestParseReason:
    def test_single_tag_hit(self) -> None:
        assert parse_reason("plastic look") == {"plastic_look"}

    def test_multi_tag_hit(self) -> None:
        tags = parse_reason("plastic look, flat lighting")
        assert tags == {"plastic_look", "flat_light"}

    def test_case_insensitive(self) -> None:
        assert parse_reason("PLASTIC LOOK") == {"plastic_look"}

    def test_empty_string_returns_empty_set(self) -> None:
        assert parse_reason("") == set()

    def test_no_match_returns_empty_set(self) -> None:
        assert parse_reason("absolutely amazing render") == set()

    def test_returns_set_type(self) -> None:
        result = parse_reason("plastic look")
        assert isinstance(result, set)


class TestParseReasonProperty:
    @given(text=st.text(
        alphabet=string.ascii_letters + string.digits + " .,;-",
        max_size=80,
    ))
    def test_always_returns_set_subset_of_builtin(self, text: str) -> None:
        # TRAP-3 alphabet 限定为 jury 实际输出字符集
        result = parse_reason(text)
        assert isinstance(result, set)
        assert result <= BUILTIN_TAGS

    @given(text=st.text(
        alphabet=string.ascii_letters + " ",
        max_size=80,
    ))
    def test_pure_function_same_input_same_output(self, text: str) -> None:
        assert parse_reason(text) == parse_reason(text)
```

- [ ] **Step 2：跑测试确认 RED**

Run: `python -m pytest tests/jury_loop/test_reason_parser.py -v`
Expected: 全 fail，ImportError

- [ ] **Step 3：实现 reason_parser.py**

```python
# tools/jury_loop/reason_parser.py
"""jury reason 文本 → tag 集合的纯函数。"""
from __future__ import annotations

import re
import string

# tag → 触发关键词 patterns（spec §4.2 内置 tag_dictionary 起步集）
BUILTIN_TAG_DICTIONARY: dict[str, list[str]] = {
    "plastic_look":   ["plastic", "toy-like", "rubbery", "matte plastic"],
    "flat_light":     ["flat lighting", "no shadows", "ambient only", "diffuse"],
    "soft_edge":      ["soft edge", "blurry edge", "out of focus", "fuzzy"],
    "blurry":         ["blurry", "low resolution"],
    "dull_color":     ["dull", "muted", "low contrast"],
    "washed_out":     ["washed out", "faded", "desaturated"],
    "dark_overall":   ["too dark", "underexposed", "low light"],
    "cluttered_bg":   ["cluttered background", "busy background"],
    "distracting_bg": ["distracting background", "noisy backdrop"],
    # 备选 tag（rule 暂未配，实施时根据 jury 输出扩充）
    "dull_metal":        [],
    "fake_glass":        [],
    "missing_pbr":       [],
    "harsh_shadow":      [],
    "blown_highlights":  [],
    "jagged":            [],
    "oversharpened":     [],
    "oversaturated":     [],
    "color_cast":        [],
    "dirty_bg":          [],
}
BUILTIN_TAGS: frozenset[str] = frozenset(BUILTIN_TAG_DICTIONARY.keys())

_PRINTABLE_ASCII = set(string.printable) - set("\x0b\x0c")  # 排除 vert tab / form feed
_REASON_MAX_LEN = 200


def reason_sanitized(text: str) -> str:
    """SEC-MAJOR-3 净化：剥控制字符、ANSI escape、非 ASCII、≤200 截断。"""
    if not isinstance(text, str):
        return ""
    # 剥 ANSI escape
    no_ansi = re.sub(r"\x1b\[[0-9;]*m", "", text)
    # 剥所有非 ASCII printable（含中文 / 控制字符）
    cleaned = "".join(c for c in no_ansi if c in _PRINTABLE_ASCII and c not in {"\t", "\n", "\r"})
    return cleaned[:_REASON_MAX_LEN]


def parse_reason(text: str) -> set[str]:
    """jury reason → tag 集合。大小写不敏感；纯函数。"""
    if not isinstance(text, str) or not text:
        return set()
    lowered = text.lower()
    hits: set[str] = set()
    for tag, patterns in BUILTIN_TAG_DICTIONARY.items():
        for pat in patterns:
            if pat.lower() in lowered:
                hits.add(tag)
                break
    return hits
```

- [ ] **Step 4：跑测试确认 GREEN**

Run: `python -m pytest tests/jury_loop/test_reason_parser.py -v`
Expected: 全 pass（含 2 个 hypothesis property）

- [ ] **Step 5：commit**

```bash
git add tools/jury_loop/reason_parser.py tests/jury_loop/test_reason_parser.py
git commit -m "feat(jury-loop): reason_parser 含 reason_sanitized + 19 内置 tag（TRAP-3 alphabet 限定）"
```

---

## CP-2：rule_table（规则表加载 + 合并 + 范围校验）

### Task 2.1：内置 photoreal_v1.yaml

**Files:**
- Create: `tools/jury_loop/rules/photoreal_v1.yaml`

- [ ] **Step 1：写 yaml**

```yaml
# tools/jury_loop/rules/photoreal_v1.yaml
# 内置规则表 v1。spec §4.2 起步集 6 条规则 + 19 tag dictionary。
schema_version: 1

rules:
  - id: plastic_look_to_metallic
    when_tags: [plastic_look]
    prompt_addons:
      - "matte metallic finish, anodized aluminum"
      - "subtle anisotropic reflections"
    param_overrides:
      gemini_chat_image:        { temperature: 0.3, top_p: 0.9 }
      openai_images_edit:       { quality: "hd", style: "natural" }
      comfyui_workflow_cloud:   { denoise_strength: 0.45, cfg_scale: 7.5 }

  - id: flat_lighting_to_studio
    when_tags: [flat_light]
    prompt_addons:
      - "studio softbox lighting from left, fill light from right"
      - "subtle rim light, gradient seamless backdrop"
    param_overrides: {}

  - id: soft_edge_to_sharp
    when_tags: [soft_edge, blurry]
    prompt_addons:
      - "razor-sharp product edges, crisp specular highlights"
    param_overrides:
      # 仅 comfyui_workflow_cloud 支持 ControlNet 边缘锁
      comfyui_workflow_cloud:   { canny_strength: 0.95, canny_end_pct: 0.95 }

  - id: dull_color_to_vibrant
    when_tags: [dull_color, washed_out]
    prompt_addons:
      - "vivid saturated product colors, professional color grading"
    param_overrides: {}

  - id: dark_to_brighter
    when_tags: [dark_overall]
    prompt_addons: ["bright key light, high-key product photography"]
    param_overrides:
      comfyui_workflow_cloud:   { denoise_strength: 0.4 }
      gemini_chat_image:        { temperature: 0.4 }

  - id: cluttered_bg_to_clean
    when_tags: [cluttered_bg, distracting_bg]
    prompt_addons: ["seamless white backdrop, isolated product, clean studio background"]
    param_overrides: {}

tag_dictionary:
  plastic_look:    ["plastic", "toy-like", "rubbery", "matte plastic"]
  flat_light:      ["flat lighting", "no shadows", "ambient only", "diffuse"]
  soft_edge:       ["soft edge", "blurry edge", "out of focus", "fuzzy"]
  blurry:          ["blurry", "low resolution"]
  dull_color:      ["dull", "muted", "low contrast"]
  washed_out:      ["washed out", "faded", "desaturated"]
  dark_overall:    ["too dark", "underexposed", "low light"]
  cluttered_bg:    ["cluttered background", "busy background"]
  distracting_bg:  ["distracting background", "noisy backdrop"]
  dull_metal: []
  fake_glass: []
  missing_pbr: []
  harsh_shadow: []
  blown_highlights: []
  jagged: []
  oversharpened: []
  oversaturated: []
  color_cast: []
  dirty_bg: []
```

- [ ] **Step 2：验证 yaml 语法合法**

Run: `python -c "import yaml; yaml.safe_load(open('tools/jury_loop/rules/photoreal_v1.yaml','r',encoding='utf-8').read())"`
Expected: 不抛 yaml.YAMLError

- [ ] **Step 3：commit**

```bash
git add tools/jury_loop/rules/photoreal_v1.yaml
git commit -m "feat(jury-loop): 内置 photoreal_v1.yaml 规则表（6 rules + 19 tags）"
```

---

### Task 2.2：rule_table 加载 + 安全校验 + 合并语义

**Files:**
- Create: `tools/jury_loop/rule_table.py`
- Test: `tests/jury_loop/test_rule_table.py`
- Create: `tests/jury_loop/fixtures/user_rule_yaml_valid.yaml`
- Create: `tests/jury_loop/fixtures/user_rule_yaml_unknown_field.yaml`
- Create: `tests/jury_loop/fixtures/user_rule_yaml_wrong_schema.yaml`

- [ ] **Step 1：写 fixture yaml 三件套**

```yaml
# tests/jury_loop/fixtures/user_rule_yaml_valid.yaml
schema_version: 1
rules:
  - id: plastic_look_to_metallic   # 替换内置 (DRIFT-MAJOR-1 同 id 替换保留位置)
    when_tags: [plastic_look]
    prompt_addons: ["custom premium metallic finish"]
    param_overrides: {}
  - id: user_custom_rule           # 新增追加到末尾
    when_tags: [oversaturated]
    prompt_addons: ["balanced color grading"]
    param_overrides:
      comfyui_workflow_cloud: { cfg_scale: 6.0 }
tag_dictionary:
  plastic_look: ["fake plastic", "vinyl"]   # 追加而非替换
```

```yaml
# tests/jury_loop/fixtures/user_rule_yaml_unknown_field.yaml
schema_version: 1
rules:
  - id: typo_rule
    when_tags: [plastic_look]
    prompt_addon: ["拼错的字段（漏 s）"]    # closed schema 应 hard fail
    param_overrides: {}
```

```yaml
# tests/jury_loop/fixtures/user_rule_yaml_wrong_schema.yaml
schema_version: 999   # SEC-MINOR-3 降级 loop_disabled 而非 hard fail
rules: []
```

- [ ] **Step 2：写 RED 测试**

```python
# tests/jury_loop/test_rule_table.py
from __future__ import annotations

from pathlib import Path

import pytest

from tools.jury_loop.rule_table import (
    KNOWN_PARAMS,
    RuleTableLoadError,
    RuleTableUnsupportedSchemaWarning,
    RuleTableLookupResult,
    load_rule_table,
    lookup,
)


class TestLoadBuiltin:
    def test_load_default_returns_table(self) -> None:
        table = load_rule_table()
        assert table.schema_version == 1
        assert len(table.rules) == 6
        assert "plastic_look" in table.tag_dictionary

    def test_safe_load_blocks_python_obj(self, tmp_path: Path) -> None:
        evil = tmp_path / "evil.yaml"
        evil.write_text("!!python/object/apply:os.system ['echo pwn']")
        with pytest.raises(RuleTableLoadError):
            load_rule_table(user_yaml_path=evil, project_root=tmp_path)

    def test_user_yaml_outside_project_root_rejects(self, tmp_path: Path, fixture_dir: Path) -> None:
        outside = tmp_path / "outside.yaml"
        outside.write_text("schema_version: 1\nrules: []\n")
        # project_root 设为另一个不相干目录
        with pytest.raises(RuleTableLoadError, match="rule_table_path 必须在项目目录内"):
            load_rule_table(user_yaml_path=outside, project_root=tmp_path / "elsewhere")


class TestSchemaValidation:
    def test_unknown_field_hard_fail(self, fixture_dir: Path) -> None:
        with pytest.raises(RuleTableLoadError, match="unknown field"):
            load_rule_table(
                user_yaml_path=fixture_dir / "user_rule_yaml_unknown_field.yaml",
                project_root=fixture_dir.parent.parent,
            )

    def test_wrong_schema_version_warns_falls_back(self, fixture_dir: Path) -> None:
        with pytest.warns(RuleTableUnsupportedSchemaWarning):
            table = load_rule_table(
                user_yaml_path=fixture_dir / "user_rule_yaml_wrong_schema.yaml",
                project_root=fixture_dir.parent.parent,
            )
        # 仅用内置（用户规则全弃）
        assert len(table.rules) == 6


class TestUserOverrideMerge:
    def test_user_yaml_replaces_same_id_keeps_position(self, fixture_dir: Path) -> None:
        table = load_rule_table(
            user_yaml_path=fixture_dir / "user_rule_yaml_valid.yaml",
            project_root=fixture_dir.parent.parent,
        )
        # plastic_look_to_metallic 仍是 list 第 0 个（保留内置位置）
        assert table.rules[0].id == "plastic_look_to_metallic"
        assert table.rules[0].prompt_addons == ["custom premium metallic finish"]

    def test_user_yaml_appends_new_rule_to_tail(self, fixture_dir: Path) -> None:
        table = load_rule_table(
            user_yaml_path=fixture_dir / "user_rule_yaml_valid.yaml",
            project_root=fixture_dir.parent.parent,
        )
        # user_custom_rule 在末尾
        assert table.rules[-1].id == "user_custom_rule"

    def test_tag_dict_user_patterns_appended_not_replaced(self, fixture_dir: Path) -> None:
        table = load_rule_table(
            user_yaml_path=fixture_dir / "user_rule_yaml_valid.yaml",
            project_root=fixture_dir.parent.parent,
        )
        assert "plastic" in table.tag_dictionary["plastic_look"]   # 内置保留
        assert "fake plastic" in table.tag_dictionary["plastic_look"]   # 用户追加


class TestLookup:
    def test_single_tag_hit(self) -> None:
        table = load_rule_table()
        result = lookup(table, tags={"plastic_look"}, backend_kind="comfyui_workflow_cloud")
        assert "matte metallic finish, anodized aluminum" in result.prompt_addons
        assert result.param_overrides["denoise_strength"] == 0.45

    def test_multi_tag_hit_addons_dedup_preserve_order(self) -> None:
        table = load_rule_table()
        result = lookup(table, tags={"plastic_look", "flat_light"}, backend_kind="comfyui_workflow_cloud")
        # 顺序按 yaml 中 rule 出现顺序
        assert result.prompt_addons[0] == "matte metallic finish, anodized aluminum"
        assert "studio softbox lighting from left, fill light from right" in result.prompt_addons

    def test_no_match_returns_empty(self) -> None:
        table = load_rule_table()
        result = lookup(table, tags={"unmapped_tag"}, backend_kind="gemini_chat_image")
        assert result.prompt_addons == []
        assert result.param_overrides == {}

    def test_param_overrides_per_backend_isolated(self) -> None:
        table = load_rule_table()
        result_gemini = lookup(table, tags={"plastic_look"}, backend_kind="gemini_chat_image")
        result_comfy = lookup(table, tags={"plastic_look"}, backend_kind="comfyui_workflow_cloud")
        # gemini_chat_image 段不含 comfyui_workflow_cloud 字段，反之亦然
        assert "denoise_strength" not in result_gemini.param_overrides
        assert "temperature" not in result_comfy.param_overrides


class TestParamRangeClamp:
    def test_clamp_strength_to_unit_range(self) -> None:
        # M-12 越界 clamp + warnings
        from tools.jury_loop.rule_table import _clamp_param

        clamped, warning = _clamp_param("canny_strength", 2.0)
        assert clamped == 1.0
        assert "param_clamped" in warning

    def test_unknown_param_returns_orig_with_warning(self) -> None:
        from tools.jury_loop.rule_table import _clamp_param

        clamped, warning = _clamp_param("bogus_param", 99.0)
        assert clamped == 99.0
        assert "unknown_param" in warning


class TestKnownParams:
    def test_known_params_const_has_strength_keys(self) -> None:
        assert "canny_strength" in KNOWN_PARAMS
        assert KNOWN_PARAMS["canny_strength"] == (0.0, 1.0)
        assert KNOWN_PARAMS["cfg_scale"] == (1.0, 30.0)
```

- [ ] **Step 3：跑测试确认 RED**

Run: `python -m pytest tests/jury_loop/test_rule_table.py -v`
Expected: 全 fail

- [ ] **Step 4：实现 rule_table.py**

```python
# tools/jury_loop/rule_table.py
"""规则表加载 + 用户 yaml override + 范围校验。

安全：yaml.safe_load 强制；用户 yaml 路径限定在 project_root 内（SEC-MAJOR-1）。
"""
from __future__ import annotations

import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import yaml
from importlib.resources import files


SCHEMA_VERSION = 1
_BUILTIN_RESOURCE = "photoreal_v1.yaml"

# M-12 范围常量：(min, max)。已知 key 在此声明，未知 key 静默忽略
KNOWN_PARAMS: dict[str, tuple[float, float]] = {
    "canny_strength":   (0.0, 1.0),
    "depth_strength":   (0.0, 1.0),
    "canny_end_pct":    (0.0, 1.0),
    "denoise_strength": (0.0, 1.0),
    "img2img_strength": (0.0, 1.0),
    "guidance_scale":   (1.0, 30.0),
    "cfg_scale":        (1.0, 30.0),
    "steps":            (1, 200),
}

# DRIFT-MINOR-6 closed schema 允许字段集
_TOP_KEYS_ALLOWED = {"schema_version", "rules", "tag_dictionary"}
_RULE_KEYS_ALLOWED = {"id", "when_tags", "prompt_addons", "param_overrides"}
_BACKEND_KEYS_ALLOWED = {"fal", "fal_comfy"}


class RuleTableLoadError(Exception):
    """yaml load / schema 校验 / 路径限制 / 反序列化失败。"""


class RuleTableUnsupportedSchemaWarning(UserWarning):
    """SEC-MINOR-3 用户 yaml schema_version 不支持，降级仅用内置。"""


@dataclass(frozen=True)
class Rule:
    id: str
    when_tags: frozenset[str]
    prompt_addons: tuple[str, ...]
    param_overrides: dict[str, dict[str, Any]]   # {"fal": {...}, "fal_comfy": {...}}


@dataclass(frozen=True)
class RuleTable:
    schema_version: int
    rules: tuple[Rule, ...]
    tag_dictionary: dict[str, list[str]]


@dataclass
class RuleTableLookupResult:
    prompt_addons: list[str] = field(default_factory=list)
    param_overrides: dict[str, Any] = field(default_factory=dict)
    matched_rule_ids: list[str] = field(default_factory=list)
    matched_tags: set[str] = field(default_factory=set)
    warnings: list[str] = field(default_factory=list)


def load_rule_table(
    user_yaml_path: Path | None = None,
    project_root: Path | None = None,
) -> RuleTable:
    """加载内置 + 可选用户 yaml 合并后的规则表。"""
    builtin_text = files("tools.jury_loop.rules").joinpath(_BUILTIN_RESOURCE).read_text(encoding="utf-8")
    try:
        builtin = yaml.safe_load(builtin_text)
    except yaml.YAMLError as e:
        raise RuleTableLoadError(f"内置 photoreal_v1.yaml 解析失败：{e}") from e
    _assert_closed_schema(builtin)
    table = _build_table(builtin)

    if user_yaml_path is not None:
        if project_root is None:
            raise RuleTableLoadError("project_root 必填当 user_yaml_path 提供时")
        try:
            user_resolved = user_yaml_path.resolve()
            project_resolved = project_root.resolve()
            user_resolved.relative_to(project_resolved)
        except (OSError, ValueError) as e:
            raise RuleTableLoadError(f"rule_table_path 必须在项目目录内：{user_yaml_path}") from e

        try:
            user_text = user_yaml_path.read_text(encoding="utf-8")
            user = yaml.safe_load(user_text)
        except (OSError, yaml.YAMLError) as e:
            raise RuleTableLoadError(f"用户 yaml 加载失败：{e}") from e

        if not isinstance(user, dict):
            raise RuleTableLoadError("用户 yaml 顶层必须是 mapping")

        user_sv = user.get("schema_version")
        if user_sv != SCHEMA_VERSION:
            warnings.warn(
                f"用户 yaml schema_version={user_sv} 不被支持（仅 {SCHEMA_VERSION}），降级为仅用内置",
                RuleTableUnsupportedSchemaWarning,
                stacklevel=2,
            )
            return table

        _assert_closed_schema(user)
        table = _merge(table, user)

    return table


def _assert_closed_schema(data: dict[str, Any]) -> None:
    """closed schema：除 _* 前缀外不允许未知字段。"""
    if not isinstance(data, dict):
        raise RuleTableLoadError("yaml 顶层必须是 mapping")
    for k in data:
        if k.startswith("_"):
            continue
        if k not in _TOP_KEYS_ALLOWED:
            raise RuleTableLoadError(
                f"unknown field at top level: {k!r}（是否拼写错误？允许字段：{sorted(_TOP_KEYS_ALLOWED)}）"
            )

    rules = data.get("rules", [])
    if not isinstance(rules, list):
        raise RuleTableLoadError("rules 必须是 list")
    for i, rule in enumerate(rules):
        if not isinstance(rule, dict):
            raise RuleTableLoadError(f"rules[{i}] 必须是 mapping")
        for rk in rule:
            if rk.startswith("_"):
                continue
            if rk not in _RULE_KEYS_ALLOWED:
                raise RuleTableLoadError(
                    f"unknown field in rules[{i}] (id={rule.get('id', '?')!r}): {rk!r}"
                )

        # M-11 param_overrides 浅 + 一级 flat
        po = rule.get("param_overrides", {})
        if not isinstance(po, dict):
            raise RuleTableLoadError(f"rules[{i}].param_overrides 必须是 mapping")
        for backend, params in po.items():
            if backend not in _BACKEND_KEYS_ALLOWED:
                raise RuleTableLoadError(
                    f"rules[{i}].param_overrides 仅允许 backend keys {_BACKEND_KEYS_ALLOWED}，得到 {backend!r}"
                )
            if not isinstance(params, dict):
                raise RuleTableLoadError(f"rules[{i}].param_overrides.{backend} 必须是 mapping")
            for pkey, pval in params.items():
                if isinstance(pval, dict):
                    raise RuleTableLoadError(
                        f"rules[{i}].param_overrides.{backend}.{pkey} 不允许嵌套 dict（M-11 必须 flat）"
                    )
                if not isinstance(pval, (int, float, str, bool)):
                    raise RuleTableLoadError(
                        f"rules[{i}].param_overrides.{backend}.{pkey} 类型必须是 int|float|str|bool，得到 {type(pval)}"
                    )


def _build_table(data: dict[str, Any]) -> RuleTable:
    rules: list[Rule] = []
    for r in data.get("rules", []):
        rules.append(Rule(
            id=r["id"],
            when_tags=frozenset(r.get("when_tags", [])),
            prompt_addons=tuple(r.get("prompt_addons", [])),
            param_overrides={k: dict(v) for k, v in r.get("param_overrides", {}).items()},
        ))
    return RuleTable(
        schema_version=int(data["schema_version"]),
        rules=tuple(rules),
        tag_dictionary=dict(data.get("tag_dictionary", {})),
    )


def _merge(builtin: RuleTable, user: dict[str, Any]) -> RuleTable:
    """合并内置 + 用户 yaml。同 id 替换保留内置位置；新 id 追加；tag_dict 同 key 追加。"""
    builtin_rule_by_id = {r.id: i for i, r in enumerate(builtin.rules)}
    merged_rules: list[Rule] = list(builtin.rules)

    for ur in user.get("rules", []):
        rule_obj = Rule(
            id=ur["id"],
            when_tags=frozenset(ur.get("when_tags", [])),
            prompt_addons=tuple(ur.get("prompt_addons", [])),
            param_overrides={k: dict(v) for k, v in ur.get("param_overrides", {}).items()},
        )
        if ur["id"] in builtin_rule_by_id:
            merged_rules[builtin_rule_by_id[ur["id"]]] = rule_obj
        else:
            merged_rules.append(rule_obj)

    merged_tagdict = {k: list(v) for k, v in builtin.tag_dictionary.items()}
    for tag, patterns in user.get("tag_dictionary", {}).items():
        if tag in merged_tagdict:
            for p in patterns:
                if p not in merged_tagdict[tag]:
                    merged_tagdict[tag].append(p)
        else:
            merged_tagdict[tag] = list(patterns)

    return RuleTable(
        schema_version=builtin.schema_version,
        rules=tuple(merged_rules),
        tag_dictionary=merged_tagdict,
    )


def lookup(
    table: RuleTable,
    tags: set[str],
    backend_kind: str,   # 注册到 BACKEND_REGISTRY 的字符串 key（在 Task 2.5.5 中接入）
) -> RuleTableLookupResult:
    """规则表查询：返回合并后的 prompt_addons + param_overrides。

    NOTE: 本 Task (CP-2) 先用 str 签名 + 静态 KNOWN_PARAMS 实现；
    Task 2.5.5 (CP-2.5) 会回头改 _clamp_param 走 BACKEND_REGISTRY[backend_kind].known_params。
    """
    result = RuleTableLookupResult()
    seen_addons: set[str] = set()

    for rule in table.rules:
        if not rule.when_tags.issubset(tags):
            continue
        result.matched_rule_ids.append(rule.id)
        result.matched_tags |= rule.when_tags

        for addon in rule.prompt_addons:
            if addon not in seen_addons:
                result.prompt_addons.append(addon)
                seen_addons.add(addon)

        backend_params = rule.param_overrides.get(backend, {})
        for pkey, pval in backend_params.items():
            clamped, warn = _clamp_param(pkey, pval)
            if warn:
                result.warnings.append(warn)
            result.param_overrides[pkey] = clamped

    return result


def _clamp_param(key: str, value: Any) -> tuple[Any, str | None]:
    """对已知 param 做范围 clamp，越界写 warning；未知 key 透传写 unknown_param warning。"""
    if key not in KNOWN_PARAMS:
        return value, f"unknown_param: {key}"
    lo, hi = KNOWN_PARAMS[key]
    if not isinstance(value, (int, float)):
        return value, None
    if value < lo:
        return lo, f"param_clamped: {key}={value}→{lo}"
    if value > hi:
        return hi, f"param_clamped: {key}={value}→{hi}"
    return value, None
```

- [ ] **Step 5：跑测试确认 GREEN**

Run: `python -m pytest tests/jury_loop/test_rule_table.py -v`
Expected: 全 pass（含 closed schema / 路径限制 / safe_load / 合并语义 / range clamp）

- [ ] **Step 6：commit**

```bash
git add tools/jury_loop/rule_table.py \
        tests/jury_loop/test_rule_table.py \
        tests/jury_loop/fixtures/user_rule_yaml_valid.yaml \
        tests/jury_loop/fixtures/user_rule_yaml_unknown_field.yaml \
        tests/jury_loop/fixtures/user_rule_yaml_wrong_schema.yaml
git commit -m "feat(jury-loop): rule_table 安全加载 + 合并 + 范围 clamp（SEC-MAJOR-1 + DRIFT-MAJOR-1 + M-11/12）"
```

---

> **Plan 后续 checkpoints（CP-3 到 CP-8）继续在下个版本扩展，由于篇幅限制本文档保持精简版。每个后续 task 都遵循上面同样的 RED→GREEN→COMMIT 5-step 模板。**

## CP-2.5：BackendAdapter Protocol + 3 内置 adapter

### Task 2.5.1：BackendAdapter Protocol + 4 异常类 + Registry

**Files:**
- Create: `tools/jury_loop/backends/__init__.py`
- Create: `tools/jury_loop/backends/protocol.py`
- Test: `tests/jury_loop/test_backend_protocol.py`

`protocol.py` 实现 spec §2.1：`BackendRequest` / `BackendResponse` NamedTuple + `BackendAdapter` Protocol（5 接口：`kind` / `known_params` / `supports_controlnet` / `estimate_cost_usd` / `call`）+ 4 类异常 (`BackendError` 基类 / `BackendAuthError` / `BackendRateLimitError` / `BackendQuotaExceededError` / `BackendCallError`)。

`__init__.py` 维护 `BACKEND_REGISTRY: dict[str, BackendAdapter]`；`register_backend(adapter)` 函数；启动时调 `_register_builtin_adapters()` 把 3 个内置实例注册（lazy import 避免循环依赖）。

测试：
- BackendAdapter Protocol 用 `runtime_checkable` 装饰，typing 检查通过
- 注册重复 kind 抛 ValueError
- BACKEND_REGISTRY 启动时含 `gemini_chat_image` / `openai_images_edit` / `comfyui_workflow_cloud` 三个 key
- 异常分类：BackendAuthError isinstance BackendError

提交：`feat(jury-loop): BackendAdapter Protocol + Registry + 4 类异常分类`

---

### Task 2.5.2：gemini_chat_image adapter

**Files:**
- Create: `tools/jury_loop/backends/gemini_chat_image.py`
- Test: `tests/jury_loop/test_backend_gemini_chat_image.py`

实现 chat-completions 传图：POST `{base_url}/v1/chat/completions`（或 gemini-style `:generateContent`，按 base_url 路径自动判断），messages 数组含 `inline_data` (base64 image) + text prompt；response 提 base64 image 写盘。`known_params = {"temperature": (0.0, 2.0), "top_p": (0.0, 1.0), "top_k": (1, 100)}`；`supports_controlnet=False`；`estimate_cost_usd` 按 model 名查内置定价表（gemini-3-pro=0.04 / gemini-2.5-flash=0.01 / 默认 0.05）。

异常映射：HTTP 401/403 → BackendAuthError；429 → BackendRateLimitError；402 / quota / billing → BackendQuotaExceededError；其他 → BackendCallError。

测试 (用 `httpx.MockTransport` mock)：
- 正常调用返 BackendResponse 含 output_image_path
- 401 → BackendAuthError
- 429 + Retry-After header → BackendRateLimitError
- estimate_cost_usd 按 model 返不同值
- known_params 含 temperature 范围 (0.0, 2.0)

提交：`feat(jury-loop): gemini_chat_image adapter（chat-completions 传图，HTTP 错误分类）`

---

### Task 2.5.3：openai_images_edit adapter

**Files:**
- Create: `tools/jury_loop/backends/openai_images_edit.py`
- Test: `tests/jury_loop/test_backend_openai_images_edit.py`

实现 REST `/v1/images/edits`：multipart POST 含 image + prompt，response url/b64_json 取图写盘。`known_params = {"quality": (None, None), "style": (None, None), "n": (1, 4), "size": (None, None)}`（None 表示非数值，仅做存在性 + 类型校验）；`supports_controlnet=False`；`estimate_cost_usd` 按 size 维度（1024×1024=$0.04 / 1024×1792=$0.08）。

异常映射同 Task 2.5.2。

测试：
- 正常调用 multipart body 含 image + prompt 字段
- 400 + body 含 "content_policy_violation" → BackendCallError（不是 auth）
- 401 → BackendAuthError
- 402 / "insufficient quota" → BackendQuotaExceededError
- known_params n 字段范围 (1, 4)

提交：`feat(jury-loop): openai_images_edit adapter（multipart /v1/images/edits）`

---

### Task 2.5.4：comfyui_workflow_cloud adapter（任意 ComfyUI 兼容云 + ControlNet 锁）

**Files:**
- Create: `tools/jury_loop/backends/comfyui_workflow_cloud.py`
- Test: `tests/jury_loop/test_backend_comfyui_workflow_cloud.py`

**kind = "comfyui_workflow_cloud"**（不再叫 fal_comfy）。包装现有 `src/cad_spec_gen/data/python_tools/fal_comfy_enhancer.py:enhance_image()`（baseline 模块名保留不动）；adapter 通过 `request.base_url` 决定上传到哪个 vendor：
- 默认 `https://queue.fal.run/fal-ai/comfy`（fal.ai）
- 用户可改 `https://api.runcomfy.com/...` / `https://your-self-hosted.example.com/...` 等
- 任何接受 ComfyUI workflow JSON 的 endpoint 都能跑

`known_params = {"denoise_strength": (0.0, 1.0), "cfg_scale": (1.0, 30.0), "canny_strength": (0.0, 1.0), "canny_end_pct": (0.0, 1.0), "depth_strength": (0.0, 1.0), "steps": (1, 200), "guidance_scale": (1.0, 30.0)}`；`supports_controlnet=True`；`estimate_cost_usd = 0.18`（fal.ai 默认价；其他 vendor 用户可在 plugin 阶段覆写）。

异常映射：现有 fal_comfy_enhancer 抛的 `fal_client.exceptions.*` + 通用 HTTP 错误（请求其他 vendor 时不一定走 fal_client）映射到 BackendError 子类。

测试：
- 正常调用 default base_url (fal.ai) 走入 fal_comfy_enhancer.enhance_image() (mock)
- 切 base_url 到自定义 endpoint 时仍以 ComfyUI workflow JSON 形式上传（mock 验证 request body 含 workflow JSON）
- supports_controlnet 返 True
- known_params 含 ControlNet 参数 (canny_strength / depth_strength)

提交：`feat(jury-loop): comfyui_workflow_cloud adapter 通用 ComfyUI 工作流云端（fal.ai/RunComfy/自部署）+ ControlNet`

---

### Task 2.5.5：rule_table.lookup 接入 BACKEND_REGISTRY known_params

**Files:**
- Modify: `tools/jury_loop/rule_table.py`
- Modify: `tests/jury_loop/test_rule_table.py`

回头改 rule_table.py（CP-2 已用 `backend_kind: str` 签名；本 task 仅改 `_clamp_param` 内部）：
1. `_clamp_param(key, value, backend_kind: str)` 增加 backend_kind 参数；改为从 `BACKEND_REGISTRY[backend_kind].known_params` 拿白名单 + 范围而非读静态 KNOWN_PARAMS
2. `lookup` 内部调 `_clamp_param(pkey, pval, backend_kind=backend_kind)` 传入
3. 删除 rule_table.py 顶部静态 KNOWN_PARAMS 常量（CP-2 临时占位过渡）；改用 `BACKEND_REGISTRY[backend_kind].known_params` 动态拿
4. backend_kind 不在 BACKEND_REGISTRY 时 lookup 抛 ValueError（与 orchestrator Gate-1 配合：orchestrator 早就拦截，lookup 只是兜底）

测试加：
- lookup(backend_kind="gemini_chat_image") → temperature 字段命中 + clamp
- lookup(backend_kind="comfyui_workflow_cloud") → canny_strength 命中
- lookup(backend_kind="openai_images_edit") → quality/style 字符串字段不 clamp 仅存在性校验
- lookup(backend_kind="unknown_kind") 抛 ValueError "kind 未注册到 BACKEND_REGISTRY"

提交：`refactor(jury-loop): rule_table.lookup 接入 BACKEND_REGISTRY.known_params（接 Task 2.5.1）`

---

## CP-3：llm_fallback + score_select Strategy Protocol

### Task 3.1：llm_fallback (复用 jury llm_client / 不同 prompt template)

**Files:**
- Create: `tools/jury_loop/llm_fallback.py`
- Test: `tests/jury_loop/test_llm_fallback.py`

接口：`translate(unmapped_reason: str, sanitized_reason: str) -> list[str]` 返 prompt_addons；调用 jury llm_client（mock 在测试里），prompt template 形如 "你是产品摄影术导。基于此 jury 反馈：{reason}，给出 ≤3 个英文 prompt 增强词，逗号分隔，不解释。"

测试：
- 正常调用返 list[str]，每元素 ≤80 字
- 空 reason 返空 list
- LLM client 抛异常 → raise LlmFallbackError（不静默吞）
- 返回包含 secrets 字符串时（mock 注入 `FAL_KEY=xxx`），调用方负责 scrub（fallback 自身不 scrub）

提交：`feat(jury-loop): llm_fallback 复用 jury client + 翻译 prompt template`

---

### Task 3.2：score_select Strategy Protocol + 两实现

**Files:**
- Create: `tools/jury_loop/score_select.py`
- Test: `tests/jury_loop/test_score_select.py`

按 spec §4.5.2：定义 `CandidateImage` / `SelectionResult` NamedTuple；`ScoreSelectStrategy` Protocol 含 `select(candidates, jury_callable, budget) -> SelectionResult`；`PickMaxJuryStrategy` 调一次 jury_callable 选高分；`ForceRetryStrategy` 不调 jury 直接选 list[1]；`STRATEGY_REGISTRY` dict 提供字符串到类的映射。

测试：
- pick_max_jury：retry > baseline → 选 retry
- pick_max_jury：retry < baseline → 选 baseline（保守）
- pick_max_jury：retry == baseline → 选 baseline
- pick_max_jury：jury_callable 抛异常 → 选 baseline + extra_jury_calls=0
- force_retry：直接选 retry，extra_jury_calls=0
- force_retry：候选 list 长度 ≠ 2 抛 ValueError（SP1 收紧）
- registry：字符串 → 实例化正确策略

提交：`feat(jury-loop): score_select Strategy Protocol + Pick* 实现（M-2 SP3 兼容）`

---

## CP-4：enhance_budget + metadata sidecar

### Task 4.1：enhance_budget.py 跨 SP 通用 LoopBudget

**Files:**
- Create: `enhance_budget.py`
- Test: `tests/jury_loop/test_enhance_budget.py`

按 spec §3 实现注记：`JURY_LLM_CALL_COST_USD = 0.005`；`USD_TO_CNY_RATE = 7.2`；**不再保留** `BACKEND_RETRY_COST_USD` 静态常量（每个 BackendAdapter 自己实现 `estimate_cost_usd`）；`LoopBudget(cap_usd, n_views)` 含 `_lock: threading.Lock`；`try_spend(amount) -> bool`、`record_actual(amount)`、`spent` 只读、`extra_cost_cny` 属性。`estimate_retry_cost(adapter: BackendAdapter, request: BackendRequest, with_jury: bool)` 函数 = `adapter.estimate_cost_usd(request) + (JURY_LLM_CALL_COST_USD if with_jury else 0)`。

测试：
- try_spend 累计扣减
- 超 cap 返 False 不扣减
- record_actual 修正
- 并发调 try_spend 总和正确（threading 测试 100 线程 × 0.01 各调一次）
- 默认 cap 固定 1.5 USD（≈ 5 视角×0.25 + 安全余量，与 spec §4.1 一致）
- extra_cost_cny 换算正确

提交：`feat(enhance-budget): LoopBudget 跨 SP 通用 + threading.Lock（M-1 + M-13）`

---

### Task 4.2：metadata sidecar schema + 写出

**Files:**
- Create: `tools/jury_loop/metadata.py`
- Test: `tests/jury_loop/test_metadata.py`

`SidecarSchema` dataclass 锁 §4.4 字段集；`write_sidecar(view, render_dir, ...)` 调用前必经 `Path(view).name` basename + 拒绝 `..`/绝对路径前缀（SEC-MAJOR-2）；`errors[].message_summary` + `backend_payload` 写盘前过 `scrub_secrets`；`write_degraded_sidecar(view, error)` 给 cmd_enhance 异常隔离时用；JSON 字段顺序按 spec §7 强制（OrderedDict 序列化）。

测试覆盖 §4.4 全部 5 种特殊状态形态：loop_disabled / above_threshold / delivered_retry (pick_max_jury) / delivered_retry (force_retry) / delivered_baseline-with-retry。
路径净化测试：`view = "../../etc/passwd"` 抛 ValueError。
secrets 测试：`errors[].message_summary` 含 `FAL_KEY=sk-real` 写盘后字符串不含 sk-real，含 `[REDACTED]`。

提交：`feat(jury-loop): metadata sidecar schema + 路径净化 + scrub_secrets（A-3 + SEC-MAJOR-2 + SEC-MINOR-2）`

---

## CP-5：orchestrator 主入口

### Task 5.1：orchestrator 视角级 hook + 全 Gate 流程

**Files:**
- Create: `tools/jury_loop/orchestrator.py`
- Test: `tests/jury_loop/test_orchestrator.py`

接口：
```python
def run_loop_if_eligible(
    *,                                  # kwarg-only（防止位置参数 typo 错位）
    view: str,
    backend_kind: str,                  # 来自 jury_loop.backend.kind
    rc: dict[str, Any],
    baseline_path: Path,
    base_params: dict[str, Any],        # baseline 跑时实际生效的 backend params（retry 浅合并的 base）
    budget: LoopBudget,
    project_root: Path,
    config: JuryLoopConfig,             # pipeline_config 解析后的 dataclass
    jury_profile: JuryProfile,          # 已加载的 JuryProfile（subprocess + llm_fallback 共用）
    jury_profile_path: Path,            # photo3d_jury subprocess 的 --config 参数
    # adapter 由 orchestrator 自己从 BACKEND_REGISTRY 取，不再注入 enhance_image_callable
) -> LoopResult:
    """单视角闭环。LoopResult 含 final_path / loop_status / sidecar 数据。"""
```

> **签名升级（SP1 session 5 spec rev 3 决议）**：相比初稿加 `*` kwarg-only + `base_params` / `jury_profile` / `jury_profile_path` 三 kwarg。kwarg-only 防止位置参数 typo 错位；`base_params` 让 retry 浅合并不依赖全局 rc dict 推断；`jury_profile` + `jury_profile_path` 让 subprocess 与 llm_fallback 共用同一 JuryProfile 实例，避免重复 IO 加载。

实现 §3 所有 10 步 + 8 个 Gate：
- Gate-1: `BACKEND_REGISTRY.get(backend_kind)` 为 None → loop_disabled
- 拿到 adapter = BACKEND_REGISTRY[backend_kind] 后，retry 调用走 `adapter.call(BackendRequest(...))`
- retry 失败 catch BackendAuthError/BackendRateLimitError/BackendQuotaExceededError/BackendCallError 4 类异常
- 异常类型直接对应 retry_auth_failed / retry_rate_limited / retry_quota_exceeded / retry_failed loop_status；不再读 HTTP 码（adapter 已映射好）
- BackendResponse.actual_cost_usd 不为 None → budget.record_actual；为 None → sidecar.warnings 加 cost_estimated_only

调用 score_select 策略；写 sidecar 经 metadata 模块；返回 final_path 给 cmd_enhance 用作 hero_image 更新。

测试 (用 mock 注入 jury subprocess + enhance_image)：
- Gate-1 backend_kind="engineering" (未注册) → loop_disabled
- Gate-2 enabled=false → loop_disabled
- Gate-3 jury 失败 → jury_unavailable
- Gate-3 jury 返 reason="" → empty_reason
- Gate-4 score=80 → above_threshold
- Gate-5 budget 耗尽 → cost_capped
- Gate-6 reason 全 unknown tag → no_tags_parsed
- Gate-7 全 miss + llm_fallback=false → no_rules_hit_no_llm
- Gate-8 adapter.call 抛 BackendRateLimitError → retry_rate_limited
- Gate-8 adapter.call 抛 BackendAuthError → retry_auth_failed
- Gate-8 adapter.call 抛 BackendQuotaExceededError → retry_quota_exceeded
- Gate-8 adapter.call 抛 BackendCallError → retry_failed
- 正常流程 retry 提分 → delivered_retry
- 正常流程 retry 降分 (pick_max_jury) → delivered_baseline + retry_score_delta < 0
- BackendResponse.actual_cost_usd is None → sidecar.warnings 含 cost_estimated_only
- 测试用 mock adapter 注册到 BACKEND_REGISTRY 模拟 vendor 行为，不调真 HTTP

提交：`feat(jury-loop): orchestrator 视角级 hook 全 Gate 流程 + 错误码细分（OPS-MAJOR-5）`

---

## CP-6：photo3d-jury CLI 扩接口

### Task 6.1：--single-view + --image flag (SUPPRESS)

**Files:**
- Modify: `tools/photo3d_jury.py:_build_parser` + `main`
- Test: `tests/jury_loop/test_jury_cli_single_view.py`

`_build_parser` 加：
```python
p.add_argument("--single-view", help=argparse.SUPPRESS)
p.add_argument("--image", nargs="+", help=argparse.SUPPRESS)
```

`main()` 检测 `args.single_view` 时分支：跳过 batch 全视角循环、跳过 PHOTO3D_JURY_REPORT.json 写盘；遍历 `--image` 列表对每张调 LLM 解析 verdict；list[dict] → stdout JSON dump；orchestrator 解析时检测：rc != 0 / json.JSONDecodeError / list len 不匹配 / 任一 verdict=needs_review → jury_unavailable。

stdout cap (SEC-MINOR-4)：subprocess 调用方用 Popen + 1 MiB read limit。

测试 (subprocess + mock):
- `--single-view V1 --image baseline.jpg` 返 1 元素 list
- `--single-view V1 --image a.jpg b.jpg` 返 2 元素 list  
- `--single-view` 但缺 `--image` argparse error
- LLM 解析失败 needs_review → exit code 0 + verdict=needs_review（调用方解析为 jury_unavailable）

提交：`feat(jury-cli): --single-view + --image nargs+ 隐藏 flag（M-3 + N-3 + M-10）`

---

## CP-7：cmd_enhance 集成

### Task 7.1：cmd_enhance 视角级 hook + try/except 隔离

**Files:**
- Modify: `cad_pipeline.py:cmd_enhance` (line ~2700, baseline 跑完后)
- Modify: `cad_pipeline.py` argparse — 加 `--rerun-loop` flag
- Test: `tests/jury_loop/test_cmd_enhance_integration.py`

视角循环改 (在 baseline `enhance_image()` 调用之后)：
```python
try:
    loop_result = orchestrator.run_loop_if_eligible(
        view=view,
        backend_kind=jury_loop_config.backend.kind,   # 从 config.backend.kind 取，不再传 fal/fal_comfy 字面量
        rc=rc,
        baseline_path=baseline_path,
        base_params=baseline_backend_params,          # baseline 实际生效的 backend params（与 backend_kind 匹配）
        budget=budget,
        project_root=PROJECT_ROOT,
        config=jury_loop_config,
        jury_profile=jury_profile,                    # 已加载的 JuryProfile 实例（subprocess + llm_fallback 共用）
        jury_profile_path=jury_profile_path,
    )
    if reference_mode == "v1_anchor" and view == "V1":
        hero_image = loop_result.final_path   # BL-4 状态传递
except FileNotFoundError as e:
    # Precondition fail-fast：baseline 文件缺失；不写 sidecar 防误覆盖既有产物 + 防无限循环
    log.warning("Loop hook precondition failed for %s (baseline missing): %s", view, e)
    continue
except ValueError as e:
    # Precondition fail-fast：view 名注入（path traversal 等）；不写 sidecar 同上
    log.error("Loop hook precondition failed for %s (invalid view): %s", view, e)
    continue
except Exception as e:
    # 未知 Exception：orchestrator 内层已 write_degraded_sidecar；此处仅 log
    # 不重写 sidecar — `--rerun-loop` 默认 false 时下次会 fast-path 跳过该视角（spec §6 OPS-MAJOR-3）
    log.error("Loop hook crashed for %s: %s", view, e)
```

注：cmd_enhance 既有的 backend 分发逻辑（gemini/comfyui/fal/fal_comfy/engineering）保留 — 那是 baseline enhance 用的。jury_loop 的 backend_kind 是闭环 retry 专用配置，独立于 baseline backend；用户可以 baseline 用 engineering（零成本），retry 用 gemini_chat_image（云上调优）。

LoopBudget 实例化在视角循环外；视角循环结束后聚合 loop_summary（仅当 enabled=true 才写入 ENHANCEMENT_REPORT.json，OPS-MAJOR-2）。

`--rerun-loop` flag (OPS-MAJOR-3) 控制：默认 false 时 detect 既有 sidecar 跳过该视角；true 时强制重跑。

测试：
- L2 mock orchestrator raise 任意 Exception → 其他视角不受影响 + 写 degraded sidecar（DRIFT-MAJOR-7）
- v1_anchor 模式 V1 retry 成功后 V2 拿到 V1_enhanced.jpg 作 anchor（BL-4）
- enabled=false 跑完后 ENHANCEMENT_REPORT.json 不含 loop_summary key（OPS-MAJOR-2）
- --rerun-loop false + sidecar 已存在 delivered_retry → fast path skip
- --rerun-loop true → 强制重跑

提交：`feat(cmd-enhance): 视角级 hook + 异常隔离 + --rerun-loop + 条件 loop_summary（BL-4 + DRIFT-MAJOR-7 + OPS-MAJOR-2/3）`

---

### Task 7.2：pipeline_config.json 加 jury_loop 段

> **物理实施前置至 Task 5.0**（CP-5 子 plan `2026-05-11-cp5-orchestrator-plan.md` Task 5.0）：`tools/jury_loop/config.py` 含 `JuryLoopConfig` / `BackendConfig` / `load_jury_loop_config` 已 SP1 session 5 commit `6b47560` 落地。本节剩余范围仅做：(a) 把 `pipeline_config.json` 顶层加 `jury_loop` 段实例；(b) 加一个 config-load 集成测试 锁 schema 校验路径。dataclass 实现 + 单测已不在 Task 7.2 范围。

**Files:**
- Modify: `pipeline_config.json`
- Test: 一个简单的 config 解析测试

按 spec §4.1：顶层 `enabled=true` + `cost_cap_usd=1.5`；`backend` 子段含 5 项 (kind / base_url / api_key_env / model_name / timeout_s)；`advanced` 子段含 5 项；schema 校验函数检测顶层与 advanced 同名 key 共存 → ValueError（DRIFT-MAJOR-4）。

实现 `JuryLoopConfig` dataclass（嵌套含 `BackendConfig` dataclass：`kind` / `base_url` / `api_key_env` / `model_name` / `timeout_s`） + `load_jury_loop_config(pipeline_config_dict) -> JuryLoopConfig`。`api_key_env` 字段触发时通过 `os.environ.get(name)` 读 raw key，缺失时启动期 warn 但不阻塞（首次 retry 时再 hard fail）；妥善处理 backend.kind ∉ BACKEND_REGISTRY 时 config 加载不抛（让 orchestrator Gate-1 决定走 loop_disabled）。

提交：`feat(jury-loop): pipeline_config.json jury_loop 段 + JuryLoopConfig 嵌套 BackendConfig（M-5 + M-6 + M-8）`

---

## CP-8：L3 契约 + L4 smoke + 文档

### Task 8.1：L3 契约测试（schema 锁字段集）

**Files:**
- Create: `tests/jury_loop/test_l3_contract.py`

JSON Schema 锁定 sidecar / loop_summary 字段集；用户 yaml override 6+ fixture 案例 case；ENHANCEMENT_REPORT additive-only 兼容性回归（v0/v1 解析器读 v1 报告不破）。

提交：`test(jury-loop): L3 契约 schema 锁 + additive-only 回归`

---

### Task 8.2：L4 smoke 端到端（marker）

**Files:**
- Create: `tests/jury_loop/test_l4_smoke.py`

```python
@pytest.mark.requires_fal_key
@pytest.mark.slow
class TestL4Smoke:
    def test_l4_1_提分(self, tmp_path):  # 跑 1 张已知低分 baseline 跑 10 次取均值 score 提升 > 5
    def test_l4_2_防误触发(self, tmp_path):  # baseline 已 score≥75 时 loop_triggered=False
    def test_l4_3_anchor_串行(self, tmp_path):  # v1_anchor 模式 V2 anchor 路径 == V1_enhanced.jpg
```

CI 默认 skip；本地 `pytest --run-slow tests/jury_loop/test_l4_smoke.py`。

DRIFT-MINOR-8 fixture LFS 推迟 §11 follow-up——SP1 用临时本地 fixture 即可。

提交：`test(jury-loop): L4 smoke 三 case（fal_key marker，CI skip）`

---

### Task 8.3：文档 + AGENTS.md / 更新主 README

**Files:**
- Modify: `docs/cad-jury-config.md`（如有）或新建 `docs/jury-loop-config.md`
- Modify: `AGENTS.md`（追加 SP1 章节）

写法：用户视角"闭环是什么、怎么开关、cost 估算、问题排查"；不要重复 spec 技术细节。

提交：`docs(jury-loop): 用户文档 + AGENTS.md SP1 段`

---

### Task 8.4：最终验收 — 全测试 + Linux/Windows CI 双绿

- [ ] 跑全量 pytest：`python -m pytest tests/jury_loop/ -v --tb=short`
- [ ] 跑全量回归：`python -m pytest --tb=short`
- [ ] 检查 ENHANCEMENT_REPORT 旧解析器（autopilot）能否 import 不爆
- [ ] git push → 等 CI Linux + Windows 双绿
- [ ] 开 PR

---

## §11 实施期 follow-up（plan 内不办）

- N-2 终端日志 warn/info 中文化聚合 → SP4 wizard
- N-5 llm_fallback 启用时 wizard 提示费用 → SP4
- N-10 rule_table 加载 cache → 实测有性能瓶颈才加
- N-11 score_delta float / int 一致性 → 实施时按 metadata 字段类型严格 int
- N-12 L4-1 deterministic seed → 数据集成熟后做
- N-13 tag_dictionary vs rule 同 key 不对称 → 用户反馈驱动
- N-14 部分命中 + LLM 失败边界 → §4.6 enum 注释已写，实施时注意
- DRIFT-MINOR-8 L4 fixture LFS → 跑通 SP1 后入 git LFS
- OPS-MINOR-7 跨次统计 dashboard → SP4
- OPS-MINOR-8 PII redact 扩展 → SP4

---

## Self-Review

**Spec coverage:**
- §1 目标 → CP-0 起步 / 全 plan 兑现
- §2 模块布局 → CP-0 创建 + CP-1/2/3/4 落实每模块
- §3 数据流 + Gates → Task 5.1 orchestrator 全 8 Gate 测试
- §4.1 config schema → Task 7.2
- §4.2 内置 yaml → Task 2.1
- §4.3 合并语义 → Task 2.2
- §4.4 sidecar schema → Task 4.2
- §4.5 score_select Protocol → Task 3.2
- §4.6 loop_status enum → Task 5.1 测试 + Task 4.2 sidecar 写 loop_status_zh
- §5 错误矩阵 → Task 5.1 / Task 4.2 共同覆盖
- §6 jury CLI → Task 6.1
- §7 loop_summary → Task 7.1
- §8 测试金字塔 → Task 8.1 (L3) + Task 8.2 (L4)
- §9 风险 → §11 follow-up 登记
- §10 SP2-5 移交 → spec 已锁，plan 内不动
- §11 follow-up → plan §11 同步

**Placeholder scan：** plan 后段 CP-3 到 CP-8 用了"接口签名 + 测试要点 + 提交语句"的紧凑形式（非完整 RED→GREEN→COMMIT 5 步），rationale：avoid 文件超长；实施时 subagent-driven 模式每 Task 拿到上下文会自动展开。如果你希望每个 task 都展开成完整 5 步代码块，这是 follow-up 增强工作。

**Type consistency：** Rule / RuleTable / RuleTableLookupResult / LoopBudget / LoopResult / SidecarSchema / JuryLoopConfig / CandidateImage / SelectionResult / ScoreSelectStrategy 在引用处全部一致；no naming drift。

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-05-10-jury-prompt-loop-plan.md`. 两个执行选项：**

**1. Subagent-Driven（推荐）** — 每 Task 派一个新 subagent 跑 RED→GREEN→COMMIT 然后我两阶段 review；适合本 plan（Task 数多 + 跨多模块）

**2. Inline Execution** — 在当前 session 跑完所有 task，按 CP 边界做 checkpoint 暂停；上下文压力大但中间不切换

**哪种？**
