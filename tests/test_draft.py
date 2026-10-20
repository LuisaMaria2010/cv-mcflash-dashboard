"""Tests per i dati della bozza (dashboard/components/draft.py)."""
from __future__ import annotations

from datetime import date

import pytest

from dashboard.components.draft import (
    draft_from_record,
    fill_from_record,
    parse_languages,
    with_identity,
    identity_from_record,
    split_full_name,
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


def test_split_full_name_matches_the_record_trittico():
    assert split_full_name("Mario De Luca", "MDE") == ("Mario", "De Luca")
    assert split_full_name("De Luca Mario", "MDE") == ("Mario", "De Luca")
    assert split_full_name("Adeleke Adebowale Julius", "AAD") == ("Adeleke", "Adebowale Julius")
    assert split_full_name("Anna Bianchi", "XYZ") == ("Anna", "Bianchi")
    assert split_full_name("Cher", None) == ("Cher", None) and split_full_name("", "X") == (None, None)


def test_identity_from_record_replaces_the_anonymous_name():
    extraction = {"first_name": "ATR", "last_name": "ATR", "full_name": "ATR ATR", "trittico": "AAT", "age": None,
                  "role": "QA"}
    record = {"nome_completo": "Agostino Trovato", "trittico": "ATR", "eta": 29}
    out = identity_from_record(extraction, record)
    assert (out["first_name"], out["last_name"], out["full_name"], out["trittico"], out["age"]) ==         ("Agostino", "Trovato", "Agostino Trovato", "ATR", 29)
    assert out["role"] == "QA" and extraction["first_name"] == "ATR"  # l'originale non cambia


def test_parse_languages():
    assert parse_languages("Inglese: Avanzato, Francese: Base") == [
        {"lang": "inglese", "level": "Avanzato"}, {"lang": "francese", "level": "Base"}]
    assert parse_languages("Spagnolo") == [{"lang": "spagnolo", "level": None}] and parse_languages(None) == []


def test_draft_from_record():
    record = {"nome_completo": "Adeleke Adebowale Julius", "trittico": "AAD", "eta": 41, "sede": "Milano/remoto",
              "ruolo": "Cloud Engineer/DevOps Engineer", "lingue": "Inglese: Avanzato", "seniority": "Senior",
              "disponibilita": "45 gg", "budget": 445, "site": "mcflashcandidati.mcengineering.eu"}
    out = draft_from_record(record, [{"role": "cloud engineer/devops engineer", "label": "Cloud Engineer"}])
    assert (out["first_name"], out["last_name"], out["trittico"]) == ("Adeleke", "Adebowale Julius", "AAD")
    assert out["age"] == 41 and out["location"] == "Milano" and out["catalog_role"] == "cloud engineer/devops engineer"
    assert out["mcflash"] == {"seniority": "Senior", "disponibilita": "45 gg", "budget": 445,
                              "site": "mcflashcandidati.mcengineering.eu"}
    assert draft_from_record({**record, "ruolo": "Altro"})["catalog_role"] is None


def test_with_identity_only_for_anonymous_cvs():
    anonymous = {"first_name": "ATR", "last_name": "ATR", "age": None, "location": "Milano"}
    out = with_identity(anonymous, "Agostino", "Trovato", age=29, location="Roma")
    assert (out["first_name"], out["trittico"], out["age"], out["location"]) == ("Agostino", "ATR", 29, "Milano")
    named = {"first_name": "Mario", "last_name": "Rossi", "trittico": "MRO"}
    assert with_identity(named, "Agostino", "Trovato")["first_name"] == "Mario"
    record = {"nome_completo": "Agostino Trovato", "trittico": "ATR", "eta": 29, "sede": "Milano/remoto"}
    assert fill_from_record({}, record)["full_name"] == "Agostino Trovato"


def test_record_city_and_empty_sections():
    from dashboard.components.draft import changed_fields, record_city
    assert record_city({"sede": "Milano/remoto"}) == "Milano" and record_city({"sede": "remoto"}) is None
    out = draft_from_record({"nome_completo": "Lorenzo Giura", "trittico": "LGI", "sede": "remoto"})
    assert out["location"] is None
    form = {**out, "cv_skills": [], "experiences": [], "education": [], "trainings": [], "certifications": []}
    assert changed_fields(out, form) == set()
