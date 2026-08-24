"""Adapting ``load_c3d``'s marker_mapping to whatever a file actually contains.

myogait's own ``DEFAULT_C3D_MARKER_MAP`` assumes one specific clinical
marker set (CAST-style: LASIS/RASIS, LLFE/RLFE/LMFE/RMFE, LLM/RLM/LMM/RMM,
LCAL/RCAL, LTT2/RTT2). A file produced by a different lab or capture system
-- Vicon Plug-in Gait being the other marker set in wide clinical use --
labels the same anatomical points differently, so the package default
silently matches nothing and ``load_c3d`` raises ``ValueError``.

This module builds an effective ``marker_mapping`` for an arbitrary file in
two passes: known-alias lookup (the package default plus Plug-in Gait)
first, then a side (L/R prefix or suffix) plus anatomical-keyword scan over
whatever labels neither matched, so an unfamiliar convention still resolves
as long as it follows the near-universal abbreviation style motion capture
marker sets use. Presets are a fast path, not a boundary: any file gets both
passes, so a hand-rolled lab convention is not stuck with manual mapping
either.
"""

from __future__ import annotations

import re
from pathlib import Path

#: Vicon Plug-in Gait: the other marker set in wide clinical use, alongside
#: myogait's own CAST-style default. Standard PiG labels.
PLUGINGAIT_ALIASES: dict[str, list[str]] = {
    "LEFT_HIP": ["LASI"],
    "RIGHT_HIP": ["RASI"],
    "LEFT_KNEE": ["LKNE"],
    "RIGHT_KNEE": ["RKNE"],
    "LEFT_ANKLE": ["LANK"],
    "RIGHT_ANKLE": ["RANK"],
    "LEFT_HEEL": ["LHEE"],
    "RIGHT_HEEL": ["RHEE"],
    "LEFT_FOOT_INDEX": ["LTOE"],
    "RIGHT_FOOT_INDEX": ["RTOE"],
    "LEFT_SHOULDER": ["LSHO"],
    "RIGHT_SHOULDER": ["RSHO"],
    "LEFT_ELBOW": ["LELB"],
    "RIGHT_ELBOW": ["RELB"],
    "LEFT_WRIST": ["LWRA", "LWRB"],
    "RIGHT_WRIST": ["RWRA", "RWRB"],
    "NOSE": ["LFHD", "RFHD"],
}

#: Anatomical keyword rules for the fuzzy fallback, applied to a label's
#: remainder after its L/R side has been stripped. ``"eq"`` requires an
#: exact match (for short, ambiguous tokens like the malleolus initials);
#: ``"has"`` is a substring check.
_CONCEPT_KEYWORDS: dict[str, list[tuple[str, str]]] = {
    "HIP": [
        ("has", "ASIS"), ("has", "ASI"), ("has", "PSI"), ("has", "HIP"),
        ("has", "PELV"), ("has", "ILIAC"), ("eq", "HJC"),
    ],
    "KNEE": [
        ("has", "KNEE"), ("has", "KNE"), ("has", "LFE"), ("has", "MFE"),
        ("has", "EPICON"),
    ],
    "ANKLE": [
        ("has", "ANKLE"), ("has", "ANK"), ("has", "MALLEOL"),
        ("eq", "LM"), ("eq", "MM"),
    ],
    "HEEL": [("has", "HEEL"), ("has", "HEE"), ("has", "CALC"), ("eq", "CAL")],
    "FOOT_INDEX": [
        ("has", "TOE"), ("has", "MTP2"), ("has", "MT2"), ("eq", "TT2"),
        ("has", "D2"),
    ],
    "SHOULDER": [("has", "SHOULDER"), ("has", "SHO"), ("has", "ACROM")],
    "ELBOW": [("has", "ELBOW"), ("has", "ELB")],
    "WRIST": [
        ("has", "WRIST"), ("has", "WRA"), ("has", "WRB"), ("eq", "WRI"),
    ],
}

_SIDE_PREFIX_RE = re.compile(r"^(LEFT|RIGHT|L|R)[_\-. ]?(?=[A-Z0-9])", re.IGNORECASE)
_SIDE_SUFFIX_RE = re.compile(r"[_\-. ](LEFT|RIGHT|L|R)$", re.IGNORECASE)


def _normalize(label: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", label.strip().upper())


def _infer_side(label: str) -> tuple[str | None, str]:
    """Return (``"L"``/``"R"``/``None``, remainder) after stripping a side marker.

    Suffix is checked first: a prefix match on a label like ``"KNEE_L"``
    would otherwise never fire, since ``"K"`` is not a side letter.
    """
    raw = label.strip()
    m = _SIDE_SUFFIX_RE.search(raw)
    if m:
        side = "L" if m.group(1).upper().startswith("L") else "R"
        return side, raw[: m.start()]
    m = _SIDE_PREFIX_RE.match(raw)
    if m:
        side = "L" if m.group(1).upper().startswith("L") else "R"
        return side, raw[m.end():]
    return None, raw


def _matches(remainder: str, rules: list[tuple[str, str]]) -> bool:
    return any(
        remainder == token if kind == "eq" else token in remainder
        for kind, token in rules
    )


def read_c3d_labels(c3d_path: str | Path) -> list[str]:
    """Return the POINT labels a C3D file declares, without building a pivot.

    Cheap enough to run on every upload: unlike ``load_c3d`` this skips
    projecting or normalising any coordinate, it only reads the parameter
    block.
    """
    import ezc3d

    c3d = ezc3d.c3d(str(c3d_path))
    return [lbl.strip() for lbl in c3d["parameters"]["POINT"]["LABELS"]["value"]]


def auto_detect_mapping(
    labels: list[str], base: dict[str, list[str]] | None = None
) -> tuple[dict[str, list[str]], dict[str, str]]:
    """Build a ``marker_mapping`` for *labels*, whatever convention produced them.

    Parameters
    ----------
    labels : list[str]
        The raw ``POINT`` labels from the file, as returned by
        :func:`read_c3d_labels`.
    base : dict, optional
        Alias source for the first pass. Defaults to myogait's own
        ``DEFAULT_C3D_MARKER_MAP``.

    Returns
    -------
    (mapping, source)
        *mapping* is ready to pass as ``load_c3d(..., marker_mapping=mapping)``.
        *source* records, per matched landmark, whether it came from
        ``"alias"`` (package default or Plug-in Gait), ``"fuzzy"`` (keyword
        scan) or ``"fallback"`` (NOSE borrowing the hip markers, matching
        the package default's own behaviour) -- for display only.
    """
    from myogait.experimental_vicon import DEFAULT_C3D_MARKER_MAP

    if base is None:
        base = DEFAULT_C3D_MARKER_MAP

    norm_to_actual: dict[str, str] = {}
    for lbl in labels:
        norm_to_actual.setdefault(_normalize(lbl), lbl.strip())

    alias_pool: dict[str, list[str]] = {}
    for landmark, candidates in base.items():
        alias_pool.setdefault(landmark, []).extend(candidates)
    for landmark, candidates in PLUGINGAIT_ALIASES.items():
        bucket = alias_pool.setdefault(landmark, [])
        for candidate in candidates:
            if candidate not in bucket:
                bucket.append(candidate)

    mapping: dict[str, list[str]] = {}
    source: dict[str, str] = {}

    all_landmarks = set(alias_pool) | {
        f"{side}_{concept}"
        for side in ("LEFT", "RIGHT")
        for concept in _CONCEPT_KEYWORDS
    }

    # Pass 1: known aliases, exact match modulo case/punctuation.
    for landmark in all_landmarks:
        found = [
            norm_to_actual[_normalize(candidate)]
            for candidate in alias_pool.get(landmark, [])
            if _normalize(candidate) in norm_to_actual
        ]
        if found:
            mapping[landmark] = found
            source[landmark] = "alias"

    # Pass 2: side + anatomical-keyword scan over whatever is left.
    used = {lbl for found in mapping.values() for lbl in found}
    remaining = [lbl for lbl in labels if lbl.strip() not in used]
    for side, prefix in (("LEFT", "L"), ("RIGHT", "R")):
        for concept, rules in _CONCEPT_KEYWORDS.items():
            landmark = f"{side}_{concept}"
            if landmark in mapping:
                continue
            found = []
            for lbl in remaining:
                inferred_side, remainder = _infer_side(lbl)
                if inferred_side != prefix:
                    continue
                if _matches(_normalize(remainder), rules):
                    found.append(lbl.strip())
            if found:
                mapping[landmark] = found
                source[landmark] = "fuzzy"

    # NOSE has no side to key off; fall back to the hip markers, same as
    # the package default does when no head marker is present.
    if "NOSE" not in mapping:
        fallback = mapping.get("LEFT_HIP", []) + mapping.get("RIGHT_HIP", [])
        if fallback:
            mapping["NOSE"] = fallback
            source["NOSE"] = "fallback"

    return mapping, source
