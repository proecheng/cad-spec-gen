# SW self-hosted runner smoke CI — 设计文档

- **日期**：2026-04-17
- **作者**：proecheng（Claude Code 协作）
- **状态**：design（待实施，第 3 版 — 多角色审查后修正）
- **归属 phase**：sw-inspect Follow-up F-1.3
- **前置决策**：#37（solidworks optional extra）/ #38（sw-inspect 作为正式诊断入口）
- **实施计划**（待生成）：`docs/superpowers/plans/2026-04-17-sw-self-hosted-runner.md`

---

## 1. 背景与动机

### 1.1 现状

决策 #38 落地 `cad_pipeline.py sw-inspect` 后，深度 smoke 测试 `tests/test_sw_inspect_real.py::TestSwInspectRealSmoke` 用 `@pytest.mark.requires_solidworks` 标记——`tests/conftest.py` 的 `pytest_collection_modifyitems` 钩子在非 Windows / 无 pywin32 / 无 SolidWorks 安装的环境全量 skip。

当前 CI 矩阵 `.github/workflows/tests.yml`：

| job | runner | Python | 真 SW 可达 |
|---|---|---|---|
| `test` | `ubuntu-latest` × `windows-latest` × 3.10/3.11/3.12 | 均 GitHub-hosted | ❌（windows-latest 无 SW 安装）|
| `regression` | `ubuntu-latest` | 3.12 | ❌ |

结果：**真 SW 的 deep smoke 只在开发者本机跑**。合并到 main 的代码若破坏 Dispatch / LoadAddIn / 材质扫描 / Toolbox 索引，CI 看不见，要靠开发者下次本机跑才发现。

### 1.2 目标与 KPI

让决策 #38 的 deep smoke 在 CI 有**可追溯**的真 SW 证据：每次 push to main（以及手动触发）自动跑 `test_sw_inspect_real.py` 在真 SolidWorks 环境中，产物 JSON 上传为 artifact 供 F-4a baseline 与未来 dashboard 消费。

**可量化 KPI**（本 F-1.3 成功的客观标准）：
- **K1**：上线后 6 个月内，`sw-inspect-deep.json.layers.dispatch.data.elapsed_ms` 至少有 **10 次** 独立 main-push 记录（供 F-4a 做 baseline）
- **K2**：上线后 12 个月内，**至少 1 次** 真 SW 回归被 sw-smoke 捕获（回归指在开发者本机未发现但被 CI 抓出）。**若 12 个月 K2 = 0，评估是否降级为 F-1.3e**（本地跑 + runbook）
- **K3**：CI 假阳率（flaky fail）< 5%——超过则按 §9 F-1.3f 处理

### 1.3 非目标

- **不**在 pull_request 上跑（public repo 安全前提，见 §3）
- **不**做 Python 版本矩阵（fast/deep smoke 对 3.10 vs 3.12 不敏感，YAGNI）
- **不**覆盖 Stage C / sw-warmup 端到端（属 F-4a baseline 范围）
- **不**做 runner 多机冗余 / 容器化（单机足够；SW 本身 license-per-machine）
- **不**改动既有 `tests.yml` / `regression` job（隔离原则，新增独立 workflow；composite action 抽取见 §4.5）
- **不**覆盖 `env-check` 其它 6 条 pipeline（Blender / Gemini / fal / ComfyUI / engineering / Toolbox 路由）；env-check 仍靠开发者本机或 tests.yml

---

## 2. 决策总览

| # | 决策 | 来源章节 |
|---|---|---|
| D1 | 新建独立 workflow `.github/workflows/sw-smoke.yml`，不改 `tests.yml` | §4.1 |
| D2 | 路径 C1：`push: main` + `workflow_dispatch`，**不**监听 `pull_request` | §3.1 |
| D3 | runner label 组合：`[self-hosted, windows, solidworks]` 三 label 联合定位 | §4.2 |
| **D4（重写）** | **Long-lived runner**（非 ephemeral）+ 每 job 开始 `git clean -fdx` + 运行目录隔离。放弃 ephemeral 是因其自动重注册需要持续有效的 registration token（1h 有效期），而存放长期 PAT 又破坏"专用受限账户"的安全假设 | §3.3 |
| D5 | runner **不**装为 Windows Service；用 Task Scheduler at-logon 启动（SW 需交互式 GUI 会话）| §3.3 |
| D6 | 专用受限 Windows 账户（例 `ghrunner`），无 Administrators、无 RDP、无个人文件访问 | §3.2 |
| **D7（修正）** | `concurrency: { group: sw-smoke, cancel-in-progress: false }`——排队时保留队首、新来的排后面；避免 `cancel-in-progress: true` 在 cancel 时硬杀正跑 job 吃掉 artifact | §4.3 |
| D8 | `timeout-minutes: 15`，防 Dispatch 悬挂锁死 runner | §4.3 |
| D9 | 新增 runbook `docs/superpowers/runbooks/sw-self-hosted-runner-setup.md`，登记决策 #39 | §5 |
| D10 | Skip-guard：用 `xml.etree.ElementTree` 解析 junit.xml 区分 skipped vs real executed，`real < 1` 显式 fail | §4.4 |
| D11 | 数据流双轨：pytest 负责回归断言（失败即炸），独立 CLI step `python cad_pipeline.py sw-inspect --deep --json > sw-inspect-deep.json` 负责数据产出；理由：`run_sw_inspect` 只 `print` 到 stdout 不落盘（`tools/sw_inspect.py:184`）| §4.1 |
| D12 | 依赖安装不用 `pip install -e .`：对齐 `tests.yml` 风格直接列依赖 `pywin32 pytest pytest-timeout Jinja2 psutil PyYAML`，规避 `hatch_build.py` custom hook 副作用 | §4.1 |
| **D13（新）** | JSON schema 断言抽到共享 helper `tools/assert_sw_inspect_schema.py`，workflow 调 `python tools/assert_sw_inspect_schema.py sw-inspect-deep.json`。schema 升级时只改一处 | §4.6 |
| **D14（新）** | 依赖安装 + `dev_sync.py` + `setup-python` 三步抽成 composite action `.github/actions/setup-cad-env/action.yml`，sw-smoke 首个消费者；为未来 F-1.3b 等扩展做好复用准备 | §4.5 |
| **D15（新）** | commit message 含 `[skip smoke]` 或 `[skip sw-smoke]` 时跳过本 workflow，给机械设计师 / 3D 设计师"我正在 SW 建模，先不要抢 license"的主动避让通道 | §4.1 / §7 |
| **D16（新）** | workflow 末尾把 text 模式 `sw-inspect --deep` 输出追加到 `$GITHUB_STEP_SUMMARY`，失败时 Actions 页直接展示彩色人类可读摘要 | §4.7 |

---

## 3. 安全模型

### 3.1 为什么 public repo + self-hosted = 高风险默认态

GitHub 官方[明确警告](https://docs.github.com/en/actions/hosting-your-own-runners/managing-self-hosted-runners/about-self-hosted-runners#self-hosted-runner-security)：**不要给 public repo 配 self-hosted runner 默认接收 PR**。原因：任何人 fork 仓库后发 PR，workflow 会在你的机器上执行其 PR 分支的代码——等价于给所有互联网用户你机器的代码执行权。

缓解：**不在 `pull_request` 事件上触发 sw-smoke**。触发器只接 `push: branches: [main]`（合并后）和 `workflow_dispatch`（显式手动）。两者都要求代码已通过 main 的保护（或手动启动者是 repo collaborator），因此攻击面归零。

### 3.2 Runner 账户隔离

| 项 | 配置 | 理由 |
|---|---|---|
| 账户 | `ghrunner`（新建本地标准用户）| 不共享开发者日常账户的个人文件 / keychain / SSH key |
| 组 | Users（非 Administrators）| 阻断 job 内提权 |
| RDP | 禁用 | 不给远端登录面 |
| 登录方式 | 仅 console 登录（Task Scheduler at-logon）| 不开放 SMB / WinRM |
| runner 工作目录 | `D:\actions-runner`（独立盘根外）| 隔离日常 dev 盘 |
| token 存储 | runner 自身 `.runner` / `.credentials` 文件，不进 git | GitHub 默认行为，确认不误传 |
| SW 用户数据 | `C:\Users\ghrunner\AppData\...` 与开发者 `proecheng` session 的 SW profile 物理隔离 | 避免 runner 污染开发者日常设置；runbook §5 列清空 SOP |

### 3.3 Long-lived runner + 每 job 清场（D4 重写）

前一版选 `--ephemeral` 是因为"job 间无状态泄漏"，但 ephemeral 要求每次重新注册，而**自动重注册需长期 PAT**。PAT 存在受限账户里相当于给了日常账户级别的 GitHub 操作权，这破坏了 §3.2 的隔离假设——ephemeral 的安全收益被 PAT 存储抵消。

**改用 long-lived runner**：
- `config.cmd --url ... --token <one-time-registration-token> --labels solidworks --replace` 注册一次，runner 持久驻留
- Task Scheduler at-logon 启动 `run.cmd`，崩溃重启但**不**重新注册
- 每 job 开始加 step `git clean -fdx && git reset --hard HEAD`（checkout@v6 的 `clean: true` 默认能覆盖但显式更稳）
- runner 工作目录 `_work/_temp` 可能跨 job 共享 pip cache 等——接受此泄漏窗口，因已限定在 `ghrunner` 账户本地，且 push-to-main 才触发（已通过 main 的保护流程）

**为何不装 Service**：SolidWorks COM 需要交互式用户会话（Windows session 0 隔离问题），runner 以 Service 身份跑会导致 SW Dispatch 失败或静默挂起。改用 `ghrunner` 账户开机自动登录 + Task Scheduler at-logon 启动 `run.cmd`。副作用：机器重启后必须有人确认 `ghrunner` 的自动登录成功（Sysinternals Autologon 工具，LSA-encrypted 存密码）。

### 3.4 Token 轮换

GitHub self-hosted runner registration token 有效期约 1 小时，用于 initial 注册；runner 本身使用长期 credential（存在 `.credentials` 里）。长期 credential 没有 GitHub 侧强制过期，但**runbook 要求 90 天手动轮换**（Settings → Actions → Runners 删除 runner → 重新 `config.cmd` 注册），以控制凭据泄漏窗口。

---

## 4. 组件设计

### 4.1 workflow 文件：`.github/workflows/sw-smoke.yml`

**依赖安装策略**：对齐 `tests.yml` 既有风格——**直接列依赖**，不走 `pip install -e .`。理由：`pyproject.toml` 配了 `tool.hatch.build.targets.wheel.hooks.custom` = `hatch_build.py`，`-e` 会触发 custom hook 同步 `src/cad_spec_gen/data/`，在 CI 上引入不必要的副作用与失败面。sw-inspect 链路导入 `adapters.solidworks.sw_probe`（项目根）+ `tools.sw_inspect`（项目根），pytest 默认把 rootdir 加到 sys.path，无需 `-e` 即可 import。

**数据流双轨**：pytest 只负责**回归断言**（失败即炸）；真 SW JSON 数据靠**独立 CLI 步骤**产出（stdout 重定向到文件），供 F-4a baseline / 未来 dashboard 消费。`tools/sw_inspect.py:run_sw_inspect` 在 `--json` 模式下仅 `print(json.dumps(...))` 到 stdout，不落盘，这也是此处必须独立跑的原因。

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
        # 内部做：setup-python@v6 3.12 + pip install 依赖 + dev_sync.py
        # 详见 §4.5

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
          # xml.etree 解析 junit.xml 区分 real vs skipped；硬 grep 的 magic number 问题消除
          python -c "
          from xml.etree import ElementTree as ET
          root = ET.parse('sw-smoke-junit.xml').getroot()
          all_tcs = list(root.iter('testcase'))
          skipped = [tc for tc in all_tcs if tc.find('skipped') is not None]
          real = len(all_tcs) - len(skipped)
          print(f'skip-guard: total={len(all_tcs)} skipped={len(skipped)} real={real}')
          assert real >= 1, 'expected ≥ 1 real testcase, got 0 — @requires_solidworks 可能被全量 skip'
          "

      - name: Emit sw-inspect JSON artifact (独立 CLI run, D11)
        # run_sw_inspect 只 print 到 stdout（tools/sw_inspect.py:184），重定向到文件。
        # 即便 exit code 非 0（warn/fail），仍要保留 JSON 供诊断消费，故 || true。
        shell: bash
        env:
          PYTHONUTF8: "1"
        run: |
          python cad_pipeline.py sw-inspect --deep --json > sw-inspect-deep.json || true
          # D13：schema 断言抽到共享 helper
          python tools/assert_sw_inspect_schema.py sw-inspect-deep.json

      - name: Write human-readable step summary (D16)
        if: always()
        shell: bash
        env:
          PYTHONUTF8: "1"
        run: |
          # text 模式 sw-inspect 追加到 $GITHUB_STEP_SUMMARY，CI 页直接展示
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

### 4.2 runner 标签

三 label 组合 `[self-hosted, windows, solidworks]`：
- `self-hosted`：GitHub 自动保留 label
- `windows`：GitHub 自动保留 label（基于 OS 检测）
- `solidworks`：自定义 label，注册时 `--labels solidworks` 显式加上

为何用三 label：`self-hosted` + `windows` 可能匹配到未来其他用途的 Windows self-hosted runner（如 GPU 测试），`solidworks` label 锁定"这台装了 SW 的机器"。

### 4.3 并发与超时

- `concurrency.group: sw-smoke` + `cancel-in-progress: false`（D7）：队首 job 跑完前，后来的排队等待；不会硬杀正跑的 job 导致 artifact 丢失。离线积压时多个 run queued——接受，runbook 给 `gh run cancel --all` 清理命令
- `timeout-minutes: 15`：远大于 deep smoke 正常耗时（< 30s Dispatch + < 30s LoadAddIn + 余量），但足以防止 Dispatch 真悬挂把 runner 锁 2 小时

### 4.4 Skip-guard（D10 ET-based）

`@requires_solidworks` 是在 `tests/conftest.py` 里靠 `pytest_collection_modifyitems` 动态 skip 的。若未来 refactor 误改该 gate（例如条件反了），test_sw_inspect_real.py 会全量 skip，pytest exit code 仍是 0，CI 绿——但没跑任何真 SW 逻辑。

防御（ET 解析替代 grep magic number）：
```python
from xml.etree import ElementTree as ET
root = ET.parse('sw-smoke-junit.xml').getroot()
all_tcs = list(root.iter('testcase'))
skipped = [tc for tc in all_tcs if tc.find('skipped') is not None]
real = len(all_tcs) - len(skipped)
assert real >= 1
```

语义正确性：pytest junit.xml 的 `<testcase>` 嵌 `<skipped>` child 表示跳过；`real = total - skipped` 是"实际跑了"的测试数。断言 `real >= 1` 意为"至少一条真跑"——未来 test_sw_inspect_real.py 增删 testcase 无需改 workflow。

### 4.5 Composite action：`.github/actions/setup-cad-env/action.yml`（D14 新增）

抽取 sw-smoke 与未来 workflow 共享的三步（setup-python + pip install 依赖 + dev_sync）。sw-smoke 是首个消费者；未来 F-1.3b（追加 sw-warmup / Stage C smoke）或其他 CAD workflow 可直接 `uses: ./.github/actions/setup-cad-env`。

**为何现在抽不 defer**：F-1.3b 的触发时间未定；若今天 sw-smoke 不抽，F-1.3b 时会出现"第二个 workflow 复制粘贴 setup 步骤 → 第三个 workflow 来临时再重构"的技术债链路。一次到位。

```yaml
# .github/actions/setup-cad-env/action.yml
name: Setup CAD env
description: |
  sw-smoke / 未来 CAD-related CI 共享的前置：
  setup-python 3.12 + pip install 运行期依赖 + dev_sync.py 同步 data/ mirrors

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
        # 对齐 tests.yml 的 unpinned 约定（见 §8 已知债务）
        pip install pywin32 pytest pytest-timeout Jinja2 psutil PyYAML

    - name: Sync data/ mirrors
      # 与 tests.yml 一致：exit 0 无变更 / 1 有同步 / >1 真错误
      shell: bash
      run: |
        rc=0
        python scripts/dev_sync.py || rc=$?
        if [ "$rc" -gt 1 ]; then exit "$rc"; fi
```

**不影响 tests.yml 的取舍**：tests.yml 不在本 scope（隔离原则，§1.3）。未来若 tests.yml 迁移到 composite action 是独立重构（记为 F-1.3g）。

### 4.6 JSON schema 断言 helper：`tools/assert_sw_inspect_schema.py`（D13 新增）

把 workflow 里内联的 `assert 'layers' in d and 'dispatch' in d['layers']` 抽到独立脚本。sw-inspect schema（决策 #38 定义）升级时改一处即可。

```python
# tools/assert_sw_inspect_schema.py
"""断言 sw-inspect --json 输出符合 v1 schema（决策 #38）。

workflow / CI / 任何机读消费方统一调用此脚本而非自己写断言。
schema 升级到 v2 时只改本文件。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


REQUIRED_TOP_KEYS = ("version", "mode", "layers", "overall", "elapsed_ms")
REQUIRED_LAYERS_DEEP = (
    "environment", "pywin32", "detect", "clsid",
    "toolbox_index", "materials", "warmup",
    "dispatch", "loadaddin",
)
REQUIRED_LAYER_FIELDS = ("layer", "ok", "severity", "summary", "data")


def assert_schema_v1(path: Path) -> None:
    doc = json.loads(path.read_text(encoding="utf-8"))

    for k in REQUIRED_TOP_KEYS:
        assert k in doc, f"缺顶层字段 {k!r}"

    # deep 模式时校验全 9 层；fast 模式跳过 dispatch/loadaddin
    mode = doc["mode"]
    layers = doc["layers"]
    required = REQUIRED_LAYERS_DEEP if mode == "deep" else REQUIRED_LAYERS_DEEP[:-2]
    for layer_name in required:
        assert layer_name in layers, f"mode={mode} 缺 layer {layer_name!r}"
        for field in REQUIRED_LAYER_FIELDS:
            assert field in layers[layer_name], f"layer {layer_name} 缺 {field!r}"

    # deep 模式：dispatch 层必须有 elapsed_ms（F-4a baseline 消费字段）
    if mode == "deep":
        assert "elapsed_ms" in layers["dispatch"]["data"], \
            "deep 模式 dispatch.data 缺 elapsed_ms（F-4a baseline 消费字段）"


if __name__ == "__main__":
    assert_schema_v1(Path(sys.argv[1]))
    print(f"schema v1 OK: {sys.argv[1]}")
```

同时新建 `tests/test_assert_sw_inspect_schema.py` 覆盖：
- 合法 fast / deep 样本通过
- 缺顶层字段 → AssertionError
- deep 模式缺 `dispatch.data.elapsed_ms` → AssertionError

### 4.7 Step summary（D16 新增）

workflow 末尾把 `sw-inspect --deep` 的 **text 模式** 输出追加到 `$GITHUB_STEP_SUMMARY`：

```yaml
echo '## sw-inspect (deep) 输出' >> "$GITHUB_STEP_SUMMARY"
echo '```' >> "$GITHUB_STEP_SUMMARY"
python cad_pipeline.py sw-inspect --deep >> "$GITHUB_STEP_SUMMARY" 2>&1 || true
echo '```' >> "$GITHUB_STEP_SUMMARY"
```

效果：CI 页 job summary 区块直接展示 sw-inspect 的彩色文本输出（markdown code block 保留 ANSI 色会被过滤但结构保留）。3D / 机械设计师 failing CI 时无需下载 artifact 即可理解状态。

### 4.8 `tests/test_sw_inspect_real.py` 追加断言（3D-1 修正）

现有 2 条断言仅验 `dispatch.severity != fail` + `elapsed_ms < 30_000`，不覆盖 Toolbox / 材质。追加：

```python
def test_deep_real_smoke(self):
    args = argparse.Namespace(deep=True, json=True)
    buf = io.StringIO()
    with redirect_stdout(buf):
        run_sw_inspect(args)
    doc = json.loads(buf.getvalue())

    assert doc["mode"] == "deep"
    disp = doc["layers"]["dispatch"]
    assert disp["severity"] in ("ok", "warn"), f"dispatch={disp}"
    assert disp["data"]["elapsed_ms"] < 30_000

    # 新增（F-1.3）：Toolbox 索引层
    tb = doc["layers"]["toolbox_index"]
    assert tb["data"]["by_standard"], \
        f"toolbox_index.by_standard 空，可能 Toolbox 索引失效；data={tb['data']}"

    # 新增（F-1.3）：materials 层
    mat = doc["layers"]["materials"]
    assert mat["data"]["sldmat_files"] > 0, \
        f"materials.sldmat_files = 0，SW 材质库可能失效；data={mat['data']}"
```

字段名已核对 `adapters/solidworks/sw_probe.py`：`toolbox_index` layer（第 286 行返回 `by_standard` dict）/ `materials` layer（第 485 行返回 `sldmat_files` int）。

---

## 5. 文档产出

### 5.1 Runbook：`docs/superpowers/runbooks/sw-self-hosted-runner-setup.md`

章节：
1. 前置要求（Windows 11 / SolidWorks 2024+ license / 可联网 / Python 3.12 预装或允许 `actions/setup-python` 下载）
2. 创建 `ghrunner` 账户（net user + 组权限收敛清单）
3. 开机自动登录配置（Sysinternals Autologon 工具，LSA-encrypted；**不**用注册表明文 DefaultPassword）
4. 下载并安装 GitHub Actions Runner（版本锁 + 校验）
5. 注册 runner（long-lived，D4）：`config.cmd --url ... --token <one-time> --labels solidworks --replace`
   - 并列"SW 用户数据隔离"节：ghrunner 首次启动 SW 时跑一遍 `File → Options → Reset All` 清掉继承的开发者默认设置
6. Task Scheduler 条目（at-logon trigger、working dir `D:\actions-runner`、restart on failure、`run.cmd`）
7. 首次跑 sw-smoke 验证（`workflow_dispatch` 触发 + Actions 页确认）
   - 记录首次 `skip-guard: total=X skipped=Y real=Z` 作为 baseline
   - 记录首次 `sw-inspect-deep.json.layers.dispatch.data.elapsed_ms` 作为 K1 第一个数据点
8. 故障排查：
   - runner offline 诊断
   - SW Dispatch 失败 → 确认非 Service 模式 + user session 活跃
   - License 冲突 → 合并前关 SW 或 commit message 加 `[skip smoke]`（D15）
   - 积压 queued job 清理（`gh run cancel --all`）
9. 90 天 token 轮换 SOP
10. 卸载：`config.cmd remove --token ...` + 清 Task Scheduler

### 5.2 决策日志：`docs/superpowers/decisions.md` 追加 #39

内容要点：
- 路径选择 C1 的理由（不在 PR 跑 = 公开仓库安全前提）
- 不装 Service 的理由（SW 交互式会话约束）
- long-lived 而非 ephemeral 的理由（避免 PAT 存储破坏账户隔离，D4 重写）
- `cancel-in-progress: false` 的理由（D7 修正，保护 artifact）
- 决策生效前提：开发者拥有一台常可开机的 Windows + SW 机器
- Follow-up：若后续有多机需求或 license 冲突，再考虑 F-1.3c（§9）

### 5.3 README / CLAUDE.md

- README CI 段：追加 "sw-smoke: 真 SW 环境回归（self-hosted runner，仅 main push + 手动触发；commit 含 `[skip smoke]` 跳过）" 一行
- CLAUDE.md：不改

---

## 6. 验收标准

- [ ] `.github/workflows/sw-smoke.yml` 合入 main，语法 `actionlint` 通过
- [ ] `.github/actions/setup-cad-env/action.yml` 合入（D14），sw-smoke 成功消费
- [ ] `tools/assert_sw_inspect_schema.py` + `tests/test_assert_sw_inspect_schema.py` 合入（D13）；单测覆盖合法 / 缺字段 / 缺 elapsed_ms 三情况
- [ ] `tests/test_sw_inspect_real.py::test_deep_real_smoke` 追加 `toolbox_index.by_standard` 和 `materials.sldmat_files > 0` 断言（§4.8）
- [ ] self-hosted runner 在 `Settings → Actions → Runners` 页可见，labels 含 `self-hosted`, `Windows`, `solidworks`
- [ ] 至少一次 `push: main` 触发的 sw-smoke 成功 run（绿），Actions 页可下载 `sw-smoke-artifacts`
- [ ] artifact 内 `sw-smoke-junit.xml` 经 ET 解析后 `real >= 1`（fast + deep 均真跑非 skip）
- [ ] artifact 内 `sw-inspect-deep.json` 可下载、非空，且 `assert_sw_inspect_schema.py` 通过
- [ ] CI 页 job summary 展示 sw-inspect text 输出（D16）
- [ ] `[skip smoke]` commit message 能跳过 workflow（D15，验证：手工 push 一次空 commit 验证 workflow 被 skip）
- [ ] `docs/superpowers/runbooks/sw-self-hosted-runner-setup.md` commit
- [ ] 决策 #39 追加到 `docs/superpowers/decisions.md`
- [ ] 既有 `tests.yml` / `regression` job 零改动（`git diff main -- .github/workflows/tests.yml` 空 diff）
- [ ] Skip-guard baseline：runbook §7 记录首次 `real` 值；后续若回退到 < 1，skip-guard 报 fail

---

## 7. 风险清单

| 风险 | 可能性 | 影响 | 缓解 |
|---|---|---|---|
| runner token 或 workflow 配置泄漏 | 低 | 攻击者在你机器执行任意代码 | long-lived runner 专用账户无 admin；不在 PR 跑；`.credentials` 不进 git；90 天轮换 |
| SW license 占用冲突（runner 跑 smoke 时你也在用 SW）| 中 | smoke fail 或你的 SW 报 license unavailable | `[skip smoke]` commit 标记主动避让（D15）；concurrency 队列（D7）；runbook 给手动 disable 命令 |
| **资源竞争**（runner 起 SW 吃 4–8GB RAM + 磁盘 IO，开发者日常 SW 卡顿）| 中 | 日常建模体验下降，尤其大型装配 | 建议 runner 机器 ≥ 32GB RAM + NVMe；否则考虑 F-1.3e 本地降级路径；`[skip smoke]` 主动避让同样有效 |
| 机器长期关机 → main 上 smoke 积压 | 高 | Actions 页有大量 Queued | `cancel-in-progress: false` 下积压会真正排队——runbook 建议定期 `gh run cancel --all` |
| `@requires_solidworks` gate 误改导致全 skip | 低 | CI 绿但无真跑 | §4.4 ET-based skip-guard |
| Autologon 密码泄漏（注册表 `DefaultPassword` 明文）| 中 | 物理接触者可拿 runner 账户密码 | 用 Sysinternals Autologon 工具（LSA-encrypted 存）而非注册表明文；账户无 admin 权限限制伤害范围 |
| SolidWorks 2024+ 交互式会话超时自动登出 | 低 | runner session 断 → 后续 job 挂 | 配 Windows 电源方案"从不休眠" + "从不锁屏" for `ghrunner` 账户 |
| GitHub Actions Runner 自升级导致 Task Scheduler 脚本 break | 低 | runner 离线 | runbook 要求用官方 `run.cmd`（自带 updater），不 hardcode 版本号 |
| deep smoke `elapsed_ms < 30_000` flaky（SW 冷启受 Windows Update / 杀软影响）| 中 | 偶发 CI 红 | 记 F-1.3f follow-up：连续 3 次 p95 > 20s 时放宽门槛；K3 要求 flaky 率 < 5% |

---

## 8. 依赖与外部假设

- **SolidWorks license**：假定开发机持久授权（非网络浮动），不因 runner 账户切换失效。若是网络浮动，首次 smoke 可能冲突，需 runbook 追加"license swap"节
- **License 席位数**：假定单席位 SW license 允许同机多 Windows 用户 session 各自启动一个 SW 实例（实际 per-user licensing 可能冲突）；不满足时需开发者用 `[skip smoke]` 主动避让
- **GitHub Actions 计费**：self-hosted runner 不消耗 GitHub 配额（public repo 本来也是无限），但 artifact 存储占 GitHub 免费额度 500MB；sw-smoke artifact 每次 < 100KB，可忽略
- **机器可用性**：F-1.3 价值与 runner 在线率成正比。如果每月在线时间 < 30%，考虑降级为 F-1.3e（见 §9）：仅保留 runbook + 本地 `pwsh scripts/run_sw_smoke.ps1` 产物贴 PR 描述，不开 self-hosted runner
- **Pip 依赖 unpinned（已知债务）**：sw-smoke 的 `pip install pywin32 pytest pytest-timeout Jinja2 psutil PyYAML` 沿用 tests.yml 的 unpinned 风格。理论上上游新版本可 break CI，但迄今无前科；待未来 pyproject 引入 `[test]` / `[dev]` extra 时一并 pin（独立重构，不在本 F-1.3 scope）

---

## 9. Follow-up（本设计显式标出的延后项）

| ID | 内容 | 触发条件 |
|---|---|---|
| F-1.3a | 把 sw-smoke 的 JSON artifact 消费到 dashboard（Grafana / GitHub Pages 静态图）| K1 达成（≥ 10 次 main run）|
| F-1.3b | `workflow_dispatch` 加 input `full: bool`，full=true 时追加跑 sw-warmup / Stage C | F-4a baseline 工作开启时 |
| F-1.3c | 若未来有第二台 SW 机器，加 `runner-group` 做负载均衡 | 出现 license / 可用性冲突连续 14 天或 K3 flaky 率 > 10% |
| F-1.3d | 把 `actionlint` 加到 pre-commit + CI | 本 F-1.3 收尾时一并做或另立 |
| F-1.3e | "runner 低在线率"降级路径：保留 runbook + **届时新建** `scripts/run_sw_smoke.ps1`，本地一键跑 + 手工贴 PR，不开 self-hosted runner | K2 = 0（12 个月零价值）或 runner 月在线率 < 30% |
| F-1.3f | deep smoke `elapsed_ms` 门槛调整（30s → 60s 或 p95-based 动态）| K3 flaky 率 > 5% 或连续 3 次 p95 > 20s |
| F-1.3g | tests.yml 也迁移到 `.github/actions/setup-cad-env` composite action | 有第三个 workflow 需要相同前置时 |
| F-1.3h | `test_deep_real_smoke` 追加 `toolbox_index.by_standard` 断言（T2 实施时发现被 conftest autouse `isolate_cad_spec_gen_home` 阻挡，需 pre-seed fake_home 或 fixture override）| `sw-smoke` 稳定运行后，想补齐 §4.8 的完整 3D-1 覆盖时 |

---

## 10. 修订历史

- **v1（2026-04-17）**：初稿。定义 C1 路径、ephemeral runner、`cancel-in-progress: true`、inline JSON schema 断言。commit `9dfdf52`
- **v2（2026-04-17）**：二审修正。artifact path 数据流（run_sw_inspect 只 print 到 stdout → 独立 CLI step）、依赖安装对齐 tests.yml（规避 hatch custom hook）、新增 D11/D12。commit `1881396`
- **v3（2026-04-17，本版）**：多角色审查修正。D4 重写（ephemeral → long-lived）、D7 修正（cancel-in-progress → false）、新增 D13/D14/D15/D16，§1.2 KPI、§1.3 env-check 范围、§4.5/4.6/4.7/4.8 新组件、§7 资源竞争风险、§8 unpinned 债务、§9 新 follow-up F-1.3f/g
