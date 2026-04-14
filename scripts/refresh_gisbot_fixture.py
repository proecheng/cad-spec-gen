"""从 GISBOT 源 CAD_SPEC.md 抽 §3 + §5 生成 tests fixture。

避免在 tests/ 直接依赖绝对路径 D:/Work/cad-tests/。
每次 GISBOT 更新后需手动重跑本脚本同步 fixture。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

SRC = Path("D:/Work/cad-tests/GISBOT/cad/end_effector/CAD_SPEC.md")
DST = Path(__file__).parent.parent / "tests" / "fixtures" / "gisbot_cad_spec_snippet.md"


def main() -> int:
    if not SRC.exists():
        print(f"[error] 源文件不存在: {SRC}", file=sys.stderr)
        return 2

    text = SRC.read_text(encoding="utf-8")

    def slice_section(num: int) -> str:
        pat = re.compile(rf"^##\s+{num}\.[^\n]*\n", re.MULTILINE)
        next_pat = re.compile(r"^##\s+\d+\.", re.MULTILINE)
        m = pat.search(text)
        if not m:
            return ""
        start = m.start()
        rest = text[m.end():]
        nm = next_pat.search(rest)
        end = m.end() + (nm.start() if nm else len(rest))
        return text[start:end].rstrip() + "\n\n"

    out = "# GISBOT CAD_SPEC Snippet (§3 + §5)\n\n"
    out += "> 自动生成，请勿手工编辑。刷新: `python scripts/refresh_gisbot_fixture.py`\n\n"
    out += slice_section(3)
    out += slice_section(5)

    DST.parent.mkdir(parents=True, exist_ok=True)
    DST.write_text(out, encoding="utf-8")
    print(f"[ok] wrote {DST} ({len(out)} chars)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
