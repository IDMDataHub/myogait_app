"""myogait_app.kinetics: wrapper around myogait.estimate_kinetics (markerless GRF / moments)."""

import numpy as np
import pytest

from myogait_app import kinetics as AK


class _Subj:
    def __init__(self, weight_kg=70.0, height_m=1.75, femur_length_mm=None, sex="M"):
        self.weight_kg, self.height_m, self.femur_length_mm, self.sex = (
            weight_kg,
            height_m,
            femur_length_mm,
            sex,
        )


def _walker():
    fs, n, W, H, v, f, scale = 60.0, 360, 1920, 1080, 1.2, 0.9, 1 / 600.0
    t = np.arange(n) / fs
    frames = []
    for i in range(n):
        x = v * t[i]
        L = {}
        for s, ph in (("LEFT", 0.0), ("RIGHT", np.pi)):
            sw = 0.25 * np.sin(2 * np.pi * f * t[i] + ph)
            pts = {
                "HIP": (x, 0.92),
                "KNEE": (x + 0.5 * sw, 0.50),
                "ANKLE": (x + sw, 0.09),
                "HEEL": (x + sw - 0.06, 0.03),
                "FOOT_INDEX": (x + sw + 0.18, 0.02),
                "SHOULDER": (x, 1.40),
                "ELBOW": (x - 0.3 * sw, 1.12),
                "WRIST": (x - 0.5 * sw, 0.86),
            }
            for k, (px, py) in pts.items():
                L[f"{s}_{k}"] = {
                    "x": (300 + px / scale) / W,
                    "y": (900 - py / scale - 4 * np.sin(4 * np.pi * f * t[i])) / H,
                }
        L["NOSE"] = {"x": (300 + x / scale) / W, "y": (900 - 1.62 / scale) / H}
        frames.append({"frame_idx": i, "time_s": float(t[i]), "landmarks": L})
    T = 1 / f
    ev = {"left_hs": [], "left_to": [], "right_hs": [], "right_to": []}
    for k in range(4):
        b = int((0.6 + k * T) * fs)
        ev["left_hs"].append({"frame": b})
        ev["right_to"].append({"frame": b + 7})
        ev["right_hs"].append({"frame": b + int(0.5 * T * fs)})
        ev["left_to"].append({"frame": b + int(0.62 * T * fs)})
    return {
        "meta": {"fps": fs, "width": W, "height": H},
        "frames": frames,
        "events": ev,
    }


def test_missing_mass_returns_none():
    assert AK.compute_kinetics(_walker(), _Subj(weight_kg=None)) is None
    assert AK.compute_kinetics(_walker(), _Subj(height_m=None)) is None


def test_compute_kinetics_table_and_curves():
    if not AK.kinetics_available():
        pytest.skip("myogait without estimate_kinetics")
    res = AK.compute_kinetics(_walker(), _Subj(), camera_moving=False)
    assert "error" not in res
    tab = res["table"]
    assert len(tab) >= 2 and {
        "a1/a2",
        "propulsion peak (BW)",
        "ankle plantarflexor peak (N·m/kg)",
    } <= set(tab.columns)
    assert np.all(np.isfinite(tab["vGRF peak 1 (BW)"]))
    assert "left" in res["mean_curves"] and res["mean_curves"]["left"]["vgrf_bw"][
        "mean"
    ].shape == (101,)


def test_kinetics_tab_renders_three_states():
    pytest.importorskip("streamlit")
    pytest.importorskip("plotly")
    from streamlit.testing.v1 import AppTest

    def app(state):
        import numpy as np
        from types import SimpleNamespace
        from myogait_app.ui.page_pipeline import _kinetics_tab
        from myogait_app import kinetics as AK

        if state == "missing":
            _kinetics_tab(SimpleNamespace(kinetics=None))
        elif state == "error":
            _kinetics_tab(SimpleNamespace(kinetics={"error": "boom"}))
        else:
            st_ = {"side": "left", "on": 10, "off": 70}
            T = np.linspace(0, 1, 101)
            for k in (
                "vgrf_bw",
                "apgrf_bw",
                "cop_minus_ankle_m",
                "ankle_Nm_kg",
                "knee_Nm_kg",
                "hip_Nm_kg",
                "ankle_power_W_kg",
            ):
                st_[k] = np.sin(np.pi * T)
            res = {
                "stances": [st_, dict(st_, side="right")],
                "camera": {"moving": False},
                "walking_speed_m_s": 1.2,
            }
            res["table"] = AK.kinetics_table(res)
            res["mean_curves"] = AK.mean_curves(res)
            _kinetics_tab(SimpleNamespace(kinetics=res))

    for state in ("missing", "error", "ok"):
        at = AppTest.from_function(app, args=(state,)).run(timeout=60)
        assert not at.exception, (state, at.exception)
        if state == "error":
            assert any("boom" in w.value for w in at.warning)
        if state == "ok":
            assert len(at.dataframe) == 1
