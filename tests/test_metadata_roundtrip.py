"""Subject/study metadata round-trip: pre-fill from a pivot, edit, persist.

The UI wiring (sidebar seeding, export button) is covered by the app smoke;
here we lock the pure, Streamlit-free logic the round-trip rests on.
"""
from __future__ import annotations

from myogait_app.pipeline import (
    STUDY_KEYS,
    SubjectConfig,
    _apply_subject,
    apply_study,
    study_from_data,
)


def _pivot(**top):
    d = {"meta": {"fps": 30.0}, "frames": []}
    d.update(top)
    return d


# ── SubjectConfig.from_subject_dict (pre-fill) ───────────────────────


def test_from_subject_dict_maps_all_known_fields():
    subject = {"age": 40, "sex": "M", "height_m": 1.8,
               "femur_length_mm": 430.0, "tibia_length_mm": 410.0,
               "foot_length_mm": 260.0}
    cfg = SubjectConfig.from_subject_dict(subject)
    assert cfg.age == 40 and cfg.sex == "M" and cfg.height_m == 1.8
    assert cfg.femur_length_mm == 430.0
    assert cfg.tibia_length_mm == 410.0
    assert cfg.foot_length_mm == 260.0


def test_from_subject_dict_empty_is_empty_config():
    assert SubjectConfig.from_subject_dict(None).is_empty
    assert SubjectConfig.from_subject_dict({}).is_empty


def test_from_subject_dict_ignores_unknown_keys():
    cfg = SubjectConfig.from_subject_dict({"height_m": 1.7, "notes": "x", "foo": 1})
    assert cfg.height_m == 1.7  # unknown keys simply not mapped, no crash


# ── _apply_subject persists the measured segments into the pivot ─────


def test_apply_subject_writes_segments_into_pivot():
    cfg = SubjectConfig(height_m=1.75, femur_length_mm=420.0, tibia_length_mm=400.0)
    data = _apply_subject(_pivot(), cfg)
    assert data["subject"]["femur_length_mm"] == 420.0
    assert data["subject"]["tibia_length_mm"] == 400.0
    assert data["subject"]["height_m"] == 1.75


def test_apply_subject_noop_when_empty():
    data = _apply_subject(_pivot(), SubjectConfig())
    assert "subject" not in data


def test_subject_survives_config_roundtrip():
    # pivot subject -> config -> pivot subject is stable on the known fields.
    cfg = SubjectConfig(age=33, height_m=1.72, femur_length_mm=415.0)
    data = _apply_subject(_pivot(), cfg)
    back = SubjectConfig.from_subject_dict(data["subject"])
    assert back.age == 33 and back.height_m == 1.72 and back.femur_length_mm == 415.0


# ── study_from_data + apply_study ────────────────────────────────────


def test_study_from_data_returns_stored_study():
    data = _pivot(study={"patient_id": "P1", "condition": "pre"})
    assert study_from_data(data) == {"patient_id": "P1", "condition": "pre"}


def test_study_from_data_absent_is_empty():
    assert study_from_data(_pivot()) == {}


def test_apply_study_merges_and_drops_blanks():
    data = _pivot(study={"patient_id": "P1", "run": "r1", "condition": "pre"})
    out = apply_study(data, {"condition": "post", "group": "", "run": "r1"})
    # condition updated, run kept, blank group ignored, patient_id preserved.
    assert out["study"]["condition"] == "post"
    assert out["study"]["patient_id"] == "P1"
    assert out["study"]["run"] == "r1"
    assert "group" not in out["study"]


def test_apply_study_none_is_noop():
    data = _pivot(study={"patient_id": "P1"})
    assert apply_study(data, None)["study"] == {"patient_id": "P1"}


def test_full_edit_roundtrip():
    # Load a pivot with metadata -> pre-fill -> edit condition + femur -> export.
    import myogait as mg
    data = _pivot()
    mg.set_subject(data, height_m=1.7, femur_length_mm=400.0)
    mg.set_study(data, patient_id="P9", condition="baseline")
    # pre-fill the editors
    cfg = SubjectConfig.from_subject_dict(data["subject"])
    study = study_from_data(data)
    # user edits
    cfg = SubjectConfig(**{**cfg.__dict__, "femur_length_mm": 425.0})
    study["condition"] = "post-op"
    # export merge
    exported = _apply_subject(_pivot(study=dict(data["study"])), cfg)
    exported = apply_study(exported, study)
    assert exported["subject"]["femur_length_mm"] == 425.0
    assert exported["study"]["condition"] == "post-op"
    assert exported["study"]["patient_id"] == "P9"


def test_study_keys_constant():
    assert STUDY_KEYS == ("patient_id", "run", "group", "condition")
