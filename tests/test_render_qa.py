from PIL import Image, ImageDraw


def _save_rgb(path, size=(256, 256), color=(255, 255, 255)):
    image = Image.new("RGB", size, color)
    image.save(path)


def test_qa_image_accepts_nonblank_image_with_subject_area(tmp_path):
    from tools.render_qa import qa_image

    image_path = tmp_path / "V1.png"
    image = Image.new("RGB", (256, 256), (245, 245, 245))
    draw = ImageDraw.Draw(image)
    draw.rectangle((64, 64, 192, 192), fill=(40, 90, 160))
    image.save(image_path)

    qa = qa_image(image_path)

    assert qa["passed"] is True
    assert qa["width"] == 256
    assert qa["height"] == 256
    assert qa["nonblank"] is True
    assert qa["transparent"] is False
    assert qa["object_occupancy"] > 0.15
    assert qa["cropped"] is False
    assert qa["sha256"].startswith("sha256:")


def test_qa_image_rejects_pure_white_render(tmp_path):
    from tools.render_qa import qa_image

    image_path = tmp_path / "V1_blank.png"
    _save_rgb(image_path)

    qa = qa_image(image_path)

    assert qa["passed"] is False
    assert qa["nonblank"] is False
    assert "blank_image" in qa["reasons"]


def test_qa_image_rejects_fully_transparent_render(tmp_path):
    from tools.render_qa import qa_image

    image_path = tmp_path / "V1_transparent.png"
    Image.new("RGBA", (256, 256), (0, 0, 0, 0)).save(image_path)

    qa = qa_image(image_path)

    assert qa["passed"] is False
    assert qa["transparent"] is True
    assert "transparent_image" in qa["reasons"]


def test_qa_image_rejects_subject_too_small(tmp_path):
    from tools.render_qa import qa_image

    image_path = tmp_path / "V1_tiny.png"
    image = Image.new("RGB", (256, 256), (250, 250, 250))
    draw = ImageDraw.Draw(image)
    draw.rectangle((124, 124, 130, 130), fill=(20, 20, 20))
    image.save(image_path)

    qa = qa_image(image_path)

    assert qa["passed"] is False
    assert qa["object_occupancy"] < 0.01
    assert "low_object_occupancy" in qa["reasons"]


def test_qa_image_flags_subject_touching_border_as_cropped(tmp_path):
    from tools.render_qa import qa_image

    image_path = tmp_path / "V1_cropped.png"
    image = Image.new("RGB", (256, 256), (245, 245, 245))
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 80, 150, 180), fill=(45, 45, 45))
    image.save(image_path)

    qa = qa_image(image_path)

    assert qa["passed"] is False
    assert qa["cropped"] is True
    assert "cropped_subject" in qa["reasons"]


def test_qa_image_reports_missing_file_without_secondary_exception(tmp_path):
    from tools.render_qa import qa_image

    qa = qa_image(tmp_path / "missing.png")

    assert qa["passed"] is False
    assert qa["sha256"] is None
    assert "missing_image" in qa["reasons"]
