# Phase 4 Render Visual Regression 执行计划

## 背景

目标是把“新渲染比旧渲染少视角、少元件、混入旧 run 或证据漂移”变成通用门禁，而不是围绕某个设备或某个零件做临时收紧。

## 范围

- 新增 `render-visual-check` CLI。
- 新增 `tools/render_visual_regression.py`。
- 写 `RENDER_VISUAL_REGRESSION.json` 到当前 active run 目录。
- 只通过 `ARTIFACT_INDEX.json.active_run_id` 解析当前产物，不扫描 render 目录猜最新图片。

## 契约

输入：
- `PRODUCT_GRAPH.json`
- `ASSEMBLY_SIGNATURE.json`
- `render_manifest.json`
- 可选 accepted baseline 的 `render_manifest.json` / `ASSEMBLY_SIGNATURE.json`

检查：
- subsystem / run_id / path_context_hash 一致。
- product/model/assembly/render hash 链一致。
- `render_dir` 必须是 `cad/output/renders/<subsystem>/<run_id>`。
- render file 必须存在、在 render_dir 内、sha256 匹配。
- manifest 视角不能重复，不能缺 view。
- 产品图必需实例必须进入运行时装配签名。
- 有 accepted baseline 时，当前视角集合和装配实例不能少于 baseline。
- 如 manifest 携带 `visible_instance_ids` 等逐视角实例证据，则比较当前与 baseline 的可见实例证据。
- 如缺少逐视角实例证据，只给 warning，不宣称图片内元件身份已被证明。

输出：
- `status`: `pass` / `warning` / `blocked`
- `blocking_reasons`
- `warnings`
- `counts`
- `current`
- `baseline`
- `artifacts`
- `artifact_hashes`

## 完成标准

- 新增测试先红后绿。
- `render-visual-check --help` 说明 active-run、accepted baseline、per-view instance evidence 和 no-scan 规则。
- `skill.json`、`.claude/commands/cad-help.md`、`skill_cad_help.md`、`docs/cad-help-guide-zh.md` 同步。
- 安装版镜像由 `scripts/dev_sync.py` 同步。
- `tests/test_render_visual_regression.py`、用户流程和打包同步测试通过。
