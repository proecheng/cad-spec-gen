"""生成 fake_toolbox 目录结构用于单元测试（v4 决策 #2/#21）。"""
from __future__ import annotations
import sys
from pathlib import Path

FIXTURE_ROOT = Path(__file__).parent / "fake_toolbox"

STRUCTURE = {
    "GB/bolts and studs/hex bolt.sldprt": b"",
    "GB/bolts and studs/stud.sldprt": b"",
    "GB/bolts and studs/sizes.xls": b"",             # ★ 应被过滤
    "GB/nuts/hex nut.sldprt": b"",
    "GB/screws/socket head cap screw.sldprt": b"",
    "GB/bearing/deep groove ball bearing.sldprt": b"",
    "GB/drawings/sample.slddrw": b"",                 # ★ 应被过滤
    "GB/metadata/catalog.xml": b"",                   # ★ 应被过滤
    "ISO/bolts/hex bolt.sldprt": b"",
    "ISO/nuts/hex nut.sldprt": b"",
    "ISO/bearings/deep groove ball bearing.sldprt": b"",
    "DIN/bolts/hex bolt.sldprt": b"",
}


def generate(root: Path = FIXTURE_ROOT) -> None:
    for rel, content in STRUCTURE.items():
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)


if __name__ == "__main__":
    generate()
    print(f"Generated {len(STRUCTURE)} files under {FIXTURE_ROOT}")
    sys.exit(0)
