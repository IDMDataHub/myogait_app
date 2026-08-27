from __future__ import annotations

from datetime import datetime, timezone

from myogait_app.pipeline import PipelineConfig
from myogait_app.provenance import build_provenance, fingerprint_pivot, write_provenance
from myogait_app.quality import assess_quality
from myogait_app.runtime import Runtime
from myogait_app.storage import read_json


def _runtime() -> Runtime:
    return Runtime("0.8.2", "1.4.8", "cpu", "test", (), (), ())


def test_provenance_is_reproducible_when_given_a_timestamp():
    created_at = datetime(2026, 8, 25, tzinfo=timezone.utc)
    provenance = build_provenance(PipelineConfig(), _runtime(), created_at)

    assert provenance["created_at"] == "2026-08-25T00:00:00+00:00"
    assert provenance["packages"] == {"myogait": "0.8.2", "gaitkit": "1.4.8"}
    assert provenance["pipeline_config"]["normalize"]["butterworth_cutoff"] == 4.0
    assert provenance["schema_version"] == 2


def test_provenance_sidecar_is_valid_json(tmp_path):
    destination = write_provenance(tmp_path / "result.provenance.json", PipelineConfig())

    assert read_json(destination)["schema_version"] == 2


def test_provenance_records_source_fingerprint_and_quality_without_source_content():
    source = {
        "frames": [
            {
                "confidence": 0.9,
                "landmarks": {
                    "LEFT_HIP": {"x": 0.4, "y": 0.5},
                    "RIGHT_HIP": {"x": 0.6, "y": 0.5},
                },
            }
        ],
        "subject": {"patient_id": "secret"},
    }
    quality = assess_quality(source, {"cycles": [{"side": "left"}]})

    provenance = build_provenance(
        PipelineConfig(),
        _runtime(),
        source_data=source,
        source_key="a1b2",
        source_kind="json",
        model="mediapipe",
        quality=quality,
    )

    assert provenance["input"] == {
        "source_key": "a1b2",
        "kind": "json",
        "model": "mediapipe",
        "sha256": fingerprint_pivot(source),
    }
    assert "patient_id" not in str(provenance)
    assert provenance["quality_assessment"]["status"] in {"accepted", "warning"}
