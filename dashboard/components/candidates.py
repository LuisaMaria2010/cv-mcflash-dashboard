"""Testi, tabella e contatori derivati dalle righe candidato di GET /api/candidates.

Nessuna chiamata a Streamlit qui: le pagine usano queste funzioni e i test le
provano direttamente.
"""
from __future__ import annotations

import math
from typing import Any, Iterable

import pandas as pd
from pandas.io.formats.style import Styler

# Filtri della home, uno per ogni campo MCFlash: chiave -> (etichetta, tipo).
# "text" = il campo contiene il testo, "choice" = uno dei valori scelti,
# "range" = numero nell'intervallo, "flag" = tutti / si' / no.
FILTERS: dict[str, tuple[str, str]] = {
    "id": ("Id", "text"),
    "trittico": ("Codice", "text"),
    "nome_completo": ("Nome", "text"),
    "cv": ("CV indicizzato", "flag"),
    "ruolo": ("Ruolo", "choice"),
    "seniority": ("Seniority", "choice"),
    "sede": ("Sede", "choice"),
    "disponibilita": ("Disponibilità", "choice"),
    "site": ("Site", "choice"),
    "lingue": ("Lingue", "text"),
    "eta": ("Età", "range"),
    "budget": ("Budget", "range"),
    "abilitato": ("Abilitato", "flag"),
    "is_talent_up": ("TalentUp", "flag"),
    "cv_file": ("File CV", "text"),
}

# Opzioni dei filtri "flag": etichetta mostrata -> valore richiesto.
CV_FILTERS: dict[str, bool | None] = {"tutti": None, "presente": True, "manca": False}
FLAG_FILTERS: dict[str, bool | None] = {"tutti": None, "sì": True, "no": False}


def flag_options(key: str) -> dict[str, bool | None]:
    return CV_FILTERS if key == "cv" else FLAG_FILTERS

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
_SELECTED = "background-color: #D6E4FB; color: #1F3864; font-weight: 700"
_MARK = "color: #FFFFFF; background-color: #2E5AAC; font-weight: 700; text-align: center"


def cv_label(row: dict[str, Any]) -> str:
    """'sì · v3', 'sì' (versione sconosciuta) oppure 'manca'."""
    cv = row.get("cv")
    if not cv:
        return "manca"
    version = cv.get("version")
    return f"sì · v{version}" if version else "sì"


def text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def field_value(row: dict[str, Any], key: str) -> Any:
    """Valore del campo filtrato: lo stato del CV e il suo file stanno in row["cv"]."""
    if key == "cv":
        return bool(row.get("cv"))
    if key == "cv_file":
        return (row.get("cv") or {}).get("file")
    return row.get(key)


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def distinct_values(rows: Iterable[dict[str, Any]], key: str) -> list[str]:
    """Valori distinti di un campo, ordinati senza badare alle maiuscole."""
    seen: dict[str, str] = {}
    for row in rows:
        value = text(field_value(row, key))
        if value:
            seen.setdefault(value.casefold(), value)
    return sorted(seen.values(), key=str.casefold)


def value_range(rows: Iterable[dict[str, Any]], key: str) -> tuple[int, int] | None:
    """Minimo e massimo (interi) di un campo numerico; None se non ci sono numeri."""
    numbers = [n for n in (_number(field_value(r, key)) for r in rows) if n is not None]
    if not numbers:
        return None
    return math.floor(min(numbers)), math.ceil(max(numbers))


def filter_rows(rows: list[dict[str, Any]], values: dict[str, Any]) -> list[dict[str, Any]]:
    """Righe che rispettano tutti i filtri attivi. Valori per tipo (vedi FILTERS):
    text -> str, choice -> lista di valori, range -> (min, max), flag -> bool.
    Un valore vuoto o None vuol dire filtro spento."""
    def keep(row: dict[str, Any]) -> bool:
        for key, value in values.items():
            kind = FILTERS[key][1]
            field = field_value(row, key)
            if kind == "text" and text(value):
                if text(value).casefold() not in text(field).casefold():
                    return False
            elif kind == "choice" and value:
                if text(field).casefold() not in {text(v).casefold() for v in value}:
                    return False
            elif kind == "range" and value is not None:
                number = _number(field)
                if number is None or not value[0] <= number <= value[1]:
                    return False
            elif kind == "flag" and value is not None:
                if bool(field) != value:
                    return False
        return True

    return [row for row in rows if keep(row)]


def summary(rows: list[dict[str, Any]]) -> dict[str, int]:
    """Contatori per i riquadri in cima alla home."""
    return {
        "totale": len(rows),
        "abilitati": sum(1 for r in rows if r.get("abilitato") is True),
        "con_cv": sum(1 for r in rows if r.get("cv")),
        "senza_cv": sum(1 for r in rows if not r.get("cv")),
        "talent_up": sum(1 for r in rows if r.get("is_talent_up") is True),
    }


# Prima colonna della tabella: la spunta sulla riga del candidato aperto.
OPEN_MARK = " "


def candidates_frame(rows: list[dict[str, Any]], opened: int | None = None) -> pd.DataFrame:
    """Tabella con tutte le colonne di TABLE_COLUMNS, intestazioni in italiano, e
    davanti la colonna OPEN_MARK con la spunta sulla riga `opened` (posizione)."""
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
    frame = pd.DataFrame.from_records(records, columns=list(TABLE_COLUMNS)).rename(columns=TABLE_COLUMNS)
    frame.insert(0, OPEN_MARK, ["✔" if i == opened else "" for i in range(len(frame))])
    return frame


def style_frame(frame: pd.DataFrame, selected: int | None = None) -> Styler:
    """Colori: CV presente in verde, mancante in arancio, record disabilitati in grigio.
    La riga `selected` (posizione) e' evidenziata in azzurro, tranne la cella del CV."""
    def cv_cell(value: Any) -> str:
        return _TODO if value == "manca" else _OK

    def disabled_row(row: pd.Series) -> list[str]:
        style = _OFF if row.get("Abilitato") is False else ""
        return [style] * len(row)

    styler = (
        frame.style
        .apply(disabled_row, axis=1)
        .map(cv_cell, subset=["CV"])
        .map(lambda _: _CODE, subset=["Codice"])
    )
    if OPEN_MARK in frame.columns:
        styler = styler.map(lambda v: _MARK if v else "", subset=[OPEN_MARK])
    if selected is not None and 0 <= selected < len(frame):
        others = [c for c in frame.columns if c not in ("CV", OPEN_MARK)]
        styler = styler.apply(lambda _: [_SELECTED] * len(others), axis=1,
                              subset=pd.IndexSlice[frame.index[selected], others])
    return styler


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
