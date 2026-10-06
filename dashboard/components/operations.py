"""Tabella e contatori della pagina Operazioni (righe di GET /api/operations).

Nessuna chiamata a Streamlit qui: la pagina usa queste funzioni e i test le
provano direttamente.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import pandas as pd
from pandas.io.formats.style import Styler

from dashboard.components.draft import STATUS_LABELS, STEP_LABELS

# Periodo -> giorni indietro (None = tutto).
PERIODS: dict[str, int | None] = {"oggi": 0, "7 giorni": 7, "30 giorni": 30, "tutte": None}
STATUSES: dict[str, str | None] = {"tutte": None, "in corso": "in_corso", "completate": "completata",
                                   "fallite": "fallita"}

_STEP_TEXT = {"ok": "✓ fatto", "in_attesa": "⏳ in attesa", "errore": "✗ errore", "da_fare": "· da fare"}
_STEP_STYLE = {
    "✓ fatto": "background-color: #E3F4EA; color: #1E6B42",
    "⏳ in attesa": "background-color: #E6EDF8; color: #2E5AAC",
    "✗ errore": "background-color: #FBE3E3; color: #A12A2A; font-weight: 600",
    "· da fare": "color: #8A94A6",
}
_STATUS_STYLE = {
    "Completata": "background-color: #E3F4EA; color: #1E6B42; font-weight: 600",
    "In corso": "background-color: #E6EDF8; color: #2E5AAC; font-weight: 600",
    "Fallita": "background-color: #FBE3E3; color: #A12A2A; font-weight: 600",
}


def since(period: str, now: datetime | None = None) -> str | None:
    """Data ISO (UTC) da cui partire per il filtro 'da' del backend."""
    days = PERIODS.get(period)
    if days is None:
        return None
    now = now or datetime.now(timezone.utc)
    start = now.astimezone().replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=days)
    return start.astimezone(timezone.utc).isoformat(timespec="seconds")


def counts(ops: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "totale": len(ops),
        "completata": sum(1 for o in ops if o.get("status") == "completata"),
        "in_corso": sum(1 for o in ops if o.get("status") == "in_corso"),
        "fallita": sum(1 for o in ops if o.get("status") == "fallita"),
    }


def local_time(iso: str | None) -> str:
    if not iso:
        return ""
    try:
        return datetime.fromisoformat(iso).astimezone().strftime("%d/%m/%Y %H:%M")
    except ValueError:
        return iso


def operations_frame(ops: list[dict[str, Any]]) -> pd.DataFrame:
    """Una riga per operazione, una colonna per passo."""
    rows = []
    for o in ops:
        name = o.get("nome") or ""
        tri = o.get("trittico") or ""
        rows.append({
            "Data": local_time(o.get("created_at")),
            "Utente": o.get("user") or "",
            "Tipo": "Crea" if o.get("kind") == "crea" else "Aggiorna",
            "Candidato": f"{name} ({tri})" if tri else name,
            "Id MCFlash": str(o.get("id_mcflash") or ""),
            **{label: _STEP_TEXT.get(o.get(f"step_{step}") or "", o.get(f"step_{step}") or "")
               for step, label in STEP_LABELS.items()},
            "Stato": STATUS_LABELS.get(o.get("status") or "", o.get("status") or ""),
            "Errore": (o.get("error") or "")[:120],
        })
    columns = ["Data", "Utente", "Tipo", "Candidato", "Id MCFlash", *STEP_LABELS.values(), "Stato", "Errore"]
    return pd.DataFrame(rows, columns=columns)


def style_operations(frame: pd.DataFrame) -> Styler:
    steps = list(STEP_LABELS.values())
    return (
        frame.style
        .map(lambda v: _STEP_STYLE.get(v, ""), subset=steps)
        .map(lambda v: _STATUS_STYLE.get(v, ""), subset=["Stato"])
    )


def draft_link(op: dict[str, Any]) -> tuple[str, dict[str, str]]:
    """Pagina e parametri per riaprire la bozza dell'operazione (in sola lettura)."""
    if op.get("kind") == "aggiorna" and op.get("id_mcflash"):
        return "views/aggiorna.py", {"id": str(op["id_mcflash"]), "bozza": op.get("draft_id") or ""}
    return "views/crea.py", {"bozza": op.get("draft_id") or ""}
