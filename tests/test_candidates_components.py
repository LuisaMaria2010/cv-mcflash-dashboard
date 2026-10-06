"""Tests per tabella, contatori e testi derivati dalle righe candidato (dashboard/components/candidates.py)."""
from __future__ import annotations

from dashboard.components.candidates import (
    TABLE_COLUMNS,
    candidate_title,
    candidates_frame,
    cv_label,
    cv_replacement_note,
    sede_options,
    style_frame,
    summary,
)

ROWS = [
    {"id": "1884", "trittico": "DCA", "nome_completo": "Davide Carli", "ruolo": "PM", "seniority": "Senior",
     "eta": 40, "sede": "Torino", "lingue": "Inglese C1", "disponibilita": "Immediata", "budget": 350,
     "site": "mcflashcandidati", "abilitato": True, "is_talent_up": False,
     "cv": {"file": "Skill Tecnico_DCA_MC Engineering.pdf", "version": 3}},
    {"id": "12", "trittico": "MRO", "nome_completo": "Mario Rossi", "abilitato": False, "is_talent_up": True,
     "cv": None},
]


def test_cv_label():
    assert cv_label({"cv": None}) == "manca"
    assert cv_label({"cv": {"file": "a.pdf", "version": 3}}) == "sì · v3"
    assert cv_label({"cv": {"file": "a.pdf", "version": None}}) == "sì"


def test_sede_options_distinct_and_sorted():
    rows = [{"sede": "Torino"}, {"sede": "roma"}, {"sede": "torino"}, {"sede": None}, {"sede": " "}]
    assert sede_options(rows) == ["roma", "Torino"]


def test_summary():
    assert summary(ROWS) == {"totale": 2, "abilitati": 1, "con_cv": 1, "senza_cv": 1, "talent_up": 1}


def test_frame_has_every_mcflash_field_in_clear():
    frame = candidates_frame(ROWS)
    assert list(frame.columns) == list(TABLE_COLUMNS.values())
    first = frame.iloc[0].to_dict()
    assert first["Id"] == 1884 and first["Codice"] == "DCA" and first["Nome"] == "Davide Carli"
    assert first["Lingue"] == "Inglese C1" and first["Budget"] == 350 and first["Site"] == "mcflashcandidati"
    assert first["CV"] == "sì · v3" and first["File CV"] == "Skill Tecnico_DCA_MC Engineering.pdf"
    second = frame.iloc[1].to_dict()
    assert second["CV"] == "manca" and second["File CV"] == ""
    assert bool(second["Abilitato"]) is False and bool(second["TalentUp"]) is True


def test_style_colors_cv_and_disabled_rows():
    html = style_frame(candidates_frame(ROWS)).to_html()
    assert "#E3F4EA" in html   # CV presente
    assert "#FDEBD6" in html   # CV mancante
    assert "#8A94A6" in html   # record disabilitato


def test_candidate_title_and_note():
    row = {"trittico": "DCA", "ruolo": "PM", "sede": None, "cv": {"file": "Skill Tecnico_DCA_MC.pdf", "version": 3}}
    assert candidate_title(row) == "DCA · PM"
    assert "sostituirà il v3" in cv_replacement_note(row)
    assert "Skill Tecnico_DCA_MC.pdf" in cv_replacement_note(row)
    assert "verrà aggiunto" in cv_replacement_note({"cv": None})
