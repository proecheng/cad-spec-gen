# v2.10.0 — data/ mirror 根治 + legacy P2 regex 清除

**Release date:** 2026-04-12
**Theme:** 结构性清理。mirror 文件从 git tracking 移除，改由 `dev_sync.py` + pre-commit hook 同步（根治 v2.9.2 的 drift 问题）；移除 v2.9.0 遗留的 `_legacy_p2_regex_block` 和 `CAD_SPEC_WALKER_ENABLED` feature flag。

---

## TL;DR

- **56 个 mirror 文件**从 git tracking 移除（`git rm --cached`），改由 `scripts/dev_sync.py` 按需生成
- **`_legacy_p2_regex_block`** 和 **`CAD_SPEC_WALKER_ENABLED`** 正式移除——section-header walker 是唯一的 P2 提取路径
- **pre-commit hook** 自动同步，开发者无需手动 `cp`
- **488 passed / 3 skipped** 全套测试零回归

---

## 起因

v2.9.2 用 `tests/test_data_dir_sync.py` 的 47 个参数化 case 止住了 data/ mirror drift，但根因未解：`hatch_build.py` 在 wheel build 时把 root 源文件复制到 `src/cad_spec_gen/data/`，两份拷贝都 git-tracked，每次 build 后 `git status` 冒假 `M`。

同时，v2.9.0 引入的 section-header walker 已经过三个版本（v2.9.0-v2.9.2）的真实文档验证，保留在 `_legacy_p2_regex_block` 函数中的旧 regex P2 提取和 `CAD_SPEC_WALKER_ENABLED=0` 回退机制不再有存在价值。

---

## 工作块 1：data/ mirror 根治

### 方案

`.gitignore` 掉 hatch build 复制的 mirror 文件，改由 `scripts/dev_sync.py` + pre-commit hook 在开发环境同步。

### 涉及的 data/ 子目录

| 子目录/文件 | 来源 | 处理 |
|-------------|------|------|
| `python_tools/` | hatch 从 root 复制 ~20 个 .py | .gitignore + git rm --cached |
| `codegen/` | hatch 从 root `codegen/` 整目录复制 | .gitignore + git rm --cached |
| `templates/` | hatch 从 root `templates/` 整目录复制 | .gitignore + git rm --cached |
| `config/` | hatch 从 root `config/` 整目录复制 | .gitignore + git rm --cached |
| `commands/zh/` | hatch 从 `.claude/commands/` 复制 | .gitignore + git rm --cached |
| `knowledge/skill_cad_help_zh.md` | hatch 从 root 复制 | .gitignore + git rm --cached |
| `knowledge/skill_mech_design_zh.md` | hatch 从 root 复制 | .gitignore + git rm --cached |
| `system_prompt.md` | hatch 从 root 复制 | .gitignore + git rm --cached |
| `parts_library.default.yaml` | hatch 从 root 复制 | .gitignore + git rm --cached |
| `commands/en/` | 原创手写英文版 | 保留 git-tracked |
| `knowledge/*_en.md` | 原创手写英文版 | 保留 git-tracked |
| `skill.json` | 版本元数据，非 mirror | 保留 git-tracked |

### `scripts/dev_sync.py`

用 `ast.parse()` 从 `hatch_build.py` 提取 `_PIPELINE_TOOLS`、`COPY_DIRS`、`TOP_LEVEL_FILES` 常量列表（不 import `hatch_build`，避免 `hatchling` 运行时依赖），MD5 比较后增量同步。覆盖 hatch_build 的全部 6 个同步分类：

1. `python_tools/` — 平铺 .py 文件
2. `COPY_DIRS` — codegen/config/templates 递归复制 + 陈旧文件清理
3. `commands/zh/` — 从 `.claude/commands/*.md`
4. `knowledge/*_zh.md` — 两个知识文件
5. `system_prompt.md`
6. `TOP_LEVEL_FILES` — parts_library.default.yaml 等

提供 `sync(root: Path) -> list[Path]` API 和 CLI 入口（有变更 exit 1，无变更 exit 0）。

### `.pre-commit-config.yaml`

```yaml
repos:
  - repo: local
    hooks:
      - id: dev-sync
        name: Sync root sources to data/
        entry: python scripts/dev_sync.py
        language: python
        always_run: true
        pass_filenames: false
```

### `tests/test_data_dir_sync.py` 重写

从 v2.9.2 的 git drift 检测重写为 dev_sync.py 正确性验证：
- session-scope fixture 跑一次 `sync()`，59 个参数化 case 共享结果
- 新增 `commands_zh`、`knowledge_zh`、`system_prompt` 三个分类
- 保留 `test_sync_pair_count_is_nontrivial`（健康检查）和 `test_python_tools_has_no_stray_files`（反向哨兵）

---

## 工作块 2：legacy P2 清除

### `cad_spec_extractors.py` 变更

**删除**:
- `_WALKER_ENABLED = os.environ.get("CAD_SPEC_WALKER_ENABLED", "1") == "1"` 及注释
- `import os`（仅被 `_WALKER_ENABLED` 使用）
- `_legacy_p2_regex_block()` 函数（~50 行，含 box 和 cylinder regex）
- `elif not _WALKER_ENABLED` 和 `else` 两个 fallback 分支

**简化后的 P2 分支**:
```python
if _WALKER_AVAILABLE and bom_data:
    # walker 路径（不变）
else:
    # walker 不可用 → 跳过 P2，log.warning
```

**行为变化**:
- `CAD_SPEC_WALKER_ENABLED=0` 环境变量不再被读取
- walker import 失败时 P2 直接跳过，不 fallback 到 regex

---

## CI 影响

`.github/workflows/tests.yml` 中两个 job（`test` 和 `regression`）的 pytest 步骤前各加 `python scripts/dev_sync.py` 填充 data/ mirrors。退出码 0（无变更）和 1（有变更）均为正常，exit 2+（异常）会使 CI 失败。

---

## 升级迁移（v2.9.x → v2.10.0）

- `CAD_SPEC_WALKER_ENABLED=0` 环境变量不再生效。如果之前设置过，可以安全移除。
- `git pull` 后 mirror 文件仍在磁盘上但被 `.gitignore` 忽略，`git status` 干净。
- 首次 clone 的新开发者需要 `pip install pre-commit && pre-commit install`，或手动跑 `python scripts/dev_sync.py`。

---

## Validation

- **488 passed / 3 skipped** 全套测试（零回归）
- **59 sync case 全通过** `tests/test_data_dir_sync.py`（从 v2.9.2 的 51 扩展到 59）
- `git status` 在 commit 后干净——无假 `M` 标记

---

## Files

- New: `scripts/dev_sync.py`, `.pre-commit-config.yaml`, `RELEASE_v2.10.0.md`
- Modified: `cad_spec_extractors.py`, `tests/test_data_dir_sync.py`, `tests/test_envelope_prose_regex.py`, `.github/workflows/tests.yml`, `.gitignore`, `pyproject.toml`, `CHANGELOG.md`, `README.md`, `skill.json`, `docs/pipeline_architecture.md`
- Version metadata: `pyproject.toml`, `src/cad_spec_gen/__init__.py`, `skill.json`, `src/cad_spec_gen/data/skill.json`, `.cad_skill_version.json`
- Removed from tracking (git rm --cached): 56 files under `src/cad_spec_gen/data/`
