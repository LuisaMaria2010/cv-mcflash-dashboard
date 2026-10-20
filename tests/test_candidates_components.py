"""Tests per tabella, contatori e testi derivati dalle righe candidato (dashboard/components/candidates.py)."""
from __future__ import annotations

from dashboard.components.candidates import (
    OPEN_MARK,
    TABLE_COLUMNS,
    candidate_title,
    candidates_frame,
    cv_label,
    cv_replacement_note,
    distinct_values,
    filter_rows,
    value_range,
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


def test_distinct_values_sorted_ignoring_case():
    rows = [{"sede": "Torino"}, {"sede": "roma"}, {"sede": "torino"}, {"sede": None}, {"sede": " "}]
    assert distinct_values(rows, "sede") == ["roma", "Torino"]


def test_value_range():
    assert value_range(ROWS, "eta") == (40, 40)
    assert value_range([{"budget": 300.5}, {"budget": "120"}, {"budget": None}], "budget") == (120, 301)
    assert value_range(ROWS, "budget") == (350, 350) and value_range([{}], "eta") is None


def test_filter_rows_by_every_kind():
    names = lambda values: [r["nome_completo"] for r in filter_rows(ROWS, values)]
    assert names({}) == ["Davide Carli", "Mario Rossi"]
    assert names({"trittico": "dc", "ruolo": [], "eta": None, "abilitato": None}) == ["Davide Carli"]
    assert names({"sede": ["torino"]}) == ["Davide Carli"]
    assert names({"eta": (41, 60)}) == [] and names({"eta": (30, 40)}) == ["Davide Carli"]
    assert names({"abilitato": False}) == ["Mario Rossi"] and names({"is_talent_up": True}) == ["Mario Rossi"]
    assert names({"cv": False}) == ["Mario Rossi"] and names({"cv_file": "skill"}) == ["Davide Carli"]


def test_summary():
    assert summary(ROWS) == {"totale": 2, "abilitati": 1, "con_cv": 1, "senza_cv": 1, "talent_up": 1}


def test_frame_has_every_mcflash_field_in_clear():
    frame = candidates_frame(ROWS)
    assert list(frame.columns) == [OPEN_MARK, *TABLE_COLUMNS.values()]
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


def test_style_frame_highlights_the_selected_row_but_keeps_cv_color():
    frame = candidates_frame(ROWS, opened=1)
    assert list(frame[OPEN_MARK]) == ["", "✔"]

    def highlighted(styler):
        styler._compute()
        return {(r, frame.columns[c]) for (r, c), props in styler.ctx.items()
                if ("background-color", "#D6E4FB") in props}

    cells = highlighted(style_frame(frame, selected=1))
    assert cells == {(1, col) for col in frame.columns if col not in ("CV", OPEN_MARK)}  # tranne CV e spunta
    assert highlighted(style_frame(frame)) == set()
