from __future__ import annotations

from myogait_app.demo import make_demo_data
from myogait_app.jobs import C3D_IMPORT_MODEL_LABEL, DONE, FAILED, RUNNING, Job, JobManager
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


def test_c3d_import_model_label_lives_in_jobs_module():
    # Moved here 2026-09-04 from ui/page_data.py: it names a Job.model
    # sentinel (this module's own domain type), and jobs.py stays
    # Streamlit-free -- several ui/ pages need this constant without
    # pulling in Streamlit just to reach a string. Regression guard so it
    # does not quietly drift back to a ui/ module.
    assert C3D_IMPORT_MODEL_LABEL == "c3d-import"
