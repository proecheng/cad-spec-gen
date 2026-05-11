"""tools/photo3d_jury.py --single-view + --image CLI flag 测试（CP-6 Task 6.1.1）。

测试矩阵：
- Task 6.1.1：3 case 验证 argparse 注册 + SUPPRESS 隐藏 help
- Task 6.1.2：4 case 验证 main() --single-view 分支契约
"""
from __future__ import annotations

import pytest


# ==== Task 6.1.1：CLI flag 注册 ==== #


def test_single_view_image_flags_register_in_parser() -> None:
    """--single-view <V> --image <p> 应被 argparse 接受。"""
    from tools.photo3d_jury import _build_parser

    parser = _build_parser()
    args = parser.parse_args([
        "--subsystem", "dummy",
        "--single-view", "V1",
        "--image", "baseline.jpg",
    ])
    assert args.single_view == "V1"
    assert args.image == ["baseline.jpg"]


def test_single_view_image_nargs_plus_accepts_batch() -> None:
    """--image nargs='+' 支持多张图（SP3 batch 兼容）。"""
    from tools.photo3d_jury import _build_parser

    parser = _build_parser()
    args = parser.parse_args([
        "--subsystem", "dummy",
        "--single-view", "V1",
        "--image", "a.jpg", "b.jpg", "c.jpg",
    ])
    assert args.image == ["a.jpg", "b.jpg", "c.jpg"]


def test_single_view_image_flags_hidden_from_help() -> None:
    """两 flag 都用 argparse.SUPPRESS 隐藏 help（N-3 外行用户不误用）。"""
    from tools.photo3d_jury import _build_parser

    parser = _build_parser()
    help_text = parser.format_help()
    assert "--single-view" not in help_text, "SUPPRESS 失效：--single-view 出现在 help 中"
    assert "--image" not in help_text, "SUPPRESS 失效：--image 出现在 help 中"


def test_single_view_without_image_fails_argparse() -> None:
    """这一 case 由 main() 自定义 validator 处理（argparse required= 与其他 mode 冲突），先占位锁定 RED。

    完整契约见 Task 6.1.2：缺 --image 时 main() 写 stderr + 返 exit code 2。
    """
    pytest.skip("由 Task 6.1.2 main() 校验，本测试在 Task 6.1.2 落地后改成 main() 集成测试")
