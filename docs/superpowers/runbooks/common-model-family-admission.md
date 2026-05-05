# 通用模型族准入 Runbook

本 runbook 用于把新的常用外购件/标准件模型族加入默认模型库。目标不是把某个设备调到看起来正确，而是让不同用户、不同产品、不同 BOM 都能用同一套规则稳定走向照片级 3D 输出。

机读准入清单在 `docs/superpowers/specs/common_model_family_admission.json`。新增或调整默认模型族时，必须同步更新该 manifest，并运行 `tests/test_common_model_family_admission.py`。

## 核心门禁

| Gate | 要求 | 防止的问题 |
| --- | --- | --- |
| `explicit_category_and_family_intent` | 默认库路由必须同时满足明确 category 和明确 family intent。 | 裸型号、尺寸或行业词把其他产品的 BOM 行抢走。 |
| `broad_token_negative_examples` | 每个新增族必须给出宽泛词负例，例如普通支架、标签、手册、包装袋、普通板件。 | 临时收紧只对当前设备有效，换产品后误分类。 |
| `nonterminal_default_route` | `parts_library.default.yaml` 中应有显式默认规则，且不能依赖 `{any: true}` 终端 fallback。 | 表面“能出图”，实际只是无语义盒子或粗略 fallback。 |
| `specific_template_precedence` | 成熟专用模板、真实 STEP、标准件 catalog 必须优先于新增宽泛族。 | 新族吞掉更正确的老模型。 |
| `category_scoped_dimensions` | 尺寸查表中会跨族复用的 token 必须受 category 限制。 | material 中的别族描述覆盖 name 中的真实型号尺寸。 |
| `geometry_within_real_dims` | 参数化模板生成的 bbox 不得超过 `real_dims`。 | 装配、渲染、Photo3D gate 的包络证据被污染。 |
| `b_grade_reusable_metadata` | 可复用 B 级模板必须标记 `PARAMETRIC_TEMPLATE`、`B`、`requires_model_review=False`、`template_scope=reusable_part_family`、`source_tag=parametric_template:<template>`。 | 报告无法区分“可信可复用模板”和“仍需审查 fallback”。 |
| `real_model_sources_before_default_templates` | 项目/用户 STEP、vendor cache、SolidWorks/Toolbox、bd_warehouse、PartCAD 等真实或 catalog 模型优先。 | 默认 B 级模板覆盖 A 级真实模型来源。 |
| `no_project_exact_part_no_in_default_family_routes` | skill-wide 默认库不得用某个项目的精确 `part_no` 做通用族路由；vendor/demo stand-in 必须在注释和测试中说明。 | 把单项目修补混进全局默认行为。 |

## 新模型族准入步骤

1. 从真实跨产品 BOM 中确认高频族。不要因为单个设备缺了某个零件就直接加默认族。
2. 定义正例：至少一个中文名、一个 material/model 字段、目标 category、目标 template、`real_dims`。
3. 定义负例：列出共享宽泛 token 但不应命中的行，覆盖 name 和 material 两个字段。
4. 定义默认路由：在真实 STEP/vendor/SolidWorks/catalog 规则之后、终端 fallback 之前加入显式规则。
5. 定义优先级保护：如果已有成熟模板或 catalog 路由能更准确表示该零件，新增族不得抢先。
6. 定义尺寸策略：新增尺寸 key 若可能和其他 family 共享 token，加入 category-scoped 保护。
7. 定义几何包络测试：执行模板 `body_code`，确认 CadQuery bbox 不超过 `real_dims`。
8. 更新 `docs/superpowers/specs/common_model_family_admission.json`，把正例、负例、路由、优先级、尺寸、包络样本都写进去。
9. 运行：

```powershell
D:\Work\cad-spec-gen\.venv\Scripts\python.exe -m pytest tests\test_common_model_family_admission.py -q
D:\Work\cad-spec-gen\.venv\Scripts\python.exe -m pytest tests\test_common_model_library_batch_4.py tests\test_common_model_library_batch_3.py tests\test_common_model_library_batch_2.py tests\test_common_model_library_expansion.py tests\test_parts_library_standard_categories.py tests\test_jinja_generators_new.py -q
D:\Work\cad-spec-gen\.venv\Scripts\python.exe scripts\dev_sync.py --check
git diff --check
```

## 禁止模式

- 只按当前项目的 `part_no`、装配位置或设备名匹配默认模型族。
- 用裸 `M12`、`DIN`、`2020`、`PC6`、`支架`、`模块`、`阀`、`按钮`、`真空`、`型材` 这类宽泛 token 直接决定模板。
- 为了让某一张渲染图好看，缩小负例范围或强行把未知件塞进 B 级模板。
- 让 AI 增强环节补救 CAD 阶段缺件、错件、错尺寸或错路由；照片级只发生在可信 CAD 证据之后。

## 给大模型的执行边界

当用户只说“按建议执行”时，大模型应按 manifest gate 做机械检查，而不是临时猜测：

- 先确认新增族是否跨产品复用。
- 先写红测或 manifest case，再改代码/库。
- 修改默认库后同时检查分类、路由、尺寸、模板 metadata、bbox 和负例。
- 每轮结束更新 `docs/PROGRESS.md` 与 `docs/superpowers/README.md`。
