from __future__ import annotations

import pytest

from myogait_app.calibration import calibrated_metrics


def _data(width: int, height: int) -> dict:
    return {
        "meta": {"width": width, "height": height},
        "frames": [
            {"landmarks": {"LEFT_ANKLE": {"x": 0.20}, "RIGHT_ANKLE": {"x": 0.20}}},
            {"landmarks": {"LEFT_ANKLE": {"x": 0.30}, "RIGHT_ANKLE": {"x": 0.30}}},
        ],
        "events": {"left_hs": [{"frame": 0}], "right_hs": [{"frame": 1}]},
    }


def test_isotropic_calibration_applies_the_source_aspect_ratio():
    data = _data(1920, 1080)
    anisotropic = calibrated_metrics(data, {"cycles": []}, 2.0, isotropic=False)
    isotropic = calibrated_metrics(data, {"cycles": []}, 2.0, isotropic=True)

    assert anisotropic.step_length_right_m is not None
    assert isotropic.step_length_right_m is not None
    assert isotropic.step_length_right_m / anisotropic.step_length_right_m == pytest.approx(1920 / 1080)


def test_isotropic_calibration_is_a_noop_without_image_metadata():
    data = _data(1, 1)
    data.pop("meta")

    anisotropic = calibrated_metrics(data, {"cycles": []}, 2.0, isotropic=False)
    isotropic = calibrated_metrics(data, {"cycles": []}, 2.0, isotropic=True)

    assert isotropic.step_length_right_m == anisotropic.step_length_right_m
