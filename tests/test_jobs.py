from __future__ import annotations

from myogait_app.jobs import DONE, Job
from myogait_app.settings import Settings
from myogait_app.storage import job_dir


def test_job_result_path_rejects_path_traversal(tmp_path):
    settings = Settings(workspace_root=tmp_path)
    ticket = "MG-ABCD-2345"
    root = job_dir(ticket, settings)
    root.mkdir(parents=True)
    valid = root / "result.json"
    valid.write_text("{}", encoding="utf-8")
    outside = tmp_path / "secret.json"
    outside.write_text("secret", encoding="utf-8")

    job = Job(ticket=ticket, status=DONE, result_file="result.json")
    escaped = Job(ticket=ticket, status=DONE, result_file="../../secret.json")

    assert job.result_path(settings) == valid
    assert escaped.result_path(settings) is None


def test_job_serialization_preserves_study_metadata():
    job = Job(ticket="MG-ABCD-2345", status=DONE, study={"participant": "synthetic"})

    restored = Job.from_dict(job.to_dict())

    assert restored.study == {"participant": "synthetic"}
    assert restored.succeeded
