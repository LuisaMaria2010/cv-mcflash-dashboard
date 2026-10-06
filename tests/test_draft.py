"""Tests per i dati della bozza (dashboard/components/draft.py)."""
from __future__ import annotations

from datetime import date

import pytest

from dashboard.components.draft import (
    changed_fields,
    changed_labels,
    commit_blockers,
    full_name,
    list_to_text,
    mcflash_defaults,
    normalize,
    tariff_for,
    text_to_list,
    to_date,
    to_iso,
    trittico,
)


@pytest.mark.parametrize("first, last, expected", [
    ("Mario", "Rossi", "MRO"),
    ("Mario", "De Luca", "MDE"),
    ("Luca", "D'Amico", "LDA"),
    ("Élodie", "Ñúñez", "ENU"),
    ("Mario", "R", None),
    ("", "Rossi", None),
])
def test_trittico_same_rule_as_backend(first, last, expected):
    assert trittico(first, last) == expected


def test_normalize_treats_blank_and_empty_rows_as_missing():
    assert normalize("  ") is None
    assert normalize({"a": " x ", "b": ""}) == {"a": "x", "b": None}
    assert normalize([{"name": " ", "level": None}, {"name": "Python", "level": ""}]) == [
        {"name": "Python", "level": None}]


def test_changed_fields_top_level_and_experiences():
    extracted = {
        "email": "a@b.it", "phone": None, "cv_skills": [{"name": "Python", "level": None}],
        "experiences": [{"company": "ACME", "role": "Dev", "projects": []}],
    }
    edited = {
        "email": "a@b.it ", "phone": "", "cv_skills": [{"name": "Python", "level": "Buona conoscenza"}],
        "experiences": [{"company": "ACME", "role": "Senior Dev", "projects": []},
                        {"company": "Nuova", "role": "PM", "projects": []}],
    }
    changed = changed_fields(extracted, edited)
    assert "email" not in changed and "phone" not in changed
    assert {"cv_skills", "experiences", "experiences[0].role", "experiences[1].company"} <= changed
    assert "experiences[0].company" not in changed
    assert changed_labels(changed) == ["Skill", "Esperienze"]


def test_no_changes_without_edits():
    data = {"first_name": "Mario", "experiences": [{"company": "ACME"}]}
    assert changed_fields(data, dict(data)) == set()


def test_conversions():
    assert to_date("2021-03-01") == date(2021, 3, 1)
    assert to_date("2021-03-01T00:00:00") == date(2021, 3, 1)
    assert to_date("marzo 2021") is None and to_date(None) is None
    assert to_iso(date(2021, 3, 1)) == "2021-03-01" and to_iso(None) is None
    assert text_to_list("Python, Django;  SQL\nAzure ,") == ["Python", "Django", "SQL", "Azure"]
    assert list_to_text(["Python", " ", "SQL"]) == "Python, SQL"
    assert full_name(" Mario ", "Rossi") == "Mario Rossi" and full_name("", None) is None


def test_mcflash_defaults_and_tariff():
    budget = {"junior": 270, "mid": 310, "senior": 360}
    assert tariff_for(budget, "Senior") == 360 and tariff_for(budget, "Neo") == 270 and tariff_for(budget, None) is None
    crea = mcflash_defaults({"seniority": "mid"}, None, budget)
    assert crea == {"seniority": "Medium", "disponibilita": "Immediata", "budget": 310,
                    "site": "mcflashcandidati.mcengineering.eu"}
    row = {"seniority": "Senior", "disponibilita": "30 gg", "budget": 345, "site": "mcflashrisorse"}
    assert mcflash_defaults({}, row, budget) == row
    assert mcflash_defaults({"mcflash": {"seniority": "Junior"}}, row, budget) == {"seniority": "Junior"}


def test_commit_blockers():
    ok = {"trittico": "MRO", "role": "Dev", "mcflash": {"seniority": "Senior", "site": "x"}}
    assert commit_blockers(ok, "crea") == []
    assert commit_blockers({"trittico": "MRO", "role": "Dev"}, "aggiorna") == []
    assert commit_blockers({}, "crea") == ["nome e cognome (per il trittico)", "ruolo", "seniority", "site"]
