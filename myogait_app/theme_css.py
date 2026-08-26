"""Nocturne — the design-system CSS that Streamlit's native theme cannot do.

`.streamlit/config.toml` sets the dark ground, the blurple accent and Inter.
This module layers the *identity* on top: the geometric Bauhaus/constructivist
voice — generous empty space, a hairline-outlined card, rules that fade at
both ends, tracked-uppercase micro-labels, outlined buttons, and selection
controls that read as real pressed buttons. Injected once by ``app.main`` via
``st.markdown(CSS, unsafe_allow_html=True)``.

Values mirror the Nocturne tokens (see myogait_app/branding.py). Selectors are
kept as stable as Streamlit allows (data-testid first, class fallbacks).
"""

from __future__ import annotations

import base64
from functools import lru_cache
from pathlib import Path

_ASSETS = Path(__file__).resolve().parent / "assets"


@lru_cache(maxsize=8)
def _data_uri(name: str, mime: str) -> str:
    """Base64 data URI for a bundled asset, or empty string if missing."""
    path = _ASSETS / name
    if not path.is_file():
        return ""
    return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode()}"


def background_css() -> str:
    """The walker illustration, dimmed to a faint texture behind everything.

    A near-opaque dark overlay sits over the image so it reads as a whisper of
    the app's own identity, never competing with the content on top.
    """
    uri = _data_uri("walker.jpg", "image/jpeg")
    if not uri:
        return ""
    return f"""
<style>
.stApp {{
  background-image:
    linear-gradient(rgba(22,24,38,0.90), rgba(22,24,38,0.945)),
    url("{uri}");
  background-size: cover; background-position: center right;
  background-attachment: fixed;
}}
</style>
"""


CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

:root {
  --nk-bg: #161826;
  --nk-surface: #232532;
  --nk-text: #e9e9ed;
  --nk-accent: #9184d9;
  --nk-accent-100: #f5f4ff;
  --nk-accent-400: #b5abfc;
  --nk-accent-800: #423a6a;
  --nk-divider: rgba(233,233,237,0.16);
  --nk-hair: #3f424d;
  --nk-radius: 8px;
}

/* ── Type: Inter everywhere, tight tracked headings ─────────────────── */
html, body, .stApp, [data-testid="stAppViewContainer"], .stMarkdown,
button, input, select, textarea, [data-baseweb] {
  font-family: "Inter", system-ui, -apple-system, "Segoe UI", sans-serif;
}
.stMarkdown h1, .stMarkdown h2, .stMarkdown h3, .stMarkdown h4 {
  font-weight: 500; letter-spacing: -0.015em; line-height: 1.12;
}
/* Tracked-uppercase micro label — the Bauhaus kicker voice. */
.stMarkdown h6, [data-testid="stMetricLabel"] {
  text-transform: uppercase; letter-spacing: 0.10em;
  font-size: 11px !important; font-weight: 600;
  color: color-mix(in srgb, var(--nk-text) 62%, transparent);
}

/* ── More air: the constructivist empty space ───────────────────────── */
.block-container { padding-top: 3.2rem; padding-bottom: 4rem; max-width: 1180px; }
[data-testid="stVerticalBlock"] { gap: 1.15rem; }

/* ── Wordmark: the app name, capitalised and underlined ─────────────── */
[data-testid="stSidebar"] .nk-wordmark {
  font-weight: 600; font-size: 21px; letter-spacing: -0.01em;
  text-transform: capitalize;
  padding-bottom: 3px; border-bottom: 2px solid var(--nk-accent);
  display: inline-block;
}
/* A constructivist geometric mark set beside it: a square + a disc. */
[data-testid="stSidebar"] .nk-mark {
  display: inline-flex; gap: 6px; align-items: center; margin-bottom: 6px;
}
[data-testid="stSidebar"] .nk-mark i { width: 13px; height: 13px; display: block; }
[data-testid="stSidebar"] .nk-mark i.sq { background: var(--nk-accent); }
[data-testid="stSidebar"] .nk-mark i.disc { background: var(--nk-accent-400); border-radius: 50%; }
[data-testid="stSidebar"] .nk-mark i.bar { width: 22px; height: 5px; background: var(--nk-hair); }

/* ── Rules that fade to transparent at both ends (Nocturne signature) ── */
hr, [data-testid="stDivider"] hr {
  border: 0 !important; height: 1px !important; background: linear-gradient(
    to right, transparent, var(--nk-divider) 48px,
    var(--nk-divider) calc(100% - 48px), transparent) !important;
}

/* ── Buttons: outlined, transparent fill, accent voice ──────────────── */
.stButton > button, .stDownloadButton > button {
  border-radius: var(--nk-radius); font-weight: 500;
  border: 1px solid var(--nk-divider); background: transparent;
  transition: background .12s ease, border-color .12s ease;
}
.stButton > button:hover, .stDownloadButton > button:hover {
  border-color: color-mix(in srgb, var(--nk-text) 45%, transparent);
  background: color-mix(in srgb, var(--nk-text) 7%, transparent);
}
/* Primary = the accent, outlined not filled. */
.stButton > button[kind="primary"], .stButton > button[data-testid="baseButton-primary"] {
  color: var(--nk-accent); border-color: var(--nk-accent); background: transparent;
}
.stButton > button[kind="primary"]:hover {
  background: color-mix(in srgb, var(--nk-accent) 14%, transparent);
}
.stButton > button[kind="primary"]:active {
  background: color-mix(in srgb, var(--nk-accent) 24%, transparent);
}

/* ── Selection as real pressed buttons: pills & segmented control ────── */
[data-testid="stPills"] button, [data-testid="stSegmentedControl"] button,
[data-baseweb="button-group"] button {
  border-radius: var(--nk-radius) !important;
  border: 1px solid var(--nk-divider) !important;
  background: transparent !important; color: var(--nk-text) !important;
  font-weight: 500 !important;
}
/* Pressed / selected: it stays lit with an accent inset border + tint. */
[data-testid="stPills"] button[aria-checked="true"],
[data-testid="stPills"] button[aria-selected="true"],
[data-testid="stPills"] button[kind="pillsActive"],
[data-testid="stSegmentedControl"] button[aria-checked="true"],
[data-testid="stSegmentedControl"] button[kind="segmented_controlActive"] {
  color: var(--nk-accent) !important;
  box-shadow: inset 0 0 0 1.5px var(--nk-accent) !important;
  background: color-mix(in srgb, var(--nk-accent) 12%, transparent) !important;
}

/* ── Tabs: the active one carries the accent, others recede ─────────── */
.stTabs [data-baseweb="tab-list"] { gap: 4px; border-bottom: 1px solid var(--nk-divider); }
.stTabs [data-baseweb="tab"] {
  font-weight: 500; letter-spacing: 0.01em; color: color-mix(in srgb, var(--nk-text) 60%, transparent);
}
.stTabs [aria-selected="true"] { color: var(--nk-accent) !important; }
.stTabs [data-baseweb="tab-highlight"] { background: var(--nk-accent) !important; }

/* ── Cards: bordered containers become surfaces with a hairline ─────── */
[data-testid="stVerticalBlockBorderWrapper"] {
  background: var(--nk-surface); border-radius: var(--nk-radius);
  box-shadow: 0 0 0 1px var(--nk-hair);
}
/* Metrics read as small constructivist cards. */
[data-testid="stMetric"] {
  background: var(--nk-surface); border-radius: var(--nk-radius);
  box-shadow: 0 0 0 1px var(--nk-hair); padding: 14px 16px;
}
[data-testid="stMetricValue"] { font-weight: 600; letter-spacing: -0.01em; }

/* ── Inputs: quiet surfaces, accent on focus ────────────────────────── */
[data-baseweb="input"], [data-baseweb="select"] > div, .stTextInput input,
.stNumberInput input, [data-baseweb="textarea"] {
  border-radius: var(--nk-radius) !important;
}
[data-testid="stExpander"] { border: 1px solid var(--nk-divider); border-radius: var(--nk-radius); }

/* ── Progress + the persistent job banner accent ────────────────────── */
.stProgress > div > div > div { background: var(--nk-accent) !important; }

/* ── Footer: credits, package links and the partner marks ───────────── */
.nk-footer-rule {
  height: 1px; margin: 2.5rem 0 1rem; background: linear-gradient(
    to right, transparent, var(--nk-divider) 48px,
    var(--nk-divider) calc(100% - 48px), transparent);
}
.nk-credits {
  font-size: 12px; color: color-mix(in srgb, var(--nk-text) 55%, transparent);
  line-height: 1.7;
}
.nk-credits a { color: var(--nk-accent-400); text-decoration: none; text-underline-offset: 3px; }
.nk-credits a:hover { text-decoration: underline; }
/* The partner marks are already tinted to the ground; keep them quiet. */
.nk-footer [data-testid="stImage"] img { opacity: 0.85; }
</style>
"""


def inject() -> str:
    """Return the Nocturne stylesheet to hand to ``st.markdown``."""
    return CSS


#: GitHub homes for the packages the app is built on, linked in the footer.
_PACKAGE_LINKS = {
    "myogait": "https://github.com/IDMDataHub/myogait",
    "gaitkit": "https://github.com/IDMDataHub/gaitkit",
    "app myogait": "https://github.com/IDMDataHub/myogait_app",
}

_CONTACT_EMAIL = "r.feigean@institut-myologie.org"


def render_footer() -> None:
    """A discreet footer: partner marks, package links and a contact."""
    import streamlit as st

    st.markdown('<div class="nk-footer-rule"></div>', unsafe_allow_html=True)
    st.markdown('<div class="nk-footer">', unsafe_allow_html=True)
    left, right = st.columns([1, 1.6], vertical_alignment="center")
    with left:
        marks = st.columns(2, vertical_alignment="center")
        for col, name in zip(marks, ("logo_aim.png", "logo_telethon.png")):
            path = _ASSETS / name
            if path.is_file():
                col.image(str(path), width=118 if "telethon" in name else 70)
    with right:
        links = " · ".join(
            f'<a href="{url}" target="_blank">{name}</a>'
            for name, url in _PACKAGE_LINKS.items()
        )
        st.markdown(
            f'<div class="nk-credits">Built on {links}'
            f'<br>Assistmyo · NeuPEL · Institut de Myologie — '
            f'<a href="mailto:{_CONTACT_EMAIL}">{_CONTACT_EMAIL}</a></div>',
            unsafe_allow_html=True,
        )
    st.markdown("</div>", unsafe_allow_html=True)
