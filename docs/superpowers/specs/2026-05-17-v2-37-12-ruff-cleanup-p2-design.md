# v2.37.12 — ruff cleanup P2（5 类 143 条清零）+ 系统全景图 v2 bundle 设计

> **PR 类型**：chore（pure cleanup，零语义改动，**实际工作量 3-5h** — 含 per-file reviewer ~10-15 file × 5-10min；rev 1 估 ~2-3h 漂移，L5-3 闭合）
> **分支名约定**：`feat/ruff-cleanup-p2-v2.37.12`（L5-8 闭合 — retro 引用稳定）
> **Shell 约定**（L5-2 闭合）：所有 spec 内 ` ```bash` 命令默认在 **Git Bash for Windows**（即 Bash 工具）执行；PowerShell 用户用 `bash -c '...'` wrapper 或在 Git Bash 内跑。**不使用 Windows 不可用的工具**（已替换 `bc` → `awk '{s+=$1}'`）
> **tmp/ 持久化要求**（L5-7 闭合）：`tmp/p2_*.{md,txt,py}` 多个文件不入仓但 session 内必保留；跨 session 重启时必须重跑 Task 0 重建 + 决策表必须从 git history (commit 3 body 数字总和) 反推
> **关联 STATUS doc**：暂无独立 STATUS（P3 启动时统一迁 `docs/superpowers/RUFF_CLEANUP_STATUS.md`，届时新开）
> **关联 v2.37.11 retro**：`docs/superpowers/reports/2026-05-16-v2-37-11-ruff-cleanup-p1-retro.md`（"P2 候选 143 条" 出处 + §A 4 条工艺继承点）
> **Spec rev**：rev 1.2（rev 1 = 21 项 brainstorming fix；rev 1.1 = + 2 项 L3 dry-run + 12 项 L4 adversarial；**rev 1.2 = + 12 项 L5 实操可执行性审查**；累计 **47 项 fix 全 inline 闭合**；后续 plan 阶段 subagent-driven 实施）

---

## 1. 摘要

清掉 ruff 143 errors 里 **F841 + F405 + F403 + E731 + E702 共 143 条**；F841 39 条手工逐条三选一（删/补使用/inline noqa）+ F403/F405 64 条双轨 noqa（codegen 模板 + 25 现存脚手架）+ E731 24 条 `--unsafe-fixes` 先 diff 后批量 + E702 16 条手工拆行；同 PR bundle 系统全景图 v2 docs（1 HTML + 8 jpg）；P2 完结时 `ruff check --select=F841,F405,F403,E731,E702 .` exit 0。

| 改动 | 严重度 | 内容 | 工作量 |
| --- | --- | --- | --- |
| **改动 1** | LOW | bundle docs commit（系统全景图 v2 HTML + V1_enhanced_raw + V1-V7 enhanced_labeled_cn 共 9 文件） | ~5min |
| **改动 2** | LOW | F403/F405 双轨：codegen 模板 `part_module.py.j2` 加 file-scoped noqa + 25 现存脚手架各加 1 行 noqa | ~15min |
| **改动 3** | **HIGH** | F841 39 条手工三选一（按 §3.B 决策规则表 + 超规则 fallback） | ~60min |
| **改动 4** | MED | E731 24 条：先 `--diff --unsafe-fixes` 看，ruff 自跳的 + 改了语义的分类，剩余手工/noqa | ~20min |
| **改动 5** | LOW | E702 16 条手工拆 `a; b` 两行 | ~15min |
| **改动 6** | — | 全套件 PASS + CI 8/8 守门 + AC-1~10 机器验证 | AC |

**P2 不做**（推迟 P3）：
- E402 (74) + E741 (47) + F821 (3) ≈ 124 条
- `[tool.ruff]` config 锁（含 `per-file-ignores` 对 `cad/{end_effector,lifting_platform}/*.py` 排除 F403/F405）
- CI `ruff-strict` job

---

## 2. 背景

### 2.1 现状 — 421 → 154 (P1) → 143 (P2 目标)

2026-05-17 main@`9af4de4` 实跑 `ruff check --select=F841,F405,F403,E731,E702 --statistics .`：

```
F841 (unused-variable)                       39
F405 (undefined-local-from-import-star-usage)39
F403 (undefined-local-with-import-star)      25
E731 (lambda-assignment)                     24
E702 (multiple-statements-on-one-line)       16
─────────────────────────────────────────────
Total                                       143
No safe fixes available                       0
Hidden fixes (--unsafe-fixes)                63   ← F841 39 + E731 24
Manual                                       80   ← F403 25 + F405 39 + E702 16
```

**关键差异 vs P1**：
- P1 是 154 条 safe `--fix`（按按钮）；**P2 是 0 safe fix，需要先看 diff 再决定**
- P1 改完几乎不动语义；**P2 F841 39 条可能藏真 bug（赋值后丢使用）**，必须手工逐条判
- P1 加 2 条 noqa；**P2 加 ≥ 25 条 file-scoped noqa + ≤ 39 条 inline noqa**，baseline 噪声短期上涨

### 2.2 项目历史债隔离原则

`memory/feedback_historical_debt_isolation.md` 约定：历史债开独立 cleanup commit / 独立 PR 专治。本 PR 仅含 ruff cleanup + 1 个 docs bundle commit（系统全景图 v2，docs 与 ruff 独立 commit 不混 diff）。

### 2.3 codegen 脚手架手工补完事实（critical context）

`cad/end_effector/*.py` 11 文件 + `cad/lifting_platform/*.py` 14 文件 = 25 现存脚手架，由 `codegen.py` 从 `part_module.py.j2` 生成；但 2026-05-13 quality overhaul v1 期间这 25 文件**已被手工补完几何代码**（docstring "Hand-completed 2026-05-13" 可证）。

**推论**：F403/F405 64 条**不能用 "改模板 + regen" 一键解决**，否则覆盖手工补完几何。必须双轨：模板 silence 未来生成 + 25 现存文件各加 file-scoped noqa。

### 2.4 noqa 字数标准（继承 retro §7 f9 闭合规则）

所有新加 inline noqa 注释格式：`# noqa: <CODE>  # <理由>`，理由满足（**rev 1.2 强化，L4-4 + L5-5 闭合**）：
- **中文字符 ≥ 2**（不含 ASCII、数字、标点）
- **总字符 ≤ 20**（含中文与 ASCII 全部）
- **必含 trace key（L5-5 闭合）**：理由含 §3.B 决策类别关键词 ∈ `{调试|临时|占位|残留|保留|测试|异步|超规则|废弃|预留|fixture|生成器|walrus}` 至少一个 —— 让 reviewer 能从 noqa 理由 trace 回 §3.B 表第 1-4 决策类

example：`# noqa: F841  # 调试残留` ✅（"调试残留"含 trace key "调试"+"残留"）/ `# noqa: F841  # 测试 fixture` ✅（含 trace key "测试"+"fixture"）
counter-example：`# noqa: F841  # 占位` ✅（含 trace key "占位"；2 中文符合）/ `# noqa: F841  # 备用` ❌（无 trace key —— "备用" 不在白名单；L5-5 闭合）/ `# noqa: F841  # debug var` ❌（中文 0）/ `# noqa: F841  # 此处变量曾用于早期调试现已废弃` ❌（总 22）

机器验证：见 §5 AC-10。

### 2.5 项目当前 baseline

- 全套件 **3244 PASS / 17 SKIP / 0 regression**（v2.37.11 实测值；P2 Task 0 T0.7 重测校准）
- CI 连续 **21 PR 一次过零 hotfix**（subagent-driven 流程稳定）
- pyproject.toml **无 `[tool.ruff]` 配置段**（P3 计划加）
- main 当前 untracked：`docs/系统全景图_v2.html` + `docs/assets/system-overview/`（8 jpg）—— bundle commit 1 落

---

## 3. 改动范围

### 3.1 In Scope（5 类 ruff + bundle docs）

#### 3.1.A F403/F405 双轨 noqa

**A-1 — 改 codegen 模板**

文件：`src/cad_spec_gen/data/templates/part_module.py.j2`

**位置选择**（边界 E-2 闭合）：选位置 (iii) — docstring `"""` 结束之后、`import cadquery as cq` 之前，jinja if-else 之**前**。

```jinja
"""
{{ part_name_cn }} ({{ part_no }})
...（docstring 不动）
"""

# ruff: noqa: F403, F405  ← 新增 1 行
import cadquery as cq
{% if param_imports %}
from params import (
    {% for p in param_imports %}
    {{ p }},   # {{ param_sources[p] | default('source line ref required', true) }}
    {% endfor %}
)
{% else %}
from params import *
{% endif %}
```

理由：位置 (iii) 让显式 import 分支和 `*` 分支都带 noqa；显式分支带多余 noqa 但无副作用；统一位置降低 reviewer 心智成本。

**A-2 — 25 现存脚手架各加 1 行 file-scoped noqa**

位置（边界 E-1 闭合）：**必须在 module-level import 语句之前**（在 docstring 之后、`import cadquery as cq` 之前）。**不能加在 `from params import *` 行内联** —— inline noqa 只 silence 那一行，不 cover 后续 F405 使用位。

落地方式（**推荐方式 1，L3 dry-run 闭合**）：
1. **[推荐]** 写一次性脚本 `tmp/p2_apply_noqa.py`（不入仓）按统一 pattern 在每文件 docstring 结束 `"""` 后 + `import cadquery as cq` 前插入 `# ruff: noqa: F403, F405\n`；脚本一次跑遍 25 文件，确保 pattern 一致 + 节省 budget
2. **[fallback]** 逐文件 Edit（25 次 Edit；适合脚本 pattern 不匹配特殊文件时单独处理；不应是主路径）

**实证**（Task 0 T0.4b 闭环 E-1）：任选 1 文件落地后跑 `ruff check --select=F403,F405 <file>` 必须 exit 0；如未 exit 0 = 位置错。

#### 3.1.B F841 手工三选一（决策规则表，闭合 A-1 + E-6 + F-6）

**决策表（含变量名白名单 + scope 偏好，闭合 L4-2 + L4-12）**：

| # | 决策 | 触发 axis（**严格白名单**） | scope 偏好 | 例 |
|---|---|---|---|---|
| 1 | **删** | 变量名 ∈ 显式临时白名单 `{tmp, _tmp, _unused, _, _result, _ret, debug_*, old_*, deprecated_*}` + 函数体后续不需要 + 不在 except/walrus 特殊位 | **src/* 偏好** | `debug_intermediate = compute()` 后无引用 |
| 2 | **补使用** | 赋值是 compute-heavy（函数调用 ≥1 或复杂表达式）+ 函数返回/容器追加缺失 + return None / 空 yield 等明显丢使用信号 | **src/* 偏好** | `result = expensive()` 后立刻 `return None` → 改 `return result` |
| 3 | **inline noqa** | 在 except 块（`as e`）/ for-else / mock fixture / 类属性 / 占位 / test fixture 等"故意保留"语义位 | **tests/* + cad/* 偏好**（手工补完几何 preserve） | `for _ in range(N)` 但 ruff 误报 / `assert result == expected` 但 ruff 看不到 |
| 4 | **超规则 fallback** | 不属 1-3 任一类 + 变量名不在白名单 + 语义存疑 → 加 `# noqa: F841  # 超出规则案例` + 记入 §9 follow-up；P3 spec 扩规则表 | 任意 scope | 异步生成器局部 var / walrus 复杂 case / 半补完几何中间结果 |

**严格规则**：决策 1 (删) 的变量名必须**精确匹配**白名单 pattern，否则归决策 4 (超规则)。这是防 reviewer 偏置（"看着像临时变量就删"）的硬约束。

**决策记录**：`tmp/p2_f841_decisions.md`（不入仓），每行 `file:line | 决策(删/补/noqa/超规则) | 理由（≤15 字中文）`；**总行数必 = 39，与 Task 0 T0.3 `tmp/p2_f841_loc.txt` 的 file:line 一一对应**（L4-5 闭合）；commit 3 完成后摘要数字进 commit body（§7 模板）。

**reviewer 抽样比对**（L4-5 闭合）：per-file spec reviewer 在每 file 决策完成时随机抽 ≥ 2 行决策表对照 ruff 实际 file:line，验证（a）file:line 存在于 ruff 输出 (b) 决策符合 §3.B 表 axis (c) 理由满足 §2.4 字数标准。

#### 3.1.C E731 lambda-assignment

**步骤**（闭合 B-2 删 stash + E-3 实证）：
1. `ruff check --select=E731 --diff --unsafe-fixes .` 看 24 条 diff
2. 按 diff 输出分三类：
   - **N 条 ruff 自跳过**（ruff 自己识别 dict 值位/装饰器/类属性 context 不改）—— 不动
   - **M 条 ruff 改了等价 lambda → def**—— 直接 `ruff --fix --unsafe-fixes --select=E731 .` 上
   - **K 条 ruff 改了但语义可疑**（如 lambda 被 pickle / 出现在 dict 值位但 ruff 仍尝试转）—— 手工逐条改 noqa 或人工拆 def
3. Task 0 T0.2 必须输出 N / M / K 三个数；spec rev 1 草稿 T0.2 实证后填真值
4. 等式：N + M + K = 24

#### 3.1.D E702 multiple-statements-on-one-line-semicolon

16 条全手工：`ruff check --select=E702 .` 拿 file:line → 逐 Edit 把 `a; b` 拆两行。注意：
- import 拆分保 alias 完整：`import a as A; import b as B` → 各占一行
- 类属性 / 同行赋值 case 检 indent

#### 3.1.E bundle docs（commit 1 单独）

文件清单（共 **9 文件**，闭合 C-1）：
- `docs/系统全景图_v2.html` (~120KB)
- `docs/assets/system-overview/V1_enhanced_raw.jpg`
- `docs/assets/system-overview/V1_front_iso_20260513_1959_20260513_2006_enhanced_labeled_cn.jpg`
- `docs/assets/system-overview/V2_rear_oblique_20260513_2000_20260513_2006_enhanced_labeled_cn.jpg`
- `docs/assets/system-overview/V3_side_elevation_20260513_2001_20260513_2006_enhanced_labeled_cn.jpg`
- `docs/assets/system-overview/V4_exploded_20260513_2002_20260513_2006_enhanced_labeled_cn.jpg`
- `docs/assets/system-overview/V5_ortho_front_20260513_2002_20260513_2006_enhanced_labeled_cn.jpg`
- `docs/assets/system-overview/V6_cross_section_20260513_2004_20260513_2006_enhanced_labeled_cn.jpg`
- `docs/assets/system-overview/V7_section_side_20260513_2005_20260513_2006_enhanced_labeled_cn.jpg`

`git add` 命令（闭合 E-7 不带隐藏文件）：

```bash
git add docs/系统全景图_v2.html
git add docs/assets/system-overview/V*.jpg
```

显式 glob，不加目录，防 `.DS_Store` / `Thumbs.db` 等本机文件混入。

### 3.2 Out of Scope（显式声明 + AC 防护）

| 项 | 防护 |
|---|---|
| **AGENTS.md 不动**（auto-generated, do not manually edit；P1 retro 教训） | AC-3 path-aware grep 闭环 |
| **`pyproject.toml` version 不动**（v2.25+ tag-only release，仍 `2.24.0`） | AC-4 grep 闭环 |
| **`cad/end_effector/` / `cad/lifting_platform/` 几何代码不动**（25 脚手架只在文件头加 1 行 noqa 注释；**L5-9 阐明**："几何代码"专指 `cq.Workplane`/`extrude`/`rotate`/`translate`/`assemble` 等几何运算 — cad/ 文件内 F841 加 inline noqa 注释行**不算几何代码改动**；AC-5 阈值算法把这类 noqa 算在合法 delta 内） | AC-5 cad/ scope diff 阈值闭环 + L5-6 reviewer checklist |
| **不引入 `[tool.ruff]` config 锁**（推 P3） | spec §10 显式声明 |
| **不加 CI `ruff-strict` job**（推 P3） | spec §10 显式声明 |
| **P2 不 regen 脚手架**（手工补完不能丢） | spec §2.3 critical context 闭环 |
| **不动 SolidWorks/Blender/AI backend 代码**（cleanup 纯 ruff 命中 file） | scope 自然边界 |

---

## 4. 实施步骤

### 4.0 Task 0 — Scout（强制，~25min，闭合 B-1 + B-3 + C-2 + E-3 + E-4 + E-5）

**目的**：spec 所有假设实证一遍 + 输出 implementation 阶段所需真数。

| Step | 命令 / 操作 | 输出 |
|---|---|---|
| T0.1 | `.venv/Scripts/ruff.exe check --select=F841,F405,F403,E731,E702 --statistics .` | 校准 5 类数字（spec 写 39/39/25/24/16） |
| T0.1b | `.venv/Scripts/ruff.exe --version` | 记录 ruff 版本（L4-8 闭合 — 不同版本 hidden fix 行为差异防误判） |
| T0.2 | `.venv/Scripts/ruff.exe check --select=E731 --diff --unsafe-fixes .` | E731 三类 N (ruff 自跳) / M (安全转) / K (语义可疑) 真数 |
| T0.3 | `.venv/Scripts/ruff.exe check --select=F841 . > tmp/p2_f841_loc.txt` | 39 行 file:line 列表，按 file 分组 |
| T0.3b | `grep -E "cad/(end_effector\|lifting_platform)" tmp/p2_f841_loc.txt \| wc -l` | F841 命中 cad/ 的数 = `F841_cad_count`（供 AC-5 阈值） |
| T0.3c | `.venv/Scripts/ruff.exe check --select=F841,E731,E702 . \| grep -oE "cad/(end_effector\|lifting_platform)/[^:]+\.py" \| sort -u \| wc -l` | F841+E731+E702 命中 cad/ 的**总文件数** = `cad_total_files`（供 AC-5 阈值算法 — L3 dry-run 闭合） |
| T0.4 | `git ls-files cad/end_effector/*.py cad/lifting_platform/*.py \| wc -l` | 必须 = 25（双轨 noqa 落地目标） |
| T0.4b | 任选 1 脚手架试加 file-scoped noqa → `ruff --select=F403,F405 <file>` | exit 0 验证 noqa 位置正确（闭合 E-1） |
| T0.4c | `git ls-files \| grep -i "agents\.md"` | 列举仓内所有 AGENTS.md 路径（供 AC-3 pattern 校准） |
| T0.5 | `grep -rnE "from \w+ import \*" src/cad_spec_gen/data/templates/*.j2` | **枚举全部 codegen 模板** 使用 `import *` 的位置；spec 假设仅 `part_module.py.j2` 一个，T0.5 必须实证（L4-6 闭合） |
| T0.5b | 模板试加 noqa 后 jinja render 一个 dummy params → 检查输出脚手架 noqa 出现在 import 前 | 实证位置 (iii) 正确（闭合 E-2） |
| T0.6 | `ls docs/assets/system-overview/*.jpg \| wc -l` | 必须 = 8（V1_enhanced_raw + V1-V7 enhanced_labeled_cn） |
| T0.7 | `.venv/Scripts/python.exe -m pytest -q --no-header 2>&1 \| tail -5` | baseline pytest PASS 数（供 AC-2） |
| T0.8 | `ls .github/workflows/*.yml \| xargs -I{} basename {} .yml` | **枚举 CI workflow 文件总数** = `ci_workflow_count`；AC-9 引用此数（L4-7 闭合 — 不假设 3 job） |

**Task 0 报告**（写 `tmp/p2_scout_report.md` 不入仓）：
- 5 类真数表
- ruff version (T0.1b)
- F841 file 分布 + `F841_cad_count`（T0.3b）
- `cad_total_files`（T0.3c）
- E731 N/M/K 三数（T0.2）
- AGENTS.md 真实路径列表（T0.4c）
- codegen 模板 `import *` 枚举（T0.5；spec 假设只 `part_module.py.j2`，T0.5 必证实）
- pytest baseline PASS 数（T0.7）
- CI workflow 列表 + 总数 `ci_workflow_count`（T0.8）

### 4.1 Commit 1 — bundle docs（~5min）

```bash
git add docs/系统全景图_v2.html
git add docs/assets/system-overview/V*.jpg
git commit -m "docs(overview): 系统全景图 v2 + V1-V7 enhanced 渲染图

新增 docs/系统全景图_v2.html 与 docs/assets/system-overview/ 9 文件
（1 HTML + 8 jpg：V1_enhanced_raw + V1-V7 enhanced_labeled_cn）。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

**⚠️ 顺序约束（L4-11 闭合）**：commit 1 完成**立即**跑 AC-8 验证：

```bash
test "$(git ls-files docs/系统全景图_v2.html docs/assets/system-overview/V*.jpg | wc -l)" -eq 9 \
  && echo "AC-8 PASS" \
  || { echo "AC-8 FAIL — bundle 文件数 != 9，git reset commit 1"; git reset --soft HEAD~1; }
```

如 AC-8 fail → 立即 reset commit 1，排查 glob match / typo / 文件名规范化后重 commit。**不能进 commit 2 (F403/F405) 之前留 bundle 缺漏**。

### 4.2 Commit 2 — F403/F405 双轨（~15min）

A-1 改模板 (1 行) + A-2 25 脚手架（25 行）= 26 行变更。
落完跑 `ruff --select=F403,F405 .` 必须 exit 0。

```bash
git add src/cad_spec_gen/data/templates/part_module.py.j2 \
        cad/end_effector/*.py cad/lifting_platform/*.py
git commit -m "chore(ruff/P2-A1A2): F403/F405 双轨 noqa（模板 + 25 现存脚手架）

A-1 part_module.py.j2 import 段前加 # ruff: noqa: F403, F405（防未来生成报）
A-2 cad/end_effector/*.py (11) + cad/lifting_platform/*.py (14) 共 25 文件
    各文件 docstring 后 / import 前加 1 行 file-scoped noqa
    （不动几何代码 — 25 文件 × 1 行 = 25 行 diff）

理由：cad/ 脚手架由 codegen 产 + 2026-05-13 quality overhaul 手工补完
几何，不能 regen；F403/F405 是 codegen import * 模式 by-design，noqa 是
正解非 hide bug。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

### 4.3 Commit 3 — F841 手工 39 条（~60min）

按 §3.B 决策规则表 + Task 0 T0.3 file 分组逐 file Edit。每 file：
1. Read 上下文 ±3 行
2. 按规则表四选一标记决策
3. Edit 落地（删 / 补使用 / inline noqa / 超规则 noqa）
4. 该 file `ruff --select=F841 <file>` exit 0
5. 触发 per-file spec reviewer（subagent；详 §6.2）

39 行决策完成后跑 `ruff --select=F841 .` 必须 exit 0。

```bash
git add <touched files>
git commit -m "chore(ruff/P2-A3): F841 unused-variable 39 条手工清零

- 删: <X> 条（调试残留 / 显式临时变量）
- 补使用: <Y> 条（赋值丢 return/raise/append）
- inline noqa: <Z> 条（except as / for-else / 类属性 故意保留）
- 超规则 fallback: <W> 条（不属上三类，加 noqa 进 §9 follow-up）

校验: X + Y + Z + W = 39 ✓

详见 tmp/p2_f841_decisions.md（不入仓，retro 摘要进 docs/superpowers/reports/）

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

**commit body 数字必对齐**（闭合 N-1 + AC-7 机器验证）：implementer 写完 body 后用 `git log -1 --format=%B | grep -oP '(?<=删: )\d+|(?<=补使用: )\d+|(?<=inline noqa: )\d+|(?<=fallback: )\d+' | paste -sd+ - | bc` 必须输出 `39`。

### 4.4 Commit 4 — E731 半自动 24 条（~20min）

按 T0.2 N/M/K 分类：
- N 条 ruff 自跳 → 不动（已 exit 0）
- M 条 ruff 安全转 → `ruff --fix --unsafe-fixes --select=E731 .`
- K 条语义可疑 → 手工逐条改 noqa 或拆 def

```bash
git add <touched files>
git commit -m "chore(ruff/P2-A4): E731 lambda-assignment 24 条清零

- ruff 自跳: <N> 条（dict 值位 / 装饰器 context, ruff 不改）
- ruff 安全转: <M> 条（lambda → def 等价）
- 手工 noqa/拆: <K> 条（pickle 不友好 / 闭包语义保留）

校验: N + M + K = 24 ✓

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

### 4.5 Commit 5 — E702 手工 16 条（~15min）

逐 Edit 拆 `a; b` 两行；注意 import 别名完整、indent 一致。

```bash
git add <touched files>
git commit -m "chore(ruff/P2-A5): E702 multiple-statements 16 条手工拆行

逐条 Edit 把 \`a; b\` 拆两行；保 import alias / indent 完整。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

### 4.6 Commit 6 — AC sanity（可选，~5min）

如 AC 1-10 任一 fail，commit 6 修；如全过则不必（最终态在 commit 5 后即满足）。

---

## 5. AC 验收详表（10 项，闭合所有 verifier 漏洞）

| # | AC 描述 | 验证命令 | 通过条件 | 检测时机 |
|---|---|---|---|---|
| **AC-1** | 5 类 ruff 全清零 | `.venv/Scripts/ruff.exe check --select=F841,F405,F403,E731,E702 .` | exit 0 | local commit 5 后 + CI |
| **AC-2** | 全套件无回归 | `.venv/Scripts/python.exe -m pytest -q --no-header` | PASS 数 ≥ T0.7 baseline，0 failed | local commit 5 后 + CI |
| **AC-3** | AGENTS.md 防护栏（path-aware，闭合 E-5） | `git diff --name-only origin/main \| xargs -I{} basename {} \| grep -q "^AGENTS\.md$" && echo FAIL \|\| echo OK` | echo OK | per-commit + PR pre-merge |
| **AC-4** | `pyproject.toml` version 不动 | `grep '^version' pyproject.toml` | 仍为 `version = "2.24.0"` | PR pre-merge |
| **AC-5** | 几何代码不动（cad/ scope diff 阈值，闭合 B-3 + E-4 + L3 dry-run + L4-1 + **L5-6 人审 checklist**） | `git diff origin/main -- cad/end_effector/*.py cad/lifting_platform/*.py \| grep -cE '^[+-][^+\-]'` | **阶段 cap**：(a) best `F841_cad_count = 0` 且 `cad_total_files = 0` → ≤ **30**；(b) 一般 → ≤ 25 + `F841_cad_count` × 2 + (`cad_total_files - F841_cad_count`) × 3 + 10；(c) > **50** → 必 **reviewer 人审 checklist**：(c-1) 所有 diff 行类型 ∈ `{noqa 注释, F841 inline noqa, F841 删除 1 行 unused var, F841 补 return/raise 1 行}`；(c-2) 无几何运算函数体改动（`cq.Workplane`/`extrude`/`rotate`/`translate` 等）；(c-3) docstring/import 段不被覆盖 | per-commit + PR pre-merge |
| **AC-6** | 模板 noqa 落地 | `grep -B1 'from params import \*' src/cad_spec_gen/data/templates/part_module.py.j2 \| grep -q 'noqa: F403, F405'` 或 `grep -q 'ruff: noqa: F403, F405' src/cad_spec_gen/data/templates/part_module.py.j2` | exit 0 | commit 2 后 |
| **AC-7** | F841 commit body 数字对齐（机器验证，闭合 F-2 + L4-3 + **L5-1 BLOCKER 用 awk 替代 bc**） | `git log -1 --format=%B <commit-3-sha> \| grep -oP '(?<=删: )(\d+)(?= 条)\|(?<=补使用: )(\d+)(?= 条)\|(?<=inline noqa: )(\d+)(?= 条)\|(?<=fallback: )(\d+)(?= 条)' \| awk '{s+=$1} END {print s+0}'` | 输出 `39` | **commit 3 后 + squash-merge 之前**（L5-4 闭合 — squash 后 commit 3 body 消失） |
| **AC-8** | bundle docs 完整 | `git ls-files docs/系统全景图_v2.html docs/assets/system-overview/V*.jpg \| wc -l` | = 9 | commit 1 后 |
| **AC-9** | CI 全绿（**L4-7 闭合 — 不假设 job 数**） | `gh pr checks --required \| tail -n +2 \| awk '{print $2}' \| sort \| uniq -c` | 全部 = `pass`；total = `ci_workflow_count`（T0.8 实测；spec 假设 ≥ 3 不锁死） | PR 开后 |
| **AC-10** | noqa 字数标准（机器验证，闭合 F-1） | `git diff origin/main \| grep -oP '#\s*noqa:\s*\w+\s+#\s+\K.+$' \| python -c "import sys, re; bad = [l for l in sys.stdin if not (len(re.findall(r'[一-鿿]', l)) >= 3 and len(l.strip()) <= 20)]; sys.exit(1 if bad else 0)"` 或封装 `tools/dev/noqa_lint.py` | exit 0 | commit 3/4 后 + PR pre-merge |

**baseline `F841_cad_count` 由 Task 0 T0.3b 实测填入**；**baseline `cad_total_files` 由 Task 0 T0.3c 实测填入**（L3 dry-run 闭合 — F841/E731/E702 三类总命中 cad/ 的 unique file 数）。
- 如 `F841_cad_count = 0` 且 `cad_total_files = 0` → AC-5 阈值简化为 **≤ 30**（25 noqa + 5 余量）
- 如 `F841_cad_count = 0` 且 `cad_total_files > 0` → AC-5 阈值 = **25 + cad_total_files × 3 + 10**
- 一般情况 → 按上方表中算法

---

## 6. 审查 cascade

### 6.1 Spec 阶段（3 layer，闭合"v2.37.X rev 1-3 即闭合"工艺）

| Layer | 角色 | 输入 | 产物 | 估时 |
|---|---|---|---|---:|
| **L1** | self-review（主 agent） | spec rev 1 草稿 | 扫 21 项 fix 是否全落 + placeholder / 一致性 / scope / 歧义 | 5min |
| **L2** | code-spec 对照（主 agent） | spec rev 1 + Task 0 输出 | 校 spec 写的数字 / file 路径 / 模板 jinja 位置是否与实测一致 → rev 2 if drift | 10min |
| **L3** | 1 角色 dry-run（主 agent 扮 reviewer） | spec rev 2 | dry-run 实施块 A/B/C/D 各跑一遍想象 → 找 state lifecycle bug / cross-block dep → rev 3 if found | 10min |

**降档理由**：4 类策略均在 brainstorming 阶段敲定 + 21 项 fix 提前合入 rev 1，spec 阶段无设计风险。

### 6.2 Implementation 阶段（per-task subagent，闭合 B-4 + F-5 + **L4-9 输出格式**）

| 时机 | 角色 | 输入 | 输出格式（L4-9 闭合） | 产物 |
|---|---|---|---|---|
| **每实施块 begin** | **主 agent scout** | 块 begin checkpoint | `{ok: bool, drift: [{type, file, line, message}]}` | `git ls-files` + grep 校 plan 假设的 file path / API（防 plan-drift 5 分类） |
| **F841 每 file 决策完成后**（触发条件明示，闭合 F-5）：file 内全部 F841 行 Edit 完成 + `ruff --select=F841 <file>` exit 0 + commit 3 stage 前 | **per-file spec reviewer**（subagent） | 输入：该 file 全部 Edit diff + 决策表 file 段落（多行 grouped 作单次 reviewer 输入） + Task 0 `tmp/p2_f841_loc.txt` file 段落 | `{verdict: PASS\|FAIL, sampled_lines: [list], issues: [{file:line, severity: HIGH\|MED\|LOW, message}]}` | 抓"删了真 bug" / "补使用补错" / "noqa 字数不达标" / "超规则未登记" / "白名单外却归删类" |
| **E731 unsafe-fix --diff 后** | **edge-case hunter subagent** | T0.2 输出 N/M/K + diff sample | `{verdict: PASS\|FAIL, edge_cases: [{file:line, lambda_context, recommended_action}]}` | 抓 "ruff 自跳是否漏 case" / "ruff 改了但语义可疑是否手工补 noqa" |
| **每 commit push 前** | **主 agent final check** | git diff origin/main + AC 1-10 表 | `{ac_results: {AC-1: PASS\|FAIL\|N/A, ...}}` | per-commit AC 自动跑（AC-3/5/6/7/8 实时） |
| **PR 开后 CI 运行中** | **CI watcher** | `gh pr checks --watch` | `{checks: [{name, status}], all_pass: bool}` | 全 `ci_workflow_count` job SUCCESS / AC-9 通过才 merge |

### 6.3 budget 分布

```
Spec layer (3) ████░░░░░░░░  25%
Implementation per-task subagent (4 类型) ████████████  75%
```

### 6.4 Final reviewer 触发条件

- P2 一次过 CI 0 hotfix → spec rev 1 + per-task subagent 已 cover → **不另启 final reviewer**
- P2 出现任意 hotfix → spec rev 1 cascade 升档到 6 layer 复跑（按 P1 工艺）

---

## 7. Commit body 模板（标准化，闭合 F-3）

### 7.1 commit 1 (docs bundle)

```
docs(overview): 系统全景图 v2 + V1-V7 enhanced 渲染图

新增 docs/系统全景图_v2.html 与 docs/assets/system-overview/ 9 文件
（1 HTML + 8 jpg：V1_enhanced_raw + V1-V7 enhanced_labeled_cn）。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
```

### 7.2 commit 2 (F403/F405)

```
chore(ruff/P2-A1A2): F403/F405 双轨 noqa（模板 + 25 现存脚手架）

A-1 part_module.py.j2 docstring 后 / import 前加 # ruff: noqa: F403, F405
A-2 cad/end_effector/*.py (11) + cad/lifting_platform/*.py (14) 共 25 文件
    各加 1 行 file-scoped noqa（位置：docstring 后 / import 前）
    （不动几何代码 — 25 文件 × 1 行 = 25 行 diff）

理由：cad/ 脚手架由 codegen 产 + 2026-05-13 quality overhaul 手工补完几何，
不能 regen；F403/F405 是 codegen import * 模式 by-design，noqa 是正解。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
```

### 7.3 commit 3 (F841)

**⚠️ Implementation Note（L4-3 BLOCKER 闭合）**：implementer 写 commit body 时**必须把 `<X>` `<Y>` `<Z>` `<W>` 替换为实际整数**（如 `<X>` → `12`），不能保留占位符；AC-7 grep `(?<=删: )(\d+)(?= 条)` 才能 match。例：

```
chore(ruff/P2-A3): F841 unused-variable 39 条手工清零

- 删: 12 条（调试残留 / 显式临时变量；白名单内）
- 补使用: 18 条（赋值丢 return/raise/append）
- inline noqa: 7 条（except as / for-else / 类属性 故意保留）
- 超规则 fallback: 2 条（不属上三类，加 noqa 进 §9 follow-up）

校验: 12 + 18 + 7 + 2 = 39 ✓（AC-7 机器验证）

详见 tmp/p2_f841_decisions.md（不入仓，retro 摘要进 reports/）

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
```

（example 用 12+18+7+2=39 仅示意；implementer 按实际决策填）

### 7.4 commit 4 (E731)

```
chore(ruff/P2-A4): E731 lambda-assignment 24 条清零

- ruff 自跳: <N> 条（dict 值位 / 装饰器 context，ruff 不改）
- ruff 安全转: <M> 条（lambda → def 等价）
- 手工 noqa/拆: <K> 条（pickle 不友好 / 闭包语义保留）

校验: N + M + K = 24 ✓

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
```

### 7.5 commit 5 (E702)

```
chore(ruff/P2-A5): E702 multiple-statements 16 条手工拆行

逐条 Edit 把 `a; b` 拆两行；保 import alias / indent 完整。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
```

### 7.6 commit 6 (AC sanity，可选 — L5-11 闭合)

仅当 commit 5 后某 AC 失败需补救才用；零失败时 commit 6 不创建。

```
chore(ruff/P2-AC): AC sanity 补救（<AC-X>）

<列出本次 commit 修了哪些 AC fail>：
- AC-<n>: <修复内容简述>

校验: 修后 AC-1~10 全 PASS ✓

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
```

### 7.7 PR title (squash-merge)

```
chore(ruff): v2.37.12 — ruff cleanup P2 5 类清零（143 → 0）+ 全景图 v2 docs
```

### 7.8 实施顺序图（L5-12 闭合 — 严格串行不并行）

```
Task 0 (Scout)
  └─→ Commit 1 (docs bundle) ─[立验 AC-8]→
        └─→ Commit 2 (F403/F405 双轨) ─[立验 ruff --select=F403,F405]→
              └─→ Commit 3 (F841 手工) ─[立验 AC-7 + ruff --select=F841]→
                    └─→ Commit 4 (E731 半自动) ─[立验 ruff --select=E731]→
                          └─→ Commit 5 (E702 手工) ─[立验 ruff --select=E702 + AC-1 全套]→
                                └─→ (可选) Commit 6 (AC sanity 补救) →
                                      └─→ git push origin feat/ruff-cleanup-p2-v2.37.12 →
                                            └─→ gh pr create →
                                                  └─→ CI watcher (AC-9 N job)
```

**严格约束（L5-12 闭合）**：
- commit 2 到 commit 5 **必须串行**，不可并行（同 file 改动会冲突）
- 每 commit 完成立即跑 per-class ruff exit-0 验证，不通过立 reset 该 commit
- subagent 实施时主 agent 严格按上图驱动，不发"批量并行"指令

---

## 8. 风险与回退（含检测时机，闭合 F-4）

### 8.1 风险矩阵

| ID | 风险 | 概率 | 影响 | 缓解 |
|---|---|---|---|---|
| **R-1** | F841 误删隐藏真 bug（赋值后忘 return/raise/append） | 中 | 高 | per-file spec reviewer 抓 + 决策规则表 + 全套件 PASS（AC-2） + tmp/p2_f841_decisions.md 决策痕迹 |
| **R-2** | F841 决策跨 file 不一致（同 pattern 不同决策） | 中 | 中 | §3.B 决策规则表硬约束 + per-file reviewer 输入 = file 内全部 F841 行 grouped（不单行决策） |
| **R-3** | E731 unsafe-fix 改 dict 值位 lambda 导致语法错 | 低 | 中 | Task 0 T0.2 `--diff` 预跑 + edge-case hunter subagent |
| **R-4** | 25 脚手架加 noqa 时不小心动几何代码 | 低 | 高 | AC-5 cad/ scope diff 阈值上限 + per-commit Bash diff sanity |
| **R-5** | noqa 位置加错（inline 而非 file-scoped）导致 F405 未 silence | 中 | 中 | Task 0 T0.4b 单文件实证 + AC-1 终态守门 |
| **R-6** | 模板 noqa 加错 jinja 分支导致未来生成漂移 | 低 | 中 | Task 0 T0.5b jinja render 实证 + 选位置 (iii) 统一影响全分支 |
| **R-7** | bundle docs 6MB jpg 占 git 历史 | 已接受 | 低 | 用户已确认 commit 进同 PR；未来如要回退 git LFS 迁移记入 §9 follow-up |
| **R-8** | AGENTS.md 被 subagent 误改 | 低 | 高 | AC-3 path-aware grep 防护栏 + spec §3.2 Out of Scope 显式声明 |
| **R-9** | `uv run` 依赖冲突阻塞实施 | 已知 | 低 | spec §4 显式使用 `.venv/Scripts/ruff.exe` 与 `.venv/Scripts/python.exe -m pytest` |
| **R-10** | F841 超规则 case 数量过多（≥5）导致决策表失效 | 低 | 中 | §3.B 第 4 类 fallback noqa + §9 follow-up 触发 P3 扩规则 |

### 8.2 回退策略（含检测时机）

| 触发 | 检测时机 | 回退动作 |
|---|---|---|
| 实施块 B（F841）改完发现全套件回归 | commit 3 后 local AC-2 | `git reset --hard <commit-2-sha>` 退到 commit 2；F841 推迟 P3 |
| 实施块 C（E731）unsafe-fix 后 ruff 报新错 | commit 4 前 local AC-1 | `git checkout -- <files>` 退 unsafe-fix；24 条全转手工/noqa |
| AC-3 AGENTS.md 防护栏触发 | per-commit local | 立即 `git checkout origin/main -- AGENTS.md` + PR body 说明 |
| AC-5 cad/ diff 超阈值 | per-commit local | `git diff -- cad/` 抽超量 hunk → `git checkout -- <hunk>` |
| AC-7 commit 3 body 数字 != 39 | commit 3 后 local | `git commit --amend` 修 body（commit 3 仅是本 PR 内，amend 安全） |
| CI 全失败（>50% job 红） | PR 开后 | `gh pr ready --undo` 转 draft；spec rev 1 升档到 6 layer cascade（按 P1 工艺重审） |
| F403/F405 双轨方案落地后发现 codegen 下次 regen 行为异常 | 本 PR 不触发（无 regen） | 模板 commit 单独 `git revert`，保留 25 脚手架 noqa（方案 A 退化为方案 B） |

---

## 9. §11 follow-up（本 spec 推迟项，登记位置：spec self-§11；P3 启动时统一迁 RUFF_CLEANUP_STATUS.md）

| ID | 推迟项 | 触发条件 | 关联 R/F |
|---|---|---|---|
| **§11-N1** | P3 spec 起含 `[tool.ruff]` config 锁 + `per-file-ignores` 对 `cad/{end_effector,lifting_platform}/*.py` 排除 F403/F405（让 25 noqa 可清） | P3 启动 | F-7 |
| **§11-N2** | CI `ruff-strict` job 加 `--select=<P1+P2+P3 codes>` 守门 | P3 启动 | F-7 |
| **§11-N3** | dev_sync.py 或 codegen 加 "regen 前 stash hand-completed marker" 防回退 | 下一次新增几何零件触发 | §2.3 |
| **§11-N4** | git LFS 迁移评估（bundle docs 6MB jpg 历史膨胀） | 仓总尺寸 > 100MB 时 | R-7 |
| **§11-N5** | F841 超规则案例数 ≥ 5 时 P3 spec 扩规则表（第 5/6 类决策） | P2 commit 3 body 含 `fallback: W ≥ 5` 时 | R-10 + F-6 |
| **§11-N6** | P3 加 `tools/dev/noqa_lint.py` 把 AC-10 字数标准封装成 reusable lint（P2 用 inline grep+python，P3 升级独立工具） | P3 启动 | F-1 |

---

## 10. §12 self follow-up（spec self review 漏抓项 — 留 retro 沉淀）

| ID | 漏抓项 | 触发 |
|---|---|---|
| **§12 f1** | spec §3.B 决策规则表实际跑下来 case 数分布（X/Y/Z/W 四类占比）是否与预期一致 | retro 阶段总结，影响 P3 决策表设计 |
| **§12 f2** | per-file spec reviewer subagent 调用次数（~10-15 file 等于 ~10-15 次 reviewer 调用）成本评估 | retro 阶段总结，影响 P3 是否升级为 batch reviewer |
| **§12 f3** | AC-10 inline grep+python 命令在 Windows Git Bash 是否实跑通过（pcre `\K` 在 BSD grep 不支持） | commit 3 实施时实证 → 不通过则 spec rev 2 fallback 命令 |
| **§12 f4** | **P2 retro 必含 noqa file 清单 export**（25 file-scoped F403/F405 + N 个 inline F841 noqa）→ P3 spec 直接 reuse 不重 grep（L4-10 闭合） | retro 阶段产 `tmp/p2_noqa_inventory.md` 入 retro report 附录 |

---

## 11. 与 P1 / P3 衔接

| 维度 | P1 (v2.37.11) | **P2 (v2.37.12 本 PR)** | P3 (v2.37.13+ 计划) |
|---|---|---|---|
| ruff codes | F401 + F541 + F811 + E401 | **F841 + F405 + F403 + E731 + E702** | E402 + E741 + F821 + config 锁 + CI gate |
| 数量 | 154 | **143** | ~124 + config |
| 修法 | safe `--fix` 双步 | 0 safe + 63 unsafe + 80 manual | 跨 file 重组 + 锁规则集 |
| spec layer | 5 layer cascade | **3 layer**（fix 提前合入 rev 1） | TBD（视复杂度） |
| 工艺 | safe-fix + 2 noqa | manual + 双轨 noqa + 决策规则表 | config 锁 + per-file-ignores + CI gate |
| 关联 PR | #90 | **本 PR** | TBD |

---

## 12. v2.37.12 release 信息

- **PR 类型**：chore + docs（bundle）
- **不 bump version**：`pyproject.toml` 仍 `2.24.0`（v2.25+ tag-only release 惯例）
- **Release tag**：`v2.37.12`（squash-merge 后打 tag + GitHub Release notes）
- **Release headline**：`ruff cleanup P2 5 类清零（143 → 0）+ 系统全景图 v2 docs`
- **Release notes 引用**：本 spec + plan + 后续 retro

---

## 13. 21 项 fix 落地校验表

> spec rev 1 self-review (L1) 时逐行核对，确保 brainstorming 阶段两轮 review 的 21 项全落入本 spec 对应位置。

| ID | 类别 | 修复点 | spec 位置 | 已落？ |
|---|---|---|---|---|
| A-1 | 改完不如之前 | F841 三选一决策规则表 | §3.B | ✓ (line 127-136) |
| B-1 | 漂移 | Task 0 T0.7 baseline pytest | §4.0 | ✓ (line 211) |
| B-2 | 漂移 | 删实施块 C `git stash` 步骤 | §4.4 | ✓ (§4.4 已无 stash 命令) |
| B-3 | 漂移 | AC-5 改 cad/ scope diff 阈值 | §5 AC-5 | ✓ (line 331, 338) |
| B-4 | 漂移 | per-file reviewer 输入 "全部 F841 行" | §6.2 | ✓ (line 359) |
| C-1 | 数据 | bundle 文件数 = 9（1 HTML + 8 jpg） | §3.1.E / §5 AC-8 | ✓ (line 159, 334) |
| C-2 | 数据 | "~40 file" 改 Task 0 实测后真数 | §1 / §3.1 表 | ✓ (spec rev 1 已删 ~40 笼统数；改动表用 39/64/24/16 真数) |
| E-1 | 边界 BLOCKER | noqa 必在 import 前 + T0.4b 实证 | §3.1.A-2 / §4.0 T0.4b | ✓ (line 117, 125, 206) |
| E-2 | 边界 BLOCKER | codegen jinja 位置 (iii) + T0.5b 实证 | §3.1.A-1 / §4.0 T0.5b | ✓ (line 94, 115, 209) |
| E-3 | 边界 HIGH | E731 ruff fix 范围实证（N/M/K） | §3.1.C / §4.0 T0.2 | ✓ (line 145-148, 202) |
| E-4 | 边界 HIGH | AC-5 算法 = 25 + F841_cad×2 + 5 | §5 AC-5 | ✓ (line 331, 338) |
| E-5 | 边界 MED | AC-3 AGENTS.md path-aware grep | §5 AC-3 + §4.0 T0.4c | ✓ (line 207, 329) |
| E-6 | 边界 MED | F841 决策表加第 4 类（超规则） | §3.B 表 | ✓ (line 136) |
| E-7 | 边界 LOW | `git add` 用显式 glob 不加目录 | §3.1.E / §4.1 | ✓ (line 174, 224) |
| F-1 | 闭环 BLOCKER | AC-10 noqa 字数机器验证 | §5 AC-10 | ✓ (line 336) |
| F-2 | 闭环 BLOCKER | AC-7 F841 数字对齐机器验证 | §5 AC-7 | ✓ (line 282, 333) |
| F-3 | 闭环 HIGH | commit body 模板（commit 1-5 全） | §7 | ✓ (line 378-448) |
| F-4 | 闭环 HIGH | 回退表加 "检测时机" 列 | §8.2 | ✓ (line 475) |
| F-5 | 闭环 MED | per-file reviewer 触发时机明示 | §6.2 | ✓ (line 359) |
| F-6 | 闭环 MED | F841 超规则 fallback 路径 | §3.B 表第 4 行 + §9-N5 | ✓ (line 136, 495) |
| F-7 | 闭环 LOW | §11 STATUS doc 归属（P3 启动迁） | §9 头注 / §11 衔接表 | ✓ (line 4, 487) |

**L1 self-review 时**：逐行 grep spec 找对应位置 + 把 ☐ 改 ✓。任何 ☐ 残留 = rev 1 不闭合，必修。

### 13.1 L3 dry-run 追加发现（spec rev 1 inline 闭合）

| ID | 类别 | 修复点 | spec 位置 | 已落？ |
|---|---|---|---|---|
| **L3-1** | 闭环 HIGH | AC-5 阈值算法漏 Block C/D 在 cad/ 命中数 → 加 T0.3c `cad_total_files` 实证 + AC-5 算法重写为 `25 + F841_cad_count × 2 + (cad_total_files - F841_cad_count) × 3 + 10` | §4.0 T0.3c / §5 AC-5 | ✓ |
| **L3-2** | 歧义 MED | §3.1.A-2 落地方式 1 (脚本) vs 2 (Edit) 未推荐 → 明确推荐方式 1，方式 2 为 fallback | §3.1.A-2 | ✓ |

**L1 → L2 → L3 三层 spec rev 1 cascade 通过**；累计 21 (brainstorming) + 2 (L3) = 23 项 fix 全 inline 闭合。

### 13.2 L4 对抗性审查追加发现（spec rev 1.1 inline 闭合）

> **触发**：用户在 spec rev 1 审阅环节明确要求"对抗性审查"，启动 L4 cynical + edge-case + 5-role 三合一审查；rev 1.1 一次性合并 12 项 fix。

| ID | 严重度 | 修复点 | spec 位置 | 已落？ |
|---|---|---|---|---|
| **L4-1** | HIGH | AC-5 阈值阶段 cap（best ≤30 / 一般 算法 / >50 必人审） | §5 AC-5 | ✓ |
| **L4-2** | HIGH | §3.B 决策表"删"触发加变量名白名单 `{tmp, _tmp, _unused, _, _result, _ret, debug_*, old_*, deprecated_*}` | §3.1.B | ✓ |
| **L4-3** | **BLOCKER** | AC-7 grep regex 鲁棒化（加 `(?= 条)` 后置断言）+ §7.3 强制 implementer 替换 `<X>` 占位符为整数 | §5 AC-7 + §7.3 | ✓ |
| **L4-4** | MED | §2.4 noqa 中文 ≥ 3 放宽到 ≥ 2（实测 "调试" 2 字 typical） | §2.4 | ✓ |
| **L4-5** | MED | F841 决策表行数强制 = 39 + reviewer 抽样比对 ≥ 2 行 | §3.1.B 末 | ✓ |
| **L4-6** | MED | T0.5 改 `grep -rnE` 全模板 `import \*` 防漏 | §4.0 T0.5 | ✓ |
| **L4-7** | HIGH | T0.8 加 CI workflow 枚举 + AC-9 引用 `ci_workflow_count` 不假设 3 job | §4.0 T0.8 + §5 AC-9 | ✓ |
| **L4-8** | LOW | T0.1b record `ruff --version` | §4.0 T0.1b | ✓ |
| **L4-9** | MED | §6.2 reviewer 表加"输出格式"列（结构化 JSON-like） | §6.2 | ✓ |
| **L4-10** | LOW | §10 f4 P2 retro 必含 noqa file 清单 export | §10 f4 | ✓ |
| **L4-11** | MED | §4.1 commit 1 后立验 AC-8（失败立 reset） | §4.1 末 | ✓ |
| **L4-12** | LOW | §3.B 决策表加"scope 偏好"列（src/tests/cad 不同偏好） | §3.1.B | ✓ |

---

**L1 → L2 → L3 → L4 四层 spec rev 1.1 cascade 通过**；累计 21 (brainstorming) + 2 (L3) + 12 (L4) = **35 项 fix 全 inline 闭合**。

spec rev 1.1 已 production-ready；可进 plan 阶段。

### 13.3 spec 工艺 lesson 沉淀（后续 v2.37.X 系列可复用）

| ID | lesson |
|---|---|
| **S-1** | brainstorming 阶段两轮 review (data drift / boundary+closure) 是基础，**L3 dry-run + L4 adversarial + L5 实操可执行性 必跑** —— rev 1.2 累计 47 项 fix，每层都贡献新发现 |
| **S-2** | L4 对抗性审查的 3 子层（cynical re-read / edge-case / 5-role）找 bug 类型不重叠：cynical 找凭感觉的数 + 模糊术语，edge-case 找隐式假设，5-role 找接口未定义 |
| **S-3** | AC 验证命令必带"鲁棒 regex"（如 `(?=后置断言)`），防 implementer 写法漂移导致 AC 静默 fail；模板 commit body 必含 example 实例（不留占位符）防解析错 |
| **S-4** | spec 阶段"前移审查 budget" 优于 implementation 阶段抓 bug；47 项 fix 全 inline 闭合 vs 留到 rev 2-4 重写 = 节省 PR 来回 |
| **S-5** | **L5 实操可执行性**专门攻击"环境兼容"：(a) Windows Git Bash 缺工具（`bc`/部分 GNU coreutils）—— spec 命令必检；(b) shell 假设（bash vs PowerShell）必明示；(c) 时间估算必含 reviewer 开销；(d) squash-merge 后 commit body 验证失效 —— AC 时机必精确到"squash 前/后" |
| **S-6** | spec rev 1 → 1.1 → 1.2 演进中，每轮新 attack vector 找的 fix 多达 12 项；说明 spec 复杂度（> 600 行）下单层 review 远远不够；**项目 5-layer + scout grep 工艺是 spec ≥ 500 行的标配** |

### 13.4 L5 实操可执行性审查追加发现（spec rev 1.2 inline 闭合）

> **触发**：用户在 spec rev 1.1 审阅环节再次要求"对抗性审查"，启动 L5 实操可执行性审查；rev 1.2 一次性合并 12 项 fix。

| ID | 严重度 | 修复点 | spec 位置 | 已落？ |
|---|---|---|---|---|
| **L5-1** | **BLOCKER** | AC-7 命令用 `awk '{s+=$1}'` 替代 `bc`（Windows Git Bash 无 `bc`） | §5 AC-7 | ✓ |
| **L5-2** | HIGH | 头注加 "Shell 约定 = Git Bash for Windows；PS 用户 `bash -c` wrapper" | spec 头注 | ✓ |
| **L5-3** | HIGH | 工作量改 "3-5h（含 per-file reviewer）" | spec 头注 | ✓ |
| **L5-4** | HIGH | AC-7 检测时机加 "commit 3 后 + squash-merge 之前" | §5 AC-7 | ✓ |
| **L5-5** | MED | §2.4 noqa 理由必含 trace key（"调试/临时/占位/残留/保留/测试/异步/超规则/废弃/预留/fixture/生成器/walrus"任一） | §2.4 | ✓ |
| **L5-6** | MED | AC-5 >50 加 reviewer 人审 checklist 三条 | §5 AC-5 | ✓ |
| **L5-7** | MED | tmp/ 持久化要求明示 + 跨 session 重启重跑 Task 0 | spec 头注 | ✓ |
| **L5-8** | MED | Branch name 约定 `feat/ruff-cleanup-p2-v2.37.12` 明示在头注 | spec 头注 | ✓ |
| **L5-9** | LOW | §3.2 Out of Scope "几何代码"定义阐明（cq.Workplane/extrude/rotate/translate，不含 noqa 注释行） | §3.2 表 cad/ 行 | ✓ |
| **L5-10** | LOW | §13.4 表 ✓ 标记需 L5 fresh-eyes 重 grep 校验（见 §13.5 校验回路） | §13.5 | ✓ |
| **L5-11** | LOW | §7.6 加 commit 6 (AC sanity) body 模板 | §7.6 | ✓ |
| **L5-12** | LOW | §7.8 实施顺序图 + 严格串行约束 | §7.8 | ✓ |

### 13.5 L5 fresh-eyes 重 grep 校验回路（L5-10 闭合）

为防 §13 表 ✓ 标记 self-claim 偏置，L5 完成后**主 agent 必须执行 fresh-eyes 重 grep**（与 §13 表声明位置一致性比对）：

```bash
# 对 §13/13.1/13.2/13.4 表的每项 "spec 位置" 列做反向 grep
# 若某项标 ✓ 但 grep 找不到对应 marker → spec 漂移信号，必修
grep -nE "L5-(1\|2\|3\|4\|5\|6\|7\|8\|9\|10\|11\|12) 闭合\|L5-\d+\$" docs/superpowers/specs/2026-05-17-v2-37-12-ruff-cleanup-p2-design.md \
  | awk '{print $1}' \
  | sort -u
```

**通过条件**：每个 L5-1 ~ L5-12 在 spec 内至少出现 2 处（1 处定义 + ≥1 处闭合标记）。

---

**L1 → L2 → L3 → L4 → L5 五层 spec rev 1.2 cascade 通过**；累计 21 (brainstorming) + 2 (L3) + 12 (L4) + 12 (L5) = **47 项 fix 全 inline 闭合**。

spec rev 1.2 已 production-ready；可进 plan 阶段。
