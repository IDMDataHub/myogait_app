from __future__ import annotations

from myogait_app.demo import make_demo_data
from myogait_app.jobs import (
    C3D_IMPORT_MODEL_LABEL,
    DONE,
    FAILED,
    RUNNING,
    Job,
    JobManager,
    paired_ready_groups,
)
from myogait_app.settings import Settings
from myogait_app.storage import job_dir, write_json_atomic


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


def test_stale_job_cannot_be_revived_by_a_late_worker(tmp_path):
    settings = Settings(workspace_root=tmp_path, job_stale_minutes=1)
    manager = JobManager(settings)
    ticket = "MG-ABCD-2345"
    job = Job(ticket=ticket, status=RUNNING, created_at=1.0, updated_at=1.0)
    write_json_atomic(job_dir(ticket, settings) / "job.json", job.to_dict())

    stale = manager.get(ticket)
    assert stale is not None
    assert stale.status == FAILED

    job.status = DONE
    assert not manager._write(job)
    assert manager.get(ticket).status == FAILED
    manager._pool.shutdown(wait=True)


def test_corrupt_job_records_do_not_break_polling_or_listing(tmp_path):
    settings = Settings(workspace_root=tmp_path)
    manager = JobManager(settings)
    ticket = "MG-ABCD-2345"
    record = job_dir(ticket, settings) / "job.json"
    record.parent.mkdir(parents=True)
    record.write_text('["not", "a", "job"]', encoding="utf-8")

    assert manager.get(ticket) is None
    assert manager.list_jobs() == []
    manager._pool.shutdown(wait=True)


def test_register_immediate_lists_a_c3d_import_like_a_finished_job(tmp_path):
    """A C3D load is synchronous and never goes through submit()/_run -- it

    needs its own path to a DONE job with a readable result, so it can be
    tick-selected in Recent jobs next to a video extraction and pooled via
    the same _selection_actions -> pooling.load_runs shortcut (see
    JobManager.register_immediate's docstring for the gap this closes).
    """
    settings = Settings(workspace_root=tmp_path)
    manager = JobManager(settings)
    data = make_demo_data()
    study = {"patient_id": "P03", "condition": "walk"}

    ticket = manager.register_immediate(data, "markers.c3d", "c3d-import", study=study)

    job = manager.get(ticket)
    assert job is not None
    assert job.status == DONE
    assert job.succeeded
    assert job.model == "c3d-import"
    assert job.video_name == "markers.c3d"
    assert job.study == study
    result_path = job.result_path(settings)
    assert result_path is not None and result_path.is_file()

    from myogait import load_json

    reloaded = load_json(str(result_path))
    assert reloaded["study"] == study

    assert any(j.ticket == ticket for j in manager.list_jobs())
    manager._pool.shutdown(wait=True)


def test_paired_ready_groups_finds_only_complete_video_c3d_pairs():
    """Feeds page_pool.py's "Accuracy vs C3D" history picker (audit UX-04):
    only a (patient_id, condition) group holding both a video job and a
    C3D-import job is "ready" -- a lone video, a lone C3D, or an untagged
    job (no patient_id) must never show up as pairable."""
    video = Job(ticket="MG-0001-AAAA", status=DONE, model="mediapipe",
                study={"patient_id": "P03", "condition": "walk"})
    c3d = Job(ticket="MG-0002-BBBB", status=DONE, model=C3D_IMPORT_MODEL_LABEL,
              study={"patient_id": "P03", "condition": "walk"})
    video_only = Job(ticket="MG-0003-CCCC", status=DONE, model="mediapipe",
                      study={"patient_id": "P04", "condition": "walk"})
    untagged = Job(ticket="MG-0004-DDDD", status=DONE, model="mediapipe", study={})

    groups = paired_ready_groups([video, c3d, video_only, untagged])

    assert set(groups) == {("P03", "walk")}
    assert {j.ticket for j in groups[("P03", "walk")]} == {video.ticket, c3d.ticket}


def test_paired_ready_groups_ignores_a_second_c3d_without_a_video():
    c3d_a = Job(ticket="MG-0005-EEEE", status=DONE, model=C3D_IMPORT_MODEL_LABEL,
                study={"patient_id": "P05", "condition": "walk"})
    c3d_b = Job(ticket="MG-0006-FFFF", status=DONE, model=C3D_IMPORT_MODEL_LABEL,
                study={"patient_id": "P05", "condition": "walk"})

    assert paired_ready_groups([c3d_a, c3d_b]) == {}
