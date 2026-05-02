import cadquery as cq

from adapters.parts.parametric_transmission import make_trapezoidal_lead_screw


def _bbox(obj):
    bb = obj.val().BoundingBox()
    return (
        round(bb.xlen, 1),
        round(bb.ylen, 1),
        round(bb.zlen, 1),
    )


def test_trapezoidal_lead_screw_preserves_overall_envelope():
    screw = make_trapezoidal_lead_screw(
        outer_diameter_mm=16.0,
        pitch_mm=4.0,
        total_length_mm=350.0,
        thread_length_mm=230.0,
        lower_shaft_diameter_mm=12.0,
        lower_shaft_length_mm=70.0,
        upper_shaft_diameter_mm=12.0,
        upper_shaft_length_mm=40.0,
    )

    assert _bbox(screw) == (16.0, 16.0, 350.0)


def test_trapezoidal_lead_screw_has_visible_thread_cues():
    screw = make_trapezoidal_lead_screw(
        outer_diameter_mm=16.0,
        pitch_mm=4.0,
        total_length_mm=120.0,
        thread_length_mm=80.0,
        lower_shaft_diameter_mm=12.0,
        lower_shaft_length_mm=20.0,
        upper_shaft_diameter_mm=12.0,
        upper_shaft_length_mm=20.0,
    )

    solids = screw.val().Solids()
    assert len(solids) >= 1
    assert len(screw.val().Edges()) > 80
    assert len(screw.val().Faces()) > 20
