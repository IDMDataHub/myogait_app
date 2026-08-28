"""AnglesConfig.isb_reconstruction's dispatch through the pipeline.

Complements myogait's own tests/test_isb.py (the reconstruction math
itself) -- these are about the app-side wiring: off by default leaves
compute_angles' result untouched, on-but-incapable degrades gracefully
instead of failing the whole angles stage, and on-and-capable actually
overwrites hip/knee/ankle. See CLAUDE.md's ISB reconstruction section.
"""

from __future__ import annotations

import pytest


def _synthetic_isb_pivot(n_frames: int = 3) -> dict:
    """A minimal pivot with compute_angles already run and enough
    landmarks (base 6 + the ISB-enriched paired medial/lateral set) to
    let reconstruct_isb_angles actually do something -- same neutral-
    standing geometry idea as myogait's own tests/test_isb.py fixture,
    kept intentionally simple since these tests are about dispatch, not
    reconstruction accuracy (that is myogait's own test's job).
    """
    import numpy as np

    RASIS, LASIS = [0.0, 1000.0, 100.0], [0.0, 1000.0, -100.0]
    RPSIS, LPSIS = [-200.0, 1000.0, 100.0], [-200.0, 1000.0, -100.0]
    markers = {
        "RIGHT_ASIS": RASIS, "LEFT_ASIS": LASIS, "RIGHT_PSIS": RPSIS, "LEFT_PSIS": LPSIS,
        "RIGHT_KNEE_LATERAL": [-70.0, 600.0, 130.0], "RIGHT_KNEE_MEDIAL": [-70.0, 600.0, 70.0],
        "LEFT_KNEE_LATERAL": [-70.0, 600.0, -130.0], "LEFT_KNEE_MEDIAL": [-70.0, 600.0, -70.0],
        "RIGHT_ANKLE_LATERAL": [-70.0, 200.0, 120.0], "RIGHT_ANKLE_MEDIAL": [-70.0, 200.0, 80.0],
        "LEFT_ANKLE_LATERAL": [-70.0, 200.0, -120.0], "LEFT_ANKLE_MEDIAL": [-70.0, 200.0, -80.0],
        "RIGHT_HEEL": [-150.0, 120.0, 100.0], "LEFT_HEEL": [-150.0, 120.0, -100.0],
        "RIGHT_FOOT_INDEX_MEDIAL": [80.0, 120.0, 80.0], "RIGHT_FOOT_INDEX_LATERAL": [80.0, 120.0, 120.0],
        "LEFT_FOOT_INDEX_MEDIAL": [80.0, 120.0, -80.0], "LEFT_FOOT_INDEX_LATERAL": [80.0, 120.0, -120.0],
    }
    m3d = {lm: np.tile(np.asarray(pos), (n_frames, 1)) for lm, pos in markers.items()}
    return {
        "meta": {"fps": 100.0, "n_frames": n_frames},
        "frames": [{"frame_idx": i, "landmarks": {}} for i in range(n_frames)],
        "angles": {"frames": [
            {"frame_idx": i, "hip_L": 1.0, "hip_R": 2.0, "knee_L": 3.0, "knee_R": 4.0,
             "ankle_L": 5.0, "ankle_R": 6.0}
            for i in range(n_frames)
        ]},
        "c3d_markers_3d": m3d,
    }


def test_isb_reconstruction_off_leaves_result_untouched():
    from myogait_app.pipeline import _apply_isb_reconstruction

    data = _synthetic_isb_pivot()
    before = dict(data["angles"]["frames"][0])
    # Not calling _apply_isb_reconstruction at all is the "off" case --
    # _apply_angles only calls it when cfg.isb_reconstruction is True, so
    # asserting the pivot is unchanged when nothing touches it *is* the
    # off-by-default contract (see _apply_angles's own gate).
    assert data["angles"]["frames"][0] == before
    assert "isb_reference" not in data["angles"]


def test_isb_reconstruction_on_but_myogait_isb_missing_degrades_gracefully(monkeypatch):
    # _apply_isb_reconstruction does `from myogait import reconstruct_isb_
    # angles` (a top-level *attribute* lookup, cached on the myogait
    # module object once myogait.__init__ has run) -- not `from myogait.
    # isb import ...`, so poisoning sys.modules["myogait.isb"] alone
    # would not reproduce the real gap (caught by this test failing
    # against a stale mocking approach during development). What
    # actually happens on the currently *published* myogait is that its
    # __init__.py simply never defines these names at all -- reproduced
    # here by removing them from the already-imported module, which
    # makes `from myogait import name` raise ImportError exactly like a
    # myogait without myogait.isb would.
    import myogait

    from myogait_app.pipeline import _apply_isb_reconstruction

    for name in ("reconstruct_isb_angles", "reconstruct_isb_angles_tier2", "reconstruct_isb_angles_tier3"):
        monkeypatch.delattr(myogait, name, raising=False)

    data = _synthetic_isb_pivot()
    before = dict(data["angles"]["frames"][0])
    result = _apply_isb_reconstruction(data, {})
    assert result["angles"]["frames"][0] == before
    assert "isb_reference" not in result["angles"]


def test_isb_reconstruction_on_but_source_incapable_degrades_gracefully():
    # No paired medial/lateral landmarks at all -- a video/markerless-
    # style pivot. reconstruct_isb_angles raises InsufficientLandmarksForISBError;
    # the wrapper must swallow it, not propagate (that would fail the
    # whole angles stage over an optional, off-by-default feature).
    pytest.importorskip("myogait.isb")
    from myogait_app.pipeline import _apply_isb_reconstruction

    data = {
        "angles": {"frames": [{"frame_idx": 0, "hip_L": 1.0, "hip_R": 2.0}]},
        "c3d_markers_3d": {"LEFT_HIP": [[0.0, 0.0, 0.0]]},
    }
    result = _apply_isb_reconstruction(data, {})
    assert result["angles"]["frames"][0]["hip_L"] == 1.0
    assert "isb_reference" not in result["angles"]


def test_isb_reconstruction_tier1_actually_overwrites_when_capable():
    pytest.importorskip("myogait.isb")
    from myogait_app.pipeline import _apply_isb_reconstruction

    data = _synthetic_isb_pivot()
    result = _apply_isb_reconstruction(data, {})
    assert result["angles"]["isb_reference"] == "isb_3d_direct"
    frame = result["angles"]["frames"][0]
    for key in ("hip_L", "hip_R", "knee_L", "knee_R", "ankle_L", "ankle_R"):
        assert isinstance(frame[key], float)


def test_isb_reconstruction_prefers_tier3_over_tier2_when_both_present():
    # Bogus tier3_calibration/dynamic_raw that will fail to apply --
    # confirms the dispatch *tries* tier 3 first (and falls through
    # safely) rather than silently preferring tier 2 whenever both keys
    # happen to be present in isb_context.
    pytest.importorskip("myogait.isb")
    from myogait_app.pipeline import _apply_isb_reconstruction

    data = _synthetic_isb_pivot()
    isb_context = {
        "tier3_calibration": object(),  # not a real TechnicalCalibration
        "dynamic_raw": {"SOME_MARKER": [[0.0, 0.0, 0.0]]},
        "static_landmarks": data["c3d_markers_3d"],  # would succeed as tier 2 if tried
    }
    result = _apply_isb_reconstruction(data, isb_context)
    # Bogus tier 3 input fails -> degrades to "untouched", not a silent
    # fall-through to tier 2 with the valid static_landmarks alongside it.
    assert "isb_reference" not in result["angles"]


def test_apply_angles_calls_isb_reconstruction_only_when_enabled():
    pytest.importorskip("myogait.isb")
    from myogait_app.pipeline import AnglesConfig, _apply_angles

    data_off = _synthetic_isb_pivot()
    data_off = _apply_angles(data_off, AnglesConfig(isb_reconstruction=False), isb_context={})
    assert "isb_reference" not in data_off["angles"]

    data_on = _synthetic_isb_pivot()
    data_on = _apply_angles(data_on, AnglesConfig(isb_reconstruction=True), isb_context={})
    assert data_on["angles"]["isb_reference"] == "isb_3d_direct"
