from bom_parser import classify_part


def test_classifies_chinese_lead_screw_as_transmission():
    assert classify_part("丝杠 L350", "") == "transmission"


def test_classifies_trapezoidal_lead_screw_model_as_transmission():
    assert classify_part("lead screw", "Tr16x4, 45# steel") == "transmission"
    assert classify_part("梯形丝杠", "Tr16×4") == "transmission"


def test_classifies_t16_threaded_pair_text_as_transmission():
    assert classify_part("丝杠螺母副", "T16×4") == "transmission"
    assert classify_part("T16 螺母", "") == "transmission"
