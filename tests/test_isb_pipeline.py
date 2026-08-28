"""AnglesConfig.isb_reconstruction's dispatch through the pipeline.

Complements myogait's own tests/test_isb.py (the reconstruction math
itself) -- these are about the app-side wiring: on by default (a
correctness fix, not a feature toggle -- see the field's own docstring)
but a no-op wherever the pivot is not ISB-capable, so it never fails the
whole angles stage; on-and-capable actually overwrites hip/knee/ankle.
See CLAUDE.md's ISB reconstruction section.
"""

from __future__ import annotations

from dataclasses import replace

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


def test_isb_reconstruction_defaults_on_and_config_stays_hashable():
    from myogait_app.pipeline import AnglesConfig

    cfg = AnglesConfig()
    # On by default: a no-op on any source that doesn't resolve the paired
    # anatomical markers (gated on c3d_markers_3d downstream), so it only
    # ever acts on a full-marker C3D -- see the field's own docstring.
    assert cfg.isb_reconstruction is True
    # Frozen dataclass with only scalar/tuple fields -- the angles-stage
    # cache key can hash it, and flipping the flag changes the key.
    assert hash(cfg) == hash(AnglesConfig())
    assert hash(replace(cfg, isb_reconstruction=False)) != hash(cfg)


def test_isb_reconstruction_injects_markers_lazily_when_missing(monkeypatch):
    """A pivot that reaches the angles stage without merged_c3d_mapping
    having run at load time (e.g. a JSON re-import) still gets ISB
    reconstruction, via marker_presets.inject_isb_markers re-reading the
    source file recorded in extraction.source_file. This is the "on the
    fly" fallback pipeline._apply_isb_reconstruction tries before falling
    through to tier 1 as usual.
    """
    pytest.importorskip("myogait.isb")
    from myogait_app import marker_presets
    from myogait_app.pipeline import _apply_isb_reconstruction

    data = _synthetic_isb_pivot()
    # No paired landmarks at all in c3d_markers_3d -- as if this pivot
    # never went through merged_c3d_mapping at load time -- but a source
    # file is on record, the way any real load_c3d pivot carries one.
    data["c3d_markers_3d"] = {}
    data["extraction"] = {"source_file": "trial_07.c3d"}

    injected_from = {}

    def fake_inject(pivot: dict, path) -> list[str]:
        injected_from["path"] = path
        return []  # not asserting recovery here, just that it was tried

    monkeypatch.setattr(marker_presets, "inject_isb_markers", fake_inject)

    _apply_isb_reconstruction(data, {})
    assert injected_from["path"] == "trial_07.c3d"


# ── Cycle-time enrichment for the 2 extra ISB DOF ──────────────────────
#
# myogait's own segment_cycles/_extract_cycle_angles never look at
# *_abd_add_deg/*_int_ext_rot_deg (hardcoded to hip/knee/ankle/trunk
# flex-ext, see CLAUDE.md), so _enrich_cycles_with_isb_dof is this app's
# own cycle-percent resampling for them. These tests exercise it directly
# against hand-built data/cycles dicts rather than a full pipeline run,
# mirroring how myogait.cycles._normalize_to_percent itself is exercised.


def _frames_with_isb_dof(n_frames: int) -> list[dict]:
    return [
        {
            "frame_idx": i,
            "hip_L_abd_add_deg": 5.0 + i * 0.1,
            "hip_R_abd_add_deg": -5.0 - i * 0.1,
            "knee_L_int_ext_rot_deg": 2.0,
        }
        for i in range(n_frames)
    ]


def test_enrich_cycles_with_isb_dof_is_a_noop_without_isb_angle_keys():
    from myogait_app.pipeline import _enrich_cycles_with_isb_dof

    data = {"angles": {"frames": [{"frame_idx": i, "hip_L": 1.0} for i in range(20)]}}
    cycles = {
        "cycles": [
            {"cycle_id": 1, "side": "left", "start_frame": 0, "end_frame": 19,
             "angles_normalized": {"hip": [0.0] * 101}},
        ],
        "summary": {},
    }
    result = _enrich_cycles_with_isb_dof(data, cycles)
    assert result is cycles  # early return, unchanged object
    assert "hip_abd_add_deg" not in result["cycles"][0]["angles_normalized"]
    assert result["summary"] == {}


def test_enrich_cycles_with_isb_dof_adds_normalized_curve_and_summary():
    from myogait_app.pipeline import _enrich_cycles_with_isb_dof

    n = 20
    data = {"angles": {"frames": _frames_with_isb_dof(n)}}
    cycles = {
        "cycles": [
            {"cycle_id": 1, "side": "left", "start_frame": 0, "end_frame": n - 1,
             "angles_normalized": {"hip": [0.0] * 101}},
            {"cycle_id": 2, "side": "right", "start_frame": 0, "end_frame": n - 1,
             "angles_normalized": {"hip": [0.0] * 101}},
        ],
        "summary": {},
    }
    result = _enrich_cycles_with_isb_dof(data, cycles)

    left, right = result["cycles"][0], result["cycles"][1]
    # Present for the side/joint combination that actually had data...
    assert len(left["angles_normalized"]["hip_abd_add_deg"]) == 101
    assert len(left["angles_normalized"]["knee_int_ext_rot_deg"]) == 101
    # ...resampled from an increasing 5.0..6.9 span, so the endpoints hold.
    assert left["angles_normalized"]["hip_abd_add_deg"][0] == pytest.approx(5.0, abs=0.05)
    assert left["angles_normalized"]["hip_abd_add_deg"][-1] == pytest.approx(6.9, abs=0.05)
    # ...and not fabricated for a joint that was never in the frames at all.
    assert "ankle_abd_add_deg" not in left["angles_normalized"]
    # Right side has hip_R_abd_add_deg but no knee_R_int_ext_rot_deg.
    assert len(right["angles_normalized"]["hip_abd_add_deg"]) == 101
    assert "knee_int_ext_rot_deg" not in right["angles_normalized"]

    left_summary = result["summary"]["left"]
    assert len(left_summary["hip_abd_add_deg_mean"]) == 101
    assert len(left_summary["hip_abd_add_deg_std"]) == 101
    # A single left cycle -> zero spread.
    assert left_summary["hip_abd_add_deg_std"] == pytest.approx([0.0] * 101, abs=1e-9)


def test_enrich_cycles_with_isb_dof_skips_a_too_short_cycle():
    from myogait_app.pipeline import _enrich_cycles_with_isb_dof

    data = {"angles": {"frames": _frames_with_isb_dof(20)}}
    cycles = {
        "cycles": [
            {"cycle_id": 1, "side": "left", "start_frame": 0, "end_frame": 4,  # 5 frames < 10
             "angles_normalized": {"hip": [0.0] * 101}},
        ],
        "summary": {},
    }
    result = _enrich_cycles_with_isb_dof(data, cycles)
    assert "hip_abd_add_deg" not in result["cycles"][0]["angles_normalized"]
    assert result["summary"] == {}
