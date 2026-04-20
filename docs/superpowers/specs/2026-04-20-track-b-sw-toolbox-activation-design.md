# Track B — SolidWorks Toolbox 装即用路径贯通 设计规格

> 版本: v0.4 — 2026-04-20（已过第四轮审查：非专业用户 + skill 开发者 + 一致性+边界，见附录 D 修订日志）
> 状态: 已审查修订，可落地实施
> 触发: 2026-04-20 session 发现**本机 SW 2024 已装 + Toolbox 索引 1844 条 + materials 530 张贴图全就绪**，但 SW 资产报告仍是 `Toolbox: ❌`，54 行 BOM 全归"自定义"，`std_*_std.step` 25 个全走 jinja_primitive fallback
> 前置: Phase SW-A（`SwInfo` / `sw_material_bridge`）+ Phase SW-B v4（`SwToolboxAdapter` / `sw_preflight.matrix` / 一键修 dispatch）均已合入 main @ `f91508a`
> 关联: **Track A**（`2026-04-20-track-a-visual-fidelity-quick-wins-design.md`）不依赖本文档；Track A1 的纹理桥只需要 `SwInfo.textures_dir` 目录存在，不需要 Add-in 启用。Track B 的交付让"标准件真件进来"，与 Track A 叠加后图的保真度再上一个台阶
>
> **目标**：把"SW 装了 ≠ Toolbox 生效"的断链补上，让**新装机 + 任何版次（Standard/Pro/Premium）的 SW** 在**不要求用户手工打开 SW 勾任何 Add-in 复选框**的前提下，自动能走通 sldprt→STEP→Blender 真件加载。
>
> **硬约束**：本 Track 推翻 Phase SW-B v4 决策 #13（"Add-in 启用作为 `is_available()` 硬门"）——必要的回溯性决策修订在 §2 集中列出，附证据链。

---

## 1. 目标与范围

### 1.1 问题陈述

2026-04-20 session 端到端测试揭示三层 SW 集成断链（Track A §"现状诊断"已详列）。Track B 专注修复 **SW 真件几何通道**——即从"SW sldprt 文件躺在 toolbox_dir"到"真件 STEP 被 Blender 加载"的完整链路：

```
[现状断链]
HKCU\AddInsStartup 无 Toolbox 条目
    │
    ▼
find_toolbox_addin_guid() = None
    │
    ▼
fix_addin_enable() raises "GUID not discoverable"
    │
    ▼
preflight matrix "addin_enabled" check = False
    │
    ▼
SwToolboxAdapter.is_available() = False   ← Phase SW-B v4 决策 #13 硬门在这里
    │
    ▼
parts_resolver 跳过 sw_toolbox rule，全部走 jinja_primitive fallback
    │
    ▼
25 个 std_*.step 都是 "simplified representation" 占位
```

### 1.2 实证证据（2026-04-20 本机枚举）

**本机 `C:\Program Files\SolidWorks Corp\SOLIDWORKS\` 注册表枚举结果**（session 里 `probe_all_addins.py` 输出）：

| 注册表路径 | Toolbox 条目 | 非 Toolbox 条目数 |
|---|---|---|
| `HKLM\SOFTWARE\SolidWorks\AddIns\{guid}` | **无** | 6（Composer/Marketplace/XPS 等）|
| `HKLM\SOFTWARE\SolidWorks\SOLIDWORKS 2024\AddIns\{guid}` | **无** | 12（CAM/ScanTo3D/Visualize 等）|
| `HKCU\Software\SolidWorks\AddInsStartup` | **无** | 若干 |
| `HKCU\Software\SolidWorks\SOLIDWORKS 2024\AddInsStartup` | **无** | 若干 |

**但同时**：

- `sw-inspect` 报告 `toolbox_index 健康，1844 条`（`swbrowser.sldedb` 可读）
- `sldmat=6 textures_cats=25 textures=530` 全部就绪
- `SldWorks.Application CLSID` 已注册，pywin32 可用

→ **结论**：本机 SW Toolbox 的 **物理资产（sldprt + 纹理 + 索引）100% 就绪**，只是 **Add-in DLL 没在任何注册表路径登记**。这是 Standard / Professional 某些安装选项的典型结果——Toolbox 作为**独立库文件模块**存在，**Add-in Browser GUI 模块未装或未激活**。

### 1.3 目标

| 子项 | 问题 | 产出 |
|---|---|---|
| **B1** | `find_toolbox_addin_guid` 只扫 `AddInsStartup`（2 条路径），本机 4 条 AddIns + AddInsStartup 路径都扫了**都没 Toolbox**——当前函数结构就算扩全量也救不了 | 新增 `discover_toolbox_addin_guid()`：(a) 仍优先扫 4 条 registry 路径做 Description match，(b) **全 miss 时回退扫文件系统** `install_dir\AddIns\toolbox\*.dll` / `install_dir\Toolbox\...` 并动态注册到 HKCU；用于"一键修"能拿到可用 GUID |
| **B2** | `SwToolboxAdapter.is_available()` 拒绝"有 sldprt + 有 COM 但 Add-in 未启用"的合法场景 | 解耦 Add-in 硬门 → 改为 `is_available()` 只看**"sldprt→STEP 转换路径物理可达"**（toolbox_dir 可读 + SW COM 可启动 + Toolbox 索引可解析），Add-in 启用状态降级为 advisory warning |
| **B3** | `sw-warmup` 跑完 STEP 缓存仍是 0 件（2026-04-20 报告 `warmup: error_log 有内容；STEP 0 件`）| 诊断并修 sldprt→STEP 转换流水线：COM 启动失败 root cause / Toolbox 元件打开时需要哪些额外 add-in / ExitApp 竞争。产出 smoke test 覆盖 ≥ 1 个真 sldprt 转 STEP |

### 1.4 覆盖率基准

**前基线（2026-04-20）** 本机：
- `SwToolboxAdapter.is_available()` = False
- BOM 54 行 → sw_toolbox 命中 0 行
- STEP 缓存命中 0 件
- `std_*_std.step` simplified 25/25

### 1.4.1 `end_effector` BOM 54 行分类清单（Track B 命中目标的计算基础）

系统分析师审查发现原 "≥ 11" 目标主观。按 2026-04-20 实测 BOM 分类（部分示例，完整清单 A 交付时补）：

| BOM 类别 | 件数（估算） | SW Toolbox 能否命中 | Track B 目标命中 |
|---|---|---|---|
| GB/T 紧固件（M6/M8 螺栓 + 螺母 + 垫圈）| ~8 | 能（命中 `bolts`/`nuts`/`washers` 子目录）| 7（85%）|
| GB/T O 圈（FKM Φ80×2.4 等）| ~3 | 能（命中 `o_rings`）| 2 |
| GB/T 销（定位销/圆锥销）| ~2 | 能（命中 `dowel_pins`）| 2 |
| GB/T 轴承 | ~2 | 能 or bd_warehouse 争抢（yaml 规则 GB 高优先给 SW）| 1（另 1 让 bd_warehouse）|
| Maxon/LEMO/ATI vendor STEP | ~4 | 不命中（走 step_pool）| 0（不属于 SW Toolbox 范围，不计）|
| 自制 11 件 + 其他非标 ~22 行 | ~33 | 不命中 | 0 |
| **总目标** | | | **12/54 ≈ 22%**（其中 GB/T 标准件分类 ≈ 15 件，Track B 拿下 85% = 12 件）|

### 1.4.2 Track B 交付目标

| 指标 | 目标 | 依据 |
|---|---|---|
| `SwToolboxAdapter.is_available()` | True | B-2 解耦 Add-in 硬门 |
| `sw-warmup --smoke-test`：1 个典型件（M6×20 螺栓）sldprt→STEP | ≤ 30s，输出 > 1KB，STEP header `ISO-10303` | Phase SW-B v4 §5 timeout 20s + 余量 |
| 回归 `end_effector`：BOM 54 行 → sw_toolbox 命中数 | **≥ §1.4.1 GB/T 分类件数 × 85%**（约 12 件）| 按真实 BOM 分类计算，非主观 |
| `std_*_std.step` 含 `Simplified representation` 比例 | 从 25/25 降到 ≤ 13/25 | 紧固件 + O 圈 + 销 + 部分轴承从 SW 取真件，其余（vendor + 自制 std）保持 |

### 1.5 非目标

- **不做 Toolbox 元件的 configuration 切换** — 每个 sldprt 只导出默认 config，与 Phase SW-B v4 决策 §1.3 一致
- **不装其他 SW Add-in 模块** — Track B 只碰 Toolbox Library 和 Toolbox Browser 相关注册（若必须），绝不 touch PDM/Composer/CAM 等
- **不改 sldmat 解析** — 那是 Track A1 的领地
- **不支持 SW 2022 及更早** — v4 决策 `version_year ≥ 2024` 维持
- **不做 Linux/macOS 兼容** — 产品已定 Windows-only（记忆 `user_windows_only_scope`）
- **不在 CI 跑真 SW** — self-hosted runner 用 mock；真 SW 烟测仍是本地手动触发 + Agent 诊断

---

## 2. 关键设计决策（含对 Phase SW-B v4 的修订）

| # | 决策点 | Track B 选择 | 对 v4 的关系 |
|---|---|---|---|
| B-1 | Toolbox Add-in 启用状态的语义 | 从"gate/硬门"**降级**为"advisory warning"；未启用不阻断 resolver | **推翻 v4 决策 #13**（详见 §2.1 证据链） |
| B-2 | `is_available()` 判定标准 | sldprt→STEP 转换链路的**物理**可达：`toolbox_dir 可读` + `toolbox_index 可解析` + `SldWorks.Application CLSID 注册` + `pywin32 可 import` + `version_year ≥ 2024`；Add-in 状态不进入条件 | v4 §5.3 6 项检查中删除第 6 项（Add-in 启用），其他保留 |
| B-3 | GUID 发现策略 | 三段式：**(1) 扫 4 条 registry AddIns 路径按 Description match "Toolbox"** → **(2) 扫 `AddInsStartup` 2 条路径按 name 里含 "toolbox"（既有逻辑）** → **(3) 扫 `install_dir\...` 找 Toolbox DLL 反查 CLSID** | 扩展 v4 行为，向后兼容——(2) 即旧路径 |
| B-4 | `fix_addin_enable` 的兜底行为 | GUID 通过 (1)/(2) 找到 → 写 `AddInsStartup` GUID=1（既有）；GUID 通过 (3) 在文件系统找到 → **跳过注册表写入，只发 INFO 日志告知"Add-in 已就绪但需用户首次在 SW 启动时激活"**，不阻断后续链路 | 扩展 v4，但不 break v4 的幂等 no-op 分支 |
| B-5 | preflight `addin_enabled` check 的角色 | 从 "check 结果决定整个 matrix passed/failed" 降为 "诊断信息"：check 仍跑，结果写进 `PreflightResult.diagnosis`，但不再 short-circuit `passed=False` | v4 matrix.CHECK_ORDER 里 `addin_enabled` 保留但**标记 `is_blocking=False`**（新增字段）|
| B-6 | `run_preflight(strict=True)` 的行为 | 只有 `is_blocking=True` 的 check 失败才 sys.exit(2)；Add-in 未启用 → warning 但 passed=True | Phase SW-A/B 所有调用方行为向后兼容（更宽松，不会出现"以前 pass 现在 fail"）|
| B-7 | `sw-warmup` 的熔断条件 | 延续 v4 决策 #22：单进程 COM 启动连续 3 次失败熔断；熔断后后续 warmup 跳过但**不报 adapter unavailable**——与 B-2 解耦：adapter 层看不到 warmup 熔断，warmup 只是缓存加速，miss 时 resolver 按需单件转换 | 扩展 v4 — warmup 熔断和 adapter availability 正交化 |
| B-8 | Toolbox 目录物理健康的校验 | 新增 `_check_toolbox_path_healthy(info: SwInfo) -> tuple[bool, Optional[str]]`（second element **Optional[str]** 与 A §5.4.1 `is_available()` 契约对齐；健康时返 `(True, None)` 而非 `(True, "")`）：校验 `toolbox_dir` 可 listdir + **`swbrowser.sldedb` 存在**（硬要求）+ 至少 1 个 `.sldprt` 可读。**`.sldsetupdata` 降为 advisory**（SW 操作员审查：该文件在"新装机首次启动 Toolbox Browser 之前不存在"，要求其存在会误判新装机 unhealthy）。UNC 路径容错：前置 `os.path.isfile(toolbox_dir)` 预检，失败时 reason 明示 UNC 不可达 | 替代 v4 CHECK_ORDER 里的 `toolbox_path` check（现行实现只看 `toolbox_dir` 非空）|
| B-9 | sldprt→STEP 转换的 timeout | 延续 Phase SW-B v4 决策 #10 的 `single_convert_timeout_sec=20s`，不改 | 继承 |
| B-10 | 新装机**自动激活** Toolbox Add-in 的工作量权衡 | **不做**。尝试自动写 HKLM 需要管理员权限 + 破坏审计链；Toolbox 的"真件 sldprt + COM 打开导出 STEP"这条路**根本不需要 Add-in GUI 插件**，B-2 的解耦已足够 | 产品决策：零配置 ≠ 静默改系统 |
| B-11 | Toolbox sldprt 打开时的 SW 消息循环 | `SwComSession.convert_sldprt_to_step()` 内 `OpenDoc6` → `SaveAs3` → `CloseDoc` 三步；打开时若有"Toolbox Add-in not loaded"类对话框 → 需 pre-call `CommandManager.SetUserPreferenceToggle(swUserPreferenceToggle_e.swLicenseAutoActivate, False)` 抑制弹窗 | 补 v4 §5.2 漏掉的细节（本机新发现）|
| B-12 | warmup 失败 root cause 分类 | 新增 3 类错误码到 `artifacts/{run_id}/sw_warmup_errors.log`：`NO_COM_LICENSE` / `SLDPRT_CORRUPT` / `SAVEAS_TIMEOUT` —— 用于后续运营判断"是 SW 授权问题还是我们代码问题" | 扩展 v4 §5.2 错误模型 |
| **B-13** | **Standard 版 edition 探测 + routing 分支** | 新增 `SwInfo.edition: Literal["standard","professional","premium","trial","educational","unknown"]`，通过 `GetLicenseProductLevel()` + HKLM `InstalledProducts` 填；**Standard 版 SwToolboxAdapter.is_available() 直接返 `(False, "SW Standard edition does not ship Toolbox Browser DLL")`**，routing 退 bd_warehouse；非 Standard 进入 SW 真件路径 | SW 操作员 CRITICAL：Standard 版无 Toolbox Browser DLL，B-2 "装即用"承诺在 Standard 用户上破产 |
| **B-14** | **Toolbox Browser modal dialog 抑制的真实手段** | 不用 `SetUserPreferenceToggle`（枚举号错 + toggle 选错）；**改用 `app.Visible = False` + `app.UserControl = False` + `app.FrameState = swWindowState_e.swWindowMinimized`**（worker 进程 Dispatch 后首行调用）；这组配置是"不要显示任何 UI"的正确语义，覆盖 Toolbox "select size and configuration" modal | SW 操作员 CRITICAL：原方案 `_LICENSE_AUTO_ACTIVATE = 277` 是 `swDisplaySketchEntityPoints`（跟 license 无关），对 Toolbox 对话框无抑制作用 |
| **B-15** | **COM 实例隔离** | worker 进程用 `win32com.client.DispatchEx("SldWorks.Application")` 而非 `Dispatch` —— 后者会 fallback `GetActiveObject` 复用用户手工开的 SW 实例，会出现用户点菜单 / worker hang 的串行阻塞 | SW 操作员 INFO：`CLSCTX_LOCAL_SERVER` 强制新进程 |
| **B-16** | **Toolbox multi-configuration 件的处理策略** | SW Toolbox 一个 sldprt 承载 M3~M24 全规格（每个 M6×20/M6×25 是独立 configuration）；**Track B 范围内的决定**：若 BOM 行的尺寸能对应到 `IConfigurationManager::GetConfigurationNames()` 中的某个 config 名 → `ShowConfiguration2(name)` 后再 `SaveAs3` 导出；**无法匹配 config 时该 BOM 行 resolver 跳过 sw_toolbox 落 bd_warehouse**（避免导出默认 config = 最小规格 M3×10 的错误 STEP）。**反查映射表源**：`parts_library.yaml` 新增 `solidworks_toolbox.config_name_resolver` 段（与 `size_patterns` 并列），yaml 里写死 `M6×20` → `M6x20` 这类规范化规则；运行时 `IConfigurationManager::GetConfigurationNames()` 真实枚举 + 规范化后模糊匹配；缺对应规则的 BOM 行 resolver skip sw_toolbox | SW 操作员 CRITICAL：不切 config = STEP 尺寸错 3-5 倍无视觉提示 |
| **B-17** | **Stage 3 filesystem 发现命中后自动写 HKCU** | B-10 不写 HKLM 是对的（需管理员）；但 Stage 3 找到 DLL 即证明"DLL 物理存在但未注册" —— 此时 `fix_addin_enable` 可**尝试写 HKCU\Software\SolidWorks\AddInsStartup\{guid}=1**（用户权限够），供 SW 下次启动自动加载，让"零配置"更彻底 | 架构师 W5：原 B-4 Stage 3 只 log INFO 不写注册表，Stage 3 命中功能半截 |

### 2.1 为什么推翻 v4 决策 #13（Add-in 硬门）

v4 原文：`sw_detect 新增 toolbox_addin_enabled 字段；is_available() 强制检查此字段；未启用时 env-check 给出明确指引`。

**v4 时的假设**：Toolbox Add-in 启用 ⇔ Toolbox 功能可用。

**2026-04-20 反例证据**：
- 本机 SW 2024 正常装、Toolbox 索引 1844 条、sldmat 健康、COM 可启动
- `HKLM\SOFTWARE\SolidWorks\AddIns`（全量 AddIns 注册表）下**没有任何 Toolbox 条目**
- `HKCU\...\AddInsStartup` 也没
- 即便用户去 `Tools → Add-Ins` 菜单勾选，因 Add-in DLL 未登记在 HKLM 层面，也勾不上

**意味着**：v4 决策 #13 的硬门让**这台机器上的 SW 永远不会被 adapter 认为可用**——而机器实际能打开 sldprt 并保存为 STEP。

**推翻后仍成立的约束**：sldprt→STEP 转换**物理上**依赖：
1. SW 可执行文件在
2. pywin32 可启 COM
3. sldprt 文件真实可读
4. SW 对该 sldprt 的 Toolbox Library 解码能力——由 `<install>\Toolbox\` 目录 + sldedb 决定，**与 Add-in DLL 是否装载在 Add-in Browser 菜单无关**

### 2.2 为什么不尝试"代用户自动登记 Add-in"

两个硬约束：
- HKLM 写入需管理员权限 — 违反"零配置"且需 UAC 弹窗，破坏"装即用"体验
- Toolbox Add-in DLL 若物理不存在（Standard 精简安装），无论怎么改注册表 SW 下次启动仍会自动去注 — **白忙一场**

**方案**：绕过 Add-in Browser 路径，直接用 **文件路径 + COM OpenDoc** 的组合访问 sldprt；这是 Phase SW-B 一开始就选的路径（§5.2 "SwComSession.convert_sldprt_to_step"），硬门是误加的约束。

---

## 3. B1 — GUID 发现三段式重构

### 3.1 当前实现（`sw_detect.py:511 find_toolbox_addin_guid`）

```python
# sw_detect.py:511 现状（完整逻辑，包含 _is_toolbox_guid 分支）：
def find_toolbox_addin_guid() -> Optional[str]:
    candidates = [r"Software\SolidWorks\AddInsStartup"]
    if info.version_year:
        candidates.append(rf"Software\SolidWorks\SOLIDWORKS {info.version_year}\AddInsStartup")
    for subkey in candidates:
        # 枚举 HKCU values，命中条件二择一：
        #   (a) name.lower() 含 "toolbox"
        #   (b) _is_toolbox_guid(name)  ← 按 _TOOLBOX_GUID_HINTS = ("bbf84e59",) 前缀匹配
```

**问题**：只扫 HKCU\AddInsStartup（2 条路径）——**用户启动 SW 时勾选过 Toolbox Add-in** 才会有条目。新装机 / Standard 版都是空的。

**复用约束**：Track B1 新增的 `_scan_all_addins_by_description` 必须**同样复用** `_is_toolbox_guid(name)`（见下 §3.2 实现），否则不同发现路径的判定口径不一致，会出现 Stage 1 命中 / Stage 2 漏掉同一个 GUID 的 bug。

### 3.2 Track B1 重构

**保留** `find_toolbox_addin_guid()`（向后兼容 — v2.11 的 `_check_toolbox_addin_enabled` 仍调它），行为不变。

**新增** `discover_toolbox_addin_guid() -> tuple[Optional[str], str]`（GUID + 来源标签）：

```python
def discover_toolbox_addin_guid() -> tuple[Optional[str], str]:
    """三段式发现 Toolbox Add-in 的 GUID。

    Returns:
        (guid, source) where source ∈ {"startup", "registry_fullscan", "filesystem", "none"}
    """
    # Stage 1: 老路径（快，命中率高的历史用户）
    guid = find_toolbox_addin_guid()
    if guid:
        return guid, "startup"

    # Stage 2: 全量 AddIns registry 扫描（4 条路径）按 Description/Title match "toolbox"
    guid = _scan_all_addins_by_description()
    if guid:
        return guid, "registry_fullscan"

    # Stage 3: 文件系统扫描 — 反查 DLL 对应 CLSID
    guid = _scan_addin_dll_clsid()
    if guid:
        return guid, "filesystem"

    return None, "none"


def _addins_candidates(version_year: int) -> list[tuple[int, str]]:
    """Return [(hive, subkey_path)] list; constructed at call time because
    version_year is only known after detect_solidworks() runs. Module-level
    constant would require hardcoding the year."""
    import winreg
    return [
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\SolidWorks\AddIns"),
        (winreg.HKEY_LOCAL_MACHINE, rf"SOFTWARE\SolidWorks\SOLIDWORKS {version_year}\AddIns"),
        (winreg.HKEY_CURRENT_USER,  r"Software\SolidWorks\AddIns"),
        (winreg.HKEY_CURRENT_USER,  rf"Software\SolidWorks\SOLIDWORKS {version_year}\AddIns"),
    ]


def _scan_all_addins_by_description() -> Optional[str]:
    """枚举全量 AddIns registry，三口径任一命中即返回 GUID：
       (a) Description/Title value 含 "toolbox"（大小写不敏感）
       (b) 子键名 name 含 "toolbox"（大小写不敏感）
       (c) _is_toolbox_guid(name) 前缀匹配（与老 find_toolbox_addin_guid 口径对齐）
    """
    info = detect_solidworks()
    if info.version_year == 0:
        return None
    for hive, path in _addins_candidates(info.version_year):
        # try WOW64_64KEY first, then WOW64_32KEY
        # for each GUID subkey: read Description + Title values
        # match by (a) / (b) / (c) 三个并列口径 → return guid


def _scan_addin_dll_clsid() -> Optional[str]:
    """在 <install_dir>\AddIns\{toolbox,toolbox_library,...}\*.dll 找 Toolbox DLL，反查 HKCR\CLSID。"""
    info = detect_solidworks()
    if not info.install_dir:
        return None
    candidate_dirs = [
        Path(info.install_dir) / "AddIns" / "toolbox",
        Path(info.install_dir) / "AddIns" / "Toolbox",
        Path(info.install_dir) / "Toolbox",
    ]
    for d in candidate_dirs:
        for dll in d.glob("**/*.dll"):
            guid = _clsid_from_dll(dll)
            if guid and _dll_exposes_toolbox(dll):
                return guid
    return None
```

**`_clsid_from_dll`** 用 `pywin32.win32com.client.GetModuleForProgID` 或直接读 DLL 的 `TLB` 资源——实现选型在 planning 阶段做 spike，具体到 Task B1-3 确定。

### 3.3 单元测试契约

- `test_discover_toolbox_addin_guid.py`:
  - (a) Stage 1 命中 → 返回 `(guid, "startup")`
  - (b) Stage 2 命中 → mock registry 让 stage 1 miss，stage 2 里 description="SOLIDWORKS Toolbox" → 返回 `(guid, "registry_fullscan")`
  - (c) Stage 3 命中 → mock filesystem 放 fake DLL，stage 1/2 miss → 返回 `(guid, "filesystem")`
  - (d) 三段全 miss → `(None, "none")`
  - (e) 老函数 `find_toolbox_addin_guid()` 签名/行为与 v2.11 一致（兼容性 gate）

---

## 4. B2 — `is_available()` 解耦 Add-in 硬门

### 4.1 当前实现（`adapters/parts/sw_toolbox_adapter.py:54-90`）

```python
def is_available(self) -> bool:
    # 1. 非 Windows → False
    # 2. SW 未装 → False
    # 3. version_year < 2024 → False
    # 4. pywin32 不可用 → False
    # 5. toolbox_dir 为空 → False
    # 6. toolbox_addin_enabled = False → False   ← 这是硬门
    # 7. SwComSession 熔断 → False
```

### 4.2 Track B2 重构（**返回 tuple[bool, Optional[str]]** — 与 Track A §5.4.1 契约统一）

```python
def is_available(self) -> tuple[bool, Optional[str]]:
    # ── 必要物理条件（全保留）──
    if sys.platform != "win32":
        return False, "not windows"
    info = detect_solidworks()
    if not info.installed:
        return False, "SW not installed"
    if info.version_year < 2024:
        return False, f"SW {info.version_year} too old (need 2024+)"
    if not info.pywin32_available:
        return False, "pywin32 not available"
    if not info.toolbox_dir:
        return False, "toolbox_dir empty"

    # ── B-13 新增：SW edition 探测，Standard 版直接拒 ──
    if info.edition == "standard":
        return False, "SW Standard edition does not ship Toolbox Browser DLL"

    # ── B-8 替代 v4 第 6 项：物理路径健康校验（加宽：新装机 .sldsetupdata 可不存在）──
    healthy, reason = _check_toolbox_path_healthy(info)
    if not healthy:
        return False, f"toolbox path unhealthy: {reason}"

    # ── SwComSession 熔断保留 ──
    if SwComSession.is_circuit_broken():
        return False, "SwComSession circuit breaker tripped"

    # ── Add-in 未启用 → 仅记 advisory log（B-1），不 return False ──
    if not info.toolbox_addin_enabled:
        log.info(
            "SwToolboxAdapter: Toolbox Add-in 未在 SW 菜单里启用 —— "
            "将通过 COM 直接打开 sldprt，不经 Add-in Browser。"
        )

    return True, None
```

**Edition 探测实现**（新增 `sw_detect._detect_edition(install_dir, version_year) -> tuple[str, list[str]]`，返 edition + 探测尝试日志）：

- 优先 COM：`app.RevisionNumber()` 得完整版本字符串，含 edition 提示；启动 COM 代价大可放到 cache
- 退路 registry：`HKLM\SOFTWARE\SolidWorks\SOLIDWORKS {year}\Setup\InstalledProducts` 枚举已装产品，含 Toolbox Browser DLL 对应 key → Premium/Professional；不含 → Standard
- 再退路：扫 `install_dir\AddIns\toolbox*\*.dll`（Stage 3 的副产品）—— 有 DLL → Pro+；无 → Standard
- **全 miss → `edition = "unknown"`**（当作可用放行，但 reason 字符串**必须显式拼接** `"edition=unknown (all 3 probes failed: com/registry/dll)"` — 防 bug #4 silent swallow 重犯，用户能看到根因而非只看到后续 `"SwComSession circuit breaker tripped"`）
- 熔断 reason 时同样拼接 edition 来源信息（`f"circuit breaker tripped; edition was {info.edition} (source={probe_source})"`）

**pipeline_config.json 缺失兜底**（边界审查 C4.6）：首次装机无 `pipeline_config.json` 时，`detect_solidworks` 走内置默认 `install_dir` 探测链（`shutil.which("SLDWORKS.EXE")` + 常见路径 `C:\Program Files\SOLIDWORKS Corp\SOLIDWORKS\`），**不 raise**；探不到则 `SwInfo.installed=False` + `install_dir=""`，`is_available()` 按现逻辑返 `(False, "SW not installed")`，pipeline 正常降级。

### 4.3 sw_preflight.matrix 配合改动

**结构约束**：`matrix.py:207` 现状 `CHECK_ORDER: list[tuple[str, str]]`，第二元素**必须是字符串**（`run_all_checks()` 用 `getattr(this_module, attr)` 动态解析，为了让 `unittest.mock.patch` 可生效）。改成三元素 tuple 会破坏 monkeypatch 机制。

**正确方案**：`CHECK_ORDER` 保持两元素 tuple 不动，**新增独立常量** `_BLOCKING_CHECKS: frozenset[str]`：

```python
# matrix.py

CHECK_ORDER: list[tuple[str, str]] = [   # ★ 保持不变
    ('platform',           '_check_platform'),
    ('pywin32',            '_check_pywin32'),
    ('sw_installed',       '_check_sw_installed'),
    ('toolbox_supported',  '_check_toolbox_supported'),
    ('com_healthy',        '_check_com_healthy'),
    ('toolbox_path',       '_check_toolbox_path_healthy'),   # ★ B-8：_check_toolbox_path → _check_toolbox_path_healthy 重命名（见下）
    ('addin_enabled',      '_check_addin_enabled'),
]

_BLOCKING_CHECKS: frozenset[str] = frozenset({   # ★ Track B 新增
    'platform', 'pywin32', 'sw_installed',
    'toolbox_supported', 'com_healthy', 'toolbox_path',
    # addin_enabled 故意不在此 set 里 —— B-5 advisory only
})
```

**`run_all_checks()` 语义改动**：

当前行为（matrix.py:218）遇**任一** check 失败即 short-circuit。Track B 改为：
- 所有 check 都跑到底（为了 advisory check 也能产出诊断）
- 返回 `passed = 所有 _BLOCKING_CHECKS 中的 check 都 pass`
- **返回值新增 `advisory_failures: dict[str, DiagnosisInfo]`**（非阻塞 check 的失败 → check_name 映射到 diagnosis）—— 改为 dict 而非 list[str]，支持多项 advisory 同时存在 + 每项独立诊断文案（系统分析师审查）

**`_BLOCKING_CHECKS` 判据（新增决策 B-18）**：
> **is_blocking = True** 当且仅当 check 失败时 **sldprt → STEP 物理不可达**。
> 典型 blocking：platform/pywin32/sw_installed/com_healthy/toolbox_path。
> 典型 advisory：addin_enabled（影响 GUI 功能但不影响 COM sldprt 打开）/ 未来的 `toolbox_index_parseable`（索引坏了只影响精度 + 搜索速度，不影响单件 OpenDoc）/ `sw_visible_config`（辅助诊断用）。
> 新增 check 时在本文档 §2 决策表登记归类，避免临时决策漂移。

**`_check_toolbox_path` 的替换关系**（B-8 决策）：现有 `matrix.py:_check_toolbox_path` 只看 `toolbox_dir` 非空；Track B 替换为 `_check_toolbox_path_healthy`，扩充为"可 listdir + 至少一个 `.sldsetupdata` 或 `swbrowser.sldedb` 存在 + 至少 1 个 `.sldprt` 可读"。**同步改动**：`matrix.py:604` `try_one_click_fix` dispatch 表里 `'toolbox_path': None` 这一条保留（toolbox_path 无法一键修）。

**兼容 gate**：`PreflightResult.passed` 的语义变了（从"所有 check pass"变成"所有 blocking check pass"）——任何调用方依赖老语义的点需逐一审。`grep 'PreflightResult.*passed\|\.passed'` 初估 3 处：`sw_preflight.preflight.run_preflight` 自身、`codegen/gen_std_parts.py:347` (`cached.get('preflight_result', {}).get('passed')`)、`sw_preflight/report.py:72` (`preflight.passed`)。

### 4.4 回归 Gate

以下两种情形**不能**因 Track B 退化：
- Phase SW-A 纯 sldmat 用户（不用 Toolbox adapter）：`sw_material_bridge` 行为 1:1 不变
- Phase SW-B v4 真 Add-in 已启用用户：流程不变，只是 preflight `addin_enabled` 从 check pass 变成 advisory；最终 `is_available()=True`

---

## 5. B3 — sldprt→STEP 转换流水线修复

### 5.1 现状诊断

2026-04-20 `sw-warmup` 报告：`warmup: error_log 有内容；STEP 0 件`。即 warmup 跑了但一个 STEP 都没产出。可能原因（按可能性排序）：

1. COM 启动因 Add-in 硬门（Phase SW-B v4 决策 #13）提前拒绝
2. COM 启动后 `OpenDoc6` 对 Toolbox sldprt 返回 error — 原因可能是"Toolbox Library Add-in 未激活时 sldprt 无法完整打开"
3. SW 授权类型（Standard 无 Toolbox Browser 功能）底层拒绝

**实测步骤**（B3-1 spike，在本 track 实施期前置）：
```powershell
# 手动单件 smoke test
python -c "from adapters.solidworks.sw_com_session import SwComSession; \
           sess = SwComSession.instance(); \
           out = sess.convert_sldprt_to_step(r'<toolbox_dir>\GB\bolts\hex\hex_bolt_m6x20.sldprt', \
                                              r'C:\Users\procheng\Desktop\m6x20.step'); \
           print('OK' if out else 'FAILED')"
```

结果决定 B3 的主修点：
- **原因 1**：修 B2 就够了（Add-in 硬门解耦后 COM 启动不再被拒）
- **原因 2**：需要在 `SwComSession.__enter__` 或 `convert_sldprt_to_step` 里增加"打开 sldprt 前先尝试 LoadAddIn 或 SetUserPreferenceToggle"步骤（B-11）
- **原因 3**：产品层面需要明确告诉用户"你的 SW 版次不支持 Toolbox"—— 添加 `SwInfo.edition` 的辅助文案，并在 is_available 里明确降级

### 5.2 改动清单（worker 进程）

**架构事实**：`SwComSession` 父进程**不直接持 COM**；每次 convert 起独立 subprocess 跑 `adapters.solidworks.sw_convert_worker`（见 `sw_com_session.py:4-11` doc + `:31 _WORKER_MODULE` 常量）。OpenDoc6/SaveAs3/CloseDoc 调用全在 worker 进程里。

**Track B 修订（SW 操作员 CRITICAL 审查后）**：`adapters/solidworks/sw_convert_worker.py` 内 Dispatch 后、OpenDoc 前：

```python
# sw_convert_worker.py —— worker 进程里
import win32com.client

# ── B-15：DispatchEx 强制新进程 COM 实例，不复用用户手工开的 SW ──
app = win32com.client.DispatchEx("SldWorks.Application")

# ── B-14：抑制任何 UI（包括 Toolbox "select size and configuration" modal）──
# 这组配置比 SetUserPreferenceToggle 更可靠，因为 Toolbox Browser 的对话框
# 走的是 ISldWorks::SendMsgToUser2 modal 路径，不被 preference toggle 捕获。
app.Visible = False
app.UserControl = False
# swWindowState_e.swWindowMinimized = 0；用数字常量避免依赖 pywin32 gen_py cache
app.FrameState = 0

# ── B-16：Toolbox multi-configuration 处理 ──
# 调用方在 BOM 行解析时已经确定 target_config_name（若无法匹配则该行
# resolver 已跳过 sw_toolbox 落 bd_warehouse，这里只处理能匹配的）
doc = app.OpenDoc6(sldprt_path, swDocPART, swOpenDocOptions_Silent, "", errors, warnings)
if target_config_name:
    # ShowConfiguration2 返 bool 不抛异常；名字不匹配会静默 return False
    # 然后 SaveAs3 默认 config（M3×10 最小规格）—— 与 bug #10 Blender silent exit 0
    # 同族。必须 check 返回值并 raise SwConvertError，让父进程熔断计数。
    if not doc.ShowConfiguration2(target_config_name):
        raise SwConvertError(
            f"ShowConfiguration2 failed: config '{target_config_name}' "
            f"not found in {sldprt_path}"
        )
doc.SaveAs3(step_out, 0, 0)
app.CloseDoc(doc.GetTitle())
```

**关键更正（相对 v0.2）**：
- **删除** `SetUserPreferenceToggle(277, False)`：该枚举号对应 `swDisplaySketchEntityPoints`，不是 license 或 dialog 抑制 —— 原方案无效且误导
- **新增** `Visible=False` + `UserControl=False` + `FrameState=0` 三连：SW 操作员实战证实这是抑制 Toolbox modal 的正确方式
- **新增** `DispatchEx` 替代 `Dispatch`：避免多实例串行阻塞
- **新增** config 切换：`ShowConfiguration2(target_config_name)` 在 SaveAs3 前调用；target_config_name 由 resolver 从 BOM 尺寸反查 Toolbox configuration 名得到，匹配失败则 resolver 层已跳过该行

**不在 `SwComSession.convert_sldprt_to_step` 里**：该方法父进程端只做 subprocess 编排 + timeout 守护，没有 COM app 对象可操作。

### 5.3 sw-warmup 的 smoke 硬化

`tools/sw_warmup.py` 增加 `--smoke-test` 标志：
- 跑 1 个已知好件（优先从 Toolbox Library 里挑 `hex_bolt_m6x20.sldprt` 或同等）
- 成功 → exit 0
- 失败 → 把完整 COM error 写 `artifacts/{run_id}/sw_warmup_smoke_error.log` 后 exit 2

**验收**：`sw-warmup --smoke-test` 在已启用 Track B1/B2 的本机**必须** exit 0，且产出 STEP 文件 >1KB。

---

## 6. 数据流与调用关系

### 6.1 B1+B2 融合数据流

```
detect_solidworks()
    │
    ▼
SwInfo {
  installed, version_year,
  toolbox_dir, toolbox_index_path,
  toolbox_addin_enabled ← 仍由 _check_toolbox_addin_enabled 填（诊断用），
                          **但不进入 SwToolboxAdapter.is_available()**（B-2）
}
    │
    ▼
SwToolboxAdapter.is_available()      ← B-2: Add-in 不再是硬门
    │
    ├── True → parts_resolver 正常路由到 sw_toolbox rule
    │
    └── False only when：
         sldprt→STEP 物理不可达 (toolbox_path/COM/pywin32/version)

============ 独立分支：一键修（仅当用户主动调用 sw-inspect --fix） ============

fix_addin_enable()
    │
    ▼
discover_toolbox_addin_guid()  ← B-1: 三段式发现
    │
    ├── ("startup", guid)           → 写 HKCU AddInsStartup GUID=1
    ├── ("registry_fullscan", guid) → 写 HKCU AddInsStartup GUID=1
    ├── ("filesystem", guid)        → 只 log INFO，不写注册表（B-4）
    └── ("none", None)              → raise "ADDIN_DLL_NOT_FOUND"（明确区别于原 "GUID not discoverable"）
```

### 6.2 B3 sldprt→STEP 流水线

```
SwToolboxAdapter.resolve(query)
    │
    ▼
匹配到 sldprt 文件路径
    │
    ▼
cache hit in ~/.cad-spec-gen/step_cache/sw_toolbox/{fingerprint}.step ?
    │
    ├── hit → 直接返回 STEP path
    │
    └── miss → SwComSession.convert_sldprt_to_step()  (父进程，subprocess 编排)
                  │
                  └── subprocess → adapters.solidworks.sw_convert_worker  (worker 进程)
                        ├── Dispatch("SldWorks.Application")
                        ├── SetUserPreferenceToggle(LICENSE_AUTO_ACTIVATE, False)  ← B-11 在这
                        ├── OpenDoc6
                        ├── SaveAs3（STEP）
                        └── CloseDoc
                                  │
                                  ├── success → atomic write step_cache → 返回 path
                                  └── fail    → 错误分类到 B-12 的 3 类码 → 记 log → miss
```

---

## 7. 向后兼容性

| 变更 | v2.11 行为 | Track B 行为 | 破坏性 |
|---|---|---|---|
| `find_toolbox_addin_guid()` 签名 | `-> Optional[str]` | **不变**；保留 wrapping | 否 |
| `discover_toolbox_addin_guid()` | 不存在 | `-> tuple[str?, str]` 新增 | 否（新增） |
| `SwInfo.toolbox_addin_enabled` | 字段 | 字段仍存在 + 填 | 否 |
| `SwToolboxAdapter.is_available()` 返回值 | Add-in 未启用 → False | Add-in 未启用 → True（满足其他 5 项时） | **是**（语义变化） |
| `sw_preflight matrix passed` | 7 项全 pass | blocking 6 项全 pass | **是**（一项放宽） |
| `run_preflight(strict=True)` 行为 | Add-in 未启用 → sys.exit(2) | Add-in 未启用 → 继续，只 warning | **是**（放宽）|
| `fix_addin_enable()` 错误文案 | `"ADDIN_ENABLE_FAILED: Toolbox Add-in GUID not discoverable from registry"` | 三段式命中时不报错；三段全 miss 时 `"ADDIN_DLL_NOT_FOUND: install_dir 下找不到 Toolbox Add-in DLL — 可能是 Standard 版未装 Toolbox Library"` | **是**（错误文案变） |
| `sw-warmup` 产物 | error_log 有内容、STEP 0 件 | smoke test 至少产 1 个 STEP | 否（修复）|

**所有破坏性变更都是"更宽松"方向**——v2.11 判 False 的场景 Track B 可能判 True，反之不会。不会让原先工作的用户回归。

### 7.0 `sw_preflight_cache.json` 兼容处理

`PreflightResult` 是 `@dataclass(frozen=True)`（`sw_preflight/types.py:34`），`preflight.py:98` 用 `asdict(result)` 序列化到 `artifacts/{run_id}/sw_preflight_cache.json`，`cached.get('preflight_result', {}).get('passed')` 在 `gen_std_parts.py:347` 读取判 cache 命中。

**语义变化风险**：`passed` 从 "7 项全 pass" 变成 "blocking 项全 pass"。若读取 v2.11 旧 cache JSON（`passed: true` 代表 7/7 通过）在 Track B 语义下仍算 passed，方向上兼容；若读取 v2.11 旧 cache `passed: false` (由 `addin_enabled` 失败导致) 在 Track B 语义下应被判为 advisory 不 block——但 cache 里没有区分字段。

**处理策略**：

1. `PreflightResult` 新增字段用 `field(default_factory=dict)` 而非 list（advisory_failures 改 dict，见 §4.3）确保反序列化 v2.11 cache 不炸
2. 在 `sw_preflight_cache.json` 顶层加 `cache_schema_version: 2`（v2.11 是隐式 v1）
   - **单一源定义**（防 bug #9 命名漂移重犯）：在 `sw_preflight/cache.py` 顶端定义 `CACHE_SCHEMA_VERSION = 2` 常量 + `CACHE_SCHEMA_VERSION_KEY = "cache_schema_version"`；所有 writer / reader 引用常量而非字面字符串；测试里也引用同常量
3. **`cache.read_cache()` 优先级调整（系统分析师审查）**：
   - **schema 不匹配直接返回 None**（= cache miss，重跑），**不看 TTL**
   - schema 匹配 + TTL 未过期 → 复用
   - schema 匹配 + TTL 过期 → 重跑
   - 这样避免"v1 cache 在 5 分钟 TTL 内被 v2 代码当成 passed"的 false positive

### 7.1 需要同步改的调用方

| 调用点 | 原行为 | Track B 行为 |
|---|---|---|
| `codegen/gen_std_parts.py:352` `run_preflight(...)` | Track A 已改 strict=False（2026-04-20 hotfix）| Add-in 未启用 → `is_available()=True` 后 std parts 真走 SW 路径；**strict=False 冻结**（见下）|

**`strict` 参数生命周期冻结声明**（skill 开发者 CRITICAL：防 bug #6 回流）：

- 2026-04-20 session 把 `gen_std_parts.py:352` 的 `strict=True` 改成 `strict=False` 解锁了 Add-in 未启用时 std_parts 无法生成的死锁
- Track B 内**任何 caller 均不得把 `strict` 加回 True**
- `run_preflight` 内 "blocking 有失败才 sys.exit(2)" 与 `strict=False` 的关系明确如下：

| strict | blocking 有失败 | advisory 有失败 | 行为 |
|---|---|---|---|
| True | 是 | — | `sys.exit(2)`（保留历史语义，但 Track B 所有入口都传 False 不触发）|
| False | 是 | — | 打 `[ERROR] preflight blocking failed: ...` + `return PreflightResult(passed=False)`，**不 sys.exit**；调用方（`gen_std_parts`）按 result.passed 决策继续 fallback or skip |
| False | 否 | 是 | 打 `[INFO] advisory: ...` + `return PreflightResult(passed=True, advisory_failures={...})` |
| False | 否 | 否 | 全绿 |

未来新增 blocking check **不得用 `strict=True` 作为启用开关**（应新开 spec 评审）；若真有"遇 blocking 必停 pipeline"需求，调用方自己判 `result.passed` 后 return，而非依赖 preflight 的 sys.exit。
| `codegen/gen_std_parts.py:347` `cached.get(...).get('passed')` | 直接读 cache passed | 见 §7.0 策略：缺 `advisory_failures` 字段的旧 cache `passed=False` 视为 miss 重跑 |
| `cad_pipeline.py cmd_codegen` | 无显式 preflight 调用（由 gen_std_parts 间接触发） | 不改 |
| `sw_preflight.preflight.run_preflight` | 遇第一 check 失败 short-circuit | 全 check 跑到底；blocking 有失败才 sys.exit(2) |
| `sw_preflight/report.py:72` `preflight.passed` | 报告里展示 `Toolbox: ❌` 若 addin 未启用 | 展示 `Toolbox: [WARN] (advisory: addin 未启用但 STEP 通道可用)` — **ASCII 前缀而非 `⚠️` emoji**（防 bug #3 GBK 编码重犯）；HTML 报告层面可替换回 emoji（HTML 是 UTF-8 输出非控制台）|
| `tests/test_sw_preflight_matrix.py` / `test_sw_preflight_preflight.py` | 7 项全 pass 断言 | 6 项 blocking pass 断言；`addin_enabled` 失败不影响 `passed` |
| `tests/test_sw_preflight_cache.py` | 按 v1 schema 断言 | 加 `cache_schema_version=2` 新测试；v1 schema cache 明确视为 miss 断言 |
| `tests/test_cad_pipeline_preflight_chain.py` | 按 v2.11 语义 | 链路级回归：advisory 失败不 short-circuit pipeline |
| `tests/test_cad_spec_gen_preflight_integration.py` | 按 v2.11 语义 | 改为断言 "addin=False + toolbox_path=healthy + edition=Pro → PartsResolver 调用 sw_toolbox" |
| `tests/test_gen_std_parts_preflight_integration.py` | 按 v2.11 mock addin=False 期望退出 2 | 期望继续生成 std parts；Track B hotfix `strict=False` 保持 |

---

## 8. 测试与验收

### 8.1 单元测试

**CI 兼容约束**（系统分析师审查）：所有使用 `winreg` / `pywin32` COM / `ctypes.windll` 的新测试必须加 `@pytest.mark.requires_windows` marker（`conftest.py` 已实现 `skipif not win32` 逻辑，记忆 `feedback_ci_windows_only_skipif`），确保 Linux CI matrix import 阶段不炸。

| 模块 | 新测试 | marker |
|---|---|---|
| `tests/test_discover_toolbox_addin_guid.py` | §3.3 5 条 case（Stage 1/2/3/全 miss/老函数兼容）| `@pytest.mark.requires_windows` |
| `tests/test_sw_toolbox_adapter_is_available.py` | (a) Add-in 禁用 + 其他满足 → `(True, None)`；(b) toolbox_path 不健康 → `(False, reason)`；(c) Standard 版 → `(False, "SW Standard edition does not ship Toolbox Browser DLL")`；(d) SW 未装 → `(False, "SW not installed")`；(e) 熔断 → `(False, reason)` | `@pytest.mark.requires_windows` |
| `tests/test_sw_preflight_is_blocking.py` | (a) `addin_enabled` 不在 `_BLOCKING_CHECKS`；(b) advisory 失败不影响 passed；(c) blocking 失败仍 passed=False；(d) `advisory_failures` dict 多项同时存在 | 纯 unit（可跨平台 mock）|
| `tests/test_sw_com_session_worker_suppress_ui.py` | worker 进程首行调 `app.Visible=False` + `UserControl=False` + `FrameState=0`（mock COM 断言调用链）| `@pytest.mark.requires_windows` |
| `tests/test_sw_detect_edition.py` | (a) HKLM InstalledProducts 含 Toolbox Browser → Premium；(b) 不含 → Standard；(c) 注册表键不存在 → unknown | `@pytest.mark.requires_windows` |
| `tests/test_sw_preflight_cache_schema.py` | (a) v1 cache 在 TTL 内仍返 None（miss）；(b) v2 cache TTL 内返 cached data；(c) v2 cache TTL 外返 None | 纯 unit（mock cache dir）|

### 8.2 集成测试

**必须通过**（本机手动烟测，非 CI）：
- `sw-warmup --smoke-test` exit 0 且产出 STEP
- `end_effector` full pipeline 回归：`resolve_report.json` 里 `sw_toolbox` 命中 ≥ 11（前提 Track A3 已合入可观测）
- 对比同 BOM pre-/post-Track-B：std_ee_*.py 里 `"simplified representation"` 文案**消失**于紧固件/轴承/密封/定位四类

### 8.3 回归测试

- 全量 `tests/test_sw_preflight_*` / `tests/test_parts_adapters*` 必须通过
- `tests/test_v291_regressions.py` 不退化
- 非 SW 环境（Linux CI / mock Windows 环境）行为 1:1 不变

---

## 9. 任务拆分

| Task | 子项 | 内容 | 预估 |
|---|---|---|---|
| B0 | precursor | **SW edition 探测**：实现 `sw_detect._detect_edition()` 填 `SwInfo.edition`；单测 `test_sw_detect_edition.py`（含反向验证：已知 Pro 机器跑 `_detect_edition` 必须返 professional，不能误判 Standard）；Standard 版分支路由到 bd_warehouse；_detect_edition 返 `tuple[str, list[str]]`（edition + 探测 source 列表供诊断拼接） | 0.75d |
| B1-0 | 调研 | spike：手动实证本机 SW 环境能否 sldprt→STEP（§5.1 实测），**必须先跑 edition 探测确认非 Standard** | 0.5d |
| B1-1 | B1 | `_scan_all_addins_by_description()` + 单测 | 0.5d |
| B1-2 | B1 | `_scan_addin_dll_clsid()` + 单测 | 1d |
| B1-3 | B1 | `discover_toolbox_addin_guid()` + 集成到 `fix_addin_enable` | 0.5d |
| B2-1 | B2 | `_check_toolbox_path_healthy()` + 单测 | 0.5d |
| B2-2 | B2 | `SwToolboxAdapter.is_available()` 解耦 Add-in + 单测 | 0.5d |
| B2-3 | B2 | `matrix.CHECK_ORDER` 加 `is_blocking` + `run_preflight` 语义变更 | 0.5d |
| B2-4 | B2 | 所有调用方（gen_std_parts / cad_pipeline / tests）同步更新 | 0.5d |
| B3-1 | B3 | B1-0 spike 结论驱动 —— 若原因 2，加 `SetUserPreferenceToggle` + 单测 | 0.5d |
| B3-2 | B3 | `sw-warmup --smoke-test` + 错误分类（B-12） | 0.5d |
| B3-3 | B3 | 本机手工烟测 + 对比 std_*.step 文件头 | 0.5d |
| **合计** | | | **~6d**（1 人 workweek） |

---

## 10. 风险与应急

| 风险 | 预兆 | 应急 |
|---|---|---|
| B1-0 spike 证实"原因 3"（SW 授权层拒绝）| `OpenDoc6` 返回特定授权错误码 | Track B 范围骤降——只交付 B0+B1+B2（优雅诊断），告诉用户 "Standard 版不支持 Toolbox Browser，升级 Pro 或用 bd_warehouse 替代"；不承诺 sldprt→STEP 贯通 |
| B2 的 is_available 语义变化破坏现有 spec 的断言 | v4 之前合入的测试 `assert not adapter.is_available()` 在本机会变绿 | 审计所有 `is_available` 相关断言，按新语义重写；不能因"更宽松"引入 false negative |
| B3 sldprt→STEP 虽然能跑但 SW 进程频繁崩 | smoke test 偶尔 timeout | 延续 v4 §5 的熔断 + session 周期重启策略，已足够 |

### 10.1 SW Edition × Toolbox 能力矩阵（SW 操作员 + 系统分析师审查）

| edition | `can_open_toolbox_sldprt` | `has_toolbox_browser_dll` | `can_license_auto_activate` | Track B routing |
|---|---|---|---|---|
| Standard | ❌ | ❌ | ✅ | `is_available() → (False, "Standard edition ...")`，routing 退 bd_warehouse |
| Professional | ✅ | ✅ | ✅ | 正常走 SW 真件路径 |
| Premium | ✅ | ✅ | ✅ | 正常走 SW 真件路径 |
| Trial | ⚠️ 30 天内 | ✅ | ⚠️ | 如 Pro（但 B-12 catch 授权过期错误 → 熔断 + warning）|
| Educational | ✅ | ✅ | ✅ | 如 Pro |
| unknown | 未知 | 未知 | 未知 | 当作可用放行，失败后走 B-12 错误分类 |

---

## §11 用户引导 + 失败诊断（非专业用户审查）

### 11.1 Standard 版用户的处理路径（北极星诚实评估）

第四轮审查（非专业用户视角）指出：SW Standard 版用户按 Track B 的方案跑完 → is_available 直接返 False → 退 bd_warehouse → 效果与不装 SW 相同。**这不是 bug 是物理约束**（Standard 版 SW 不含 Toolbox Browser DLL），但需要明确传达给用户：

**发版 release note 文案修订**：
- 旧: "SW 装即用 — 装了 SOLIDWORKS 即可得到真标准件几何"
- 新: **"SW Professional/Premium 装即用（全量标准件走 SW Toolbox）；SW Standard / 无 SW 用户自动走内置 bd_warehouse 模型库（ISO 标准件，装配尺寸准确，视觉风格与 SW 真件略有差异）"**

**用户侧决策树**：

```
用户装机了 SW 吗？
 ├── 否 → 走 bd_warehouse，不感知 Track B
 ├── 装了 SW Standard → 走 bd_warehouse；is_available reason 明示 "Standard edition"（见 §11.2）
 └── 装了 SW Professional/Premium
       ├── Toolbox Add-in 启用过 → Track B Stage 1 直接命中 → sw_toolbox 真件
       ├── 从未启用 Add-in → Stage 2/3 发现 GUID → Track B 自动写 HKCU 启用（见 B-17）→ sw_toolbox 真件
       └── 三段全 miss → advisory warning + 退 bd_warehouse（不阻断）
```

### 11.2 失败消息人话化映射

与 Track A §11.2 统一策略：stdout 出人话，artifacts/ log 里出完整技术细节。

| 技术 reason | 人话消息 | 建议动作 |
|---|---|---|
| `"SW Standard edition does not ship Toolbox Browser DLL"` | `您的 SOLIDWORKS 为 Standard 版，不含标准件库；本工具将使用内置 bd_warehouse 模型库，装配尺寸准确。` | `如需 SW 原生标准件几何，请升级到 SW Professional 或联系 SW 管理员` |
| `"edition=unknown (all 3 probes failed: com/registry/dll)"` | `无法确认 SOLIDWORKS 版本；本工具将尝试直接使用，若失败自动降级到内置模型库。` | `多次失败请将 artifacts/{run_id}/ 目录发给技术支持` |
| `"toolbox path unhealthy: swbrowser.sldedb missing"` | `未找到 SOLIDWORKS Toolbox 数据库文件。` | `SOLIDWORKS 安装可能不完整；请重新安装 Toolbox 组件` |
| `"ADDIN_DLL_NOT_FOUND: install_dir 下找不到 Toolbox Add-in DLL"` | `您的 SOLIDWORKS 未安装 Toolbox 模块。` | `这通常说明您的是 Standard 版；本工具已自动切换到内置模型库` |
| `"SwComSession circuit breaker tripped; edition was professional (source=registry)"` | `连续多次打开 SOLIDWORKS 失败，已切换到内置模型库。` | `检查 SOLIDWORKS 是否正常运行；或稍后重试` |
| `"ShowConfiguration2 failed: config 'M6x20' not found in ..."` | `标准件尺寸规格匹配失败（M6×20），该零件将使用内置库。` | `核对 BOM 里的规格命名是否符合 GB/T 常规写法` |

这些文案写入 `docs/user_troubleshooting.md`（Track A 同一份），发版一并更新。

### 11.3 Maintainer 发版 checklist

v2.13（Track B 发布）release 硬门：

- [ ] B0 edition 探测在 3 种 SW 版次上人工验证（Standard / Professional / Premium 各至少 1 台）
- [ ] B1-0 smoke test：本机真 SW 单件 sldprt→STEP 成功（含 ShowConfiguration2 切 config）
- [ ] `parts_library.yaml` 新增 `solidworks_toolbox.config_name_resolver` 段，覆盖 ≥ 5 类常用 GB/T 标准件（螺栓/螺母/垫圈/O 圈/销）
- [ ] `sw_preflight/cache.py` 顶端定义 `CACHE_SCHEMA_VERSION = 2` + `CACHE_SCHEMA_VERSION_KEY` 常量
- [ ] `docs/user_troubleshooting.md` 覆盖 §11.2 所有失败消息
- [ ] release note 明示"Pro+ 装即用；Standard/无 SW 走 bd_warehouse"

---

## 附录 A：涉及文件

**修改**：
- `adapters/solidworks/sw_detect.py` — `discover_toolbox_addin_guid` + `_scan_all_addins_by_description` + `_scan_addin_dll_clsid`
- `adapters/parts/sw_toolbox_adapter.py` — `is_available()` 解耦
- `sw_preflight/matrix.py` — `CHECK_ORDER` 加 `is_blocking` + `_check_toolbox_path_healthy`
- `sw_preflight/preflight.py` — `run_preflight` passed 语义
- `sw_preflight/types.py` — `PreflightResult` 可能加 `blocking_failures` 字段
- `adapters/solidworks/sw_com_session.py` — `convert_sldprt_to_step` 加 SetUserPreferenceToggle
- `tools/sw_warmup.py` — `--smoke-test` 标志 + 错误分类
- `codegen/gen_std_parts.py` / `cad_pipeline.py` — 调用方同步
- `tests/test_sw_preflight_matrix.py` — 语义变更的断言更新
- `tests/test_parts_adapters.py`（如涉及 Toolbox）— 同上

**新增**：
- `tests/test_discover_toolbox_addin_guid.py`
- `tests/test_sw_toolbox_adapter_is_available.py`
- `tests/test_sw_preflight_is_blocking.py`
- `tests/test_sw_com_session_suppress_dialog.py`
- `artifacts/{run_id}/sw_warmup_smoke_error.log`（运行时）

---

## 附录 B：v0.1 → v0.2 修订日志（审查闭环）

| # | 审查严重性 | 问题 | 修订位置 |
|---|---|---|---|
| R1 | CRITICAL | §4.3 原 `CHECK_ORDER` 改为三元素 tuple 会破坏 monkeypatch（现状 `list[tuple[str, str]]`，第二元素是字符串而非函数引用，为 `unittest.mock.patch` 服务）| §4.3 改为"`CHECK_ORDER` 保持两元素；新增独立 `_BLOCKING_CHECKS: frozenset[str]` 常量"方案 |
| R2 | CRITICAL | §4.3/附录 A `_check_toolbox_path_healthy` 与现有 `_check_toolbox_path` 的替换/新增关系不明 | §4.3 明确为**重命名替换**（`_check_toolbox_path` → `_check_toolbox_path_healthy`），并澄清 `try_one_click_fix:604` dispatch 不变 |
| R3 | WARNING | §3.1 引用的老函数遗漏 `_is_toolbox_guid` 前缀匹配分支 | §3.1 补完三口径；§3.2 `_scan_all_addins_by_description` 明确复用 `_is_toolbox_guid` |
| R4 | WARNING | §3.2 `_ADDINS_CANDIDATES` 静态常量用了未定义的 `year` 变量 | §3.2 改为 `_addins_candidates(version_year: int)` 惰性函数 |
| R5 | WARNING | §5.2 `SetUserPreferenceToggle` 原落点在 `SwComSession.convert_sldprt_to_step`；实际父进程不持 COM，该方法仅 subprocess 编排（见 `sw_com_session.py:4-11`）| §5.2 改落点到 `adapters/solidworks/sw_convert_worker.py`；§6.2 数据流图同步更新 |
| R6 | WARNING | §4.3 `PreflightResult` 是 `@dataclass(frozen=True)` + `asdict` 序列化；加 `blocking_failures` 字段会破坏旧 cache 反序列化 | 新增 §7.0 "`sw_preflight_cache.json` 兼容处理"：加 `cache_schema_version` + 新字段用 `default_factory`，语义不匹配的旧 cache 视为 miss |
| R7 | INFO | §7.1 调用方更新表的 line 号估测，需换真实 line | §7.1 按 2026-04-20 session hotfix 后的实际行号（`gen_std_parts.py:347/352`、`report.py:72`）更新 |

---

## 附录 C：v0.2 → v0.3 修订日志（5 角色专家审查闭环）

审查角色：系统架构师 / SW 操作员 / 3D 设计师 / 机械设计师 / 系统分析师。

### C.1 CRITICAL 修正（实施前必改）

| # | 来源角色 | 问题 | 修订位置 |
|---|---|---|---|
| C1 | SW 操作员 | `swLicenseAutoActivate=277` 枚举号错 + toggle 选错，抑制不了 Toolbox Browser modal 对话框 | §2 决策表 B-14；§5.2 worker 代码重写：`app.Visible=False` + `app.UserControl=False` + `app.FrameState=0` 三连；删除 `SetUserPreferenceToggle(277, ...)` |
| C2 | SW 操作员 | Standard 版不含 Toolbox Browser DLL，B-2 "装即用"承诺对 Standard 用户破产 | §2 决策表 B-13 新增；§4.2 `is_available()` 加 edition 分支；§9 任务表加 Task B0；§10.1 新增 edition × 能力矩阵 |
| C3 | SW 操作员 | Configuration 不切换 = STEP 尺寸错（M6×20/M6×25 共用 sldprt）| §2 决策表 B-16；§5.2 worker 加 `ShowConfiguration2(target_config_name)`；resolver 层 config 匹配失败时跳过 sw_toolbox 落 bd_warehouse |
| C4 | 系统分析师 | "sw_toolbox 命中 ≥ 11" 主观，没 BOM 分类依据 | §1.4.1 新增 BOM 分类清单；§1.4.2 目标改为 "GB/T 分类件数 × 85%" |

### C.2 WARNING 修正

| # | 来源 | 问题 | 修订位置 |
|---|---|---|---|
| W1 | SW 操作员 | `_check_toolbox_path_healthy` 要求 `.sldsetupdata` 存在会误判新装机 | §2 决策 B-8：`.sldsetupdata` 降为 advisory，只硬要求 `swbrowser.sldedb` |
| W2 | SW 操作员 | Dispatch 会复用用户手工开的 SW 实例造成串行阻塞 | §2 决策 B-15；§5.2 worker 改 `DispatchEx` |
| W3 | 系统架构师 | B-10 Stage 3 命中 DLL 却只 log INFO 功能半截；可写 HKCU（用户权限够）让零配置更彻底 | §2 决策 B-17 新增 |
| W4 | 系统架构师 | `_BLOCKING_CHECKS` 未给新 check 归类判据 | §4.3 "`_BLOCKING_CHECKS` 判据"段新增决策 B-18 |
| W5 | 系统架构师 | `_LICENSE_AUTO_ACTIVATE = 277` 硬编码魔数（本轮直接删除 → 不再适用）| 见 C1 |
| W6 | 系统分析师 | `advisory_failures: list[str]` 多项 advisory 塞不下文案 | §4.3 改为 `dict[str, DiagnosisInfo]` |
| W7 | 系统分析师 | cache TTL 与 schema 优先级未明 | §7.0 处理策略第 3 条：schema 不匹配优先于 TTL，直接 miss |
| W8 | 系统分析师 | 回归测试文件未具名 | §7.1 补 `test_cad_pipeline_preflight_chain.py` / `test_cad_spec_gen_preflight_integration.py` |
| W9 | 系统分析师 | Windows-only API 新测试未加 marker | §8.1 每条新测试加 `@pytest.mark.requires_windows`（已有 conftest 实现）|

### C.3 INFO / 暂不处理

- 架构 I1（Track A /B reason 字符串已通过 Track A §5.2 + §5.4 修复，Track B 这边只需对齐契约返 reason）
- SW 操作员 I1（"首次打开 SW 任意 part 生成 AddInsStartup 条目"降为用户指引文档，不写入 spec）
- SW 操作员 I2（sldedb 锁）：已通过 B-15 DispatchEx 隔离
- 系统分析 I1-I5：纹理表维护、Stage 3 filesystem 缓存、pipeline_config 兜底、UNC 性能 —— Track C 或 `docs/project_debt.md`

**最高优先级 3 条** —— v0.3 必修且已落地：C1 (UI 抑制手段替换) / C2 (edition 探测 + Standard 分支) / C3 (Toolbox config 切换)。

---

## 附录 D：v0.3 → v0.4 修订日志（第四轮审查闭环）

审查角色：**非专业用户** + **skill 开发者** + **一致性+边界综合**。

### D.1 CRITICAL 修正（实施前必改）

| # | 来源 | 问题 | 修订位置 |
|---|---|---|---|
| D1 | 一致性 C2.2 | `_check_toolbox_path_healthy -> tuple[bool, str]` 与 A §5.4.1 `Optional[str]` 契约不对齐（健康时 reason 是空串 vs None）| §2 B-8 签名改 `tuple[bool, Optional[str]]`；健康时返 `(True, None)` |
| D2 | skill dev C2 | bug #4 重犯：`edition=unknown` 放行把"不知道"当"可用"，用户看不到根因 | §4.2 _detect_edition 返 `tuple[str, list[str]]`；unknown 时 reason 拼接 `"edition=unknown (all 3 probes failed: com/registry/dll)"`；熔断 reason 同拼接 edition 来源 |
| D3 | skill dev C4 | bug #3 重犯风险：`report.py:72` `⚠️` emoji 在 GBK 控制台炸 | §7.1 表 report.py 行改 `[WARN]` ASCII 前缀；HTML 报告层面可保留 emoji |
| D4 | skill dev C5 | bug #6 回流风险：`strict=False` vs `blocking 有失败才 sys.exit(2)` 语义冲突 | §7.1 新增 "strict 参数生命周期冻结声明" 4 行决策表 |
| D5 | skill dev W3 | `ShowConfiguration2` 返 bool 不抛不 check 继续 SaveAs3 默认 config（bug #10 同族）| §5.2 worker 代码加 `if not doc.ShowConfiguration2(name): raise SwConvertError(...)` |
| D6 | skill dev C6 | bug #9 重犯：`cache_schema_version` 字面常量无单一源 | §7.0 新增 `CACHE_SCHEMA_VERSION = 2` + `CACHE_SCHEMA_VERSION_KEY` 常量声明 |
| D7 | 一致性 C4.6 | pipeline_config.json 缺失时 detect_solidworks 兜底未说 | §4.2 后新增段：首次装机走内置 `shutil.which("SLDWORKS.EXE")` 兜底 |
| D8 | 非专业用户 U1 | Standard 版破产是物理约束但文档/release note 误导"装即用" | §11.1 新增北极星诚实评估 + release note 文案修订 + 用户侧决策树 |

### D.2 WARNING 修正

| # | 来源 | 问题 | 修订位置 |
|---|---|---|---|
| W1 | skill dev W4 | BOM→config 名反查映射表源未定 | §2 B-16 明确 `parts_library.yaml.solidworks_toolbox.config_name_resolver` 单一源 |
| W2 | skill dev W5 | edition 探测可能误判 Pro 为 Standard，未证伪 | §9 Task B0 扩充：加反向验证测试（已知 Pro 机器必须不返 Standard）|
| W3 | 非专业用户 U2 | 错误消息不人话 | 新增 §11.2 人话化映射表（与 Track A §11.2 统一 `docs/user_troubleshooting.md`）|
| W4 | 非专业用户 U3 | B1-0 smoke test 用户做不了 | §11.3 Maintainer 发版 checklist 把 B1-0 列为 release 硬门 |
| W5 | 一致性 C4.2 | UNC 路径 `_check_toolbox_path_healthy` 行为未说 | §2 B-8 加 UNC 预检 + reason 明示 |

### D.3 INFO / 仍然暂不处理

- 一致性 C4.3 跨 SW 版本（2025）: `FrameState`/`Visible` 等行为假设 2024 稳定；2025 升级走 `docs/project_debt.md`
- 一致性 C4.7 中文用户名/路径：两 Track 统一延后
- skill dev I2 真 SW smoke 不在 CI：已在 §1.5 明示，属产品决策不修
- skill dev I4 v2 cache 被 v1 reader 读: 回滚场景概率低，延后

**最优先 3 条 v0.4 必修且已落地**：D1（契约类型对齐）/ D2（edition unknown reason 拼接）/ D8（Standard 用户诚实引导）。本轮关闭 8 条 CRITICAL，Track B 无 blocker 进入 writing-plans 阶段。

### D.4 第 1-4 轮审查的收敛观察

Track B 从 v0.1 到 v0.4 共 4 轮审查、汇总 ≈ 30 条 CRITICAL + 50+ WARNING 修订。**主要 bug 类别**：
- v0.1 → v0.2：虚构函数名 + 工具调用错位（`parts_resolver.resolve()` 模块级 vs 类方法；`CHECK_ORDER` tuple 破坏 monkeypatch）
- v0.2 → v0.3：SW 产品知识空洞（Standard 版无 Toolbox Browser；multi-config sldprt；`SetUserPreferenceToggle=277` 枚举号错）
- v0.3 → v0.4：silent-fail 同族风险（ShowConfiguration2 返 bool；edition unknown；⚠️ emoji；strict+blocking 冲突）

**收敛曲线**：每轮平均新发现 ≈ 5 条 CRITICAL；v0.4 后剩余 CRITICAL 预估 ≤ 2 条（属 writing-plans 阶段 TDD 可发现的实现细节，不需再开 spec 审查轮）。
