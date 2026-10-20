"""Dati della bozza: trittico, confronto tra estratto e versione corretta, conversioni.

La bozza segue il formato di POST /api/extract?profile=mcflash (CVExtraction del
backend): lo stesso dizionario andra' poi a /api/cv/render. Nessuna chiamata a
Streamlit qui.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import date
from typing import Any, Iterable

# Campi modificabili nel form -> etichetta per il riepilogo delle modifiche.
FIELD_LABELS: dict[str, str] = {
    "first_name": "Nome",
    "last_name": "Cognome",
    "email": "Email",
    "phone": "Telefono",
    "age": "Età",
    "birth_date": "Data di nascita",
    "location": "Città",
    "catalog_role": "Ruolo MC",
    "role": "Ruolo nel CV",
    "cv_skills": "Skill",
    "languages": "Lingue",
    "experiences": "Esperienze",
    "education": "Formazione",
    "trainings": "Trainings",
    "certifications": "Certificazioni",
}

EXPERIENCE_FIELDS = ("start_date", "end_date", "ongoing", "company", "role", "description", "technologies", "projects")
PROJECT_FIELDS = ("start_date", "end_date", "ongoing", "name", "role", "activities", "technologies")


# ---------------------------------------------------------------- trittico

def _ascii_letters(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text or "")
    no_marks = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return re.sub(r"[^A-Za-z]", "", no_marks).upper()


def trittico(first_name: str | None, last_name: str | None) -> str | None:
    """Prima lettera del nome + prime due lettere del cognome.

    Stessa regola di domain/candidate_identity.trittico nel backend: si ricalcola
    qui mentre l'utente scrive, senza una chiamata per ogni tasto.
    """
    first = _ascii_letters(first_name or "")
    last = _ascii_letters(last_name or "")
    if not first or len(last) < 2:
        return None
    return first[0] + last[:2]


def split_full_name(full: str | None, tri: str | None) -> tuple[str | None, str | None]:
    """Nome e cognome da un nome completo MCFlash ("Mario De Luca"). Si sceglie il
    taglio (anche con il cognome davanti) che ridà il trittico del record; se
    nessuno torna, prima parola = nome, il resto = cognome."""
    words = (full or "").split()
    if not words:
        return None, None
    cuts = [(" ".join(words[:i]), " ".join(words[i:])) for i in range(1, len(words))]
    cuts += [(b, a) for a, b in cuts]
    wanted = (tri or "").strip().upper()
    for first, last in cuts:
        if wanted and trittico(first, last) == wanted:
            return first, last
    return (cuts[0] if cuts else (words[0], None))


def identity_from_record(extraction: dict[str, Any], record: dict[str, Any]) -> dict[str, Any]:
    """Il CV attuale e' nel modello MC, quindi anonimo: al posto del nome c'e' il
    trittico. Nome, cognome e trittico si prendono dal record MCFlash; eta' solo
    se il CV non la riporta."""
    first, last = split_full_name(record.get("nome_completo"), record.get("trittico"))
    out = dict(extraction)
    out.update(first_name=first, last_name=last, full_name=full_name(first, last),
               trittico=(record.get("trittico") or "").strip().upper() or trittico(first, last))
    if not out.get("age") and record.get("eta") not in (None, ""):
        out["age"] = record.get("eta")
    return out


def _is_code(value: Any) -> bool:
    return bool(re.fullmatch(r"[A-Z]{3}", str(value or "").strip()))


def with_identity(extraction: dict[str, Any], first: str | None, last: str | None, *,
                  tri: str | None = None, age: Any = None, location: str | None = None) -> dict[str, Any]:
    """Nome e cognome gia' noti (record MCFlash o form) al posto di quelli del CV
    quando il CV e' anonimo (al posto del nome c'e' il codice) o non li riporta.
    Eta' e citta' solo se il CV non le ha."""
    out = dict(extraction)
    anonymous = (not (out.get("first_name") and out.get("last_name"))
                 or _is_code(out.get("first_name")) or _is_code(out.get("last_name")))
    if anonymous and (first or last):
        out.update(first_name=first or None, last_name=last or None, full_name=full_name(first, last),
                   trittico=(tri or "").strip().upper() or trittico(first, last))
    if not out.get("age") and age not in (None, ""):
        out["age"] = age
    if not out.get("location") and location:
        out["location"] = location
    return out


def fill_from_record(extraction: dict[str, Any], record: dict[str, Any]) -> dict[str, Any]:
    """with_identity con i dati del record MCFlash (aggiornamento di un candidato)."""
    first, last = split_full_name(record.get("nome_completo"), record.get("trittico"))
    return with_identity(extraction, first, last, tri=record.get("trittico"), age=record.get("eta"),
                         location=record_city(record))


def record_city(record: dict[str, Any]) -> str | None:
    """Citta' dalla sede MCFlash ("Milano/remoto" -> "Milano"; "remoto" -> nessuna)."""
    city = (record.get("sede") or "").split("/")[0].strip()
    return None if city.casefold() in ("remoto", "remote", "ibrido", "") else city


def parse_languages(text: str | None) -> list[dict[str, Any]]:
    """Lingue di MCFlash ("Inglese: Avanzato, Francese: Base") nel formato del form."""
    out = []
    for part in re.split(r"[,;\n]", text or ""):
        lang, _, level = part.partition(":")
        if lang.strip():
            out.append({"lang": lang.strip().lower(), "level": level.strip() or None})
    return out


def draft_from_record(record: dict[str, Any], catalog: Iterable[dict[str, Any]] = ()) -> dict[str, Any]:
    """Dati del form per un candidato MCFlash senza CV: quello che MCFlash sa gia'.
    Il resto (esperienze, skill, formazione) resta vuoto da compilare."""
    out = identity_from_record({}, record)
    # Sezioni del CV vuote ma presenti: il form le restituisce come liste vuote
    # e non devono risultare "modificate".
    out.update(cv_skills=[], experiences=[], education=[], trainings=[], certifications=[])
    ruolo = (record.get("ruolo") or "").strip()
    catalog_role = next((r["role"] for r in catalog
                         if ruolo and ruolo.casefold() in {str(r.get("role") or "").casefold(),
                                                           str(r.get("label") or "").casefold()}), None)
    out.update(
        location=record_city(record),
        role=ruolo or None,
        catalog_role=catalog_role,
        languages=parse_languages(record.get("lingue")),
        mcflash={"seniority": record.get("seniority"), "disponibilita": record.get("disponibilita"),
                 "budget": record.get("budget"), "site": record.get("site")},
    )
    return out


# ---------------------------------------------------------------- confronto

def normalize(value: Any) -> Any:
    """Forma canonica per il confronto: stringhe ripulite, vuoti -> None,
    righe vuote tolte dalle liste."""
    if isinstance(value, str):
        text = value.strip()
        return text or None
    if isinstance(value, dict):
        return {k: normalize(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        items = [normalize(v) for v in value]
        return [v for v in items if not _is_empty(v)]
    return value


def _is_empty(value: Any) -> bool:
    if value is None or value == [] or value is False:
        return True
    if isinstance(value, dict):
        return all(_is_empty(v) for v in value.values())
    return False


def changed_fields(extracted: dict[str, Any] | None, edited: dict[str, Any]) -> set[str]:
    """Percorsi modificati rispetto all'estratto: "email", "experiences",
    "experiences[1].role", "experiences[1].projects"..."""
    base = extracted or {}
    changed: set[str] = set()
    for key in FIELD_LABELS:
        if normalize(base.get(key)) != normalize(edited.get(key)):
            changed.add(key)
    old_exps = base.get("experiences") or []
    for i, exp in enumerate(edited.get("experiences") or []):
        old = old_exps[i] if i < len(old_exps) else {}
        for field in EXPERIENCE_FIELDS:
            if normalize(old.get(field)) != normalize(exp.get(field)):
                changed.add(f"experiences[{i}].{field}")
    return changed


def changed_labels(changed: Iterable[str]) -> list[str]:
    """Sezioni modificate, in ordine di form: ["Email", "Esperienze"]."""
    tops = {path.split("[")[0].split(".")[0] for path in changed}
    return [label for key, label in FIELD_LABELS.items() if key in tops]


# ---------------------------------------------------------------- conversioni

def to_date(value: Any) -> date | None:
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10]) if value else None
    except ValueError:
        return None


def to_iso(value: date | None) -> str | None:
    return value.isoformat() if value else None


def list_to_text(items: Iterable[Any] | None) -> str:
    return ", ".join(str(i).strip() for i in (items or []) if str(i).strip())


def text_to_list(text: str | None) -> list[str]:
    return [part.strip() for part in re.split(r"[,;\n]", text or "") if part.strip()]


def full_name(first: str | None, last: str | None) -> str | None:
    name = " ".join(p.strip() for p in (first or "", last or "") if p and p.strip())
    return name or None


# ---------------------------------------------------------------- dati MCFlash e conferma

SENIORITY_VALUES = ("Neo", "Junior", "Medium", "Senior")
SITE_VALUES = ("mcflashcandidati.mcengineering.eu", "mcflashrisorse")
DEFAULT_SITE = SITE_VALUES[0]
# Seniority stimata dall'estrazione -> valore MCFlash; seniority MCFlash -> colonna delle tariffe.
_SENIORITY_FROM_EXTRACTION = {"junior": "Junior", "mid": "Medium", "medium": "Medium", "senior": "Senior"}
_TARIFF_COLUMN = {"Neo": "junior", "Junior": "junior", "Medium": "mid", "Senior": "senior"}


def tariff_for(budget: dict[str, Any] | None, seniority: str | None) -> int | None:
    """Tariffa del catalogo MC per la seniority (Neo e Junior usano la junior)."""
    value = (budget or {}).get(_TARIFF_COLUMN.get(seniority or "", ""))
    try:
        return int(float(value)) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def mcflash_defaults(edited: dict[str, Any], candidate: dict[str, Any] | None,
                     role_budget: dict[str, Any] | None) -> dict[str, Any]:
    """Valori iniziali della sezione "Dati MCFlash": quelli del record per un
    aggiornamento, altrimenti seniority stimata dall'estrazione e tariffa del ruolo."""
    if edited.get("mcflash"):
        return dict(edited["mcflash"])
    if candidate:
        return {"seniority": candidate.get("seniority"), "disponibilita": candidate.get("disponibilita"),
                "budget": candidate.get("budget"), "site": candidate.get("site")}
    seniority = _SENIORITY_FROM_EXTRACTION.get(str(edited.get("seniority") or "").lower())
    return {"seniority": seniority, "disponibilita": "Immediata",
            "budget": tariff_for(role_budget, seniority), "site": DEFAULT_SITE}


def commit_blockers(edited: dict[str, Any], kind: str) -> list[str]:
    """Cosa impedisce la conferma (stesse regole del backend)."""
    missing = []
    if not edited.get("trittico"):
        missing.append("nome e cognome (per il trittico)")
    if not (edited.get("catalog_role") or edited.get("role")):
        missing.append("ruolo")
    extra = edited.get("mcflash") or {}
    if kind == "crea":
        if not extra.get("seniority"):
            missing.append("seniority")
        if not extra.get("site"):
            missing.append("site")
    return missing


# ---------------------------------------------------------------- operazioni

STEP_LABELS = {"blob": "Storage", "mcflash": "MCFlash", "indice": "Indice", "mappa": "Mappa CV → MCFlash"}
STATE_BADGES = {
    "ok": ":green-badge[:material/check: fatto]",
    "in_attesa": ":blue-badge[:material/hourglass_top: in attesa dell'indicizzazione]",
    "errore": ":red-badge[:material/error: errore]",
    "da_fare": ":gray-badge[da fare]",
}
STATUS_LABELS = {"completata": "Completata", "in_corso": "In corso", "fallita": "Fallita"}
