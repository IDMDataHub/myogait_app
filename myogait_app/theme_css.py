"""Injected CSS for the Bauhaus / 1960s postmodern identity.

Everything Streamlit's theme config cannot express: heavy rules, the
tracked-out uppercase label voice, the numbered-section signature, the
colour-block metric strip, the page-header decoration, and the "fig. N"
frame around every chart. ``inject()`` returns the stylesheet as a string
for ``app.main`` to hand to ``st.markdown`` (it does not call ``st.markdown``
itself, so it composes cleanly with ``background_css()``/``render_footer()``
below in the same call site).

Selectors are Streamlit's stable data-testid attributes only -- no
generated class names, which change between releases.

A parallel dark "Nocturne" identity (blurple accent, Inter, a dimmed
walker photo behind the app) was built and released as v0.3.0 on this
same module; product direction landed back on the paper world documented
in DESIGN.md, so ``background_css()`` is now a deliberate no-op -- see
that file's "Reconciled with Nocturne" section. ``render_footer()``'s
credits/links/partner-marks are kept and reskinned: real, non-visual
content, independent of which identity is on screen.
"""

from __future__ import annotations

from pathlib import Path

from .branding import BRANDING

_ASSETS = Path(__file__).resolve().parent / "assets"

_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700&display=swap');

:root {{
  --paper: {paper};
  --paper-2: {paper2};
  --ink: {ink};
  --muted: {muted};
  --rule: {rule};
  --red: {red};
  --blue: {blue};
  --yellow: {yellow};
  --mark: {mark};
}}

/* Rules, never shadows or radii. */
[data-testid="stAppViewContainer"] * {{ border-radius: 0 !important; box-shadow: none !important; }}

/* Sidebar: black identity slab, hairline-separated sections. */
[data-testid="stSidebar"] {{ background: var(--paper-2); border-right: 3px solid var(--ink); }}
[data-testid="stSidebar"] hr {{ border-top: 3px solid var(--ink); opacity: 1; }}
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] strong {{
  font-size: 0.7rem; letter-spacing: 2.2px; text-transform: uppercase;
}}

/* Sidebar identity block: logo mark + name + tagline, black slab. */
.mg-sidebar-id {{
  display: flex; align-items: center; gap: 0.75rem;
  background: var(--ink); margin: -1rem -1rem 0.9rem; padding: 1.1rem 1.25rem;
}}
.mg-sidebar-mark {{
  display: grid; grid-template-rows: 1fr 1fr; width: 30px; height: 30px;
  border: 2px solid var(--paper); flex-shrink: 0;
}}
.mg-sidebar-mark span {{ display: block; }}
.mg-sidebar-id-name {{
  color: var(--paper); font-weight: 700; font-size: 1.3rem;
  text-transform: uppercase; letter-spacing: -0.5px; line-height: 1.05;
}}
.mg-sidebar-id-tag {{
  color: #a9a7a0; font-size: 0.62rem; letter-spacing: 1.6px;
  text-transform: uppercase; margin-top: 0.25rem;
}}

/* Sidebar section numerals: a coloured folio chip above the matching expander. */
.mg-sec-num {{
  font-family: 'JetBrains Mono', ui-monospace, monospace; font-weight: 700;
  font-size: 1.1rem; letter-spacing: -0.5px; margin: 0.9rem 0 -0.5rem 0.1rem;
}}

/* Nav pills: pressed-box selection, not a soft chip. */
[data-testid="stPills"] button {{
  border-radius: 0 !important; border: 2px solid var(--ink) !important;
  background: transparent !important; color: var(--ink) !important;
  font-size: 0.68rem !important; font-weight: 700 !important;
  letter-spacing: 1.6px; text-transform: uppercase;
}}
[data-testid="stPills"] button[aria-checked="true"],
[data-testid="stPills"] button[aria-selected="true"],
[data-testid="stPills"] button[kind="pillsActive"] {{
  background: var(--ink) !important; color: var(--paper) !important;
  box-shadow: none !important;
}}

/* Numbered sidebar sections: "1." .. "4." get the folio treatment. */
[data-testid="stExpander"] summary p {{
  font-size: 0.7rem; letter-spacing: 2.2px; text-transform: uppercase; font-weight: 700;
}}
[data-testid="stExpander"] details {{ border: 2px solid var(--ink); background: transparent; }}

/* Headings: tracked-out uppercase, heavy. */
h1, h2, h3 {{ text-transform: uppercase; letter-spacing: -1px; font-weight: 700; }}
h3 {{ font-size: 2.6rem !important; line-height: 0.9; border-bottom: 3px solid var(--ink); padding-bottom: 0.5rem; }}

/* Page header: numbered folio, rotated colour block, boxed last word. */
.mg-header {{ position: relative; overflow: hidden; margin: 0 0 1.6rem; padding: 0.9rem 0 1.5rem; }}
.mg-header-bar {{
  position: absolute; top: 10px; right: -20px; width: 55%; max-width: 320px; height: 14px;
  background: var(--blue); transform: rotate(-4deg); z-index: 0;
}}
.mg-header-circle {{
  position: absolute; top: -30px; right: 4%; width: 90px; height: 90px;
  background: var(--blue); opacity: 0.16; border-radius: 0 0 0 90px; z-index: 0;
}}
.mg-header-top {{ position: relative; z-index: 1; display: flex; align-items: flex-end; gap: 0.9rem; }}
.mg-header-num {{
  font-family: 'JetBrains Mono', ui-monospace, monospace; font-weight: 700;
  font-size: 2.6rem; line-height: 0.8; color: var(--red); letter-spacing: -2px;
}}
.mg-header-eyebrow {{
  writing-mode: vertical-rl; transform: rotate(180deg);
  font-size: 0.62rem; letter-spacing: 2px; text-transform: uppercase; color: var(--muted);
  align-self: stretch; padding-bottom: 2px;
}}
.mg-header-side {{ margin-left: auto; display: flex; flex-direction: column; width: 18px; flex-shrink: 0; }}
.mg-header-side span {{ display: block; height: 11px; }}
.mg-header-title {{
  position: relative; z-index: 1; text-transform: uppercase; letter-spacing: -1px;
  font-weight: 700; font-size: 3rem !important; line-height: 0.92; margin: 0.4rem 0 0.55rem;
}}
.mg-header-title-block {{
  display: inline-block; background: var(--ink); color: var(--paper);
  padding: 0 0.3em; transform: rotate(-1deg);
}}
.mg-header-desc {{
  position: relative; z-index: 1; max-width: 62ch; border-left: 4px solid var(--red);
  padding-left: 0.85rem; color: var(--muted); font-size: 0.92rem; margin: 0;
}}
@media (max-width: 640px) {{
  .mg-header-title {{ font-size: 2rem !important; }}
  .mg-header-bar, .mg-header-circle {{ display: none; }}
}}

/* Every numeral in the interface is monospaced. */
[data-testid="stMetricValue"], [data-testid="stMetricDelta"], code, pre, [data-testid="stDataFrame"] {{
  font-family: 'JetBrains Mono', ui-monospace, monospace !important;
}}

/* Native st.metric strips (used outside source_summary): hairline-divided, oversized. */
[data-testid="stMetric"] {{ border-left: 1px solid var(--rule); padding: 0.9rem 1.1rem; }}
[data-testid="stMetricLabel"] p {{
  font-size: 0.58rem !important; letter-spacing: 2px; text-transform: uppercase; color: var(--muted);
}}
[data-testid="stMetricValue"] {{ font-size: 1.9rem !important; font-weight: 700; }}

/* source_summary()'s own metric grid: hairline-divided cells, alternating colour blocks. */
.mg-metric-grid {{
  display: grid; grid-template-columns: repeat(4, 1fr);
  border: 2px solid var(--ink); border-bottom: 3px solid var(--ink);
  margin: 0.25rem 0 1.2rem;
}}
.mg-metric-cell {{ padding: 0.85rem 1rem; border-left: 1px solid var(--rule); min-width: 0; }}
.mg-metric-cell:first-child {{ border-left: none; }}
.mg-metric-label {{
  font-size: 0.58rem; letter-spacing: 2px; text-transform: uppercase;
  color: var(--muted); margin-bottom: 0.3rem;
}}
.mg-metric-value {{
  font-family: 'JetBrains Mono', ui-monospace, monospace;
  font-size: clamp(1.05rem, 2.2vw, 1.5rem); font-weight: 700; overflow-wrap: anywhere;
}}
.mg-metric-ink {{ background: var(--ink); }}
.mg-metric-ink .mg-metric-label {{ color: #cfcdc6; }}
.mg-metric-ink .mg-metric-value {{ color: var(--paper); }}
.mg-metric-accent {{ background: var(--yellow); }}
.mg-metric-accent .mg-metric-label {{ color: var(--mark); }}
.mg-metric-accent .mg-metric-value {{ color: var(--ink); }}
@media (max-width: 640px) {{
  .mg-metric-grid {{ grid-template-columns: repeat(2, 1fr); }}
  .mg-metric-cell:nth-child(3) {{ border-left: none; }}
}}

/* Figure frame: bordered container, numbered tag, black caption bar. */
div[class*="st-key-mg_fig_"] {{
  position: relative; border: 3px solid var(--ink) !important;
  margin: 1.75rem 0 1.4rem; padding-top: 0.9rem !important;
}}
div[class*="st-key-mg_fig_"] .mg-fig-tag {{
  position: absolute; top: -14px; left: 14px; z-index: 2;
  font-family: 'JetBrains Mono', ui-monospace, monospace; font-size: 0.66rem;
  font-weight: 700; letter-spacing: 1.5px; text-transform: uppercase;
  padding: 3px 9px; border: 2px solid var(--ink); transform: rotate(-2deg);
}}
div[class*="st-key-mg_fig_"] .mg-fig-caption {{
  margin-top: 0.7rem; padding: 0.5rem 0.9rem; background: var(--ink); color: var(--paper);
  font-size: 0.7rem; letter-spacing: 1.2px; text-transform: uppercase;
}}

/* Tabs: yellow slab under the active one, no underline animation. */
[data-baseweb="tab-list"] {{ gap: 0; border-bottom: 3px solid var(--ink); }}
[data-baseweb="tab"] {{
  border-left: 1px solid var(--rule); padding: 0.9rem 1rem 0.75rem;
  font-size: 0.68rem; font-weight: 700; letter-spacing: 1.8px; text-transform: uppercase;
}}
[data-baseweb="tab"][aria-selected="true"] {{ box-shadow: inset 0 -8px 0 var(--yellow) !important; }}
[data-baseweb="tab-highlight"] {{ display: none; }}

/* Buttons: 3px rule, red fill for the primary action. */
[data-testid="stBaseButton-secondary"], [data-testid="stBaseButton-primary"] {{
  border: 3px solid var(--ink); font-size: 0.68rem; font-weight: 700;
  letter-spacing: 2.2px; text-transform: uppercase;
}}
[data-testid="stBaseButton-primary"] {{ background: var(--red); color: var(--paper); }}
[data-testid="stBaseButton-primary"]:hover {{ background: var(--ink); color: var(--paper); }}
[data-testid="stBaseButton-secondary"]:hover {{ background: var(--ink); color: var(--paper); }}

/* Widgets: hairline boxes, uppercase labels. */
[data-testid="stWidgetLabel"] p {{
  font-size: 0.6rem; letter-spacing: 1.6px; text-transform: uppercase; color: var(--muted);
}}
[data-baseweb="select"] > div, [data-baseweb="input"] > div {{ border: 2px solid var(--ink); background: var(--paper); }}
[data-testid="stFileUploaderDropzone"] {{ border: 3px dashed var(--ink); background: transparent; }}

/* Alerts as flat blocks of the palette, no tinted pastels. */
[data-testid="stAlertContainer"] {{ border: 3px solid var(--ink); background: var(--paper-2); }}
[data-testid="stNotification"] p {{ font-size: 0.82rem; }}

/* Captions carry the annotation voice. */
[data-testid="stCaptionContainer"] p {{ font-size: 0.72rem; color: var(--muted); }}

/* Divider = a real rule. */
hr {{ border-top: 3px solid var(--ink); opacity: 1; }}

/* Progress: yellow fill, hatched remainder. */
[data-testid="stProgress"] > div > div {{ background: repeating-linear-gradient(135deg, var(--ink) 0 3px, var(--paper) 3px 8px); }}
[data-testid="stProgress"] > div > div > div {{ background: var(--yellow); }}

/* Footer: credits, package links and the partner marks. */
.mg-footer-rule {{ height: 3px; margin: 2.5rem 0 1rem; background: var(--ink); }}
.mg-credits {{ font-size: 0.72rem; color: var(--muted); line-height: 1.7; }}
.mg-credits a {{ color: var(--mark); text-decoration: none; text-underline-offset: 3px; }}
.mg-credits a:hover {{ text-decoration: underline; }}
.mg-footer [data-testid="stImage"] img {{ opacity: 0.85; }}
</style>
"""


def inject() -> str:
    """Return the identity's stylesheet, for the caller to hand to st.markdown."""
    return _CSS.format(
        paper=BRANDING.surface_light,
        paper2=BRANDING.surface_light_secondary,
        ink=BRANDING.ink_light,
        muted=BRANDING.ink_muted_light,
        rule=BRANDING.border_light,
        red=BRANDING.primary_red,
        blue=BRANDING.primary_blue,
        yellow=BRANDING.accent,
        mark=BRANDING.accent_mark,
    )


def background_css() -> str:
    """No-op: this identity is flat and geometric, not a dimmed photograph.

    A walker-photo backdrop was part of the Nocturne pass this replaces
    (see the module docstring) -- kept as a callable no-op rather than
    removed from app.py's call site, so that reconciliation stays a
    pure content/token change here rather than a structural app.py edit.
    """
    return ""


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

    st.markdown('<div class="mg-footer-rule"></div>', unsafe_allow_html=True)
    st.markdown('<div class="mg-footer">', unsafe_allow_html=True)
    left, right = st.columns([1, 1.6], vertical_alignment="center")
    with left:
        marks = st.columns(2, vertical_alignment="center")
        for col, name in zip(marks, ("logo_aim.png", "logo_telethon.png")):
            path = _ASSETS / name
            if path.is_file():
                col.image(str(path), width=118 if "telethon" in name else 70)
    with right:
        links = " &middot; ".join(
            f'<a href="{url}" target="_blank">{name}</a>'
            for name, url in _PACKAGE_LINKS.items()
        )
        st.markdown(
            f'<div class="mg-credits">Built on {links}'
            f'<br>Assistmyo &middot; NeuPEL &middot; Institut de Myologie -- '
            f'<a href="mailto:{_CONTACT_EMAIL}">{_CONTACT_EMAIL}</a></div>',
            unsafe_allow_html=True,
        )
    st.markdown("</div>", unsafe_allow_html=True)
