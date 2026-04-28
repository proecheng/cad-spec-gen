# 模型库长期方案审查关闭报告 — 2026-04-28

## 结论

针对 5 条 review findings，在当前 `main`（`e64f58f`, v2.22.1）上复核代码与测试，结论为：审查意见均已由现有实现覆盖，可关闭；无需再做产品代码修改。

## Finding 关闭状态

| Finding | 原风险 | 当前证据 | 状态 |
|---|---|---|---|
| 1 | `DESIGN_REVIEW.json` 承载不了模型选择 | `cad_spec_gen.py::_flatten_review_items()` 已保留 `group_action`、`parts`、`candidates`、`geometry_quality`、`user_choice`、`batch_strategy` 等结构化字段；`tests/test_design_review_geometry_schema.py` 覆盖候选模型与质量字段。 | 关闭 |
| 2 | 用户补充不会驱动模型库 | `cad_pipeline.py::_save_supplements()` 提取 `model_choices`，`_save_model_choices()` 写 `model_choices.json` 并调用 `_apply_model_choice_to_parts_library()` 复制 STEP、前置写入 `parts_library.yaml`；`tests/test_model_choices_persistence.py` 覆盖。 | 关闭 |
| 3 | `resolve_report()` 重新执行有副作用的 `resolve()` | `parts_resolver.py::resolve_report()` 优先消费 `_decision_log`；只有 standalone fallback 使用 `mode="inspect"`，codegen 调用可传 `allow_inspect_fallback=False`；`tests/test_resolve_report.py` 覆盖。 | 关闭 |
| 4 | `ResolveResult` 没有几何质量契约 | `parts_resolver.py::ResolveResult` 已包含 `geometry_source`、`geometry_quality`、`validated`、`hash`、`path_kind`、`requires_model_review`，并可转换为 `GeometryDecision`；`tests/test_parts_resolver.py` 覆盖 A-E 默认质量。 | 关闭 |
| 5 | SW Toolbox resolve 在只读阶段导出 STEP | `SwToolboxAdapter.resolve()` 已支持 `mode`；缓存未命中且 `mode in {"inspect", "probe"}` 时返回 miss 并跳过 COM export；`tests/test_sw_toolbox_adapter.py` 覆盖。 | 关闭 |

## 验证命令

```powershell
.venv\Scripts\python.exe -m pytest tests\test_design_review_geometry_schema.py tests\test_model_choices_persistence.py tests\test_parts_resolver.py tests\test_resolve_report.py tests\test_sw_toolbox_adapter.py -q
```

结果：`105 passed, 7 warnings`。warnings 来自 `ezdxf/pyparsing` deprecation，不影响本审查项。

## 补充端到端验收

额外运行一次临时脚本模拟真实数据流：

1. 创建临时 `DESIGN_REVIEW.json` 所在目录。
2. 传入结构化 supplement：
   - `part_no = P-001`
   - `name_cn = 用户选择电机`
   - `user_choice.step_file = <临时 STEP>`
3. 调用 `cad_pipeline._save_supplements()`。
4. 验证：
   - 写出 `model_choices.json`
   - 写出 `user_supplements.json`
   - STEP 被复制到 `std_parts/user_provided/P-001_用户选择电机.step`
   - `parts_library.yaml` 前置新增 `step_pool` mapping
   - `PartsResolver + StepPoolAdapter` 对 `P-001` 命中 `kind="step_import"`

脚本输出：

```text
model_choice_e2e=PASS
supplements=user_supplements.json
geometry_quality=A
step_path=std_parts/user_provided/P-001_用户选择电机.step
```

## 剩余风险

- 临时 E2E 使用轻量 STEP 头文件，只验证路径、映射与 resolver 路由，不验证真实 CAD STEP 几何可导入性。
- 真 SolidWorks Toolbox COM 导出仍需依赖 self-hosted runner 或本机 SolidWorks 环境；本报告只关闭“只读阶段不得导出”的代码路径审查。
