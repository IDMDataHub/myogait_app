"""Adapting ``load_c3d``'s marker_mapping to whatever a file actually contains.

myogait's own ``DEFAULT_C3D_MARKER_MAP`` assumes one specific clinical
marker set (CAST-style: LASIS/RASIS, LLFE/RLFE/LMFE/RMFE, LLM/RLM/LMM/RMM,
LCAL/RCAL, LTT2/RTT2). A file produced by a different lab or capture system
-- Vicon Plug-in Gait being the other marker set in wide clinical use --
labels the same anatomical points differently, so the package default
silently matches nothing and ``load_c3d`` raises ``ValueError``.

This module builds an effective ``marker_mapping`` for an arbitrary file in
two passes: known-alias lookup (the package default, Plug-in Gait, and the
ISB/CAST full-body variant below) first, then a side (L/R prefix or suffix)
plus anatomical-keyword scan over whatever labels neither matched, so an
unfamiliar convention still resolves as long as it follows the
near-universal abbreviation style motion capture marker sets use. Presets
are a fast path, not a boundary: any file gets both passes, so a
hand-rolled lab convention is not stuck with manual mapping either.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
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

#: ISB/CAST full-body marker set (Cappozzo et al.) as used by the Nature
#: Scientific Data "Multimodal Gait Dataset" -- underscore side prefix on
#: two-letter anatomical codes (IAS/IPS = iliac spines, FLE/FME = femur
#: epicondyles, FAL/TAM = malleoli, FCC = calcaneus, FM1/FM2/FM5 =
#: metatarsal heads, CV7 = 7th cervical vertebra). Confirmed against a real
#: file from that dataset: none of myogait's registered conventions nor
#: the fuzzy fallback below resolve it (0/6 required landmarks) without
#: this table, since its codes don't contain the ANK/KNE/HIP-style
#: substrings the keyword scan looks for.
NATURE_MULTIMODAL_ALIASES: dict[str, list[str]] = {
    "LEFT_HIP": ["L_IAS", "L_IPS"],
    "RIGHT_HIP": ["R_IAS", "R_IPS"],
    "LEFT_KNEE": ["L_FLE", "L_FME"],
    "RIGHT_KNEE": ["R_FLE", "R_FME"],
    "LEFT_ANKLE": ["L_FAL", "L_TAM"],
    "RIGHT_ANKLE": ["R_FAL", "R_TAM"],
    "LEFT_HEEL": ["L_FCC"],
    "RIGHT_HEEL": ["R_FCC"],
    "LEFT_FOOT_INDEX": ["L_FM2", "L_FM1"],
    "RIGHT_FOOT_INDEX": ["R_FM2", "R_FM1"],
    "LEFT_SHOULDER": ["L_SIA"],
    "RIGHT_SHOULDER": ["R_SIA"],
    "NOSE": ["CV7"],
}

try:
    from myogait.experimental_vicon import C3D_MARKER_CONVENTIONS as _MYOGAIT_C3D_CONVENTIONS

    _MYOGAIT_C3D_CONVENTIONS.setdefault("nature_multimodal", NATURE_MULTIMODAL_ALIASES)
except ImportError:
    pass  # myogait < 0.7.0: no registry to extend, the alias-pool merge below still covers it.

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

    Results are cached by path and file fingerprint. Streamlit reruns the C3D
    page whenever a mapping control changes; re-opening a large trial just to
    rediscover the unchanged parameter block needlessly stalls that interface.
    """
    path = Path(c3d_path).resolve()
    stat = path.stat()
    return list(_read_c3d_labels_cached(str(path), stat.st_mtime_ns, stat.st_size))


@lru_cache(maxsize=32)
def _read_c3d_labels_cached(
    path: str, modified_ns: int, size_bytes: int
) -> tuple[str, ...]:
    """Read one immutable C3D fingerprint; kept separate for safe caching."""
    import ezc3d

    c3d = ezc3d.c3d(path)
    return tuple(lbl.strip() for lbl in c3d["parameters"]["POINT"]["LABELS"]["value"])


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
    for extra_aliases in (PLUGINGAIT_ALIASES, NATURE_MULTIMODAL_ALIASES):
        for landmark, candidates in extra_aliases.items():
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


#: The six lower-limb landmarks load_c3d needs at least 4 of, mirroring
#: myogait.experimental_vicon.detect_c3d_convention's own threshold
#: (kept as a local constant rather than importing that module's
#: underscore-prefixed one, which is private API).
REQUIRED_LANDMARKS = (
    "LEFT_HIP", "RIGHT_HIP",
    "LEFT_KNEE", "RIGHT_KNEE",
    "LEFT_ANKLE", "RIGHT_ANKLE",
)


@dataclass
class MappingDiagnostics:
    """How :func:`resolve_c3d_mapping` arrived at its mapping, for display.

    ``method`` is ``"native"`` when myogait's own ``detect_c3d_convention``
    resolved enough landmarks on its own, ``"fuzzy"`` when this module's
    alias-plus-keyword scan had to be tried instead (older myogait, or an
    exotic convention neither detector's registry covers).
    """

    method: str
    n_resolved: int
    convention: str | None = None
    scores: dict[str, int] | None = None
    source: dict[str, str] | None = None


def resolve_c3d_mapping(labels: list[str]) -> tuple[dict[str, list[str]], MappingDiagnostics]:
    """Best-effort ``marker_mapping`` for *labels*, myogait's own detector first.

    Tries :func:`myogait.detect_c3d_convention` first (myogait >= 0.7.0):
    it scores five registered conventions plus a regex fallback, and its
    result is the more transparent, better-maintained one whenever it
    resolves at least 4 of the 6 :data:`REQUIRED_LANDMARKS` -- that
    threshold matches ``load_c3d``'s own. Falls back to
    :func:`auto_detect_mapping` (this module's own alias-plus-keyword
    scan, which additionally knows the ``nature_multimodal`` convention
    myogait does not yet) when the installed myogait predates
    ``detect_c3d_convention``, or when neither its best registered
    convention nor its own fallback clears that bar.
    """
    try:
        from myogait import detect_c3d_convention
    except ImportError:
        detect_c3d_convention = None  # myogait < 0.7.0

    if detect_c3d_convention is not None:
        convention, mapping, scores = detect_c3d_convention(labels)
        n_resolved = scores.get(convention, 0)
        if n_resolved >= 4:
            return mapping, MappingDiagnostics(
                method="native",
                n_resolved=n_resolved,
                convention=convention,
                scores=scores,
            )

    mapping, source = auto_detect_mapping(labels)
    n_resolved = sum(1 for lm in REQUIRED_LANDMARKS if lm in mapping)
    return mapping, MappingDiagnostics(method="fuzzy", n_resolved=n_resolved, source=source)


# ── ISB reconstruction: the richer, paired medial/lateral landmark set ──
#
# myogait.isb.reconstruct_isb_angles needs ISB_REQUIRED_LANDMARKS -- a
# knee/ankle/forefoot marker on *each* side of the joint (lateral and
# medial separately), not the single averaged point REQUIRED_LANDMARKS
# above is happy with. There is no myogait-native detector for this
# richer set to try first (unlike resolve_c3d_mapping's detect_c3d_
# convention step) -- myogait.isb is new this session and doesn't
# register a convention registry of its own -- so this is alias tables
# for every convention resolve_c3d_mapping already knows, plus a fuzzy
# lateral/medial-aware fallback for anything else, mirroring
# auto_detect_mapping's own two-pass shape one level up.
#
# Confirmed against three real, independent files this session (session-
# local scripts, not part of this repo): Myokinesis's Plug-in-Gait-
# extended convention, the BATH open dataset's ISO/CAST-style convention,
# and the Nature Scientific Data Multimodal Gait Dataset's underscore-
# prefixed convention.

ISB_MYOKINESIS_ALIASES: dict[str, list[str]] = {
    "LEFT_ASIS": ["LASIS"], "RIGHT_ASIS": ["RASIS"],
    "LEFT_PSIS": ["LPSIS"], "RIGHT_PSIS": ["RPSIS"],
    "LEFT_KNEE_LATERAL": ["LLFE"], "LEFT_KNEE_MEDIAL": ["LMFE"],
    "RIGHT_KNEE_LATERAL": ["RLFE"], "RIGHT_KNEE_MEDIAL": ["RMFE"],
    "LEFT_ANKLE_LATERAL": ["LLM"], "LEFT_ANKLE_MEDIAL": ["LMM"],
    "RIGHT_ANKLE_LATERAL": ["RLM"], "RIGHT_ANKLE_MEDIAL": ["RMM"],
    "LEFT_HEEL": ["LCAL"], "RIGHT_HEEL": ["RCAL"],
    "LEFT_FOOT_INDEX_MEDIAL": ["LFMH1"], "LEFT_FOOT_INDEX_LATERAL": ["LFMH5"],
    "RIGHT_FOOT_INDEX_MEDIAL": ["RFMH1"], "RIGHT_FOOT_INDEX_LATERAL": ["RFMH5"],
}

ISB_BATH_ALIASES: dict[str, list[str]] = {
    "LEFT_ASIS": ["ASIS_L"], "RIGHT_ASIS": ["ASIS_R"],
    "LEFT_PSIS": ["PSIS_L"], "RIGHT_PSIS": ["PSIS_R"],
    "LEFT_KNEE_LATERAL": ["KNEE_LAT_L"], "LEFT_KNEE_MEDIAL": ["KNEE_MED_L"],
    "RIGHT_KNEE_LATERAL": ["KNEE_LAT_R"], "RIGHT_KNEE_MEDIAL": ["KNEE_MED_R"],
    "LEFT_ANKLE_LATERAL": ["MAL_LAT_L"], "LEFT_ANKLE_MEDIAL": ["MAL_MED_L"],
    "RIGHT_ANKLE_LATERAL": ["MAL_LAT_R"], "RIGHT_ANKLE_MEDIAL": ["MAL_MED_R"],
    "LEFT_HEEL": ["HEEL_L"], "RIGHT_HEEL": ["HEEL_R"],
    "LEFT_FOOT_INDEX_MEDIAL": ["MTP1_L"], "LEFT_FOOT_INDEX_LATERAL": ["MTP5_L"],
    "RIGHT_FOOT_INDEX_MEDIAL": ["MTP1_R"], "RIGHT_FOOT_INDEX_LATERAL": ["MTP5_R"],
}

ISB_NATURE_MULTIMODAL_ALIASES: dict[str, list[str]] = {
    "LEFT_ASIS": ["L_IAS"], "RIGHT_ASIS": ["R_IAS"],
    "LEFT_PSIS": ["L_IPS"], "RIGHT_PSIS": ["R_IPS"],
    "LEFT_KNEE_LATERAL": ["L_FLE"], "LEFT_KNEE_MEDIAL": ["L_FME"],
    "RIGHT_KNEE_LATERAL": ["R_FLE"], "RIGHT_KNEE_MEDIAL": ["R_FME"],
    "LEFT_ANKLE_LATERAL": ["L_FAL"], "LEFT_ANKLE_MEDIAL": ["L_TAM"],
    "RIGHT_ANKLE_LATERAL": ["R_FAL"], "RIGHT_ANKLE_MEDIAL": ["R_TAM"],
    "LEFT_HEEL": ["L_FCC"], "RIGHT_HEEL": ["R_FCC"],
    "LEFT_FOOT_INDEX_MEDIAL": ["L_FM1"], "LEFT_FOOT_INDEX_LATERAL": ["L_FM5"],
    "RIGHT_FOOT_INDEX_MEDIAL": ["R_FM1"], "RIGHT_FOOT_INDEX_LATERAL": ["R_FM5"],
}

#: Fuzzy fallback for a convention none of the alias tables above cover.
#: Same shape as _CONCEPT_KEYWORDS (applied to a label's remainder after
#: side-stripping), split lateral/medial where the base table only needs
#: one combined concept -- "eq" for short, ambiguous tokens that could
#: false-positive as a substring, "has" for longer, safer ones.
_ISB_CONCEPT_KEYWORDS: dict[str, list[tuple[str, str]]] = {
    "ASIS": [("has", "ASIS"), ("has", "IAS")],
    "PSIS": [("has", "PSIS"), ("has", "IPS")],
    "KNEE_LATERAL": [("has", "FLE"), ("has", "LFE"), ("has", "KNEELAT"), ("has", "KNEE_LAT"), ("has", "LATKNEE")],
    "KNEE_MEDIAL": [("has", "FME"), ("has", "MFE"), ("has", "KNEEMED"), ("has", "KNEE_MED"), ("has", "MEDKNEE")],
    "ANKLE_LATERAL": [("has", "FAL"), ("eq", "LM"), ("has", "MALLAT"), ("has", "MAL_LAT"), ("has", "ANKLELAT")],
    "ANKLE_MEDIAL": [("has", "TAM"), ("eq", "MM"), ("has", "MALMED"), ("has", "MAL_MED"), ("has", "ANKLEMED")],
    "FOOT_INDEX_MEDIAL": [("has", "FM1"), ("has", "MTP1"), ("eq", "TT2"), ("has", "MT2")],
    "FOOT_INDEX_LATERAL": [("has", "FM5"), ("has", "MTP5")],
}

#: The subset of ISB_REQUIRED_LANDMARKS that don't need a lateral/medial
#: split -- resolved the same way REQUIRED_LANDMARKS' HEEL concept already
#: is, reusing _CONCEPT_KEYWORDS directly rather than duplicating it.
_ISB_HEEL_LANDMARKS = {"LEFT_HEEL": ("LEFT", "HEEL"), "RIGHT_HEEL": ("RIGHT", "HEEL")}


def auto_detect_isb_mapping(labels: list[str]) -> tuple[dict[str, list[str]], dict[str, str]]:
    """Best-effort ISB-enriched ``marker_mapping`` for *labels*.

    Same two-pass shape as :func:`auto_detect_mapping`: known aliases
    from the three conventions above first, then a lateral/medial-aware
    keyword scan over whatever labels neither matched.

    Returns
    -------
    (mapping, source)
        *mapping* covers whatever of ``myogait.isb.ISB_REQUIRED_LANDMARKS``
        could be resolved -- may be a strict subset; callers check
        coverage the same way :func:`resolve_isb_mapping` does. *source*
        records "alias" or "fuzzy" per matched landmark, for display.
    """
    norm_to_actual: dict[str, str] = {}
    for lbl in labels:
        norm_to_actual.setdefault(_normalize(lbl), lbl.strip())

    alias_pool: dict[str, list[str]] = {}
    for aliases in (ISB_MYOKINESIS_ALIASES, ISB_BATH_ALIASES, ISB_NATURE_MULTIMODAL_ALIASES):
        for landmark, candidates in aliases.items():
            bucket = alias_pool.setdefault(landmark, [])
            for candidate in candidates:
                if candidate not in bucket:
                    bucket.append(candidate)

    mapping: dict[str, list[str]] = {}
    source: dict[str, str] = {}

    # Pass 1: known aliases.
    for landmark, candidates in alias_pool.items():
        found = [
            norm_to_actual[_normalize(candidate)]
            for candidate in candidates
            if _normalize(candidate) in norm_to_actual
        ]
        if found:
            mapping[landmark] = found
            source[landmark] = "alias"

    # Pass 2: side + lateral/medial-aware keyword scan over what's left.
    used = {lbl for found in mapping.values() for lbl in found}
    remaining = [lbl for lbl in labels if lbl.strip() not in used]
    for side, prefix in (("LEFT", "L"), ("RIGHT", "R")):
        for concept, rules in _ISB_CONCEPT_KEYWORDS.items():
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

    # HEEL: not lateral/medial-split, so reuse the base concept table
    # directly rather than duplicating its keyword list here.
    for landmark, (side, concept) in _ISB_HEEL_LANDMARKS.items():
        if landmark in mapping:
            continue
        prefix = "L" if side == "LEFT" else "R"
        rules = _CONCEPT_KEYWORDS[concept]
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

    return mapping, source


@dataclass
class IsbMappingDiagnostics:
    """How :func:`resolve_isb_mapping` arrived at its mapping, for display."""

    method: str  # "alias", "fuzzy", or "unavailable" (myogait too old / no landmarks resolved)
    n_resolved: int
    n_required: int
    source: dict[str, str] | None = None

    @property
    def is_isb_capable(self) -> bool:
        # n_required == 0 means "unavailable" (myogait.isb isn't
        # importable), not "nothing to resolve" -- 0 >= 0 would otherwise
        # read as capable. Caught by CI running against the currently
        # published myogait, which doesn't have myogait.isb yet.
        return self.n_required > 0 and self.n_resolved >= self.n_required


def resolve_isb_mapping(labels: list[str]) -> tuple[dict[str, list[str]] | None, IsbMappingDiagnostics]:
    """Best-effort ISB-enriched ``marker_mapping`` for *labels*, or
    ``(None, diagnostics)`` when this file cannot support ISB reconstruction.

    Never raises, and never blocks the base 6-landmark
    :func:`resolve_c3d_mapping` result this is meant to be tried
    alongside -- a file that only resolves a single point per joint
    (markerless/video sources, a sparse marker set) simply gets
    ``is_isb_capable=False`` here and stays on the existing sagittal
    method, exactly the app's current behaviour today.
    """
    try:
        from myogait.isb import ISB_REQUIRED_LANDMARKS
    except ImportError:
        return None, IsbMappingDiagnostics(method="unavailable", n_resolved=0, n_required=0)

    mapping, source = auto_detect_isb_mapping(labels)
    n_resolved = sum(1 for lm in ISB_REQUIRED_LANDMARKS if lm in mapping)
    n_required = len(ISB_REQUIRED_LANDMARKS)
    if n_resolved < n_required:
        return None, IsbMappingDiagnostics(
            method="fuzzy" if any(v == "fuzzy" for v in source.values()) else "alias",
            n_resolved=n_resolved, n_required=n_required, source=source,
        )
    method = "fuzzy" if any(v == "fuzzy" for v in source.values()) else "alias"
    return mapping, IsbMappingDiagnostics(method=method, n_resolved=n_resolved, n_required=n_required, source=source)


def merged_c3d_mapping(
    labels: list[str],
) -> tuple[dict[str, list[str]], MappingDiagnostics, dict[str, list[str]] | None, IsbMappingDiagnostics]:
    """One call for a C3D tab: the base mapping load_c3d actually needs,
    plus whatever ISB adds on top -- merged into a single mapping so a
    file resolved as ISB-capable gets *both* in the same load_c3d call
    (the base landmarks compute_angles's sagittal method needs stay
    available even when ISB reconstruction is later turned on/off).

    Returns
    -------
    (merged_mapping, base_diagnostics, isb_mapping_or_none, isb_diagnostics)
        *merged_mapping* is what to pass to ``load_c3d(marker_mapping=...)``
        -- always usable, exactly resolve_c3d_mapping's own result when
        ISB doesn't add anything. *isb_mapping_or_none* is ``None`` when
        the file isn't ISB-capable (mirrors resolve_isb_mapping's own
        contract) -- check *isb_diagnostics.is_isb_capable* instead of
        this for the capability itself.
    """
    base_mapping, base_diag = resolve_c3d_mapping(labels)
    isb_mapping, isb_diag = resolve_isb_mapping(labels)
    merged = dict(base_mapping)
    if isb_mapping:
        merged.update(isb_mapping)
    return merged, base_diag, isb_mapping, isb_diag


# ── ISB anatomical markers: lazy, on-the-fly fallback ────────────────
#
# resolve_isb_mapping/merged_c3d_mapping above are the *primary* path:
# resolved once at C3D-load time and fed into load_c3d's own
# marker_mapping, so the paired landmarks ride along in c3d_markers_3d
# from the first read -- what makes tier 2/3 calibration (which need
# static/.vsk/.prot files collected at that same load time) possible at
# all. The pair below is a fallback for the same 18 landmarks, resolved
# lazily by re-reading the source C3D file directly, for a pivot that
# reached the angles stage without going through that load-time path (a
# JSON re-import of an old export, or a caller driving PipelineRunner
# directly). pipeline._apply_isb_reconstruction tries this only when
# c3d_markers_3d is still missing landmarks tier 1 needs.
#
# ``reconstruct_isb_angles`` needs the *paired* medial and lateral
# markers as separate points -- not the single averaged joint centre
# ``load_c3d`` resolves for hip/knee/ankle. It reads them from
# ``data["c3d_markers_3d"]`` under fixed ISB names (see
# ``myogait.isb.ISB_REQUIRED_LANDMARKS``). This table maps those names to
# the raw C3D labels the marker sets we have seen actually use: the Bath
# BioCV convention (``ASIS_R``, ``KNEE_LAT_R``, ``MTP1_R`` ...), Vicon
# Plug-in Gait with its optional medial markers, and the ISB/CAST codes of
# the Nature multimodal set. First present candidate wins, same policy as
# the mapping resolver above. MTP1 (1st metatarsal head) is medial, MTP5
# (5th) is lateral.
#: Hand-maintained candidates (Bath BioCV, Plug-in Gait's optional medial
#: set, ISB/CAST). Kept separate from ISB_MYOKINESIS_ALIASES /
#: ISB_BATH_ALIASES / ISB_NATURE_MULTIMODAL_ALIASES above -- rather than
#: merged into a single literal -- as the historical record of this
#: table's own origin (an independent implementation of the same idea
#: that landed in parallel on main), but ISB_MARKER_ALIASES itself, below,
#: unions this with all three of those so the two ISB marker-resolution
#: paths can never again silently diverge in coverage the way they did
#: before reconciliation (LFMH1/LFMH5, Myokinesis's own 1st/5th-metatarsal-
#: head codes, were only in ISB_MYOKINESIS_ALIASES until this fix -- caught
#: by an end-to-end check against real Myokinesis data during
#: reconciliation, not by either alias table's own tests).
_ISB_MARKER_ALIASES_BASE: dict[str, list[str]] = {
    "LEFT_ASIS": ["ASIS_L", "LASI", "L_IAS", "LASIS"],
    "RIGHT_ASIS": ["ASIS_R", "RASI", "R_IAS", "RASIS"],
    "LEFT_PSIS": ["PSIS_L", "LPSI", "L_IPS", "LPSIS"],
    "RIGHT_PSIS": ["PSIS_R", "RPSI", "R_IPS", "RPSIS"],
    "LEFT_KNEE_LATERAL": ["KNEE_LAT_L", "LKNE", "L_FLE", "LLFE", "LLEK"],
    "LEFT_KNEE_MEDIAL": ["KNEE_MED_L", "LKNM", "L_FME", "LMFE", "LMEK"],
    "RIGHT_KNEE_LATERAL": ["KNEE_LAT_R", "RKNE", "R_FLE", "RLFE", "RLEK"],
    "RIGHT_KNEE_MEDIAL": ["KNEE_MED_R", "RKNM", "R_FME", "RMFE", "RMEK"],
    "LEFT_ANKLE_LATERAL": ["MAL_LAT_L", "LANK", "L_FAL", "LLM", "LLMAL"],
    "LEFT_ANKLE_MEDIAL": ["MAL_MED_L", "LMED", "LMMA", "L_TAM", "LMM"],
    "RIGHT_ANKLE_LATERAL": ["MAL_LAT_R", "RANK", "R_FAL", "RLM", "RLMAL"],
    "RIGHT_ANKLE_MEDIAL": ["MAL_MED_R", "RMED", "RMMA", "R_TAM", "RMM"],
    "LEFT_HEEL": ["HEEL_L", "LHEE", "L_FCC", "LCAL"],
    "RIGHT_HEEL": ["HEEL_R", "RHEE", "R_FCC", "RCAL"],
    "LEFT_FOOT_INDEX_MEDIAL": ["MTP1_L", "L_FM1", "LMT1", "LFM1"],
    "LEFT_FOOT_INDEX_LATERAL": ["MTP5_L", "L_FM5", "LMT5", "LFM5"],
    "RIGHT_FOOT_INDEX_MEDIAL": ["MTP1_R", "R_FM1", "RMT1", "RFM1"],
    "RIGHT_FOOT_INDEX_LATERAL": ["MTP5_R", "R_FM5", "RMT5", "RFM5"],
}


def _merged_isb_marker_aliases() -> dict[str, list[str]]:
    merged: dict[str, list[str]] = {
        landmark: list(candidates) for landmark, candidates in _ISB_MARKER_ALIASES_BASE.items()
    }
    for table in (ISB_MYOKINESIS_ALIASES, ISB_BATH_ALIASES, ISB_NATURE_MULTIMODAL_ALIASES):
        for landmark, candidates in table.items():
            bucket = merged.setdefault(landmark, [])
            for candidate in candidates:
                if candidate not in bucket:
                    bucket.append(candidate)
    return merged


#: The candidate raw-label list per ISB landmark that resolve_isb_markers
#: (the lazy, on-the-fly fallback) matches against -- every convention
#: known to either ISB marker-resolution path, unioned. See
#: _merged_isb_marker_aliases's docstring above for why this is computed
#: rather than hand-maintained as a second literal.
ISB_MARKER_ALIASES: dict[str, list[str]] = _merged_isb_marker_aliases()


def resolve_isb_markers(labels: list[str]) -> dict[str, str]:
    """Map each ISB anatomical landmark to the raw C3D label present in *labels*.

    Returns ``{isb_name: raw_label}`` for every ISB landmark this file can
    supply, matched case- and separator-insensitively (so ``ASIS_R``,
    ``asis-r`` and ``ASISR`` all resolve). A landmark with no matching
    candidate is simply absent from the result; the caller decides whether
    the subset is enough (myogait's reconstruction needs all of them).
    """
    norm_to_raw: dict[str, str] = {}
    for lbl in labels:
        norm_to_raw.setdefault(_normalize(lbl), lbl)
    resolved: dict[str, str] = {}
    for isb_name, candidates in ISB_MARKER_ALIASES.items():
        for cand in candidates:
            raw = norm_to_raw.get(_normalize(cand))
            if raw is not None:
                resolved[isb_name] = raw
                break
    return resolved


def inject_isb_markers(data: dict, c3d_path) -> list[str]:
    """Add the paired ISB anatomical markers to ``data["c3d_markers_3d"]``.

    Re-reads *c3d_path* for the raw, per-label 3-D trajectories
    (``load_c3d`` only keeps the six averaged joint centres) and copies the
    ISB anatomical markers in under their canonical names, leaving the 2-D
    pivot and its normalisation untouched. Idempotent and non-fatal:
    returns the list of ISB landmark names injected (empty if the file has
    none, or myogait is too old to expose ``load_raw_c3d_markers``).
    """
    try:
        from myogait import load_raw_c3d_markers
    except Exception:
        return []
    try:
        markers, _fps = load_raw_c3d_markers(str(c3d_path))
    except Exception:
        return []
    resolved = resolve_isb_markers(list(markers.keys()))
    if not resolved:
        return []
    m3d = data.setdefault("c3d_markers_3d", {})
    injected: list[str] = []
    for isb_name, raw_label in resolved.items():
        arr = markers.get(raw_label)
        if arr is not None:
            # (n_frames, 3) raw XYZ -- the same axis order load_c3d stores
            # its averaged joint centres in, so ISB reconstruction reads a
            # consistent frame.
            m3d[isb_name] = arr
            injected.append(isb_name)
    return injected
