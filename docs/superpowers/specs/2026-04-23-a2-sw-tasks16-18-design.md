# A2 Tasks 16-18 — SW COM API 参数化建模 设计规格

> 版本: v1.1 — 2026-04-23（自审 + 代码一致性审查修订：C1/C2 CRITICAL 修复，W1-W3 建模方案修订，I1/I2 补全）
> 状态: 已审查，待实施
> 前置: A2 Tasks 1-15 已落地（`feat/a2-semi-parametric-geometry @ 773a9b4`）；`SwParametricAdapter` stub 框架就绪
> 目标: 把 8 个 `_build_*` stub 替换为真实 SW COM API 建模实现，使 SW 可用时产出真实 STEP 文件

---

## 1. 范围

| 文件 | 操作 |
|---|---|
| `adapters/parts/sw_parametric_adapter.py` | 修改（`_get_swapp` 修复 + `_close_doc` 签名修正 + 8 个 `_build_*` 实现） |
| `codegen/gen_parts.py` | 修改（`_extract_params("cover", ...)` 补加 `n_hole`）|
| `tests/test_sw_parametric_adapter.py` | 修改（移除 xfail + 补齐 7 类 smoke 测试） |

不新建文件，不动 `sw_com_session.py`、`build_part()`、`is_available()`。

---

## 2. 关键设计决策

### 2.1 COM 连接方式：直连（非 subprocess）

**决策**：`_get_swapp()` 改为 `win32com.client.Dispatch("SldWorks.Application")`，绕过 `SwComSession`。

**Rationale**：
- `SwComSession` 是 subprocess 隔离架构，无 `sldworks` 属性；现有 stub 的 `session.sldworks` 运行时 `AttributeError`
- 参数化建模（圆 + Extrude / L-profile + Extrude）是简单可控的 COM 调用，卡死概率远低于转换任意 sldprt
- adapter 内已有完整 helper 基础设施，直连代码最少
- subprocess worker 方案工作量 3-4 倍，安全收益对本场景边际

**已知局限**：若 SW COM 卡死，主进程随之挂起。日后若出现卡死案例，按 `sw_convert_worker` 模式包 subprocess。

### 2.2 单位约定（显式声明，防 C1 类 bug 复发）

> **调用方（`_extract_params`）输出 mm；`_build_*` 内部负责 `/1000` 换算为 SW API 所需的米。**

换算模式（全部 `_build_*` 一致）：
```python
# 正确：先取 mm 值，统一换算
od_mm = float(params.get("od") or 0)
od = od_mm / 1000  # → 米

# ⚠ 错误（C1 原型）：fallback 在已换算后的值上再 /1000
wall = float(params.get("wall_t") or max(w, d) * 0.12) / 1000  # w,d 已是米 → 结果 ~0.07mm
```

当某参数有 mm 域 fallback 时，正确写法：
```python
wall_t_mm = float(params.get("wall_t") or 0) or (max(w_mm, d_mm) * 0.12)
wall = wall_t_mm / 1000
```

### 2.3 `_close_doc` 签名修正（C2 文档泄漏修复）

**问题**：新建未保存文档 `GetPathName()` 返回 `""`；`swApp.CloseDoc("")` 按路径查找失败 → 静默无操作 → 文档永久驻留 SW → 积累后 `NewDocument` 返回 None。

**修复**：`_close_doc` 改为接收 model 对象，通过 `GetTitle()` 获取窗口标题关闭：

```python
def _close_doc(self, swapp, model) -> None:
    """通过 GetTitle() 关闭新建文档（GetPathName() 对未保存文档返回空）。"""
    try:
        title = model.GetTitle() if model and hasattr(model, "GetTitle") else ""
        if title:
            swapp.CloseDoc(title)
    except Exception:
        pass
```

所有 `_build_*` 的 `finally` 统一改为：
```python
finally:
    self._close_doc(swapp, model)
```

### 2.4 `_build_housing` 内腔用 Cut 替代 Shell（W1 修复）

**问题**：`SelectByID2("", "FACE", 0, 0, h, ...)` 按坐标 raycast 选面，精度偏差 1e-7m 可选中侧面 → Shell 操作选错面 → 产出实心块。

**替代方案**：用内腔 Box Cut 代替 Shell，与 CadQuery `make_housing` 逻辑对齐：

```
外壳 Box Extrude → Cut 内腔 Box（偏移 wall_t）
```

```python
# 外壳
skMgr.InsertSketch(True)  # on Top Plane
skMgr.CreateCenterRectangle2(0, 0, 0, w/2, d/2, 0)
skMgr.InsertSketch(True)
ftMgr.FeatureExtrusion3(True, ..., h, ...)  # 外壳高度 h

# 内腔 Cut（从顶面向下 h - wall_t）
skMgr.InsertSketch(True)  # on Top Plane（at Z=0）
skMgr.CreateCenterRectangle2(0, 0, 0, (w-2*wall)/2, (d-2*wall)/2, 0)
skMgr.InsertSketch(True)
ftMgr.FeatureExtrusion3(False, ..., h - wall, ...)  # Cut，深度 = h - wall_t
```

无坐标依赖，几何稳定可靠。

### 2.5 `_build_bracket` 单草图 L-Profile（W2 修复）

**问题**：竖板（Front Plane）+ 底板（Top Plane）两段独立 Extrude，若不相交则 SW 产出多实体 STEP，装配位置偏移。

**替代方案**：在 Front Plane 画 L 形截面，一次 Extrude 沿宽度方向（Mid-Plane 对称），生成单实体 L-bracket：

```
Front Plane 画 L 截面（竖边 h，横边 w*0.8，厚 t）→ Extrude 深度 = width（Mid-Plane）
```

```python
# L 截面：左下角原点，竖边向上 h，横边向右 base_d
# 顶点序列：(0,0) → (t,0) → (t,base_d) → (base_d,base_d) → (base_d,t) → (0,t) → 闭合
# base_d = width * 0.8
skMgr.CreateLine2(0, 0, 0, t, 0, 0)
skMgr.CreateLine2(t, 0, 0, t, base_d, 0)
...
ftMgr.FeatureExtrusion3(True, False, True, 0, 0, width/2, 0, ...)  # Mid-Plane 双向
```

保证单体，STEP 导出无多 Solid 问题。

### 2.6 `_build_spring_mechanism` 对齐 CadQuery 质量（W3 修复）

**问题**：plan 代码仅一个空心圆柱（4 个面），而 CadQuery 版有法兰 + 分节凸缘（≥30 面）。SW 路径本应是更高质量路径，不应比 CQ 版更差。

**修订**：SW 版同样实现空心柱 + 两端法兰盘 + 均匀分布的外环凸缘（n 个 Cut 或 Extrude 切槽模拟弹簧圈间距）：

```
主体圆柱 Extrude（od, free_length）
→ 内孔 Cut（id）
→ 底端法兰圆盘 Extrude（flange_od = od*1.25, flange_h）
→ 顶端法兰圆盘 Extrude
→ coil_n 个分段外环 Extrude（seg_od = od + wire_d*0.8, seg_h*0.5）
```

面数 ≥ 30，与 CadQuery 版视觉对等。

---

## 3. 参数契约（`_extract_params` ↔ `_build_*` 对照）

> 所有参数由 `gen_parts._extract_params(tpl_type, part_meta, envelope)` 提供，单位 **mm**。

| 模板 | params 键 | 必填 | 备注 |
|---|---|---|---|
| `flange` | `od`, `id`, `thickness`, `bolt_pcd`, `bolt_count`, `boss_h` | `od`, `thickness` | `bolt_pcd` 缺失时按 `od*0.75` 推导 |
| `housing` | `width`, `depth`, `height`, `wall_t` | `width`, `depth`, `height` | `wall_t` 缺失时 = `max(w,d)*0.12`（mm 域计算，见 §2.2）|
| `bracket` | `width`, `height`, `thickness` | 全部 | — |
| `sleeve` | `od`, `id`, `length` | `od`, `length` | `id` 缺失时 = `od*0.5` |
| `spring_mechanism` | `od`, `id`, `free_length`, `wire_d`, `coil_n` | `od`, `free_length` | SW 版使用 `coil_n` 控制凸缘段数（见 §2.6）|
| `plate` | `width`, `depth`, `thickness`, `n_hole` | `width`, `depth`, `thickness` | — |
| `arm` | `length`, `width`, `thickness`, `end_hole_d` | `length`, `width`, `thickness` | — |
| `cover` | `od`, `thickness`, `id`, `n_hole` | `od`, `thickness` | **`n_hole` 需补入 `_extract_params`（I1 修复）** |

### I1 修复：`_extract_params("cover", ...)` 补加 `n_hole`

`gen_parts.py` 的 `_extract_params` 对 cover 分支：

```python
if tpl_type == "cover":
    return {
        "od":        dim_map.get("COVER_OD") or max(env_w, env_d),
        "thickness": dim_map.get("COVER_T") or env_h,
        "id":        dim_map.get("COVER_ID") or None,
        "n_hole":    int(dim_map.get("COVER_BOLT_N", 4)),  # ★ 补加
    }
```

---

## 4. 各方法建模流程

所有方法统一结构：

```
params 解包（mm）→ /1000 换算（m）→ 必填校验 → _get_swapp()
→ _new_part_doc() → 草图+特征 → _export_step() → finally: _close_doc(swapp, model)
→ 返回 step_path / None
```

| 方法 | 必填 | 建模操作（修订后）|
|---|---|---|
| `_build_flange` | `od`, `thickness` | Top Plane 双圆 Extrude → 螺栓孔环逐孔 Cut → 可选凸台 Extrude |
| `_build_housing` | `width`, `depth`, `height` | Top Plane 外壳 Box Extrude → **内腔 Box Cut**（替代 Shell，见 §2.4）|
| `_build_bracket` | `width`, `height`, `thickness` | **Front Plane L-Profile 单次 Extrude**（Mid-Plane，见 §2.5）|
| `_build_sleeve` | `od`, `length` | Top Plane 同轴双圆 Extrude |
| `_build_spring_mechanism` | `od`, `free_length` | 主体圆柱 + 内孔 Cut + 两端法兰 + coil_n 段外环（见 §2.6）|
| `_build_plate` | `width`, `depth`, `thickness` | Top Plane 矩形 Extrude → 四角孔逐孔 Cut |
| `_build_arm` | `length`, `width`, `thickness` | Front Plane 矩形 Extrude → 两端孔 Cut（孔轴沿厚度方向）|
| `_build_cover` | `od`, `thickness` | Top Plane 圆盘 Extrude → 可选中心孔 Cut → 紧固孔环 Cut |

**降级行为**：必填参数缺失（≤ 0）→ 立即 `return None`，调用方回退 CadQuery 路径。

---

## 5. `_get_swapp()` 修复

**修复前（Task 15 stub，运行时 AttributeError）**：
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

## 6. 测试设计

### 6.1 移除 xfail

`TestSwParametricAdapterBuildFlange` 的 `@pytest.mark.xfail` 在 Task 16 完成后移除。

### 6.2 补齐 7 类 smoke 测试

每类一个测试类，全部标 `@pytest.mark.requires_solidworks`：

| 测试类 | 最小参数集（mm）| 验收条件 |
|---|---|---|
| `TestBuildHousing` | `width=60, depth=40, height=30, wall_t=5` | STEP 存在 + > 1024 bytes |
| `TestBuildBracket` | `width=50, height=40, thickness=4` | 同上 |
| `TestBuildSleeve` | `od=30, id=15, length=50` | 同上 |
| `TestBuildSpringMechanism` | `od=20, free_length=40, coil_n=6` | 同上 |
| `TestBuildPlate` | `width=80, depth=60, thickness=5, n_hole=4` | 同上 |
| `TestBuildArm` | `length=120, width=20, thickness=10` | 同上 |
| `TestBuildCover` | `od=60, thickness=8, n_hole=4` | 同上 |

每个测试断言：`step is not None` + `Path(step).exists()` + `suffix == ".step"` + `size > 1024`。

### 6.3 非 SW 路径不受影响

`TestSwParametricAdapterAvailability` 三个现有测试继续通过（纯 mock，无 `requires_solidworks` marker）。

### 6.4 `_close_doc` mock 测试（C2 回归守护）

新增一个非 SW 单测（无 marker），验证 `_close_doc` 调用 `model.GetTitle()` 而非 `model.GetPathName()`：

```python
def test_close_doc_uses_get_title(monkeypatch):
    adapter = SwParametricAdapter()
    mock_swapp = MagicMock()
    mock_model = MagicMock()
    mock_model.GetTitle.return_value = "Part1"
    adapter._close_doc(mock_swapp, mock_model)
    mock_swapp.CloseDoc.assert_called_once_with("Part1")
    mock_model.GetPathName.assert_not_called()  # 不再依赖 GetPathName
```

---

## 7. 向后兼容性

| 变更 | 影响 |
|---|---|
| `_get_swapp` 改用 `win32com.client.Dispatch` | 仅在 `_build_*` 被调用时触发；`is_available()` 不调此方法 |
| `_close_doc` 签名改为接收 model 对象 | 仅在 `_build_*` 内部调用，无外部 caller |
| 8 个 stub 替换为真实实现 | SW 不可用时 `build_part()` 仍返回 None（`is_available()` 守卫在前）|
| 移除 xfail | Task 16 完成后才移除，CI 不受影响 |
| `_extract_params("cover")` 补 `n_hole` | 新增键；旧 SW stub 返回 None 不消费，无破坏 |

---

## 8. 任务拆分

| Task | 内容 | 验收 |
|---|---|---|
| 16 | `_get_swapp()` 修复 + `_close_doc` 签名修正 + `_build_flange` 实现 + C2 mock 测试 | `TestBuildFlange` PASS；C2 mock 测试 PASS |
| 17 | `_build_housing`（Cut 内腔版）+ `_build_bracket`（L-Profile 版）+ `_build_sleeve` + `_extract_params("cover")` 补 `n_hole` | 3 类 smoke PASS；全量回归无 FAIL |
| 18 | `_build_spring_mechanism`（法兰+凸缘版）+ `_build_plate` + `_build_arm` + `_build_cover` + 全量回归 | 全部 8 类 smoke PASS；`uv run pytest --tb=short -q` 无 FAIL |

---

## 附录：v1.0 → v1.1 修订日志

| # | 严重度 | 问题 | 修订 |
|---|---|---|---|
| C1 | CRITICAL | `_build_housing` wall_t fallback 在米域再 /1000 → ~0.07mm | §2.2 明确单位约定 + §4 表格修正；正确写法见 §2.2 |
| C2 | CRITICAL | `_close_doc("")` 对新建文档无效 → SW 文档泄漏 | §2.3 修改签名为接收 model 对象；§6.4 补 mock 测试 |
| W1 | WARNING | `SelectByID2` 坐标选面不可靠 → Shell 选错面 | §2.4 改为 Box Cut 内腔方案 |
| W2 | WARNING | 双 Extrude 可能多体 → STEP 含 2 个 Solid | §2.5 改为 L-Profile 单草图单次 Extrude |
| W3 | WARNING | SW spring 仅空心柱，比 CQ 版更简陋 | §2.6 补两端法兰 + coil_n 段外环 |
| I1 | INFO | `_extract_params("cover")` 缺 `n_hole` | §3 补加；§1 范围增加 `gen_parts.py` 修改项 |
| I2 | INFO | spec 缺单位约定说明 | §2.2 新增显式约定段 |
