"""Elementi grafici comuni: fascia d'intestazione e riquadri dei contatori.

I colori di base stanno in .streamlit/config.toml; qui solo cio' che il tema
non copre. I riquadri usano st.container(key="kpi_<colore>_<etichetta>"), che Streamlit
rende con la classe CSS "st-key-kpi_<colore>_<etichetta>".
"""
from __future__ import annotations

import html
import re

import streamlit as st

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
""" + "\n".join(f'[class*="st-key-kpi_{name}_"] {{ --kpi-color: {color}; }}' for name, color in KPI_COLORS.items()) + """
</style>
"""


def inject_css() -> None:
    st.html(_CSS)


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
