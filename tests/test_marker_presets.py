"""Caching contracts for C3D marker-preset helpers."""

from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

from myogait_app.marker_presets import (
    _read_c3d_labels_cached,
    read_c3d_labels,
    resolve_isb_mapping,
)


def test_read_c3d_labels_reuses_an_unchanged_file_fingerprint(tmp_path, monkeypatch):
    calls: list[str] = []
    trial = tmp_path / "trial.c3d"
    trial.write_bytes(b"fixture")

    def fake_c3d(path: str) -> dict:
        calls.append(path)
        return {"parameters": {"POINT": {"LABELS": {"value": [" LASI ", "RASI"]}}}}

    _read_c3d_labels_cached.cache_clear()
    monkeypatch.setitem(sys.modules, "ezc3d", SimpleNamespace(c3d=fake_c3d))

    assert read_c3d_labels(trial) == ["LASI", "RASI"]
    assert read_c3d_labels(trial) == ["LASI", "RASI"]

    assert calls == [str(trial.resolve())]


# ── resolve_isb_mapping: the richer, paired medial/lateral landmark set ──
#
# Label lists below are the real POINT labels from three independent
# files used to validate myogait.isb this session (session-local
# scripts, not part of this repo -- and the files themselves are private
# clinical/third-party data, never committed here). Kept as literal
# lists so these tests need no C3D fixture at all.

_MYOKINESIS_LABELS = [
    "LASIS", "LPSIS", "RPSIS", "RASIS", "LTH1", "LTH2", "LTH3", "LTH4",
    "LLFE", "LMFE", "LTTA", "LMM", "LLM", "LCAL", "LFMH5", "LFMH1", "LTT2",
    "RTH1", "RTH2", "RTH3", "RTH4", "RLFE", "RMFE", "RTTA", "RLM", "RMM",
    "RCAL", "RFMH5", "RFMH1", "RTT2",
]

_BATH_LOWER_LIMB_LABELS = [
    "ASIS_L", "ASIS_R", "PSIS_L", "PSIS_R",
    "KNEE_LAT_L", "KNEE_LAT_R", "KNEE_MED_L", "KNEE_MED_R",
    "MAL_LAT_L", "MAL_LAT_R", "MAL_MED_L", "MAL_MED_R",
    "HEEL_L", "HEEL_R", "MTP1_L", "MTP1_R", "MTP5_L", "MTP5_R",
]

_NATURE_MULTIMODAL_LABELS = [
    "L_IAS", "L_IPS", "R_IPS", "R_IAS", "L_FLE", "L_FME", "L_FAL", "L_TAM",
    "L_FCC", "L_FM1", "L_FM5", "R_FLE", "R_FME", "R_FAL", "R_TAM", "R_FCC",
    "R_FM1", "R_FM5", "CV7",
]

_MEDIAPIPE_STYLE_LABELS = [
    "LEFT_HIP", "RIGHT_HIP", "LEFT_KNEE", "RIGHT_KNEE", "LEFT_ANKLE",
    "RIGHT_ANKLE", "LEFT_HEEL", "RIGHT_HEEL", "LEFT_FOOT_INDEX",
    "RIGHT_FOOT_INDEX", "NOSE",
]


def test_resolve_isb_mapping_myokinesis_convention():
    pytest.importorskip("myogait.isb")
    mapping, diag = resolve_isb_mapping(_MYOKINESIS_LABELS)
    assert diag.is_isb_capable
    assert diag.method == "alias"
    assert mapping["LEFT_KNEE_LATERAL"] == ["LLFE"]
    assert mapping["LEFT_KNEE_MEDIAL"] == ["LMFE"]


def test_resolve_isb_mapping_bath_convention():
    pytest.importorskip("myogait.isb")
    mapping, diag = resolve_isb_mapping(_BATH_LOWER_LIMB_LABELS)
    assert diag.is_isb_capable
    assert diag.method == "alias"
    assert mapping["RIGHT_ANKLE_LATERAL"] == ["MAL_LAT_R"]
    assert mapping["RIGHT_ANKLE_MEDIAL"] == ["MAL_MED_R"]


def test_resolve_isb_mapping_nature_multimodal_convention():
    pytest.importorskip("myogait.isb")
    mapping, diag = resolve_isb_mapping(_NATURE_MULTIMODAL_LABELS)
    assert diag.is_isb_capable
    assert diag.method == "alias"
    assert mapping["LEFT_FOOT_INDEX_MEDIAL"] == ["L_FM1"]
    assert mapping["LEFT_FOOT_INDEX_LATERAL"] == ["L_FM5"]


def test_resolve_isb_mapping_rejects_a_single_point_per_joint_source():
    # A markerless/video source (or any sparse marker set) gives exactly
    # one point per joint -- no lateral/medial pair to build an
    # anatomical frame from. Must stay excluded, not degrade silently.
    mapping, diag = resolve_isb_mapping(_MEDIAPIPE_STYLE_LABELS)
    assert not diag.is_isb_capable
    assert mapping is None


def test_resolve_isb_mapping_falls_back_to_fuzzy_for_an_unknown_convention():
    # A convention in none of the three alias tables, but following the
    # same near-universal side + lateral/medial abbreviation style --
    # the flexibility the base resolve_c3d_mapping cascade already has,
    # extended to the richer landmark set.
    pytest.importorskip("myogait.isb")
    labels = [
        "L_ASIS", "R_ASIS", "L_PSIS", "R_PSIS",
        "KNEE_LATERAL_L", "KNEE_MEDIAL_L", "KNEE_LATERAL_R", "KNEE_MEDIAL_R",
        "ANKLE_LATERAL_L", "ANKLE_MEDIAL_L", "ANKLE_LATERAL_R", "ANKLE_MEDIAL_R",
        "HEEL_L", "HEEL_R", "MTP1_L", "MTP5_L", "MTP1_R", "MTP5_R",
    ]
    mapping, diag = resolve_isb_mapping(labels)
    assert diag.is_isb_capable
    assert diag.method == "fuzzy"
    assert mapping["LEFT_KNEE_LATERAL"] == ["KNEE_LATERAL_L"]
    assert diag.source["LEFT_KNEE_LATERAL"] == "fuzzy"
    # ASIS/PSIS/HEEL/forefoot happen to already match a known alias table
    # here (underscore-prefix / BATH-style tokens) -- only the knee/ankle
    # tokens above are genuinely novel and forced through the keyword scan.
    assert diag.source["LEFT_ASIS"] == "alias"


def test_resolve_isb_mapping_partial_coverage_is_not_capable():
    # Only a hip and a knee pair -- no ankle, no heel, no forefoot.
    # Coverage must be all-or-nothing (an anatomical frame needs the
    # whole chain), not "close enough".
    pytest.importorskip("myogait.isb")
    labels = ["LASIS", "RASIS", "LPSIS", "RPSIS", "LLFE", "LMFE"]
    mapping, diag = resolve_isb_mapping(labels)
    assert not diag.is_isb_capable
    assert 0 < diag.n_resolved < diag.n_required
    assert mapping is None


def test_resolve_isb_mapping_not_capable_when_myogait_isb_is_unavailable(monkeypatch):
    # Regression test for a real bug caught by CI (not local runs, which
    # always had the isb.py-carrying myogait branch installed): the
    # currently *published* myogait has no myogait.isb yet (it lives on
    # an unmerged branch), so resolve_isb_mapping's ImportError guard
    # returns n_resolved=0, n_required=0 -- and 0 >= 0 previously made
    # is_isb_capable read True. sys.modules[name] = None is the
    # documented way to force `import` to raise ImportError for one
    # module without needing myogait.isb to actually be absent here.
    monkeypatch.setitem(sys.modules, "myogait.isb", None)
    mapping, diag = resolve_isb_mapping(_MYOKINESIS_LABELS)
    assert diag.method == "unavailable"
    assert not diag.is_isb_capable
    assert mapping is None
