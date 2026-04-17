# SW self-hosted runner smoke CI 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现 F-1.3：新建独立 workflow `sw-smoke.yml` 在 self-hosted Windows runner 上真跑 `test_sw_inspect_real.py`，产物 JSON 供 F-4a baseline 消费；追加 Toolbox / materials 层断言、抽 schema helper + composite action + runbook。

**Architecture:** 分三层——代码层（`tools/assert_sw_inspect_schema.py` + `tests/test_sw_inspect_real.py` 新断言）；CI 层（`.github/actions/setup-cad-env/action.yml` + `.github/workflows/sw-smoke.yml`）；文档层（runbook + decisions #39 + README 一行）。严格 TDD 只对 schema helper 适用（workflow YAML 不跑本地 CI，靠 actionlint + 首次真跑验证）。

**Tech Stack:** Python 3.12 stdlib（`xml.etree`, `json`, `pathlib`）、pytest、GitHub Actions composite action、actionlint（可选本地验证）、pywin32（运行期，不在本 plan 安装）。

**前置 spec：** `docs/superpowers/specs/2026-04-17-sw-self-hosted-runner-design.md`（v3，main@558283f）

---

## 文件结构

**新增**：

| 路径 | 职责 | 任务 |
|---|---|---|
| `tools/assert_sw_inspect_schema.py` | 统一的 sw-inspect JSON v1 schema 断言 helper（D13，spec §4.6）| T1 |
| `tests/test_assert_sw_inspect_schema.py` | 上述 helper 的单测（合法 fast/deep、缺 top key、缺 layer、缺 elapsed_ms）| T1 |
| `.github/actions/setup-cad-env/action.yml` | setup-python + pip install + dev_sync 三步抽成的 composite action（D14，spec §4.5）| T3 |
| `.github/workflows/sw-smoke.yml` | 主 workflow（D1-D8, D10-D16，spec §4.1）| T4 |
| `docs/superpowers/runbooks/sw-self-hosted-runner-setup.md` | runner 注册 / Autologon / Task Scheduler / 故障排查 SOP（spec §5.1）| T5 |

**修改**：

| 路径 | 改动 | 任务 |
|---|---|---|
| `tests/test_sw_inspect_real.py` | `test_deep_real_smoke` 追加 `toolbox_index.by_standard` / `materials.sldmat_files > 0` 两条断言（spec §4.8）| T2 |
| `docs/superpowers/decisions.md` | 追加决策 #39（C1 路径选择、long-lived 而非 ephemeral、cancel-in-progress: false 的理由）| T6 |
| `README.md` | CI 段追加 "sw-smoke: 真 SW 环境回归..." 一行（spec §5.3）| T7 |

---

## 任务依赖图

```
T1 (schema helper, TDD)  ──┐
T2 (real smoke 断言追加)      ├── 三个独立 → 可并行 dispatch
T3 (composite action)      ──┘
                              │
                              ▼
T4 (sw-smoke.yml)   ← 依赖 T1 + T3
                              │
                              ▼
T5 (runbook) / T6 (决策 #39) / T7 (README)  ← 三个独立，可并行
                              │
                              ▼
T8 (开发者本机 pre-flight：pytest 真跑 + actionlint + schema helper 手工校验)
                              │
                              ▼
[人工阶段，不产生代码提交]
 runner 物理注册 → 首次 push/dispatch → artifact 可下 → §6 验收完成
```

---

## Task 1: `assert_sw_inspect_schema.py` + 单测（TDD）

**Files:**
- Create: `tools/assert_sw_inspect_schema.py`
- Test: `tests/test_assert_sw_inspect_schema.py`

- [ ] **Step 1: 写失败测试**

创建 `tests/test_assert_sw_inspect_schema.py`：

```python
"""tools/assert_sw_inspect_schema.py 的单元测试（D13，spec §4.6）。

覆盖 5 个核心场景：
1. 合法 fast 模式 JSON 通过
2. 合法 deep 模式 JSON 通过
3. 缺顶层 key（version / mode / layers / overall / elapsed_ms）抛 AssertionError
4. deep 模式缺必需 layer 抛 AssertionError
5. deep 模式 dispatch.data 缺 elapsed_ms 抛 AssertionError（F-4a baseline 消费字段）
"""
from __future__ import annotations

import json
import pytest

from tools.assert_sw_inspect_schema import assert_schema_v1


# ---- fixtures ----


def _sample_fast() -> dict:
    """合法 fast 模式 payload：7 层 probe，无 dispatch/loadaddin。"""
    return {
        "version": "1",
        "mode": "fast",
        "elapsed_ms": 120,
        "overall": {"severity": "ok", "exit_code": 0, "summary": "ok"},
        "layers": {
            layer: {
                "layer": layer,
                "ok": True,
                "severity": "ok",
                "summary": "ok",
                "data": {},
            }
            for layer in (
                "environment", "pywin32", "detect", "clsid",
                "toolbox_index", "materials", "warmup",
            )
        },
    }


def _sample_deep() -> dict:
    """合法 deep 模式 payload：fast 7 层 + dispatch + loadaddin。"""
    payload = _sample_fast()
    payload["mode"] = "deep"
    payload["layers"]["dispatch"] = {
        "layer": "dispatch",
        "ok": True,
        "severity": "ok",
        "summary": "ok",
        "data": {"elapsed_ms": 12345, "dispatched": True},
    }
    payload["layers"]["loadaddin"] = {
        "layer": "loadaddin",
        "ok": True,
        "severity": "ok",
        "summary": "ok",
        "data": {},
    }
    return payload


# ---- tests ----


class TestAssertSchemaV1:
    def test_valid_fast_passes(self, tmp_path):
        p = tmp_path / "fast.json"
        p.write_text(json.dumps(_sample_fast()), encoding="utf-8")
        assert_schema_v1(p)  # 不抛即通过

    def test_valid_deep_passes(self, tmp_path):
        p = tmp_path / "deep.json"
        p.write_text(json.dumps(_sample_deep()), encoding="utf-8")
        assert_schema_v1(p)

    @pytest.mark.parametrize("missing_key", ["version", "mode", "layers", "overall", "elapsed_ms"])
    def test_missing_top_key_fails(self, tmp_path, missing_key):
        doc = _sample_fast()
        del doc[missing_key]
        p = tmp_path / "bad.json"
        p.write_text(json.dumps(doc), encoding="utf-8")
        with pytest.raises(AssertionError, match=missing_key):
            assert_schema_v1(p)

    def test_deep_missing_layer_fails(self, tmp_path):
        doc = _sample_deep()
        del doc["layers"]["dispatch"]
        p = tmp_path / "bad.json"
        p.write_text(json.dumps(doc), encoding="utf-8")
        with pytest.raises(AssertionError, match="dispatch"):
            assert_schema_v1(p)

    def test_deep_missing_elapsed_ms_fails(self, tmp_path):
        """F-4a baseline 消费字段缺失必须显式 fail。"""
        doc = _sample_deep()
        del doc["layers"]["dispatch"]["data"]["elapsed_ms"]
        p = tmp_path / "bad.json"
        p.write_text(json.dumps(doc), encoding="utf-8")
        with pytest.raises(AssertionError, match="elapsed_ms"):
            assert_schema_v1(p)

    def test_fast_mode_allows_missing_dispatch_loadaddin(self, tmp_path):
        """fast 模式不应要求 deep-only 的两层。"""
        doc = _sample_fast()
        # fast 没有 dispatch / loadaddin 是合法的
        p = tmp_path / "fast.json"
        p.write_text(json.dumps(doc), encoding="utf-8")
        assert_schema_v1(p)  # 不抛
```

- [ ] **Step 2: 运行测试确认失败**

```bash
uv run pytest tests/test_assert_sw_inspect_schema.py -v
```

预期：`ModuleNotFoundError: No module named 'tools.assert_sw_inspect_schema'`

- [ ] **Step 3: 写最小实现让测试通过**

创建 `tools/assert_sw_inspect_schema.py`：

```python
"""断言 sw-inspect --json 输出符合 v1 schema（决策 #38）。

workflow / CI / 任何机读消费方统一调用此脚本而非自己写断言。
schema 升级到 v2 时只改本文件。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


REQUIRED_TOP_KEYS = ("version", "mode", "layers", "overall", "elapsed_ms")
REQUIRED_LAYERS_FAST = (
    "environment", "pywin32", "detect", "clsid",
    "toolbox_index", "materials", "warmup",
)
REQUIRED_LAYERS_DEEP = REQUIRED_LAYERS_FAST + ("dispatch", "loadaddin")
REQUIRED_LAYER_FIELDS = ("layer", "ok", "severity", "summary", "data")


def assert_schema_v1(path: Path) -> None:
    """对 path 指向的 sw-inspect JSON 做 v1 schema 断言。

    Raises:
        AssertionError: schema 不符合 v1 时，消息包含具体缺失字段名。
    """
    doc = json.loads(Path(path).read_text(encoding="utf-8"))

    for k in REQUIRED_TOP_KEYS:
        assert k in doc, f"缺顶层字段 {k!r}"

    mode = doc["mode"]
    layers = doc["layers"]
    required = REQUIRED_LAYERS_DEEP if mode == "deep" else REQUIRED_LAYERS_FAST
    for layer_name in required:
        assert layer_name in layers, f"mode={mode} 缺 layer {layer_name!r}"
        for field in REQUIRED_LAYER_FIELDS:
            assert field in layers[layer_name], (
                f"layer {layer_name} 缺字段 {field!r}"
            )

    # deep 模式：dispatch.data.elapsed_ms 是 F-4a baseline 消费字段，必须存在
    if mode == "deep":
        assert "elapsed_ms" in layers["dispatch"]["data"], (
            "deep 模式 dispatch.data 缺 elapsed_ms（F-4a baseline 消费字段）"
        )


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(f"usage: {argv[0]} <sw-inspect-json-path>", file=sys.stderr)
        return 64
    assert_schema_v1(Path(argv[1]))
    print(f"schema v1 OK: {argv[1]}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
```

- [ ] **Step 4: 再跑测试确认全部通过**

```bash
uv run pytest tests/test_assert_sw_inspect_schema.py -v
```

预期：9 个 test 全绿（2 valid + 5 parametrized missing top + 1 missing layer + 1 missing elapsed_ms）。

- [ ] **Step 5: 提交**

```bash
git add tools/assert_sw_inspect_schema.py tests/test_assert_sw_inspect_schema.py
git commit -m "feat(sw-self-hosted-runner): assert_sw_inspect_schema helper (T1)

D13：抽取 sw-inspect JSON v1 schema 断言到共享 helper，workflow /
CI / 任何机读消费方统一调用；schema 升级到 v2 时只改一处。

覆盖 5 个核心场景：合法 fast/deep、缺顶层 key、缺必需 layer、
deep 模式缺 dispatch.data.elapsed_ms（F-4a baseline 消费字段）。

spec: docs/superpowers/specs/2026-04-17-sw-self-hosted-runner-design.md §4.6
plan: docs/superpowers/plans/2026-04-17-sw-self-hosted-runner.md T1

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: `test_sw_inspect_real.py` 追加 Toolbox / materials 断言

**Files:**
- Modify: `tests/test_sw_inspect_real.py:34-47`（`test_deep_real_smoke`）

**背景**：当前 deep smoke 只断言 `dispatch.severity != fail` + `elapsed_ms < 30_000`，不验证 Toolbox 索引和材质层。追加两条覆盖 3D 设计师视角的回归保护（spec §4.8 / 3D-1）。字段名已核对 `adapters/solidworks/sw_probe.py`（`toolbox_index` layer 第 286 行返回 `by_standard` dict；`materials` layer 第 485 行返回 `sldmat_files` int）。

- [ ] **Step 1: 编辑现有测试方法，追加两条断言**

在 `tests/test_sw_inspect_real.py` 的 `test_deep_real_smoke` 末尾（现 line 46 `assert disp["data"]["elapsed_ms"] < 30_000` 之后）追加：

```python
        # F-1.3 §4.8：追加 Toolbox 索引层断言（3D-1 修正）
        tb = doc["layers"]["toolbox_index"]
        assert tb["data"]["by_standard"], (
            f"toolbox_index.by_standard 空，Toolbox 索引可能失效；data={tb['data']}"
        )

        # F-1.3 §4.8：追加 materials 层断言（3D-1 修正）
        mat = doc["layers"]["materials"]
        assert mat["data"]["sldmat_files"] > 0, (
            f"materials.sldmat_files = 0，SW 材质库可能失效；data={mat['data']}"
        )
```

- [ ] **Step 2: 本地验证（需开发者本机 Windows + SW 2024+）**

```bash
uv run pytest tests/test_sw_inspect_real.py::TestSwInspectRealSmoke::test_deep_real_smoke -v
```

预期：
- 在 Windows + SW 安装的开发机：PASS（两条新断言成立）
- 在 Linux / 无 SW 的机器：SKIPPED（`@requires_solidworks` 拦截），不算本 task 失败

**若 PASS 失败**：说明开发机 SW Toolbox 索引 or 材质库状态异常——这是真回归信号，应优先排查 SW 环境；非本 task bug。

- [ ] **Step 3: 提交**

```bash
git add tests/test_sw_inspect_real.py
git commit -m "test(sw-self-hosted-runner): deep smoke 追加 toolbox/materials 断言 (T2)

3D-1 修正：原 deep smoke 只验 dispatch severity + elapsed_ms，不覆盖
Toolbox / 材质层。追加两条断言保护 3D 设计师视角的回归（字段名已核对
adapters/solidworks/sw_probe.py 真实返回：toolbox_index.by_standard /
materials.sldmat_files）。

spec: docs/superpowers/specs/2026-04-17-sw-self-hosted-runner-design.md §4.8
plan: docs/superpowers/plans/2026-04-17-sw-self-hosted-runner.md T2

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: `setup-cad-env` composite action

**Files:**
- Create: `.github/actions/setup-cad-env/action.yml`

**背景**：sw-smoke 与未来 F-1.3b 等 workflow 共享"setup-python + pip install + dev_sync"三步前置，现在抽取避免技术债（D14 / spec §4.5）。sw-smoke 是首个消费者。

- [ ] **Step 1: 创建目录和 action.yml**

```bash
mkdir -p .github/actions/setup-cad-env
```

创建 `.github/actions/setup-cad-env/action.yml`：

```yaml
name: Setup CAD env
description: |
  sw-smoke / 未来 CAD-related CI 共享的前置：
  setup-python 3.12 + pip install 运行期依赖 + dev_sync.py 同步 data/ mirrors。

  消费者：sw-smoke（首个）；F-1.3b 扩展时复用；未来 tests.yml 迁移（F-1.3g）。

runs:
  using: composite
  steps:
    - uses: actions/setup-python@v6
      with:
        python-version: "3.12"

    - name: Install runtime deps
      shell: bash
      run: |
        python -m pip install --upgrade pip
        # 对齐 tests.yml 的 unpinned 约定（spec §8 已知债务）；
        # 不走 `pip install -e .` 规避 hatch_build.py custom hook 副作用（spec §4.1 / D12）
        pip install pywin32 pytest pytest-timeout Jinja2 psutil PyYAML

    - name: Sync data/ mirrors
      # 与 tests.yml 一致：dev_sync.py exit 0 无变更 / 1 有同步（非错误）/ >1 真错误
      shell: bash
      run: |
        rc=0
        python scripts/dev_sync.py || rc=$?
        if [ "$rc" -gt 1 ]; then exit "$rc"; fi
```

- [ ] **Step 2: YAML 语法本地验证**

```bash
python -c "import yaml; yaml.safe_load(open('.github/actions/setup-cad-env/action.yml'))"
```

预期：无输出（语法通过）。

**可选**：若本机装了 actionlint，可跑：

```bash
actionlint -config-file /dev/null
```

但 actionlint 不覆盖 composite action 的完整语义；CI 首跑才是终极验证。

- [ ] **Step 3: 提交**

```bash
git add .github/actions/setup-cad-env/action.yml
git commit -m "ci(sw-self-hosted-runner): setup-cad-env composite action (T3)

D14：抽取 setup-python + pip install + dev_sync 三步共享前置，
sw-smoke 首个消费者；F-1.3b 等未来 CAD-related workflow 复用。

避免第二个 workflow 到来时复制粘贴 → 第三个 workflow 重构的技术债。
不动 tests.yml（F-1.3g 独立重构）。

spec: docs/superpowers/specs/2026-04-17-sw-self-hosted-runner-design.md §4.5
plan: docs/superpowers/plans/2026-04-17-sw-self-hosted-runner.md T3

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: `sw-smoke.yml` workflow（依赖 T1 + T3）

**Files:**
- Create: `.github/workflows/sw-smoke.yml`

**依赖**：T1（`tools/assert_sw_inspect_schema.py` 已存在）、T3（`.github/actions/setup-cad-env/action.yml` 已存在）。若 T1/T3 未合入，本 workflow 的 `uses: ./.github/actions/setup-cad-env` 和 `python tools/assert_sw_inspect_schema.py` 会在首跑时 fail。

- [ ] **Step 1: 创建 workflow 文件**

创建 `.github/workflows/sw-smoke.yml`（完整内容见 spec §4.1，一字不改）：

```yaml
name: sw-smoke

on:
  push:
    branches: [main]
  workflow_dispatch:

concurrency:
  group: sw-smoke
  cancel-in-progress: false  # D7：保留队首，避免 cancel 吃 artifact

jobs:
  sw-smoke:
    # D15：commit message 含 [skip smoke] 或 [skip sw-smoke] 时跳过（避让开发者当前在用 SW）
    if: >-
      !contains(github.event.head_commit.message, '[skip smoke]') &&
      !contains(github.event.head_commit.message, '[skip sw-smoke]')
    runs-on: [self-hosted, windows, solidworks]
    timeout-minutes: 15
    steps:
      - uses: actions/checkout@v6
        with:
          clean: true  # 显式（D4 long-lived runner 的清场保证）

      - name: Setup CAD env (composite)
        uses: ./.github/actions/setup-cad-env

      - name: Run SW real smoke (pytest 回归)
        shell: bash
        env:
          PYTHONUTF8: "1"
        run: |
          pytest tests/test_sw_inspect_real.py -v --tb=short \
                 -m requires_solidworks \
                 --junitxml=sw-smoke-junit.xml

      - name: Skip-guard (ET-based, D10)
        shell: bash
        run: |
          python -c "
          from xml.etree import ElementTree as ET
          root = ET.parse('sw-smoke-junit.xml').getroot()
          all_tcs = list(root.iter('testcase'))
          skipped = [tc for tc in all_tcs if tc.find('skipped') is not None]
          real = len(all_tcs) - len(skipped)
          print(f'skip-guard: total={len(all_tcs)} skipped={len(skipped)} real={real}')
          assert real >= 1, 'expected >= 1 real testcase, got 0 — @requires_solidworks 可能被全量 skip'
          "

      - name: Emit sw-inspect JSON artifact (独立 CLI run, D11)
        shell: bash
        env:
          PYTHONUTF8: "1"
        run: |
          python cad_pipeline.py sw-inspect --deep --json > sw-inspect-deep.json || true
          python tools/assert_sw_inspect_schema.py sw-inspect-deep.json

      - name: Write human-readable step summary (D16)
        if: always()
        shell: bash
        env:
          PYTHONUTF8: "1"
        run: |
          echo '## sw-inspect (deep) 输出' >> "$GITHUB_STEP_SUMMARY"
          echo '```' >> "$GITHUB_STEP_SUMMARY"
          python cad_pipeline.py sw-inspect --deep >> "$GITHUB_STEP_SUMMARY" 2>&1 || true
          echo '```' >> "$GITHUB_STEP_SUMMARY"

      - if: always()
        uses: actions/upload-artifact@v4
        with:
          name: sw-smoke-artifacts
          path: |
            sw-smoke-junit.xml
            sw-inspect-deep.json
          if-no-files-found: error
```

- [ ] **Step 2: YAML 语法本地验证**

```bash
python -c "import yaml; yaml.safe_load(open('.github/workflows/sw-smoke.yml'))"
```

预期：无输出。

**可选 actionlint**（若本机装了）：

```bash
actionlint .github/workflows/sw-smoke.yml
```

预期：无输出或仅 shellcheck 警告（非阻断）。如遇 "action does not exist" 类错，说明 `./.github/actions/setup-cad-env` 路径拼错——检查 T3 是否已 commit。

- [ ] **Step 3: 提交**

```bash
git add .github/workflows/sw-smoke.yml
git commit -m "ci(sw-self-hosted-runner): sw-smoke.yml workflow (T4)

F-1.3 核心 workflow。push: main + workflow_dispatch 触发，不监听 PR
（public repo 攻击面归零）。runs-on [self-hosted, windows, solidworks]。
timeout 15min，concurrency 排队（cancel-in-progress: false 保 artifact）。

步骤：checkout → setup-cad-env composite → pytest 真跑 → ET-based
skip-guard → 独立 CLI emit JSON + schema 断言 → step summary → upload。
commit 含 [skip smoke] 时自动跳过（D15，给设计师避让通道）。

依赖已就绪：T1 tools/assert_sw_inspect_schema.py / T3 composite action。
首次真跑验证留到 runner 注册后的 [人工阶段]。

spec: docs/superpowers/specs/2026-04-17-sw-self-hosted-runner-design.md §4.1
plan: docs/superpowers/plans/2026-04-17-sw-self-hosted-runner.md T4

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: runbook

**Files:**
- Create: `docs/superpowers/runbooks/sw-self-hosted-runner-setup.md`

**背景**：runner 物理注册 / Autologon / Task Scheduler / 90 天轮换 / 故障排查 SOP（spec §5.1）。此文档**不**含代码，是开发者按章节照做的运维手册。

- [ ] **Step 1: 创建目录和文件**

```bash
mkdir -p docs/superpowers/runbooks
```

创建 `docs/superpowers/runbooks/sw-self-hosted-runner-setup.md`，10 章节内容（参考 spec §5.1）：

````markdown
# SW self-hosted runner setup runbook

承接决策 #39 / F-1.3 实施。本文档是**开发者物理配置 runner 的 SOP**，
与 workflow YAML 等代码改动分离。

---

## 1. 前置要求

- Windows 11（21H2+）
- SolidWorks 2024+ 持久授权（非网络浮动；若是浮动许可，见第 8 节）
- 机器可联网（runner 需与 github.com 保持 TLS 连通）
- Python 3.12 预装（或允许 workflow 里 `actions/setup-python@v6` 在线下载）

## 2. 创建 `ghrunner` 账户

以管理员身份启动 PowerShell：

```powershell
net user ghrunner "<强密码>" /add
net localgroup Users ghrunner /add
# 确认 ghrunner 不在 Administrators 组：
net localgroup Administrators
```

收敛权限：
- 禁用 RDP 对 ghrunner 的访问（gpedit / 组策略 `Deny log on through Remote Desktop Services`）
- 文件系统：开发者个人文件夹（如 `C:\Users\proecheng`）对 `ghrunner` 拒绝读写（右键属性 → 安全 → 编辑）

## 3. 开机自动登录配置

**不**用注册表明文 `DefaultPassword`（物理接触者可直接读）。用 Sysinternals **Autologon** 工具（LSA-encrypted 存储）：

1. 下载 https://learn.microsoft.com/en-us/sysinternals/downloads/autologon
2. 以管理员身份运行 `Autologon.exe`
3. Username = `ghrunner`、Domain = `.`、Password = 第 2 节设置的密码
4. Enable

验证：重启机器，应自动登录到 ghrunner 桌面。

## 4. 下载并安装 GitHub Actions Runner

1. GitHub → repo Settings → Actions → Runners → New self-hosted runner → Windows x64
2. 按页面给出的 PowerShell 命令下载 + 解压到 `D:\actions-runner`（独立盘，隔离日常 dev 盘）
3. 校验 SHA256（页面同时给出）

## 5. 注册 runner（long-lived，D4）

以 `ghrunner` 账户登录，在 `D:\actions-runner` 跑：

```powershell
cd D:\actions-runner
.\config.cmd --url https://github.com/proecheng/cad-spec-gen `
             --token <one-time-registration-token> `
             --labels solidworks `
             --replace
```

注意：
- **不**加 `--ephemeral`（D4：ephemeral 需要长期 PAT 自动重注册，破坏账户隔离）
- token 从"New self-hosted runner"页面复制，1 小时有效
- `--labels solidworks` 必填；另两个 label `self-hosted` / `Windows` GitHub 自动附加

### SW 用户数据隔离

首次在 ghrunner session 启动 SolidWorks：
- `File → Options → Reset All` 清掉可能从 proecheng 继承的默认设置
- 或手动删除 `C:\Users\ghrunner\AppData\Roaming\SolidWorks\`（首启会重建）

## 6. Task Scheduler 自动启动

`Task Scheduler → Create Task`（不是 Create Basic Task）：

- General
  - Name: `GitHub Actions Runner (sw-smoke)`
  - Run only when user is logged on（**不**勾 Run whether user is logged on or not，这等价于 Service 模式）
  - Configure for: Windows 11
- Triggers
  - New → Begin the task: `At log on` → Specific user: `ghrunner`
- Actions
  - New → Program: `D:\actions-runner\run.cmd`
  - Start in: `D:\actions-runner`
- Conditions
  - 取消勾选 "Start the task only if the computer is on AC power"
- Settings
  - If the task fails, restart every: `1 minute`, up to `3` times

保存，提示输入 ghrunner 密码。

## 7. 首次跑 sw-smoke 验证

1. GitHub repo → Actions → sw-smoke → Run workflow（workflow_dispatch）
2. 观察 Actions 页：runner 应 pickup job 并跑完
3. 下载 `sw-smoke-artifacts`：
   - `sw-smoke-junit.xml`：ET 解析应得 `total >= 2, skipped == 0, real >= 2`（首跑 baseline）
   - `sw-inspect-deep.json`：记录 `layers.dispatch.data.elapsed_ms` 作为 K1 第一个数据点
4. CI 页 Job Summary 区块应直接显示 sw-inspect text 输出（D16 / §4.7）

**baseline 记录**（填入本 runbook 本节）：

- 首跑日期：`____`
- `skip-guard: total=X skipped=Y real=Z`：`____`
- `sw-inspect-deep.json.layers.dispatch.data.elapsed_ms`：`____` ms

## 8. 故障排查

### 8.1 Runner offline

- Actions → Runners 页显示红点 → ghrunner session 未登录或 `run.cmd` 崩溃
- 以 ghrunner 登录，检查 `D:\actions-runner\_diag\` 最新日志

### 8.2 SW Dispatch 失败

- 确认 runner **不**以 Service 身份跑（见第 6 节 "Run only when user is logged on"）
- 确认 ghrunner session 是交互式 GUI 会话（能手动启动 SolidWorks）

### 8.3 License 冲突（"SolidWorks is being used by..."）

如果 license 是 per-user：
- 合并前关闭你的 SW 实例，或 commit message 加 `[skip smoke]` / `[skip sw-smoke]`（D15）
- 持续冲突可在 Actions → sw-smoke → Disable workflow 临时关闭

### 8.4 积压 queued job 清理

```bash
gh run list --workflow=sw-smoke --status=queued
gh run cancel --all  # 或逐个 cancel
```

### 8.5 Network license / 浮动许可首次 smoke license swap

若 SW 是网络浮动许可，ghrunner 首次启动 SW 会与你的 session 争 license。
**本 F-1.3 不覆盖此场景**；若需支持，参考 SolidWorks Admin Portal 的 multi-seat
配置；或按 §8 F-1.3e 降级为本地跑路径。

## 9. 90 天 token 轮换 SOP

目的：控制 runner credential 泄漏窗口（虽 GitHub 无强制过期，手动轮换是最佳实践）。

1. Settings → Actions → Runners → 找到本 runner → Remove
2. 以 ghrunner 登录，`D:\actions-runner` 跑 `.\config.cmd remove`
3. 按第 5 节重新注册（获取新 registration token）

日历提醒：每 90 天跑一次。

## 10. 卸载

```powershell
cd D:\actions-runner
.\config.cmd remove --token <one-time-removal-token>
```

之后：
- Task Scheduler 删除"GitHub Actions Runner (sw-smoke)"
- 如不再需要 ghrunner 账户：`net user ghrunner /delete`
- Autologon 工具 → Disable
````

- [ ] **Step 2: 提交**

```bash
git add docs/superpowers/runbooks/sw-self-hosted-runner-setup.md
git commit -m "docs(sw-self-hosted-runner): runner setup runbook (T5)

spec §5.1 落地：10 章节 SOP 覆盖前置要求 / ghrunner 账户 / Autologon /
runner long-lived 注册（D4）/ Task Scheduler at-logon / 首跑 baseline
记录 / 故障排查 / 90 天轮换 / 卸载。

关键取舍：
- Sysinternals Autologon（LSA-encrypted）替代注册表明文
- 'Run only when user is logged on'（避免 Service 模式触发 SW Dispatch 静默挂起）
- runner --labels solidworks 必填，三 label 组合锁定机器（D3）

spec: docs/superpowers/specs/2026-04-17-sw-self-hosted-runner-design.md §5.1
plan: docs/superpowers/plans/2026-04-17-sw-self-hosted-runner.md T5

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: 决策 #39

**Files:**
- Modify: `docs/superpowers/decisions.md`（末尾追加一节）

- [ ] **Step 1: 追加决策条目**

在 `docs/superpowers/decisions.md` 末尾追加：

```markdown

---

## #39 sw-smoke workflow：long-lived self-hosted runner + 不在 PR 跑（2026-04-17）

**决策：** F-1.3 实现 `sw-smoke` workflow 运行在 self-hosted Windows runner
（labels: `self-hosted, windows, solidworks`），触发条件为 `push: main` +
`workflow_dispatch`，**不**监听 `pull_request`。

**关键取舍：**
- **C1 路径 vs 全量 PR 触发**：public repo 下 fork PR 会在 runner 机器上
  执行任意代码（GitHub 官方警告），不值得承担风险；main 合并 + 手动触发
  覆盖 F-1.3 目标
- **Long-lived runner vs ephemeral**（D4，v3 审查修正）：ephemeral 自动
  重注册需要持续有效的 PAT，PAT 存在受限 `ghrunner` 账户即等于给它日常
  GitHub 操作权，抵消了 ephemeral 的安全收益。改 long-lived + `git clean`
  + 90 天手动轮换 credential
- **非 Service 模式**：SW COM 需要交互式 GUI 会话；runner 装成 Service
  会触发 SW Dispatch 静默挂起。用 Task Scheduler `at-logon` + Autologon
  代替（见 runbook）
- **`cancel-in-progress: false`**（D7，v3 审查修正）：true 会在新 push 到
  来时硬杀正跑 job 吃掉 artifact；false 下离线积压靠 `gh run cancel --all`
  清理

**决策生效前提：**
- 开发者拥有一台常可开机的 Windows + SolidWorks 2024+ 机器
- 在 12 个月内至少捕获 1 次真 SW 回归（K2）；若 K2 = 0 则评估降级到
  F-1.3e（本地跑 + runbook）

**Follow-up：**
- F-1.3a：artifact → dashboard（K1 达成时）
- F-1.3b：full=true input 追加 sw-warmup / Stage C
- F-1.3c：第二台 SW 机器 runner-group 负载均衡（license/可用性连续 14 天冲突时）
- F-1.3d：actionlint 加 pre-commit
- F-1.3e：runner 低在线率降级路径（K2 = 0 或月在线率 < 30%）
- F-1.3f：elapsed_ms 门槛调整（K3 flaky > 5%）
- F-1.3g：tests.yml 迁移到 setup-cad-env composite action

**Spec**：`docs/superpowers/specs/2026-04-17-sw-self-hosted-runner-design.md` (v3)
**Plan**：`docs/superpowers/plans/2026-04-17-sw-self-hosted-runner.md`

**修订历史：**
- v1 初稿（ephemeral + cancel-in-progress: true）
- v2 二审（artifact 数据流 + 依赖安装）
- v3 多角色审查（D4 → long-lived / D7 → cancel-in-progress: false；
  + D13/D14/D15/D16 新决策）

```

- [ ] **Step 2: 提交**

```bash
git add docs/superpowers/decisions.md
git commit -m "docs(sw-self-hosted-runner): 决策 #39 登记 (T6)

F-1.3 核心决策入库：C1 路径（不在 PR 跑）/ long-lived runner（D4 替代
ephemeral）/ 非 Service 模式 / cancel-in-progress: false（D7 修正）/
K1-K3 成功度量。

Follow-up 清单 F-1.3a~g 登记。spec v3 修订历史同步。

spec: docs/superpowers/specs/2026-04-17-sw-self-hosted-runner-design.md §5.2
plan: docs/superpowers/plans/2026-04-17-sw-self-hosted-runner.md T6

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 7: README 一行

**Files:**
- Modify: `README.md`（CI 相关段落追加一行；若无 CI 段则追加在项目介绍后）

- [ ] **Step 1: 定位 README 的 CI 段落或合适插入点**

```bash
grep -n -i "ci\|github actions\|workflow\|tests.yml" README.md | head -10
```

- [ ] **Step 2: 在 CI 段落追加一行**

形如：

```markdown
- `sw-smoke`：真 SolidWorks 环境回归（self-hosted runner，仅 `main` push + 手动触发；commit 含 `[skip smoke]` 跳过）
```

若 README 无明显 CI 段，创建 `## CI` 二级标题，包含 `tests.yml` + `sw-smoke.yml` 两项（但**不**重写 tests.yml 的原有描述）。

- [ ] **Step 3: 提交**

```bash
git add README.md
git commit -m "docs(sw-self-hosted-runner): README CI 段追加 sw-smoke 说明 (T7)

告知用户 sw-smoke workflow 的触发条件和 [skip smoke] 避让机制。

spec: docs/superpowers/specs/2026-04-17-sw-self-hosted-runner-design.md §5.3
plan: docs/superpowers/plans/2026-04-17-sw-self-hosted-runner.md T7

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 8: 开发者本机 pre-flight 验收

**Files:** 无代码改动，纯验证步骤。

**目的**：在 runner 物理注册之前，把所有能离线验证的组件一次性确认——
避免首次 CI 跑时才发现 schema helper 报错或 pytest 依赖缺失。

- [ ] **Step 1: Python deps 可装性验证**

以干净 venv 模拟 composite action 的 install 步骤：

```bash
# 新建临时 venv（不污染主环境）
python -m venv /tmp/preflight-sw-smoke
source /tmp/preflight-sw-smoke/bin/activate  # Linux/macOS
# 或 /tmp/preflight-sw-smoke/Scripts/activate  # Windows

pip install --upgrade pip
pip install pywin32 pytest pytest-timeout Jinja2 psutil PyYAML
# Linux/macOS 上 pywin32 会 skip；Windows 会真装——两者都不应 error exit
echo "exit code: $?"
deactivate
```

预期：`exit code: 0`。如有 pywin32 错（macOS 上也可能装上报错），记到 §8 已知债务跟进。

- [ ] **Step 2: schema helper 手工跑**

```bash
# 生成一个当前真 CLI 的 JSON（非 SW 环境会 fail/warn 但仍产 JSON）
python cad_pipeline.py sw-inspect --json > /tmp/swi-fast.json
python tools/assert_sw_inspect_schema.py /tmp/swi-fast.json
```

预期：`schema v1 OK: /tmp/swi-fast.json`。

若 fast 模式 JSON 不符合 schema（例如 7 层 required 里有缺失），说明
sw-inspect 本体与 schema 常量不一致——这时要**先修 schema 常量**
（以真实输出为准，因为 schema 是"契约"），再更新 spec §4.6。

- [ ] **Step 3: actionlint（可选）**

若本机有 actionlint：

```bash
actionlint .github/workflows/sw-smoke.yml .github/actions/setup-cad-env/action.yml
```

预期：无阻断性错误。shellcheck 风格警告可接受。

- [ ] **Step 4: pytest 本机跑 real smoke（仅 Windows+SW 开发者）**

```bash
uv run pytest tests/test_sw_inspect_real.py -v -m requires_solidworks
```

预期：
- Windows+SW 开发机：2 tests PASS
- Linux 或无 SW 机器：2 tests SKIPPED（不算本 task 失败）

- [ ] **Step 5: 记录 pre-flight 结果**

在 runbook §7 的 "baseline 记录" 段先填入空白占位；首次 CI 跑后再回填真实数值。

**不提交**（本 task 无代码改动，只产出日志到对话中供 reviewer 追溯）。

---

## Task 9: 人工阶段（runner 注册 + 首跑验证）

**此任务无代码改动，不产生提交**。

- [ ] **Step 1: 按 runbook 第 2–6 节操作**

在开发者本机依次：
- 创建 `ghrunner` 账户（runbook §2）
- Sysinternals Autologon 配置（§3）
- 下载 GitHub Actions Runner + 注册（§4–5）
- Task Scheduler 条目（§6）
- 重启机器验证 ghrunner 自动登录 + runner 自启

- [ ] **Step 2: 首次 workflow_dispatch 触发**

GitHub repo → Actions → sw-smoke → Run workflow（main 分支）。

- [ ] **Step 3: 验收 §6 清单**

按 spec §6 逐条打勾：
- workflow 合入 + 语法通过（T4 完成）
- composite action 合入（T3 完成）
- schema helper + 单测合入（T1 完成）
- real smoke 新断言合入（T2 完成）
- runner 在 Settings → Runners 页可见，labels 正确
- 首次 push/dispatch 成功 run，artifact 下载成功
- junit.xml ET 解析 `real >= 1`
- sw-inspect-deep.json 经 assert_schema_v1 通过
- Job Summary 展示 sw-inspect 文本输出
- `[skip smoke]` 能跳过（空 commit 验证）
- runbook + 决策 #39 + README 一行合入

- [ ] **Step 4: baseline 回填到 runbook §7**

首次成功 run 的 `skip-guard` + `elapsed_ms` 数值填入 runbook 占位。

- [ ] **Step 5: 生成 PR 描述或 project log 记录**

总结 F-1.3 完成状态到 project log，K1/K2/K3 计数器初始化（各 0）。

---

## 完成定义

spec §6 全部验收条目打勾 + Task 8 pre-flight 全绿 + Task 9 Step 3 清单全绿。

若 Task 9 Step 3 某项 fail：
- schema/assertion 类失败 → 回到 T1/T2，修后重 push → runner 重跑
- workflow YAML 失败 → 回到 T3/T4，修后重 push
- runner 物理问题 → 参考 runbook §8 故障排查

---

## Follow-up（不在本 plan 范围，已登记 §9）

F-1.3a（dashboard）/ F-1.3b（full=true 追加 sw-warmup/Stage C）/ F-1.3c（多机）/ F-1.3d（actionlint 入 pre-commit）/ F-1.3e（低在线率降级）/ F-1.3f（elapsed_ms flaky 门槛）/ F-1.3g（tests.yml 迁移到 composite action）。

