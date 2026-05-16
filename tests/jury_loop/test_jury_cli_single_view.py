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


# ==== Task 6.1.2：main() --single-view 分支 ==== #


def _fake_llm_response(score: int = 78, verdict: str = "preview") -> object:
    """构造一个 LlmResponse-like 对象，供 monkeypatch 替换 request_jury_verdict 用。"""
    from types import SimpleNamespace

    content = (
        '{"semantic_checks": {"geometry_preserved": true, "material_consistent": true,'
        ' "photorealistic": false, "no_extra_parts": true, "no_missing_parts": true},'
        f' "photoreal_score": {score}, "reason": "plastic look, flat lighting",'
        f' "verdict": "{verdict}"' "}"
    )
    return SimpleNamespace(
        content_text=content,
        finish_reason="stop",
        http_status=200,
        attempts=1,
        latency_ms=100,
        vendor_request_id="req-test",
    )


def _patch_config_and_llm(
    monkeypatch: pytest.MonkeyPatch,
    *,
    llm_responses: list[object] | None = None,
    llm_error: Exception | None = None,
) -> list[str]:
    """统一 mock load_jury_config + request_jury_verdict。

    llm_responses: 预设响应列表（按调用顺序逐个 pop）
    llm_error: 若非 None，每次调用都抛该异常
    返回：record 列表，记录每次 LLM 调用的 image_path（测试断言用）
    """
    from types import SimpleNamespace

    profile = SimpleNamespace(
        id="test", kind="openai-compatible", model="test-model",
        api_base_url="https://example.test", cost_per_call_usd=0.005,
    )
    caps = SimpleNamespace(min_photoreal_score=60)
    monkeypatch.setattr(
        "tools.photo3d_jury.load_jury_config",
        lambda _path: (profile, caps),
    )

    call_record: list[str] = []
    responses_iter = iter(llm_responses or [])

    def _fake_request(*, image_path, **_kwargs):  # noqa: ANN001
        call_record.append(str(image_path))
        if llm_error is not None:
            raise llm_error
        try:
            return next(responses_iter)
        except StopIteration:
            raise AssertionError("LLM mock 调用次数超过预设响应数")

    monkeypatch.setattr("tools.photo3d_jury.request_jury_verdict", _fake_request)
    return call_record


def test_single_view_single_image_emits_json_list_one_element(
    tmp_path, monkeypatch, capsys,
) -> None:
    """--single-view V1 --image baseline.jpg → stdout 输出 1 元素 list / exit 0。"""
    import json
    from tools.photo3d_jury import main

    img = tmp_path / "baseline.jpg"
    img.write_bytes(b"fake jpeg bytes")
    _patch_config_and_llm(monkeypatch, llm_responses=[_fake_llm_response(score=78)])

    rc = main([
        "--subsystem", "dummy",
        "--config", str(tmp_path / "fake_config.json"),
        "--single-view", "V1",
        "--image", str(img),
    ])
    assert rc == 0
    out = capsys.readouterr().out.strip()
    payload = json.loads(out)
    assert isinstance(payload, list) and len(payload) == 1
    item = payload[0]
    assert item["view"] == "V1"
    assert item["image_path"] == str(img)
    # v2.37.9 §11-N6 改动 1e (rev 4 真 vendor 实测 fix) — photorealistic=false 触发 not all(checks)
    # → semantic_checks_failed → needs_review（原 preview 语义升级，retry path）
    assert item["verdict"] == "needs_review"
    assert item["photoreal_score"] == 78


def test_single_view_batch_two_images_emits_json_list_two_elements(
    tmp_path, monkeypatch, capsys,
) -> None:
    """--image a.jpg b.jpg → stdout list 2 元素，按入参顺序。"""
    import json
    from tools.photo3d_jury import main

    img_a = tmp_path / "a.jpg"
    img_a.write_bytes(b"a")
    img_b = tmp_path / "b.jpg"
    img_b.write_bytes(b"b")
    call_record = _patch_config_and_llm(
        monkeypatch,
        llm_responses=[_fake_llm_response(score=70), _fake_llm_response(score=85)],
    )

    rc = main([
        "--subsystem", "dummy",
        "--config", str(tmp_path / "fake_config.json"),
        "--single-view", "V1",
        "--image", str(img_a), str(img_b),
    ])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert [item["image_path"] for item in payload] == [str(img_a), str(img_b)]
    assert [item["photoreal_score"] for item in payload] == [70, 85]
    assert call_record == [str(img_a), str(img_b)]  # 调用顺序锁


def test_single_view_without_image_fails_with_exit_2(
    tmp_path, monkeypatch, capsys,
) -> None:
    """缺 --image → stderr 含错误 + exit 2（main() 自定义校验）。"""
    from tools.photo3d_jury import main

    _patch_config_and_llm(monkeypatch, llm_responses=[])

    rc = main([
        "--subsystem", "dummy",
        "--config", str(tmp_path / "fake_config.json"),
        "--single-view", "V1",
        # 故意不传 --image
    ])
    assert rc == 2
    assert "--image" in capsys.readouterr().err


def test_single_view_llm_failure_yields_needs_review_verdict(
    tmp_path, monkeypatch, capsys,
) -> None:
    """LLM 调用抛异常 → 该图 verdict=needs_review + 写入 anomalies / exit 0（调用方按 needs_review 走 jury_unavailable）。"""
    import json
    from tools.photo3d_jury import main

    img = tmp_path / "baseline.jpg"
    img.write_bytes(b"x")
    _patch_config_and_llm(
        monkeypatch, llm_error=RuntimeError("vendor network down"),
    )

    rc = main([
        "--subsystem", "dummy",
        "--config", str(tmp_path / "fake_config.json"),
        "--single-view", "V1",
        "--image", str(img),
    ])
    assert rc == 0  # CLI 成功但 verdict 表 LLM 失败
    payload = json.loads(capsys.readouterr().out)
    assert len(payload) == 1
    assert payload[0]["verdict"] == "needs_review"
    assert "llm_call_failed" in payload[0]["parse_anomalies"]
