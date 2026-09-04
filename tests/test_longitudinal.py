"""End-to-end exercise of the Longitudinal engine on synthetic sessions.

The plain page smoke test only renders the empty state; this drives the exact
myogait functions the Longitudinal page calls -- gait_profile_score_2d,
plot_longitudinal, plot_session_comparison, generate_longitudinal_report -- on
several dated sessions built from the demo recording, so a regression in the
trend, the pairwise comparison or the PDF fails here instead of only in the UI.

Guarded on feature availability (older myogait may lack a piece) so it skips
cleanly rather than erroring where the app would just hide the section.
"""

from __future__ import annotations

from pathlib import Path

import pytest

# The Longitudinal engine returns matplotlib figures; skip the whole module
# (cleanly, at collection) where matplotlib is not installed -- e.g. the CI
# image, which does not ship the plotting extra -- rather than error out.
matplotlib = pytest.importorskip("matplotlib")
matplotlib.use("Agg")  # headless: build the figure objects, open no window

APP_PY = Path(__file__).resolve().parent.parent / "app.py"


def _sessions(n: int = 3) -> list[dict]:
    """Run the demo recording n times as dated sessions, like the page does."""
    from myogait_app.demo import make_demo_data
    from myogait_app.pipeline import PipelineConfig, PipelineRunner
    from myogait_app.runtime import get_runtime

    runtime = get_runtime()
    sessions = []
    for i in range(n):
        data = make_demo_data()
        result = PipelineRunner(data, source_key=f"long-test-{i}").run(PipelineConfig())
        assert result.ok, "demo recording should run under the default config"
        stats = dict(result.stats or {})
        if runtime.has("scores"):
            from myogait import gait_profile_score_2d

            stats.update(gait_profile_score_2d(result.cycles))
        sessions.append({
            "label": f"visit_{i + 1}", "date": f"2026-0{i + 1}-15",
            "data": result.data, "cycles": result.cycles, "stats": stats,
        })
    return sessions


def test_trend_plot_builds_for_each_metric():
    pytest.importorskip("myogait")
    from myogait_app.runtime import get_runtime

    runtime = get_runtime()
    if not runtime.has("longitudinal"):
        pytest.skip("myogait build lacks the longitudinal feature")
    from myogait import plot_longitudinal

    sessions = _sessions()
    metrics = ["cadence", "symmetry"]
    if runtime.has("scores"):
        metrics.append("gps_2d_overall")
    for metric in metrics:
        figure = plot_longitudinal(sessions, metric=metric)
        assert figure is not None
        assert figure.axes, f"{metric} trend produced no axes"


def test_pairwise_session_comparison_builds():
    pytest.importorskip("myogait")
    from myogait_app.runtime import get_runtime

    if not get_runtime().has("longitudinal"):
        pytest.skip("myogait build lacks the longitudinal feature")
    from myogait import plot_session_comparison

    sessions = _sessions(2)
    figure = plot_session_comparison(sessions[0], sessions[-1])
    assert figure is not None
    assert figure.axes


def test_param_mdc_estimates_from_within_session_cycle_spread():
    from myogait_app.ui.page_longitudinal import _param_mdc

    def session(seed: float) -> dict:
        # 5 cycles/session x 3 sessions -> 12 pooled degrees of freedom,
        # clearing mdc.MIN_DOF (10); a small per-cycle jitter so pooled_sw
        # is a real, non-zero spread rather than a degenerate one.
        cycles = {"cycles": [
            {"side": "left", "angles_normalized": {
                "hip": [0.0, 30.0 + seed + 0.5 * i],
            }}
            for i in range(5)
        ]}
        return {"cycles": cycles}

    sessions = [session(0.0), session(1.0), session(2.0)]
    mdc = _param_mdc(sessions, "hip_rom")
    assert mdc is not None and mdc > 0

    # A parameter that is not a "*_rom" biomarker has no per-cycle spread to
    # estimate noise from here (spatiotemporal / accelerometry are already a
    # single scalar per session).
    assert _param_mdc(sessions, "cadence_steps_per_min") is None


def test_param_mdc_needs_at_least_two_sessions_with_cycles():
    from myogait_app.ui.page_longitudinal import _param_mdc

    one_session = [{"cycles": {"cycles": [
        {"side": "left", "angles_normalized": {"hip": [0.0, 30.0]}},
    ]}}]
    assert _param_mdc(one_session, "hip_rom") is None


def test_parameter_label_formats_rom_and_plain_parameters():
    from myogait_app.ui.page_longitudinal import _parameter_label

    assert _parameter_label("hip_abd_add_deg_rom") == "Hip Abd Add ROM (deg)"
    assert _parameter_label("cadence_steps_per_min") == "Cadence Steps Per Min"


def test_biomarker_trend_section_renders_in_the_app(tmp_path, monkeypatch):
    """Advanced -> Patient over time -> "All parameters over time" wires up
    end to end: a parameter picker offering more than the fixed
    cadence/symmetry/GPS-2D set myogait's own plot_longitudinal covers
    (audit B1 extension)."""
    pytest.importorskip("streamlit")
    pytest.importorskip("myogait")
    from streamlit.testing.v1 import AppTest

    from myogait_app.demo import make_demo_data
    from myogait_app.jobs import JobManager
    from myogait_app.settings import Settings
    from myogait_app.ui import state as ui_state

    settings = Settings(workspace_root=tmp_path)
    manager = JobManager(settings)
    manager.register_immediate(
        make_demo_data(), "visit.mp4", "mediapipe", study={"patient_id": "P01"},
    )
    manager._pool.shutdown(wait=True)
    monkeypatch.setattr("myogait_app.ui.page_longitudinal.SETTINGS", settings)

    app = AppTest.from_file(str(APP_PY), default_timeout=120)
    app.run()
    app.session_state[ui_state.K_LONGITUDINAL] = _sessions(2)
    app.session_state["nav_page"] = "Advanced"
    app.run()
    assert not app.exception

    headers = " ".join(m.value for m in app.markdown)
    assert "All parameters over time" in headers
    picker = app.selectbox(key="long_trend_param")
    assert len(picker.options) > 2  # more than plot_longitudinal's fixed set
    assert "Cadence Steps Per Min" in picker.options  # AppTest exposes the formatted label


def test_multi_session_pdf_report_is_written(tmp_path):
    pytest.importorskip("myogait")
    from myogait_app.runtime import get_runtime

    if not get_runtime().has("report"):
        pytest.skip("myogait build lacks the report feature")
    from myogait import generate_longitudinal_report

    sessions = _sessions()
    out = tmp_path / "longitudinal_report.pdf"
    generate_longitudinal_report(sessions, str(out), language="fr")
    assert out.exists() and out.stat().st_size > 1000, "report PDF missing or empty"
