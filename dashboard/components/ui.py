"""Elementi grafici comuni: barra laterale, fascia d'intestazione e riquadri dei contatori.

I colori di base stanno in .streamlit/config.toml; qui solo cio' che il tema
non copre. I riquadri usano st.container(key="kpi_<colore>_<etichetta>"), che Streamlit
rende con la classe CSS "st-key-kpi_<colore>_<etichetta>".
"""
from __future__ import annotations

import html
import re
from pathlib import Path

import streamlit as st

_ASSETS = Path(__file__).resolve().parents[2] / "assets"
NAVY = "#1F3864"
KPI_COLORS = {"blue": "#2E5AAC", "green": "#2E8B57", "orange": "#E07B00", "violet": "#7B4FB8", "gray": "#7A8699"}

_CSS = """
<style>
.mc-hero {
  background: linear-gradient(115deg, #1F3864 0%, #2E5AAC 55%, #5B8DE0 100%);
  color: #FFFFFF; border-radius: 14px; padding: 18px 26px; margin: 4px 0 10px;
  box-shadow: 0 4px 14px rgba(31, 56, 100, .18);
}
.mc-hero .mc-kicker { font-size: .78rem; letter-spacing: .14em; text-transform: uppercase; opacity: .8; }
.mc-hero .mc-title { font-size: 1.9rem; font-weight: 700; line-height: 1.2; margin-top: 2px; }
.mc-hero .mc-sub { opacity: .9; margin-top: 4px; }
[class*="st-key-kpi_"] {
  background: #FFFFFF; border-radius: 12px; padding: 4px 14px 6px;
  border-left: 6px solid var(--kpi-color); box-shadow: 0 1px 4px rgba(31, 56, 100, .10);
}
/* Barra laterale: colori in config.toml ([theme.sidebar]); qui sfumatura, voci e pulsante. */
[data-testid="stSidebar"] { background: linear-gradient(180deg, #1F3864 0%, #23427A 60%, #2A4F8F 100%); }
[data-testid="stSidebarNavLink"] { border-radius: 10px; margin: 2px 0; padding: 6px 12px; }
[data-testid="stSidebarNavLink"] span { color: #E8EEF9; font-weight: 500; }
[data-testid="stSidebarNavLink"]:hover { background: rgba(255, 255, 255, .10); }
[data-testid="stSidebarNavLink"][aria-current="page"] {
  background: rgba(255, 255, 255, .16); box-shadow: inset 4px 0 0 #9DBBF0;
}
[data-testid="stSidebarNavLink"][aria-current="page"] span { color: #FFFFFF; font-weight: 700; }
/* Il pulsante per chiudere la barra di solito compare solo passandoci sopra: sempre visibile. */
[data-testid="stSidebarCollapseButton"] { display: flex !important; visibility: visible !important; opacity: 1 !important; }
[data-testid="stSidebarCollapseButton"] button { border-radius: 8px; background: rgba(255, 255, 255, .12); color: #FFFFFF; }
[data-testid="stExpandSidebarButton"] {
  border-radius: 8px; background: #1F3864; color: #FFFFFF; box-shadow: 0 2px 8px rgba(31, 56, 100, .25);
}
[data-testid="stExpandSidebarButton"] *, [data-testid="stSidebarCollapseButton"] button * { color: #FFFFFF !important; }
[data-testid="stExpandSidebarButton"]:hover, [data-testid="stSidebarCollapseButton"] button:hover { background: #2E5AAC; }
.mc-side-foot {
  margin-top: 18px; padding: 10px 12px; border-radius: 10px; font-size: .82rem; line-height: 1.5;
  background: rgba(255, 255, 255, .08); color: #C9D7F0;
}
.mc-side-foot b { color: #FFFFFF; font-weight: 600; }
.mc-side-foot .mc-dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 6px; }
""" + "\n".join(f'[class*="st-key-kpi_{name}_"] {{ --kpi-color: {color}; }}' for name, color in KPI_COLORS.items()) + """
</style>
"""


def inject_css() -> None:
    st.html(_CSS)


def sidebar(user: str, backend_url: str) -> None:
    """Logo in cima alla barra laterale e, in fondo, backend e utente in uso."""
    st.logo(str(_ASSETS / "logo.svg"), icon_image=str(_ASSETS / "icon.svg"), size="large")
    local = "localhost" in backend_url or "127.0.0.1" in backend_url
    dot, where = ("#F2B544", "locale") if local else ("#5BD08F", "Azure")
    st.sidebar.html(
        f'<div class="mc-side-foot"><div><span class="mc-dot" style="background:{dot}"></span>'
        f'Backend <b>{where}</b></div><div>Utente <b>{html.escape(user or "—")}</b></div></div>'
    )


def hero(title: str, subtitle: str = "", kicker: str = "CV · MCFlash") -> None:
    """Fascia blu in cima alla pagina. Il testo viene sempre escapato."""
    sub = f'<div class="mc-sub">{html.escape(subtitle)}</div>' if subtitle else ""
    st.html(
        f'<div class="mc-hero"><div class="mc-kicker">{html.escape(kicker)}</div>'
        f'<div class="mc-title">{html.escape(title)}</div>{sub}</div>'
    )


def kpi(column, color: str, label: str, value, help: str | None = None) -> None:
    """Riquadro con bordo colorato e un numero."""
    slug = re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")
    with column.container(key=f"kpi_{color}_{slug}"):
        st.metric(label, value, help=help)
