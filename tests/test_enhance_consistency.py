from PIL import Image, ImageDraw


def _source(path):
    image = Image.new("RGB", (256, 256), (245, 245, 245))
    draw = ImageDraw.Draw(image)
    draw.rectangle((64, 64, 192, 192), fill=(20, 90, 150))
    image.save(path)


def _shifted(path):
    image = Image.new("RGB", (256, 256), (245, 245, 245))
    draw = ImageDraw.Draw(image)
    draw.rectangle((100, 64, 228, 192), fill=(20, 90, 150))
    image.save(path)


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
