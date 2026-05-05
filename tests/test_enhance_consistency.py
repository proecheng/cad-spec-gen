from PIL import Image, ImageDraw


def _source(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (256, 256), (245, 245, 245))
    draw = ImageDraw.Draw(image)
    draw.rectangle((64, 64, 192, 192), fill=(20, 90, 150))
    image.save(path)


def _shifted(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (256, 256), (245, 245, 245))
    draw = ImageDraw.Draw(image)
    draw.rectangle((100, 64, 228, 192), fill=(20, 90, 150))
    image.save(path)


def _cropped(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (256, 256), (245, 245, 245))
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 64, 128, 192), fill=(20, 90, 150))
    image.save(path)


def _low_contrast(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (256, 256), (132, 132, 132))
    draw = ImageDraw.Draw(image)
    draw.rectangle((64, 64, 192, 192), fill=(138, 138, 138))
    image.save(path)


def _source_sized(path, size):
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", size, (245, 245, 245))
    draw = ImageDraw.Draw(image)
    width, height = size
    draw.rectangle(
        (
            int(width * 0.25),
            int(height * 0.25),
            int(width * 0.75),
            int(height * 0.75),
        ),
        fill=(20, 90, 150),
    )
    image.save(path)


def _manifest(project_root, render_dir, files):
    return {
        "schema_version": 2,
        "status": "pass",
        "run_id": "RUN001",
        "subsystem": "demo",
        "render_dir_rel_project": render_dir.as_posix(),
        "render_dir_abs_resolved": str(render_dir),
        "files": [
            {
                "view": view,
                "path_rel_project": source.relative_to(project_root).as_posix(),
                "path_abs_resolved": str(source),
                "sha256": f"sha256:{view}",
                "qa": {"passed": True},
            }
            for view, source in files
        ],
    }


def test_identical_enhanced_image_is_accepted(tmp_path):
    from tools.enhance_consistency import compare_enhanced_image

    src = tmp_path / "source.png"
    enhanced = tmp_path / "enhanced.png"
    _source(src)
    _source(enhanced)

    result = compare_enhanced_image(src, enhanced, min_similarity=0.85)

    assert result["status"] == "accepted"
    assert result["edge_similarity"] >= 0.99
    assert result["blocking_reasons"] == []


def test_shape_drift_marks_enhancement_as_preview(tmp_path):
    from tools.enhance_consistency import compare_enhanced_image

    src = tmp_path / "source.png"
    enhanced = tmp_path / "enhanced.png"
    _source(src)
    _shifted(enhanced)

    result = compare_enhanced_image(src, enhanced, min_similarity=0.85)

    assert result["status"] == "preview"
    assert result["edge_similarity"] < 0.85
    assert result["blocking_reasons"][0]["code"] == "enhancement_shape_drift"


def test_batch_report_accepts_complete_matching_enhancements(tmp_path):
    from tools.enhance_consistency import write_enhancement_report

    render_dir = tmp_path / "cad" / "output" / "renders" / "demo" / "RUN001"
    src_v1 = render_dir / "V1_front.png"
    src_v2 = render_dir / "V2_side.png"
    enhanced_v1 = render_dir / "V1_front_20260504_1200_enhanced.jpg"
    enhanced_v2 = render_dir / "V2_side_20260504_1200_enhanced.jpg"
    _source(src_v1)
    _source(src_v2)
    _source(enhanced_v1)
    _source(enhanced_v2)

    report = write_enhancement_report(
        tmp_path,
        _manifest(tmp_path, render_dir, [("V1", src_v1), ("V2", src_v2)]),
        enhanced_images=[enhanced_v1, enhanced_v2],
        output_path=render_dir / "ENHANCEMENT_REPORT.json",
    )

    assert report["status"] == "accepted"
    assert report["delivery_status"] == "accepted"
    assert report["run_id"] == "RUN001"
    assert report["subsystem"] == "demo"
    assert report["view_count"] == 2
    assert {item["view"] for item in report["views"]} == {"V1", "V2"}
    assert report["blocking_reasons"] == []
    assert report["enhancement_report"].endswith(
        "cad/output/renders/demo/RUN001/ENHANCEMENT_REPORT.json"
    )
    assert report["quality_summary"]["status"] == "accepted"
    assert report["quality_summary"]["view_count"] == 2
    assert report["quality_summary"]["warnings"] == []
    assert all("quality_metrics" in view for view in report["views"])
    written = (render_dir / "ENHANCEMENT_REPORT.json").read_text(encoding="utf-8")
    assert report["enhancement_report"] in written


def test_batch_report_marks_low_contrast_enhancement_as_preview(tmp_path):
    from tools.enhance_consistency import build_enhancement_report

    render_dir = tmp_path / "cad" / "output" / "renders" / "demo" / "RUN001"
    src_v1 = render_dir / "V1_front.png"
    enhanced_v1 = render_dir / "V1_front_20260504_1200_enhanced.jpg"
    _source(src_v1)
    _low_contrast(enhanced_v1)

    report = build_enhancement_report(
        tmp_path,
        _manifest(tmp_path, render_dir, [("V1", src_v1)]),
        enhanced_images=[enhanced_v1],
        min_similarity=0.0,
    )

    assert report["status"] == "preview"
    assert report["delivery_status"] == "preview"
    assert report["quality_summary"]["status"] == "preview"
    assert report["quality_summary"]["warnings"][0]["code"] == "photo_quality_low_contrast"
    assert report["views"][0]["quality_metrics"]["contrast_stddev"] < 12.0


def test_batch_report_marks_inconsistent_canvas_as_preview(tmp_path):
    from tools.enhance_consistency import build_enhancement_report

    render_dir = tmp_path / "cad" / "output" / "renders" / "demo" / "RUN001"
    src_v1 = render_dir / "V1_front.png"
    src_v2 = render_dir / "V2_side.png"
    enhanced_v1 = render_dir / "V1_front_20260504_1200_enhanced.jpg"
    enhanced_v2 = render_dir / "V2_side_20260504_1200_enhanced.jpg"
    _source_sized(src_v1, (256, 256))
    _source_sized(src_v2, (256, 256))
    _source_sized(enhanced_v1, (256, 256))
    _source_sized(enhanced_v2, (320, 256))

    report = build_enhancement_report(
        tmp_path,
        _manifest(tmp_path, render_dir, [("V1", src_v1), ("V2", src_v2)]),
        enhanced_images=[enhanced_v1, enhanced_v2],
    )

    assert report["status"] == "preview"
    assert report["delivery_status"] == "preview"
    assert report["quality_summary"]["status"] == "preview"
    assert {
        warning["code"] for warning in report["quality_summary"]["warnings"]
    } == {"photo_quality_inconsistent_canvas"}


def test_batch_report_blocks_missing_enhanced_view(tmp_path):
    from tools.enhance_consistency import build_enhancement_report

    render_dir = tmp_path / "cad" / "output" / "renders" / "demo" / "RUN001"
    src_v1 = render_dir / "V1_front.png"
    src_v2 = render_dir / "V2_side.png"
    enhanced_v1 = render_dir / "V1_front_20260504_1200_enhanced.jpg"
    _source(src_v1)
    _source(src_v2)
    _source(enhanced_v1)

    report = build_enhancement_report(
        tmp_path,
        _manifest(tmp_path, render_dir, [("V1", src_v1), ("V2", src_v2)]),
        enhanced_images=[enhanced_v1],
    )

    assert report["status"] == "blocked"
    assert report["delivery_status"] == "blocked"
    assert {reason["code"] for reason in report["blocking_reasons"]} == {
        "enhanced_view_missing"
    }


def test_batch_report_blocks_empty_manifest_sources(tmp_path):
    from tools.enhance_consistency import build_enhancement_report

    render_dir = tmp_path / "cad" / "output" / "renders" / "demo" / "RUN001"
    render_dir.mkdir(parents=True)
    report = build_enhancement_report(
        tmp_path,
        _manifest(tmp_path, render_dir, []),
        enhanced_images=[],
    )

    assert report["status"] == "blocked"
    assert report["delivery_status"] == "blocked"
    assert report["view_count"] == 0
    assert report["blocking_reasons"][0]["code"] == "render_manifest_no_sources"


def test_batch_report_blocks_ambiguous_enhanced_view(tmp_path):
    from tools.enhance_consistency import build_enhancement_report

    render_dir = tmp_path / "cad" / "output" / "renders" / "demo" / "RUN001"
    src_v1 = render_dir / "V1_front.png"
    enhanced_v1_a = render_dir / "V1_front_20260504_1200_enhanced.jpg"
    enhanced_v1_b = render_dir / "V1_front_20260504_1210_enhanced.jpg"
    _source(src_v1)
    _source(enhanced_v1_a)
    _source(enhanced_v1_b)

    report = build_enhancement_report(
        tmp_path,
        _manifest(tmp_path, render_dir, [("V1", src_v1)]),
        enhanced_images=[enhanced_v1_a, enhanced_v1_b],
    )

    assert report["status"] == "blocked"
    assert report["delivery_status"] == "blocked"
    assert report["views"][0]["status"] == "blocked"
    assert report["blocking_reasons"][0]["code"] == "enhanced_view_ambiguous"
    assert len(report["blocking_reasons"][0]["candidates"]) == 2


def test_batch_report_marks_shape_drift_as_preview(tmp_path):
    from tools.enhance_consistency import build_enhancement_report

    render_dir = tmp_path / "cad" / "output" / "renders" / "demo" / "RUN001"
    src_v1 = render_dir / "V1_front.png"
    enhanced_v1 = render_dir / "V1_front_20260504_1200_enhanced.jpg"
    _source(src_v1)
    _shifted(enhanced_v1)

    report = build_enhancement_report(
        tmp_path,
        _manifest(tmp_path, render_dir, [("V1", src_v1)]),
        enhanced_images=[enhanced_v1],
        min_similarity=0.85,
    )

    assert report["status"] == "preview"
    assert report["delivery_status"] == "preview"
    assert report["views"][0]["status"] == "preview"
    assert report["blocking_reasons"][0]["code"] == "enhancement_shape_drift"


def test_batch_report_rejects_enhanced_image_outside_render_dir(tmp_path):
    from tools.enhance_consistency import build_enhancement_report

    render_dir = tmp_path / "cad" / "output" / "renders" / "demo" / "RUN001"
    src_v1 = render_dir / "V1_front.png"
    outside = tmp_path / "outside" / "V1_front_20260504_1200_enhanced.jpg"
    _source(src_v1)
    _source(outside)

    try:
        build_enhancement_report(
            tmp_path,
            _manifest(tmp_path, render_dir, [("V1", src_v1)]),
            enhanced_images=[outside],
        )
    except ValueError as exc:
        assert "render_dir" in str(exc)
    else:
        raise AssertionError("expected outside enhanced image to be rejected")


def test_batch_report_keeps_project_relative_manifest_path_stable(tmp_path):
    from tools.enhance_consistency import build_enhancement_report

    render_dir = tmp_path / "cad" / "output" / "renders" / "demo" / "RUN001"
    src_v1 = render_dir / "V1_front.png"
    enhanced_v1 = render_dir / "V1_front_20260504_1200_enhanced.jpg"
    manifest_path = render_dir / "render_manifest.json"
    _source(src_v1)
    _source(enhanced_v1)
    manifest = _manifest(tmp_path, render_dir, [("V1", src_v1)])
    manifest["manifest_path"] = manifest_path.relative_to(tmp_path).as_posix()

    report = build_enhancement_report(
        tmp_path,
        manifest,
        enhanced_images=[enhanced_v1],
    )

    assert report["render_manifest"] == "cad/output/renders/demo/RUN001/render_manifest.json"
    assert not report["render_manifest"].endswith(
        "RUN001/cad/output/renders/demo/RUN001/render_manifest.json"
    )


def test_cmd_enhance_check_writes_report_and_returns_success(tmp_path):
    from argparse import Namespace

    import cad_pipeline

    render_dir = tmp_path / "cad" / "output" / "renders" / "demo" / "RUN001"
    src_v1 = render_dir / "V1_front.png"
    enhanced_v1 = render_dir / "V1_front_20260504_1200_enhanced.jpg"
    manifest_path = render_dir / "render_manifest.json"
    _source(src_v1)
    _source(enhanced_v1)
    manifest_path.write_text(
        __import__("json").dumps(
            _manifest(tmp_path, render_dir, [("V1", src_v1)]),
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    exit_code = cad_pipeline.cmd_enhance_check(
        Namespace(
            subsystem="demo",
            dir=str(render_dir),
            manifest=str(manifest_path),
            output=None,
            min_similarity=0.85,
            project_root=str(tmp_path),
        )
    )

    assert exit_code == 0
    report_path = render_dir / "ENHANCEMENT_REPORT.json"
    assert report_path.is_file()
    report = __import__("json").loads(report_path.read_text(encoding="utf-8"))
    assert report["status"] == "accepted"
    assert report["delivery_status"] == "accepted"


def test_cmd_enhance_check_returns_blocked_for_missing_view(tmp_path):
    from argparse import Namespace

    import cad_pipeline

    render_dir = tmp_path / "cad" / "output" / "renders" / "demo" / "RUN001"
    src_v1 = render_dir / "V1_front.png"
    src_v2 = render_dir / "V2_side.png"
    enhanced_v1 = render_dir / "V1_front_20260504_1200_enhanced.jpg"
    manifest_path = render_dir / "render_manifest.json"
    _source(src_v1)
    _source(src_v2)
    _source(enhanced_v1)
    manifest_path.write_text(
        __import__("json").dumps(
            _manifest(tmp_path, render_dir, [("V1", src_v1), ("V2", src_v2)]),
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    exit_code = cad_pipeline.cmd_enhance_check(
        Namespace(
            subsystem="demo",
            dir=str(render_dir),
            manifest=str(manifest_path),
            output=None,
            min_similarity=0.85,
            project_root=str(tmp_path),
        )
    )

    assert exit_code == 1
    report = __import__("json").loads(
        (render_dir / "ENHANCEMENT_REPORT.json").read_text(encoding="utf-8")
    )
    assert report["status"] == "blocked"
