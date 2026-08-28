"""ISB hip/knee reference wiring: marker resolution, injection, codegen.

The angle-level correctness of ``reconstruct_isb_angles`` is myogait's own
concern (and tested there); these tests cover the *app* seam: resolving the
paired anatomical markers out of whatever labels a file carries, injecting
them into ``c3d_markers_3d`` without disturbing the 2-D pivot, and the
config/codegen plumbing that turns the sidebar toggle into a reproducible
script.
"""
from __future__ import annotations

from dataclasses import replace

import pytest

from myogait_app.marker_presets import (
    ISB_MARKER_ALIASES,
    inject_isb_markers,
    resolve_isb_markers,
)
from myogait_app.pipeline import AnglesConfig, PipelineConfig

# The Bath BioCV convention, the set the validation ran on.
BATH_LABELS = [
    "ASIS_L", "ASIS_R", "PSIS_L", "PSIS_R",
    "KNEE_LAT_L", "KNEE_LAT_R", "KNEE_MED_L", "KNEE_MED_R",
    "MAL_LAT_L", "MAL_LAT_R", "MAL_MED_L", "MAL_MED_R",
    "HEEL_L", "HEEL_R", "MTP1_L", "MTP1_R", "MTP5_L", "MTP5_R",
    "C7", "CLAV", "T10",  # non-anatomical extras that must be ignored
]

# The 18 canonical names myogait's reconstruction requires.
ALL_ISB = tuple(ISB_MARKER_ALIASES.keys())


def test_resolves_all_eighteen_on_bath_labels():
    resolved = resolve_isb_markers(BATH_LABELS)
    assert set(resolved) == set(ALL_ISB)
    # MTP1 is the 1st metatarsal head = medial; MTP5 the 5th = lateral.
    assert resolved["LEFT_FOOT_INDEX_MEDIAL"] == "MTP1_L"
    assert resolved["LEFT_FOOT_INDEX_LATERAL"] == "MTP5_L"
    assert resolved["RIGHT_ANKLE_LATERAL"] == "MAL_LAT_R"
    assert resolved["RIGHT_ANKLE_MEDIAL"] == "MAL_MED_R"


def test_resolution_is_case_and_separator_insensitive():
    scrambled = [lbl.lower().replace("_", "-") for lbl in BATH_LABELS]
    resolved = resolve_isb_markers(scrambled)
    assert set(resolved) == set(ALL_ISB)


def test_plugingait_medial_markers_resolve_when_present():
    # PiG names the joint markers LKNE/RKNE etc.; medial markers are the
    # optional KAD/medial set, here given the CAST epicondyle codes.
    labels = [
        "LASI", "RASI", "LPSI", "RPSI",
        "LKNE", "RKNE", "LMFE", "RMFE",
        "LANK", "RANK", "LMMA", "RMMA",
        "LHEE", "RHEE", "LFM1", "RFM1", "LFM5", "RFM5",
    ]
    resolved = resolve_isb_markers(labels)
    assert resolved["LEFT_KNEE_LATERAL"] == "LKNE"
    assert resolved["LEFT_KNEE_MEDIAL"] == "LMFE"
    assert resolved["RIGHT_ASIS"] == "RASI"


def test_partial_labels_resolve_only_what_is_present():
    resolved = resolve_isb_markers(["ASIS_L", "ASIS_R", "HEEL_L"])
    assert set(resolved) == {"LEFT_ASIS", "RIGHT_ASIS", "LEFT_HEEL"}


def test_inject_is_non_fatal_on_a_bad_path():
    data: dict = {"c3d_markers_3d": {}}
    assert inject_isb_markers(data, "does/not/exist.c3d") == []
    assert data["c3d_markers_3d"] == {}


def test_config_default_on_for_c3d_and_stays_hashable():
    cfg = AnglesConfig()
    # On by default: a no-op on any source without paired anatomical
    # markers (gated on c3d_markers_3d downstream), so only ever acts on a
    # full-marker C3D, where the ISB pelvis reference is the standard.
    assert cfg.c3d_isb_angles is True
    assert cfg.c3d_isb_joints == ("hip", "knee")
    # Frozen + tuple field -> the angles-stage cache key can hash it.
    assert hash(cfg) == hash(AnglesConfig())
    assert hash(replace(cfg, c3d_isb_angles=False)) != hash(cfg)


def test_codegen_emits_isb_reconstruction_for_a_c3d_source():
    from myogait_app.codegen import python_snippet

    cfg = replace(PipelineConfig(), angles=replace(PipelineConfig().angles, c3d_isb_angles=True))
    src = python_snippet(
        cfg, source="trial.c3d", from_json=True,
        c3d_options={"marker_mapping": None, "ap_axis": 0, "vertical_axis": 2,
                     "fix_aspect_ratio": False, "ranges": None},
    )
    assert "reconstruct_isb_angles" in src
    assert "load_raw_c3d_markers" in src
    # The emitted script must compile.
    compile(src, "<generated>", "exec")


def test_codegen_omits_isb_when_off():
    from myogait_app.codegen import python_snippet

    cfg = replace(PipelineConfig(), angles=replace(PipelineConfig().angles, c3d_isb_angles=False))
    src = python_snippet(
        cfg, source="trial.c3d", from_json=True,
        c3d_options={"marker_mapping": None, "ap_axis": 0, "vertical_axis": 2,
                     "fix_aspect_ratio": False, "ranges": None},
    )
    assert "reconstruct_isb_angles" not in src


@pytest.mark.parametrize("isb_name", ALL_ISB)
def test_every_isb_landmark_has_at_least_one_candidate(isb_name):
    assert ISB_MARKER_ALIASES[isb_name], f"{isb_name} has no candidate labels"
