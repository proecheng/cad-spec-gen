# A2 Tasks 16-18 — SW COM API 参数化建模 设计规格

> 版本: v1.2 — 2026-04-23（实机 SW COM API 验证修订：C3-C9 CRITICAL 修复，覆盖方法名/平面名/Cut API/模板路径/属性括号/坐标系/VARIANT）
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

### 2.3 `_close_doc` 签名修正（C2 文档泄漏修复 + C8 属性括号修复）

**问题**：新建未保存文档 `GetPathName` 返回 `""`；`swApp.CloseDoc("")` 按路径查找失败 → 静默无操作 → 文档永久驻留 SW → 积累后 `NewDocument` 返回 None。

**修复**：`_close_doc` 改为接收 model 对象，通过 `model.GetTitle`（**COM 属性，不加括号**，见 §2.11）获取窗口标题关闭：

```python
def _close_doc(self, swapp, model) -> None:
    """通过 GetTitle 关闭新建文档（GetPathName 对未保存文档返回空）。"""
    try:
        title = model.GetTitle  # COM BSTR property，不是方法调用
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

### 2.4 `_build_housing` 内腔用 Cut 替代 Shell（W1 修复 + C3/C6/C9 修正）

**问题**：`SelectByID2` 按坐标 raycast 选面，精度偏差可选错面 → Shell 操作失败或选错面。

**替代方案**：用内腔 Box Cut 代替 Shell，与 CadQuery `make_housing` 逻辑对齐：

```
外壳 Box Extrude → Cut 内腔 Box（偏移 wall_t）
```

**坐标系注意**（见 §2.12）：`上视基准面` 是 XZ 平面，Extrude 方向为 +Y；外壳顶面 Y 坐标 = h（而非 Z = h）。内腔 Cut 从 Y=h 顶面向下 `h - wall`，Cut 深度为正值。

```python
# 外壳 Extrude（Top Plane = 上视基准面，XZ 平面，向 +Y 挤出）
model.Extension.SelectByID2("上视基准面", "PLANE", 0, 0, 0, False, 0, VARIANT_NULL, 0)
skMgr.InsertSketch(True)
skMgr.CreateCenterRectangle(0, 0, 0, w/2, d/2, 0)  # 无 "2" 后缀，见 §2.8
skMgr.InsertSketch(True)
ftMgr.FeatureExtrusion3(True, False, False, 0, 0, h, 0, False, False, False, False, 0, 0, False, False, False, False, True)

# 内腔 Cut（从顶面向下，使用 FeatureExtrusion3 第 3 参 True = cut，见 §2.9）
model.Extension.SelectByID2("上视基准面", "PLANE", 0, 0, 0, False, 0, VARIANT_NULL, 0)
skMgr.InsertSketch(True)
skMgr.CreateCenterRectangle(0, 0, 0, (w-2*wall)/2, (d-2*wall)/2, 0)
skMgr.InsertSketch(True)
ftMgr.FeatureExtrusion3(True, False, True, 0, 0, h - wall, 0, False, False, False, False, 0, 0, False, False, False, False, True)
```

`VARIANT_NULL = win32com.client.VARIANT(pythoncom.VT_DISPATCH, None)`（见 §2.13）。无坐标依赖，几何稳定可靠。

### 2.5 `_build_bracket` 单草图 L-Profile（W2 修复 + C3/C5 修正）

**问题**：竖板（Front Plane）+ 底板（Top Plane）两段独立 Extrude，若不相交则 SW 产出多实体 STEP，装配位置偏移。

**替代方案**：在 `前视基准面` 画 L 形截面，一次 Extrude 沿宽度方向（Mid-Plane 对称），生成单实体 L-bracket：

```
前视基准面 画 L 截面（竖边 h，横边 base_d=width*0.8，厚 t）→ Extrude depth=width（Mid-Plane）
```

```python
# 选 前视基准面（Front Plane = XY 平面，见 §2.7）
model.Extension.SelectByID2("前视基准面", "PLANE", 0, 0, 0, False, 0, VARIANT_NULL, 0)
skMgr.InsertSketch(True)

# L 截面顶点（逆时针，XY 坐标）：
# base_d = width * 0.8
# (0,0) → (t,0) → (t,base_d) → (base_d,base_d) → (base_d,t) → (0,t) → 闭合
skMgr.CreateLine(0, 0, 0, t, 0, 0)         # 底边横向（无 "2" 后缀，见 §2.8）
skMgr.CreateLine(t, 0, 0, t, base_d, 0)    # 内竖边
skMgr.CreateLine(t, base_d, 0, base_d, base_d, 0)  # 上横边
skMgr.CreateLine(base_d, base_d, 0, base_d, t, 0)  # 外竖边上段
skMgr.CreateLine(base_d, t, 0, 0, t, 0)    # 右横边
skMgr.CreateLine(0, t, 0, 0, 0, 0)         # 左侧闭合

skMgr.InsertSketch(True)
# Mid-Plane 双向 Extrude，每侧 width/2
ftMgr.FeatureExtrusion3(True, False, True, 0, 0, width/2, 0, False, False, False, False, 0, 0, False, False, False, False, True)
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

### 2.7 SW 2024 中文平面名（C5 — 实机验证）

英文平面名在中文版 SW 2024 返回 `False`，**必须使用以下中文名**：

| 平面 | 中文名 | 对应坐标平面 |
|---|---|---|
| Top Plane | `上视基准面` | XZ 平面（Y 轴法向） |
| Front Plane | `前视基准面` | XY 平面（Z 轴法向） |
| Right Plane | `右视基准面` | YZ 平面（X 轴法向） |

所有 `SelectByID2` 选平面时均使用上述中文名称，否则 `SelectByID2` 返回 `False`，后续草图操作在错误上下文执行。

### 2.8 Sketch API 方法名：无 "2" 后缀（C3 — 实机验证）

SW 2024 草图管理器 (`ISketchManager`) 的以下方法**不带 "2" 后缀**：

| 错误（原 plan 代码）| 正确 |
|---|---|
| `CreateCircleByRadius2(x, y, z, r)` | `CreateCircleByRadius(x, y, z, r)` |
| `CreateCenterRectangle2(x1,y1,z1,x2,y2,z2)` | `CreateCenterRectangle(x1,y1,z1,x2,y2,z2)` |
| `CreateLine2(x1,y1,z1,x2,y2,z2)` | `CreateLine(x1,y1,z1,x2,y2,z2)` |

带 "2" 的版本 (`CreateCircleByRadius2` 等) 在 SW 2024 中不存在，调用后引发 COM `AttributeError`。

### 2.9 Cut 操作：`FeatureExtrusion3` 第 3 参 True（C6 — 实机验证）

`IFeatureManager.FeatureCut3` 在 SW 2024 中**始终失败**（无论参数数量），不可用。

正确方式：在目标面建立草图后，使用 `FeatureExtrusion3` 的第 3 个布尔参数 `ReverseDirection=True` 表示向内切削：

```python
# 参数签名（18 参数，仅关键参数说明）：
# FeatureExtrusion3(
#   Sd:bool,         # True=blind, False=through all
#   Flip:bool,       # 翻转方向
#   Dir:bool,        # True=切削（切除实体），False=增加实体
#   T1:int,          # 终止条件（0=blind）
#   T2:int,
#   D1:float,        # 深度（米）
#   D2:float,
#   ...16 more bools/floats...
# )

# 示例：内腔 Cut，深度 cut_depth
ftMgr.FeatureExtrusion3(True, False, True, 0, 0, cut_depth, 0,
                         False, False, False, False, 0, 0,
                         False, False, False, False, True)
```

第 3 参 `True` = 切除方向（Dir 反转），产生 Cut 特征。

### 2.10 `_new_part_doc` 模板路径修复（C7 — 实机验证）

`swApp.GetUserPreferenceStringValue(9)` 在中文版 SW 2024 返回空字符串 `""`；`NewDocument("", ...)` 返回 `None`。

**修复**：动态搜索 GB 零件模板，搜不到时 fallback 到已知路径：

```python
def _new_part_doc(self, swapp) -> object:
    import glob as _glob
    pattern = r"C:\ProgramData\SolidWorks\SOLIDWORKS 2024\templates\gb_part.prtdot"
    fallbacks = _glob.glob(
        r"C:\ProgramData\SolidWorks\SOLIDWORKS *\templates\gb_part.prtdot"
    ) + _glob.glob(
        r"C:\ProgramData\SolidWorks\SOLIDWORKS *\templates\Part.prtdot"
    )
    template = pattern if __import__("os.path", fromlist=["exists"]).exists(pattern) else (
        fallbacks[0] if fallbacks else ""
    )
    # swDocumentTypes_Part=1, paper=0, width/height=0（使用模板默认）
    doc = swapp.NewDocument(template, 1, 0, 0)
    return doc  # None 表示失败，调用方检查
```

所有 `_build_*` 必须在 `_new_part_doc` 返回 None 时立即 `return None`：
```python
model = self._new_part_doc(swapp)
if model is None:
    return None
```

### 2.11 COM 属性访问：不加括号（C8 — 实机验证）

`win32com.client` 将 COM `BSTR property` 暴露为 Python **属性**（非方法）。加括号会对字符串对象求调用，抛 `TypeError: 'str' object is not callable`。

| 错误写法 | 正确写法 |
|---|---|
| `model.GetTitle()` | `model.GetTitle` |
| `model.GetPathName()` | `model.GetPathName` |

所有 `_build_*` 中涉及这两个属性的地方均不加括号。

### 2.12 `上视基准面` 坐标系：Extrude 方向为 +Y（C9 — 实机验证）

`上视基准面` 是 **XZ 平面**（法向量 = +Y），草图在 XZ 平面绘制，`FeatureExtrusion3` 沿 +Y 挤出。

| 操作 | 正确坐标 |
|---|---|
| 草图点坐标 | `(x, z, 0)`（XZ 平面中的 X 和 Z 分量，第三参数=0） |
| 外壳顶面 Y 坐标 | `(0, h, 0)`（不是 Z=h） |
| 外壳底面 Y 坐标 | `(0, 0, 0)` |

`前视基准面`（XY 平面，法向量=+Z）：草图在 XY 平面，extrude 沿 +Z。适用于 `_build_bracket` 的 L-Profile extrude。

这影响所有 `SelectByID2` 按坐标选面的操作。若需按面选（如用于后续特征），应通过面 index 或拓扑关系选，而非按绝对坐标，以避免浮点偏差。

### 2.13 `SelectByID2` Callout 参数：`VARIANT_NULL`（C4 — 实机验证）

`model.Extension.SelectByID2` 第 7 参数（Callout）必须是 COM `IDispatch` VARIANT，不能传 Python `None`（类型不匹配 → COM E_INVALIDARG 错误）。

**全部调用统一定义一个模块级常量**：

```python
import pythoncom
import win32com.client

VARIANT_NULL = win32com.client.VARIANT(pythoncom.VT_DISPATCH, None)
```

然后所有 `SelectByID2` 调用：
```python
model.Extension.SelectByID2("上视基准面", "PLANE", 0, 0, 0, False, 0, VARIANT_NULL, 0)
```

此常量定义在 `sw_parametric_adapter.py` 模块顶部（`_VALID_TEMPLATES` 同级），仅在 `import win32com` 成功的 Windows 环境下定义（用 `try/except ImportError` 保护，非 Windows 环境赋 `None`）。

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

### 6.4 `_close_doc` mock 测试（C2 + C8 回归守护）

新增一个非 SW 单测（无 marker），验证 `_close_doc` 访问 `model.GetTitle`（**属性不加括号**，见 §2.11）而非调用 `model.GetPathName()`：

```python
def test_close_doc_uses_get_title(monkeypatch):
    adapter = SwParametricAdapter()
    mock_swapp = MagicMock()
    mock_model = MagicMock()
    mock_model.GetTitle = "Part1"   # COM 属性：直接赋字符串值，不用 return_value
    adapter._close_doc(mock_swapp, mock_model)
    mock_swapp.CloseDoc.assert_called_once_with("Part1")
```

> **注意**：`mock_model.GetTitle = "Part1"` 而不是 `mock_model.GetTitle.return_value = "Part1"`。
> 后者模拟的是可调用对象，前者模拟的是 COM BSTR 属性（直接返回字符串）。两者在 MagicMock 上均不等价。

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

## 附录：修订日志

### v1.0 → v1.1（代码一致性审查）

| # | 严重度 | 问题 | 修订 |
|---|---|---|---|
| C1 | CRITICAL | `_build_housing` wall_t fallback 在米域再 /1000 → ~0.07mm | §2.2 明确单位约定 + §4 表格修正；正确写法见 §2.2 |
| C2 | CRITICAL | `_close_doc("")` 对新建文档无效 → SW 文档泄漏 | §2.3 修改签名为接收 model 对象；§6.4 补 mock 测试 |
| W1 | WARNING | `SelectByID2` 坐标选面不可靠 → Shell 选错面 | §2.4 改为 Box Cut 内腔方案 |
| W2 | WARNING | 双 Extrude 可能多体 → STEP 含 2 个 Solid | §2.5 改为 L-Profile 单草图单次 Extrude |
| W3 | WARNING | SW spring 仅空心柱，比 CQ 版更简陋 | §2.6 补两端法兰 + coil_n 段外环 |
| I1 | INFO | `_extract_params("cover")` 缺 `n_hole` | §3 补加；§1 范围增加 `gen_parts.py` 修改项 |
| I2 | INFO | spec 缺单位约定说明 | §2.2 新增显式约定段 |

### v1.1 → v1.2（实机 SW COM API 验证）

| # | 严重度 | 问题（实机验证发现）| 修订 |
|---|---|---|---|
| C3 | CRITICAL | 草图方法名带 "2" 后缀（`CreateCircleByRadius2` 等）在 SW 2024 不存在 → `AttributeError` | §2.8 + §2.4/§2.5 代码示例全部修正 |
| C4 | CRITICAL | `SelectByID2` Callout 参数传 Python `None` → COM E_INVALIDARG | §2.13 定义 `VARIANT_NULL = VARIANT(VT_DISPATCH, None)`；§2.4 代码更新 |
| C5 | CRITICAL | 英文平面名 `"Top Plane"` 等在中文版 SW 2024 返回 False → 草图建在错误上下文 | §2.7 平面名中文对照表；§2.4/§2.5 代码更新 |
| C6 | CRITICAL | `FeatureCut3` 在 SW 2024 始终失败（参数计数无关）→ 所有 Cut 操作全部失效 | §2.9 改用 `FeatureExtrusion3` 第 3 参 True；§2.4 代码更新 |
| C7 | CRITICAL | `GetUserPreferenceStringValue(9)` 在中文 SW 返回 `""` → `NewDocument` 返回 None → 后续全部 NullReferenceError | §2.10 动态搜索 gb_part.prtdot 模板 + fallback |
| C8 | CRITICAL | `model.GetTitle()` / `model.GetPathName()` 加括号 → `TypeError: 'str' not callable` | §2.11 明确不加括号；§2.3/§6.4 代码修正 |
| C9 | CRITICAL | `上视基准面` 是 XZ 平面，Extrude 沿 +Y，顶面坐标 `(0, h, 0)` 而非 `(0, 0, h)` → 面选坐标全部错误 | §2.12 坐标系说明；§2.4 代码注释更新 |
