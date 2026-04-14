# SW COM Spike 报告（SW-B0）

> 状态: **BLOCKED — 开发机 SW 当前无法启动**，spike 推迟
> 日期: 2026-04-13

## 环境

- OS: Windows 11
- Python: 3.12 (D:\Python312)
- pywin32: 311（已装，`import win32com.client` 正常）
- SW 安装: `D:\SOLIDWORKS Corp\SOLIDWORKS\SLDWORKS.exe`
- SW 版本: 2024（按用户记录）
- Toolbox 目录: `C:\SOLIDWORKS Data\browser\`（存在，含 sldprt 文件）

## 已观察到的事实

1. **Toolbox 目录存在且可扫描**
   - spike 脚本成功发现候选 sldprt: `C:\SOLIDWORKS Data\browser\Ansi Inch\bearings\ball bearings\instrument ball bearing_ai.sldprt` (320478 bytes)

2. **pywin32 Dispatch 调用失败**
   ```
   win32com.client.Dispatch("SldWorks.Application")
   ↓
   pywintypes.com_error: (-2147221021, '服务无法使用', None, None)   # connect 失败（无已运行实例）
   ↓
   pywintypes.com_error: (-2146959355, '服务器执行失败', None, None) # CoCreateInstance 启动新 server 失败
   ```
   - `-2147221021` = `MK_E_UNAVAILABLE`
   - `-2146959355` = `CO_E_SERVER_EXEC_FAILURE`

3. **手动双击 SLDWORKS.exe 同样失败**（弹出与 COM 相同的错误对话框）
   - 结论：**失败发生在 SW 进程层，而非 COM 层**。COM 能找到 CLSID 但 SW 可执行文件启动不起来。

4. **sldworks_fs.exe 进程存在**（Feature Server，11884，85MB 工作集）但 SLDWORKS.exe 主进程未启动

## 可能原因（需用户排查）

按概率排序：

1. **SW license / 激活状态问题** — 最常见；license server 失联 / 订阅过期 / 首次激活未完成
2. **SW 2024 Service Pack 损坏** — 需要从 SW 安装管理器修复/重装
3. **Feature Server 残留锁** — `sldworks_fs.exe` 可能锁住了某些资源。`taskkill` 该进程后再试主程序
4. **Windows 11 兼容性问题** — 某些 SW 2024 早期版本对 Win 11 某些更新不兼容
5. **注册表/DCOM 权限损坏** — 较少见

## 对 Phase SW-B 实施的影响

**不影响 Part 1 的 TDD 实施**。原因：
- Part 1 所有 Tasks 1-10 是**纯 stdlib + mock COM** 单元测试，不依赖真实 SW
- spec §1.1 承诺"无 SW 时字节等同"，正好覆盖当前情景
- `is_available()` 的 6 项检查中 `pywin32_available=True` 但 `com_available` 和后续调用会因 SW 进程启动不了而 fallthrough

**影响 Part 2 的 SW-B9 真实 COM 验收**：
- 开发机 SW 修复前，`@requires_solidworks` 测试全部 skip
- SW-B9 的 (b)(c)(d)(e) 硬门（真实 BOM 覆盖率 / session 重启 / 装配回归 / ROI 熔断）全部无法执行
- Part 2 实施可以推进到"一切就绪，等 SW 恢复即可跑验收"这个状态，但最终交付被 SW 环境 block

## 待 SW 恢复后需验证的事项（spike 清单）

| # | 验证项 | spec 决策 |
|---|--------|---------|
| 1 | Dispatch + LoadAddIn 冷启动总耗时是否 ≤ 90s | #10 |
| 2 | `OpenDoc6` Silent 选项是否真的无对话框（Toolbox configuration 弹框风险） | QA #2 |
| 3 | `SaveAs3` 产出 STEP header 是否以 `ISO-10303` 开头 | #23 |
| 4 | STEP units 默认是否 mm | 决策 #25 / §1.3 |
| 5 | 连续打开 5 个 Toolbox 零件的 SW 进程内存趋势 | #11 |

## 下一步

**选项 A**: 用户修复 SW 环境后重跑 `tmp/sw_com_spike.py`，补全本报告
**选项 B**: 跳过 spike，先按 Part 1 plan 推进（纯 mock 测试），SW 恢复后再回补 spike

当前选择: **待定**
