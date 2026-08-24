"""Recovering the true axis ratio a C3D file was normalised against.

``myogait.load_c3d`` projects 3-D marker trajectories onto a 2-D sagittal
plane and normalises the antero-posterior and vertical axes *independently*,
each by its own min/max range, then reports a square 1000x1000 virtual
canvas in ``meta.width``/``meta.height``. ``compute_angles(apply_aspect_ratio=
True)`` only rescales when ``width != height``, so for a C3D source that
correction silently never runs -- even though a walking trial's
antero-posterior excursion is almost never on the same physical scale as
its vertical one.

This module re-reads the same markers ``load_c3d`` used to derive the two
true ranges, so the app can overwrite ``meta.width``/``meta.height`` with
them before ``compute_angles`` runs, restoring a correct aspect ratio.
"""

from __future__ import annotations

import warnings
from pathlib import Path

import numpy as np


def marker_axis_ranges(
    c3d_path: str | Path,
    marker_mapping: dict[str, list[str]],
    ap_axis: int = 1,
    vertical_axis: int = 2,
) -> tuple[float, float]:
    """Return (ap_range, vertical_range) over the markers *load_c3d* used.

    Mirrors ``load_c3d``'s own marker resolution (first-match-per-landmark,
    averaged when several candidates are present) so the ranges match
    exactly what it normalised by. Requires *ezc3d*, same as ``load_c3d``.
    """
    import ezc3d

    c3d = ezc3d.c3d(str(c3d_path))
    labels = [lbl.strip() for lbl in c3d["parameters"]["POINT"]["LABELS"]["value"]]
    points = c3d["data"]["points"]  # (4, n_markers, n_frames)
    label_idx = {lbl: i for i, lbl in enumerate(labels)}

    ap_values: list[np.ndarray] = []
    vert_values: list[np.ndarray] = []
    for candidates in marker_mapping.values():
        found = [label_idx[mk] for mk in candidates if mk in label_idx]
        if not found:
            continue
        pts = points[:3, found, :].astype(float, copy=True)  # (3, n_found, n_frames)
        # ezc3d encodes an occluded sample as exact (0, 0, 0) rather than
        # NaN (same quirk load_c3d itself works around). Left alone, those
        # zeros drag the min this function returns down towards 0 on any
        # file with occlusion, understating the true range and therefore
        # the aspect-ratio correction this function exists to compute.
        missing = (pts == 0.0).all(axis=0)  # (n_found, n_frames)
        pts[:, missing] = np.nan
        with np.errstate(invalid="ignore"), warnings.catch_warnings():
            # A candidate marker that is occluded on every frame produces
            # an all-NaN row here; harmless (nanmax/nanmin below simply
            # ignore it), but numpy warns on the mean of an empty slice.
            # load_c3d silences the same warning for the same reason.
            warnings.simplefilter("ignore", RuntimeWarning)
            avg = np.nanmean(pts, axis=1)  # (3, n_frames)
        ap_values.append(avg[ap_axis])
        vert_values.append(avg[vertical_axis])

    if not ap_values:
        raise ValueError(
            f"No mapped marker found in {Path(c3d_path).name} -- cannot "
            "estimate axis ranges."
        )

    ap_all = np.concatenate(ap_values)
    vert_all = np.concatenate(vert_values)
    with np.errstate(invalid="ignore"):
        ap_range = float(np.nanmax(ap_all) - np.nanmin(ap_all)) or 1.0
        vert_range = float(np.nanmax(vert_all) - np.nanmin(vert_all)) or 1.0
    return ap_range, vert_range
