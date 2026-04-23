# A2 Tasks 16-18 — SW COM API 参数化建模 设计规格

> 版本: v1.0 — 2026-04-23
> 状态: 已审查，待实施
> 前置: A2 Tasks 1-15 已落地（`feat/a2-semi-parametric-geometry @ 773a9b4`）；`SwParametricAdapter` stub 框架就绪
> 目标: 把 8 个 `_build_*` stub 替换为真实 SW COM API 建模实现，使 SW 可用时产出真实 STEP 文件

---

## 1. 范围

| 文件 | 操作 |
|---|---|
| `adapters/parts/sw_parametric_adapter.py` | 修改（`_get_swapp` 修复 + 8 个 `_build_*` 实现） |
| `tests/test_sw_parametric_adapter.py` | 修改（移除 xfail + 补齐 7 类 smoke 测试） |

不新建文件，不动 `sw_com_session.py`、`build_part()`、`is_available()`。

---

## 2. 关键设计决策

### 2.1 COM 连接方式：直连（非 subprocess）

**决策**：`_get_swapp()` 改为 `win32com.client.Dispatch("SldWorks.Application")`，绕过 `SwComSession`。

**Rationale**：
- `SwComSession` 是 subprocess 隔离架构，无 `sldworks` 属性；现有 stub 的 `session.sldworks` 调用运行时会 `AttributeError`
- 参数化建模操作（圆 + Extrude / 矩形 + Shell）是简单可控的 COM 调用，卡死概率远低于转换任意 sldprt 文件
- adapter 内已有完整 helper 基础设施（`_new_part_doc / _close_doc / _export_step`），直连代码最少
- subprocess worker 方案工作量 3-4 倍，安全收益对本场景边际

**已知局限**：若 SW COM 卡死，主进程随之挂起。日后若出现卡死案例，按 `sw_convert_worker` 模式包 subprocess（有模板可参考）。

### 2.2 Helper 方法保持不动

`_new_part_doc / _close_doc / _export_step` 已正确实现，不改动：

```python
def _new_part_doc(self, swapp):
    # swDocPART=1, swUserPreferenceStringValue_DefaultPartTemplate=9
    template = swapp.GetUserPreferenceStringValue(9)
    return swapp.NewDocument(template, 1, 0, 0)

def _export_step(self, model, step_path):
    step_path.parent.mkdir(parents=True, exist_ok=True)
    model.SaveAs3(str(step_path), 0, 1)   # swSaveAsCurrentVersion=0, Silent=1
    return step_path.exists()
```

---

## 3. 8 类建模方法设计

所有方法遵循统一模式：

```
params 解包 → 校验必填尺寸（缺失返回 None）→ _get_swapp() → _new_part_doc()
→ 草图 + 特征操作 → _export_step() → _close_doc() → 返回 step_path / None
```

**SW API 尺寸单位为米**，所有 mm 参数均 `/1000` 换算。

| 方法 | 必填 params | 建模操作 |
|---|---|---|
| `_build_flange` | `od`, `thickness` | Top Plane 外圆(+内圆) Extrude → 螺栓孔环 Cut → 可选凸台 |
| `_build_housing` | `width`, `depth`, `height` | Top Plane 矩形 Extrude → 选顶面 Shell（抽壳） |
| `_build_bracket` | `width`, `height`, `thickness` | Front Plane 竖板 Extrude → Top Plane 底板 Extrude |
| `_build_sleeve` | `od`, `length` | Top Plane 同轴双圆 Extrude |
| `_build_spring_mechanism` | `od`, `free_length` | Top Plane 同轴双圆 Extrude（简化空心柱） |
| `_build_plate` | `width`, `depth`, `thickness` | Top Plane 矩形 Extrude → 四角孔 Cut |
| `_build_arm` | `length`, `width` | Front Plane 矩形 Extrude → 两端孔 Cut |
| `_build_cover` | `od`, `thickness` | Top Plane 圆盘(+中心孔) Extrude → 紧固孔环 Cut |

**降级行为**：任一必填参数缺失（`≤ 0`）→ 立即 `return None`，调用方回退 CadQuery 路径。

---

## 4. `_get_swapp()` 修复

**现状（Task 15 stub，运行时 AttributeError）**：
```python
def _get_swapp(self):
    from adapters.solidworks.sw_com_session import get_session
    session = get_session()
    return session.sldworks  # ← SwComSession 无此属性
```

**修复后**：
```python
def _get_swapp(self):
    import win32com.client
    return win32com.client.Dispatch("SldWorks.Application")
```

---

## 5. 测试设计

### 5.1 移除 xfail

`TestSwParametricAdapterBuildFlange` 的 `@pytest.mark.xfail` 在 Task 16 完成后移除。

### 5.2 补齐 7 类 smoke 测试

每类一个测试类，全部标 `@pytest.mark.requires_solidworks`（非 Windows CI skip）：

| 测试类 | 最小参数集 |
|---|---|
| `TestBuildHousing` | `width=60, depth=40, height=30` |
| `TestBuildBracket` | `width=50, height=40, thickness=4` |
| `TestBuildSleeve` | `od=30, length=50` |
| `TestBuildSpringMechanism` | `od=20, free_length=40` |
| `TestBuildPlate` | `width=80, depth=60, thickness=5` |
| `TestBuildArm` | `length=120, width=20, thickness=10` |
| `TestBuildCover` | `od=60, thickness=8` |

每个测试断言：`step is not None` + `Path(step).exists()` + `suffix == ".step"`。

### 5.3 非 SW 路径不受影响

`TestSwParametricAdapterAvailability` 三个现有测试继续通过（无 `requires_solidworks` marker，纯 mock）。

---

## 6. 向后兼容性

| 变更 | 影响 |
|---|---|
| `_get_swapp` 改用 `win32com.client.Dispatch` | 仅在 `_build_*` 被调用时触发；`is_available()` 不调此方法 |
| 8 个 stub 替换为真实实现 | SW 不可用时 `build_part()` 仍返回 None（`is_available()` 守卫在前） |
| 移除 xfail | Task 16 完成后才移除，CI 不受影响 |

---

## 7. 任务拆分

| Task | 内容 | 验收 |
|---|---|---|
| 16 | `_get_swapp()` 修复 + `_build_flange` 实现 | `TestBuildFlange` PASS（requires_solidworks） |
| 17 | `_build_housing / bracket / sleeve` 实现 | 3 类 smoke PASS |
| 18 | `_build_spring_mechanism / plate / arm / cover` 实现 + 全量回归 | 全部 smoke PASS；`uv run pytest --tb=short -q` 无 FAIL |
