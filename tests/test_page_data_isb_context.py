"""_build_isb_context's own tier-selection logic.

page_data.py is the single entry point for every kind of recording (video,
C3D, JSON, ticket) and this one function silently decides, at load time,
which ISB calibration tier (1/2/3) the rest of the pipeline gets for a
C3D -- a wrong or unnoticed downgrade here has knock-on effects everywhere
ISB reconstruction is used later. The audit flagged this file (33% covered,
no dedicated test file) as the least-tested code real data flows through
(DEV-03). This does not attempt the full tier-2/tier-3 success paths
(they need a real calibrated C3D fixture) -- it covers the tier-selection
logic and the documented "never raises, degrade instead" contract on
failure, which is the part most likely to silently regress.
"""

from __future__ import annotations

from pathlib import Path

import pytest


def _build_isb_context():
    pytest.importorskip("streamlit")
    from myogait_app.ui.page_data import _build_isb_context as build

    return build


def test_incapable_source_returns_no_context_without_touching_disk():
    build = _build_isb_context()

    context, diagnostics, identity = build(
        dynamic_path=Path("unused.c3d"), mapping=None, isb_capable=False,
        ap_axis=0, vertical_axis=1, static_path=None, vsk_path=None, prot_path=None,
    )

    assert context == {}
    assert diagnostics == {"capable": False}
    assert identity == ()


def test_capable_with_no_static_trial_stays_tier1(tmp_path):
    build = _build_isb_context()
    dynamic = tmp_path / "dynamic.c3d"
    dynamic.write_bytes(b"")

    context, diagnostics, identity = build(
        dynamic_path=dynamic, mapping=None, isb_capable=True,
        ap_axis=0, vertical_axis=1, static_path=None, vsk_path=None, prot_path=None,
    )

    assert context == {}
    assert diagnostics == {"capable": True, "tier": "tier1"}
    assert identity == ()


def test_static_trial_resolving_no_landmarks_degrades_to_tier1_with_a_warning(
    tmp_path, monkeypatch,
):
    """The documented "never raises" contract: a static trial that fails to
    resolve c3d_markers_3d must not blow up the load it is attached to --
    it warns once and the context degrades to tier 1 instead."""
    pytest.importorskip("myogait")
    build = _build_isb_context()
    dynamic = tmp_path / "dynamic.c3d"
    dynamic.write_bytes(b"")
    static = tmp_path / "static.c3d"
    static.write_bytes(b"")

    warnings: list[str] = []
    monkeypatch.setattr("streamlit.warning", lambda msg: warnings.append(msg))
    monkeypatch.setattr("myogait.load_c3d", lambda *a, **k: {"c3d_markers_3d": {}})

    context, diagnostics, identity = build(
        dynamic_path=dynamic, mapping=None, isb_capable=True,
        ap_axis=0, vertical_axis=1, static_path=static, vsk_path=None, prot_path=None,
    )

    assert context == {}
    assert diagnostics == {"capable": True, "tier": "tier1"}
    assert identity, "the static file's own (size, mtime) fingerprint should still be recorded"
    assert warnings and "static trial" in warnings[0]
