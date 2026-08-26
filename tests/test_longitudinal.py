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

import pytest

# The Longitudinal engine returns matplotlib figures; skip the whole module
# (cleanly, at collection) where matplotlib is not installed -- e.g. the CI
# image, which does not ship the plotting extra -- rather than error out.
matplotlib = pytest.importorskip("matplotlib")
matplotlib.use("Agg")  # headless: build the figure objects, open no window


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
