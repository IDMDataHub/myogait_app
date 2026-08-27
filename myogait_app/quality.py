"""One explicit interpretation gate for locally analysed recordings."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any, Literal


QualityStatus = Literal["accepted", "warning", "rejected"]


@dataclass(frozen=True)
class QualityPolicy:
    """Thresholds used to classify an analysis without changing its raw data."""

    reject_below_score: float = 40.0
    warn_below_score: float = 70.0


@dataclass(frozen=True)
class QualityAssessment:
    """Machine-readable decision about whether derived metrics are interpretable."""

    status: QualityStatus
    score: float | None
    n_cycles: int | None
    n_rejected_cycles: int
    reasons: tuple[str, ...]

    @property
    def allows_derived_metrics(self) -> bool:
        """Whether the app may present derived metrics without a hard stop."""
        return self.status != "rejected"

    def to_dict(self) -> dict[str, Any]:
        """Return a stable representation for exports and provenance records."""
        return {
            "status": self.status,
            "score": self.score,
            "n_cycles": self.n_cycles,
            "n_rejected_cycles": self.n_rejected_cycles,
            "reasons": list(self.reasons),
            "allows_derived_metrics": self.allows_derived_metrics,
        }


def _quality_score(data: dict) -> float | None:
    """Compute MyoGait's score on a copy, never mutating cached pipeline data."""
    stored = data.get("quality")
    if isinstance(stored, dict) and stored.get("score") is not None:
        try:
            return float(stored["score"])
        except (TypeError, ValueError):
            pass
    try:
        from myogait import data_quality_score

        score = data_quality_score(copy.deepcopy(data)).get("score")
        return float(score) if score is not None else None
    except Exception:  # A missing optional capability must not hide raw data.
        return None


def assess_quality(
    data: dict | None,
    cycles: dict | None,
    policy: QualityPolicy = QualityPolicy(),
) -> QualityAssessment:
    """Classify an analysis using extraction quality and usable cycle count.

    The gate does not alter or discard raw data. ``rejected`` means that a
    derived result should be withheld; users can still inspect and export the
    recording with the reasons attached.
    """
    if not data or not isinstance(data.get("frames"), list) or not data["frames"]:
        return QualityAssessment(
            "rejected", None, None, 0, ("The recording has no usable frames.",)
        )

    score = _quality_score(data)
    cycle_items = cycles.get("cycles") if isinstance(cycles, dict) else None
    n_cycles = len(cycle_items) if isinstance(cycle_items, list) else None
    summary = cycles.get("summary") if isinstance(cycles, dict) else None
    n_rejected = (
        int(summary.get("n_rejected_quality", 0))
        if isinstance(summary, dict)
        else 0
    )
    reasons: list[str] = []

    if n_cycles == 0:
        reasons.append("No gait cycle passed segmentation.")
    if score is not None and score < policy.reject_below_score:
        reasons.append(f"Extraction quality score is below {policy.reject_below_score:.0f}/100.")

    if reasons:
        return QualityAssessment("rejected", score, n_cycles, n_rejected, tuple(reasons))

    if score is None:
        reasons.append("Extraction quality score is unavailable.")
    elif score < policy.warn_below_score:
        reasons.append(f"Extraction quality score is below {policy.warn_below_score:.0f}/100.")
    if n_rejected:
        reasons.append(f"{n_rejected} cycle(s) were rejected by quality gates.")

    status: QualityStatus = "warning" if reasons else "accepted"
    return QualityAssessment(status, score, n_cycles, n_rejected, tuple(reasons))
