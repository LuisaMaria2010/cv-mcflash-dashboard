"""Testi, tabella e contatori derivati dalle righe candidato di GET /api/candidates.

Nessuna chiamata a Streamlit qui: le pagine usano queste funzioni e i test le
provano direttamente.
"""
from __future__ import annotations

from typing import Any, Iterable

import pandas as pd
from pandas.io.formats.style import Styler

# Filtro "CV indicizzato": etichetta mostrata -> valore di has_cv per il backend.
CV_FILTERS: dict[str, bool | None] = {"tutti": None, "presente": True, "manca": False}

# Colonne della tabella: chiave della riga -> intestazione. Sono tutti i campi
# MCFlash, in chiaro, piu' lo stato del CV indicizzato (subito dopo il nome,
# cosi' il colore si vede senza scorrere la tabella).
TABLE_COLUMNS: dict[str, str] = {
    "id": "Id",
    "trittico": "Codice",
    "nome_completo": "Nome",
    "cv_label": "CV",
    "ruolo": "Ruolo",
    "seniority": "Seniority",
    "eta": "Età",
    "sede": "Sede",
    "lingue": "Lingue",
    "disponibilita": "Disponibilità",
    "budget": "Budget",
    "site": "Site",
    "abilitato": "Abilitato",
    "is_talent_up": "TalentUp",
    "cv_file": "File CV",
}

# Colori delle celle (sfondo, testo): verdi = a posto, arancio = da fare.
_OK = "background-color: #E3F4EA; color: #1E6B42; font-weight: 600"
_TODO = "background-color: #FDEBD6; color: #9A5200; font-weight: 600"
_OFF = "color: #8A94A6"
_CODE = "color: #1F3864; font-weight: 700"


def cv_label(row: dict[str, Any]) -> str:
    """'sì · v3', 'sì' (versione sconosciuta) oppure 'manca'."""
    cv = row.get("cv")
    if not cv:
        return "manca"
    version = cv.get("version")
    return f"sì · v{version}" if version else "sì"


def text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def sede_options(rows: Iterable[dict[str, Any]]) -> list[str]:
    """Sedi distinte, ordinate senza badare alle maiuscole."""
    seen: dict[str, str] = {}
    for row in rows:
        sede = text(row.get("sede"))
        if sede:
            seen.setdefault(sede.casefold(), sede)
    return sorted(seen.values(), key=str.casefold)


def summary(rows: list[dict[str, Any]]) -> dict[str, int]:
    """Contatori per i riquadri in cima alla home."""
    return {
        "totale": len(rows),
        "abilitati": sum(1 for r in rows if r.get("abilitato") is True),
        "con_cv": sum(1 for r in rows if r.get("cv")),
        "senza_cv": sum(1 for r in rows if not r.get("cv")),
        "talent_up": sum(1 for r in rows if r.get("is_talent_up") is True),
    }


def candidates_frame(rows: list[dict[str, Any]]) -> pd.DataFrame:
    """Tabella con tutte le colonne di TABLE_COLUMNS, intestazioni in italiano."""
    records = []
    for row in rows:
        cv = row.get("cv") or {}
        records.append({
            **{key: row.get(key) for key in TABLE_COLUMNS},
            "id": int(row["id"]) if text(row.get("id")).isdigit() else row.get("id"),
            "nome_completo": text(row.get("nome_completo")) + (" (finto)" if row.get("finto") else ""),
            "cv_label": cv_label(row),
            "cv_file": text(cv.get("file")),
        })
    frame = pd.DataFrame.from_records(records, columns=list(TABLE_COLUMNS))
    return frame.rename(columns=TABLE_COLUMNS)


def style_frame(frame: pd.DataFrame) -> Styler:
    """Colori: CV presente in verde, mancante in arancio, record disabilitati in grigio."""
    def cv_cell(value: Any) -> str:
        return _TODO if value == "manca" else _OK

    def disabled_row(row: pd.Series) -> list[str]:
        style = _OFF if row.get("Abilitato") is False else ""
        return [style] * len(row)

    return (
        frame.style
        .apply(disabled_row, axis=1)
        .map(cv_cell, subset=["CV"])
        .map(lambda _: _CODE, subset=["Codice"])
    )


def _languages_text(languages: Iterable[dict[str, Any]] | None) -> str:
    return ", ".join(
        f"{text(l.get('lang')).capitalize()}: {text(l.get('level'))}" if text(l.get("level")) else text(l.get("lang"))
        for l in languages or [] if text(l.get("lang"))
    )


def _same(a: Any, b: Any) -> bool:
    return " ".join(text(a).casefold().split()) == " ".join(text(b).casefold().split())


def comparison_frame(row: dict[str, Any], edited: dict[str, Any]) -> pd.DataFrame:
    """Dati MCFlash attuali accanto a quelli del CV, per la pagina Aggiorna."""
    pairs = [
        ("Nome", row.get("nome_completo"), edited.get("full_name")),
        ("Codice", row.get("trittico"), edited.get("trittico")),
        ("Ruolo", row.get("ruolo"), edited.get("role")),
        ("Sede", row.get("sede"), edited.get("location")),
        ("Età", row.get("eta"), edited.get("age")),
        ("Lingue", row.get("lingue"), _languages_text(edited.get("languages"))),
        ("Email", "—", edited.get("email")),
        ("Telefono", "—", edited.get("phone")),
    ]
    return pd.DataFrame(
        [{"Campo": f, "MCFlash": text(a) or "—", "Dal CV": text(b) or "—",
          "Cambia": not _same(a, b) and text(b) != "" and text(a) != "—"} for f, a, b in pairs]
    )


def style_comparison(frame: pd.DataFrame) -> Styler:
    def row_style(r: pd.Series) -> list[str]:
        return [_TODO if r["Cambia"] and c == "Dal CV" else "" for c in r.index]

    return frame.style.apply(row_style, axis=1).hide(["Cambia"], axis="columns")


def candidate_title(row: dict[str, Any]) -> str:
    """Intestazione della pagina Aggiorna: 'DCA · Project manager · Torino'."""
    parts = [text(row.get("trittico")), text(row.get("ruolo")), text(row.get("sede"))]
    return " · ".join(p for p in parts if p)


def cv_replacement_note(row: dict[str, Any]) -> str:
    """Cosa succede all'indice confermando un aggiornamento."""
    cv = row.get("cv")
    if not cv:
        return "Il candidato non ha ancora un CV indicizzato: il nuovo CV verrà aggiunto all'indice."
    version = f" v{cv['version']}" if cv.get("version") else ""
    return f"Il nuovo CV sostituirà il{version} nell'indice (file «{text(cv.get('file'))}»)."
