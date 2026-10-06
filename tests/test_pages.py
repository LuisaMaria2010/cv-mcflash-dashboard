"""Tests delle pagine con streamlit.testing (AppTest) e un backend finto."""
from __future__ import annotations

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from dashboard import api
from tests.conftest import ROOT

ROWS = [
    {"id": "1", "trittico": "DCA", "nome_completo": "Davide Carli", "ruolo": "PM", "sede": "Torino",
     "seniority": "Senior", "eta": 40, "lingue": "Inglese", "disponibilita": "Immediata", "idoneo": True,
     "abilitato": False, "budget": 350,
     "cv": {"document_id": "d1", "file": "Skill Tecnico_DCA_MC Engineering.pdf", "version": 3, "status": "processed"}},
    {"id": "2", "trittico": "MRO", "nome_completo": "Mario Rossi", "ruolo": "SAP", "sede": "Roma",
     "seniority": "Mid", "eta": 30, "idoneo": True, "cv": None},
    {"id": "3", "trittico": "LBI", "nome_completo": "Luca Bianchi", "ruolo": "Java", "sede": "Roma",
     "seniority": "Junior", "eta": 25, "idoneo": False, "cv": None},
]


class _FakeClient:
    def __init__(self, fail=False):
        self.fail, self.calls = fail, []

    def list_candidates(self, *, q=None, sede=None, has_cv=None, tutti=False, limit=50, offset=0, refresh=False):
        self.calls.append(("list", q, sede, has_cv, tutti, offset))
        if self.fail:
            raise api.BackendError("Backend non raggiungibile su http://x", request_id="rid")
        rows = [r for r in ROWS if tutti or r["idoneo"]]
        if q:
            rows = [r for r in rows if q.lower() in (r["nome_completo"] + r["trittico"]).lower()]
        if sede:
            rows = [r for r in rows if r["sede"] == sede]
        if has_cv is not None:
            rows = [r for r in rows if (r["cv"] is not None) == has_cv]
        return {"total": len(rows), "offset": offset, "limit": limit, "items": rows[offset:offset + limit],
                "warnings": []}

    def get_candidate(self, candidate_id):
        row = next((r for r in ROWS if r["id"] == str(candidate_id)), None)
        if row is None:
            raise api.BackendError("Errore 404 dal backend: Candidato MCFlash non trovato", status=404)
        return {**row, "warnings": []}

    # ---- bozze e supporto
    drafts: dict = {}
    saves: list = []
    match_result: dict = {"esito": "nuovo", "motivo": "nessun record con questo trittico", "candidati": []}

    def get_draft(self, draft_id):
        if draft_id not in self.drafts:
            raise api.BackendError("Errore 404 dal backend: Bozza non trovata", status=404)
        return self.drafts[draft_id]

    def save_draft(self, draft_id, payload):
        self.saves.append((draft_id, payload))
        saved = {**self.drafts.get(draft_id, {}), **payload, "draft_id": draft_id, "updated_at": "2026-10-05T10:00:00+00:00"}
        self.drafts[draft_id] = saved
        return saved

    def list_drafts(self, *, kind=None, id_mcflash=None):
        return []

    def draft_original(self, draft_id):
        raise api.BackendError("Errore 404 dal backend: CV originale non trovato", status=404)

    def roles(self):
        return [{"role": "Sviluppatore Java", "label": "Sviluppatore Java", "budget": {"junior": 200, "mid": 280, "senior": 350}}]

    def mc_levels(self):
        return {"skill": ["Conoscenza base", "Buona conoscenza", "Ottima conoscenza"],
                "lingua": ["Base", "Intermedio", "Avanzato", "Fluente", "Madrelingua"]}

    def cv_filename(self, *, trittico, id_mcflash=None, ext=".pdf"):
        return {"trittico": trittico, "filename": f"Skill Tecnico_{trittico}_MC Engineering.pdf",
                "reused": False, "alternatives": []}

    def match_candidate(self, *, nome, cognome, trittico=None):
        return self.match_result

    renders: list = []
    commits: list = []
    op_status: str = "in_corso"

    def _op(self, draft_id):
        done = self.op_status == "completata"
        return {"id": "e" * 32, "draft_id": draft_id, "status": self.op_status, "id_mcflash": "900001",
                "step_blob": "ok", "step_mcflash": "ok", "step_indice": "ok",
                "step_mappa": "ok" if done else "in_attesa", "error": "", "error_step": "",
                "incoming_blob": "Skill Tecnico_MRO_MC Engineering.docx", "mcflash_mode": "finto"}

    def commit(self, draft_id, *, user=None):
        self.commits.append(draft_id)
        self.drafts[draft_id]["operation_id"] = "e" * 32
        return self._op(draft_id)

    def get_operation(self, op_id):
        for op in self.ops:
            if op["id"] == op_id:
                if op["status"] == "in_corso" and self.index_ready:
                    op.update(status="completata", step_mappa="ok")
                return dict(op)
        return self._op(DRAFT_ID)

    ops: list = []
    index_ready: bool = False
    retries: list = []

    def list_operations(self, *, stato=None, utente=None, da=None):
        return [dict(o) for o in self.ops if (not stato or o["status"] == stato)
                and (not utente or utente in (o.get("user") or ""))]

    def retry_operation(self, op_id):
        self.retries.append(op_id)
        op = next(o for o in self.ops if o["id"] == op_id)
        op.update(status="in_corso", step_mcflash="ok", step_indice="ok", step_mappa="in_attesa", error="")
        return dict(op)

    def render_cv(self, data, *, fmt="both"):
        import base64
        self.renders.append(data)
        return {"html": f"<div class='mc-cv'>Candidate Profile {data.get('trittico')} {data.get('location')}</div>",
                "docx_base64": base64.b64encode(b"PK-docx").decode(), "docx_bytes": 7,
                "checks": [] if data.get("catalog_role") else ["Manca il ruolo in alto: scegli un ruolo del catalogo MC."]}


EXTRACTED = {
    "first_name": "Mario", "last_name": "Rossi", "full_name": "Mario Rossi", "trittico": "MRO",
    "email": "mario@example.com", "phone": "+39 333", "age": 30, "location": "Roma",
    "role": "Sviluppatore", "catalog_role": "Sviluppatore Java",
    "cv_skills": [{"name": "Java", "level": "Buona conoscenza"}],
    "languages": [{"lang": "inglese", "level": "Avanzato"}],
    "experiences": [{"start_date": "2020-01-01", "end_date": None, "ongoing": True, "company": "ACME",
                     "role": "Dev", "description": "Sviluppo", "technologies": ["Java"],
                     "projects": [{"name": "Portale", "activities": "API", "technologies": ["Spring"]}]}],
    "education": [{"year": "2015", "title": "Laurea", "institution": "PoliTo"}],
    "trainings": [], "certifications": [],
}
DRAFT_ID = "ab" * 16


def _draft(kind="crea", id_mcflash=None):
    return {"draft_id": DRAFT_ID, "kind": kind, "id_mcflash": id_mcflash, "original_filename": "cv.pdf",
            "extracted": EXTRACTED, "edited": EXTRACTED, "filename": None, "updated_at": "2026-10-05T09:00:00+00:00"}


@pytest.fixture
def fake(monkeypatch):
    client = _FakeClient()
    client.drafts, client.saves, client.renders, client.commits = {}, [], [], []
    client.op_status = "in_corso"
    client.ops, client.index_ready, client.retries = [], False, []
    monkeypatch.setattr(api, "get_client", lambda: client)
    st.cache_data.clear()
    yield client
    st.cache_data.clear()


def _app():
    return AppTest.from_file(str(ROOT / "app.py"), default_timeout=30)


def _texts(at):
    html = " ".join(h.proto.body for h in at.get("html"))
    return html + " ".join(m.value for m in at.markdown) + " ".join(c.value for c in at.caption)


def _table(at):
    return at.dataframe[0].value


def test_home_shows_every_candidate_in_a_table(fake):
    at = _app().run()
    assert not at.exception
    table = _table(at)
    assert list(table["Nome"]) == ["Davide Carli", "Mario Rossi", "Luca Bianchi"]  # anche il non idoneo
    assert {"Id", "Codice", "Lingue", "Budget", "Site", "Abilitato", "TalentUp", "File CV"} <= set(table.columns)
    assert list(table["CV"]) == ["sì · v3", "manca", "manca"]
    assert [m.value for m in at.metric][:4] == ["3", "0", "1", "2"]
    assert "Candidati" in _texts(at)


def test_home_filters(fake):
    at = _app().run()
    at.selectbox(key="f_sede").set_value("Roma").run()
    assert list(_table(at)["Nome"]) == ["Mario Rossi", "Luca Bianchi"]
    at.selectbox(key="f_cv").set_value("manca").run()
    assert at.query_params["sede"] == "Roma" and at.query_params["cv"] == "manca"
    at.text_input(key="f_q").set_value("rossi").run()
    assert list(_table(at)["Nome"]) == ["Mario Rossi"]


def test_home_reads_filters_from_url(fake):
    at = _app()
    at.query_params["q"] = "carli"
    at.run()
    assert at.text_input(key="f_q").value == "carli"
    assert list(_table(at)["Nome"]) == ["Davide Carli"]


def test_home_shows_backend_error(monkeypatch):
    monkeypatch.setattr(api, "get_client", lambda: _FakeClient(fail=True))
    st.cache_data.clear()
    at = _app().run()
    assert not at.exception
    assert any("non raggiungibile" in e.value for e in at.error)


def test_aggiorna_from_url(fake):
    at = _app()
    at.switch_page("views/aggiorna.py")
    at.query_params["id"] = "1"
    at.run()
    assert not at.exception
    assert "Aggiorna · DCA · PM · Torino" in _texts(at)
    assert any("sostituirà il v3" in i.value for i in at.info)
    assert "Immediata" in _texts(at)


def test_aggiorna_without_id_and_unknown_id(fake):
    at = _app()
    at.switch_page("views/aggiorna.py")
    at.run()
    assert any("Nessun candidato scelto" in i.value for i in at.info)
    at = _app()
    at.switch_page("views/aggiorna.py")
    at.query_params["id"] = "99"
    at.run()
    assert any("non trovato" in e.value for e in at.error)


# ---------------------------------------------------------------- Crea / Aggiorna con bozza

K = f"ed_{DRAFT_ID[:8]}_0_"


def _open(page, **params):
    at = _app()
    at.switch_page(page)
    for k, v in params.items():
        at.query_params[k] = v
    return at.run()


def test_crea_without_draft_shows_upload(fake):
    at = _open("views/crea.py")
    assert not at.exception
    assert "Carica il CV" in _texts(at)


def test_crea_with_draft_fills_form_and_autosaves(fake):
    fake.drafts[DRAFT_ID] = _draft()
    at = _open("views/crea.py", bozza=DRAFT_ID)
    assert not at.exception, at.exception
    assert at.text_input(key=f"{K}first_name").value == "Mario"
    assert at.text_input(key=f"{K}email").value == "mario@example.com"
    assert any("verrà creato" in s.value for s in at.success)
    assert "MRO" in _texts(at)
    first_saves = len(fake.saves)  # il nome file proposto viene salvato subito
    at.text_input(key=f"{K}email").set_value("nuova@example.com").run()
    assert len(fake.saves) == first_saves + 1
    assert fake.saves[-1][1]["edited"]["email"] == "nuova@example.com"
    assert "Email" in _texts(at)  # tra le sezioni modificate
    at.text_input(key=f"{K}last_name").set_value("Bianchi").run()
    assert fake.saves[-1][1]["edited"]["trittico"] == "MBI"


def test_crea_unknown_draft(fake):
    at = _open("views/crea.py", bozza="cd" * 16)
    assert any("Bozza non trovata" in e.value for e in at.error)


def test_crea_existing_candidate_moves_to_aggiorna(fake):
    fake.drafts[DRAFT_ID] = _draft()
    fake.match_result = {"esito": "aggiorna", "motivo": "stesso trittico e stesso nome",
                         "candidati": [{**ROWS[1], "warnings": []}]}
    at = _open("views/crea.py", bozza=DRAFT_ID)
    assert any("già su MCFlash" in w.value for w in at.warning)
    at.button(key="to_upd_2").click().run()
    assert not at.exception, at.exception
    assert fake.drafts[DRAFT_ID]["kind"] == "aggiorna" and fake.drafts[DRAFT_ID]["id_mcflash"] == "2"
    assert "Aggiorna · MRO · SAP · Roma" in _texts(at)


def test_aggiorna_with_draft_shows_comparison(fake):
    fake.drafts[DRAFT_ID] = _draft("aggiorna", "2")
    at = _open("views/aggiorna.py", id="2", bozza=DRAFT_ID)
    assert not at.exception, at.exception
    frames = [d.value for d in at.dataframe]
    comparison = next(f for f in frames if "Dal CV" in f.columns)
    assert comparison.set_index("Campo").loc["Email", "Dal CV"] == "mario@example.com"


def test_aggiorna_rejects_draft_of_another_candidate(fake):
    fake.drafts[DRAFT_ID] = _draft("aggiorna", "1")
    at = _open("views/aggiorna.py", id="2", bozza=DRAFT_ID)
    assert any("non appartiene" in e.value for e in at.error)


def test_mc_preview_follows_the_form(fake):
    fake.drafts[DRAFT_ID] = _draft()
    at = _open("views/crea.py", bozza=DRAFT_ID)
    assert not at.exception, at.exception
    assert "Candidate Profile MRO Roma" in _texts(at)
    assert any("tutte le informazioni principali" in s.value for s in at.success)
    renders = len(fake.renders)
    at.run()  # nessuna modifica: l'anteprima non si rigenera
    assert len(fake.renders) == renders
    at.text_input(key=f"{K}location").set_value("Torino").run()
    assert "Candidate Profile MRO Torino" in _texts(at)
    assert len(fake.renders) == renders + 1


def test_confirm_needs_mcflash_data_then_commits(fake):
    fake.drafts[DRAFT_ID] = _draft()
    at = _open("views/crea.py", bozza=DRAFT_ID)
    assert not at.exception, at.exception
    # seniority stimata dall'estrazione assente: la conferma e' bloccata finche' non si sceglie
    assert any("mancano: seniority" in c.value for c in at.caption)
    at.selectbox(key=f"{K}mc_seniority").set_value("Senior").run()
    assert at.number_input(key=f"{K}mc_budget").value == 350  # tariffa senior del ruolo scelto
    assert not any("Per confermare mancano" in c.value for c in at.caption)
    at.button(key="ed_commit").click().run()
    assert not at.exception, at.exception
    assert fake.commits == [DRAFT_ID]
    assert fake.saves[-1][1]["edited"]["mcflash"]["seniority"] == "Senior"
    text = _texts(at)
    assert "In corso" in text and "in attesa dell'indicizzazione" in text
    assert "Skill Tecnico_MRO_MC Engineering.docx" in text


def test_committed_draft_opens_read_only(fake):
    fake.drafts[DRAFT_ID] = {**_draft(), "operation_id": "e" * 32}
    fake.op_status = "completata"
    at = _open("views/crea.py", bozza=DRAFT_ID)
    assert not at.exception, at.exception
    assert "Completata" in _texts(at)
    assert not at.text_input  # niente form
    assert not at.success or all("verrà creato" not in s.value for s in at.success)


def _ops():
    base = {"user": "luisa", "created_at": "2026-10-05T11:27:30+00:00", "step_blob": "ok", "draft_id": DRAFT_ID}
    return [
        {**base, "id": "a" * 32, "kind": "crea", "status": "in_corso", "nome": "Mario Rossi", "trittico": "MRO",
         "id_mcflash": "900001", "step_mcflash": "ok", "step_indice": "ok", "step_mappa": "in_attesa", "error": ""},
        {**base, "id": "b" * 32, "kind": "aggiorna", "status": "fallita", "nome": "Davide Carli", "trittico": "DCA",
         "id_mcflash": "1", "step_mcflash": "errore", "step_indice": "da_fare", "step_mappa": "da_fare",
         "error": "MCFlash HTTP 500", "error_step": "mcflash"},
    ]


def test_operations_page_counts_and_advances_running(fake):
    fake.ops = _ops()
    fake.index_ready = True
    at = _open("views/operazioni.py")
    assert not at.exception, at.exception
    # l'operazione in corso e' stata interrogata e quindi completata
    assert [m.value for m in at.metric] == ["2", "1", "0", "1"]
    table = at.dataframe[0].value
    assert list(table["Stato"]) == ["Completata", "Fallita"]
    assert list(table["MCFlash"]) == ["✓ fatto", "✗ errore"]


def test_operations_page_detail_and_retry_from_url(fake):
    fake.ops = _ops()
    at = _open("views/operazioni.py", op="b" * 32)
    assert not at.exception, at.exception
    assert any("MCFlash HTTP 500" in e.value for e in at.error)
    assert "operation_id: " + "b" * 32 in " ".join(c.value for c in at.code)
    at.button(key="retry_" + "b" * 32).click().run()
    assert fake.retries == ["b" * 32]


def test_operations_page_filters(fake):
    fake.ops = _ops()
    at = _open("views/operazioni.py", stato="fallite")
    assert list(at.dataframe[0].value["Candidato"]) == ["Davide Carli (DCA)"]
    at = _open("views/operazioni.py", utente="nessuno")
    assert any("Nessuna operazione" in i.value for i in at.info)
