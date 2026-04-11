"""render_3d.py 在真实 Blender 进程内的 import smoke（v2.9.2 Tier 2）。

只做一件事：把 `render_3d.py` + 其依赖的 `render_config.py` 部署到临时
目录，让 Blender headless 进程尝试 import 它，断言 stdout 出现哨兵字符串
`RENDER3D_OK`。**不渲染任何像素**。

为什么这么轻？
- 真实的单帧渲染需要一个完整的 Blender 场景（参数化 cube + 材质 +
  camera + 光源）—— 构造成本远超本测试预期的"发布前 <1 分钟"目标
- 本测试的真正价值：**catches bpy API 漂移 / 语法错** —— 每次 Blender
  升级，render_3d.py 如果调用了已被移除或签名变动的 bpy API，import 阶段
  就会炸。这种 bug 在离线 pytest 里完全看不到

覆盖的漂移场景：
- `bpy.data.lights.new(...)` → 参数名变更（Blender 4.x 偶尔改）
- `matrix_world` / `obj.matrix_world @ vec` 运算符被弃用
- `from mathutils import Vector` 导入路径变更
- 任何模块级调用 `bpy.context.xxx`（立即执行时会触发 API 漂移）

auto-skip 条件：`cad_paths.get_blender_path()` 找不到 Blender 可执行文件
—— CI runner 没装 Blender 时保持绿色不阻断。

运行方式：
- 默认：`pytest` 会跳过本文件（`-m "not slow and not blender"` 隐式）
- 手动触发：`pytest -m blender` 只跑 Blender 层测试
- 发布前：`pytest -m "blender or slow"` 跑完所有重型测试
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def _blender_available() -> bool:
    """Check if Blender is reachable via `cad_paths.get_blender_path()`.

    Uses the skill's own resolution logic so this test skips exactly when
    the real pipeline would also fail to find Blender — no divergence.
    """
    try:
        from cad_paths import get_blender_path

        return get_blender_path() is not None
    except Exception:
        return False


@pytest.mark.blender
@pytest.mark.skipif(
    not _blender_available(),
    reason="Blender not found via cad_paths.get_blender_path() — skip on CI",
)
def test_render_3d_importable_inside_blender_headless(tmp_path):
    """render_3d.py 必须能被真实 Blender 进程 import 而不抛 bpy API 错。"""
    from cad_paths import get_blender_path

    blender = get_blender_path()
    assert blender, "Blender path should be resolvable (checked by skipif)"

    # render_3d.py 依赖 render_config.py（内部 `import render_config as rcfg`）
    # 同目录查找，所以两个文件必须一起部署
    render_3d_src = _REPO_ROOT / "src" / "cad_spec_gen" / "render_3d.py"
    render_config_src = _REPO_ROOT / "render_config.py"
    assert render_3d_src.exists(), f"render_3d.py 不在 {render_3d_src}"
    assert render_config_src.exists(), f"render_config.py 不在 {render_config_src}"

    # 复制到 tmp_path 构造一个隔离的"部署场景"
    (tmp_path / "render_3d.py").write_text(
        render_3d_src.read_text(encoding="utf-8"), encoding="utf-8"
    )
    (tmp_path / "render_config.py").write_text(
        render_config_src.read_text(encoding="utf-8"), encoding="utf-8"
    )

    # 构造最小的 import 脚本 —— 若 render_3d 在模块级调用了 bpy API，
    # `import render_3d` 就会触发并暴露问题
    expr = (
        "import sys; "
        f"sys.path.insert(0, {str(tmp_path)!r}); "
        "import render_3d; "
        "print('RENDER3D_OK')"
    )

    # --background 让 Blender 以 headless 模式启动，不弹 GUI
    # --python-expr 直接执行 Python 表达式
    result = subprocess.run(
        [blender, "--background", "--python-expr", expr],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,  # Blender 冷启动 ~5s，给足 2 分钟 headroom
    )

    # 断言哨兵字符串出现 —— 若 import 失败，stderr 里会有 ImportError 或
    # bpy AttributeError，stdout 里就没有 RENDER3D_OK
    assert "RENDER3D_OK" in result.stdout, (
        f"render_3d.py 在 Blender 内 import 失败。\n"
        f"--- stdout (tail) ---\n{result.stdout[-1500:]}\n"
        f"--- stderr (tail) ---\n{result.stderr[-1500:]}"
    )
