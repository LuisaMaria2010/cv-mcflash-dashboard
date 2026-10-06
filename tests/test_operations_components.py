"""Tests per tabella e contatori della pagina Operazioni (dashboard/components/operations.py)."""
from __future__ import annotations

from datetime import datetime, timezone

from dashboard.components.operations import counts, draft_link, operations_frame, since, style_operations

OPS = [
    {"id": "a" * 32, "kind": "crea", "status": "completata", "user": "luisa", "nome": "Mario Rossi",
     "trittico": "MRO", "id_mcflash": "900001", "created_at": "2026-10-05T11:27:30+00:00",
     "step_blob": "ok", "step_mcflash": "ok", "step_indice": "ok", "step_mappa": "ok", "error": "",
     "draft_id": "d" * 32},
    {"id": "b" * 32, "kind": "aggiorna", "status": "fallita", "user": "luisa", "nome": "Anna Bianchi",
     "trittico": "ABI", "id_mcflash": "1884", "created_at": "2026-10-05T12:00:00+00:00",
     "step_blob": "ok", "step_mcflash": "errore", "step_indice": "da_fare", "step_mappa": "da_fare",
     "error": "MCFlash HTTP 500", "draft_id": "e" * 32},
    {"id": "c" * 32, "kind": "crea", "status": "in_corso", "nome": "Luca Verdi", "trittico": "LVE",
     "step_blob": "ok", "step_mcflash": "ok", "step_indice": "ok", "step_mappa": "in_attesa"},
]


def test_counts():
    assert counts(OPS) == {"totale": 3, "completata": 1, "in_corso": 1, "fallita": 1}


def test_frame_has_a_column_per_step():
    frame = operations_frame(OPS)
    assert list(frame.columns) == ["Data", "Utente", "Tipo", "Candidato", "Id MCFlash", "Storage", "MCFlash",
                                   "Indice", "Mappa CV → MCFlash", "Stato", "Errore"]
    second = frame.iloc[1].to_dict()
    assert second["Tipo"] == "Aggiorna" and second["Candidato"] == "Anna Bianchi (ABI)"
    assert second["MCFlash"] == "✗ errore" and second["Indice"] == "· da fare" and second["Stato"] == "Fallita"
    assert frame.iloc[2]["Mappa CV → MCFlash"] == "⏳ in attesa"
    html = style_operations(frame).to_html()
    assert "#FBE3E3" in html and "#E3F4EA" in html


def test_since():
    now = datetime(2026, 10, 5, 12, 0, tzinfo=timezone.utc)
    assert since("tutte", now) is None
    assert since("oggi", now) < now.isoformat()
    assert since("7 giorni", now) < since("oggi", now)


def test_draft_link():
    assert draft_link(OPS[0]) == ("views/crea.py", {"bozza": "d" * 32})
    assert draft_link(OPS[1]) == ("views/aggiorna.py", {"id": "1884", "bozza": "e" * 32})
