"""Client HTTP verso il backend (Azure Functions, repo Autocompilazione CV_ON_SITE).

Il backend risponde sempre con la busta {data, error, request_id}: il client
restituisce `data` e trasforma ogni errore in BackendError con un messaggio
leggibile da mostrare nella pagina. Fa eccezione il file originale di una
bozza, che arriva come byte.
"""
from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlsplit

import requests

from dashboard.config import Settings, load_settings

# L'estrazione di un CV lungo con il profilo mcflash arriva a un paio di minuti.
EXTRACT_TIMEOUT_SECONDS = 300


class BackendError(RuntimeError):
    def __init__(self, message: str, *, status: int | None = None, request_id: str | None = None):
        super().__init__(message)
        self.status = status
        self.request_id = request_id


class BackendClient:
    def __init__(self, settings: Settings, session: requests.Session | None = None):
        self.settings = settings
        self.session = session or requests.Session()

    def _send(self, method: str, path: str, *, params: dict | None = None, json: Any = None,
              files: Any = None, timeout: float | None = None) -> requests.Response:
        url = f"{self.settings.backend_url}/api/{path.lstrip('/')}"
        headers = {"Accept": "application/json"}
        if self.settings.function_key:
            headers["x-functions-key"] = self.settings.function_key
        clean = {k: v for k, v in (params or {}).items() if v is not None and v != ""}
        try:
            return self.session.request(method, url, params=clean, json=json, files=files, headers=headers,
                                        timeout=timeout or self.settings.timeout_seconds)
        except requests.ConnectionError as exc:
            raise BackendError(f"Backend non raggiungibile su {self.settings.backend_url}. "
                               "In locale va avviato con 'func start' nel repo backend.") from exc
        except requests.Timeout as exc:
            raise BackendError("Il backend non ha risposto in tempo.") from exc

    @staticmethod
    def _raise_for_status(resp: requests.Response, envelope: dict | None) -> None:
        if resp.status_code < 400:
            return
        request_id = (envelope or {}).get("request_id") or resp.headers.get("x-request-id")
        detail = (envelope or {}).get("error") or resp.text[:200] or resp.reason
        if resp.status_code in (401, 403):
            detail = "chiave della Function mancante o non valida (FUNCTION_KEY)"
        elif resp.status_code == 404 and envelope is None:
            # 404 senza busta: la rotta non esiste, non e' un record mancante.
            path = urlsplit(getattr(resp, "url", "") or "").path or "questo endpoint"
            detail = (f"il backend non ha {path}. In locale va aggiunto alla lista di 'func start --functions' "
                      "(vedi README); su Azure va pubblicata la versione nuova del backend.")
        raise BackendError(f"Errore {resp.status_code} dal backend: {detail}",
                           status=resp.status_code, request_id=request_id)

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        resp = self._send(method, path, **kwargs)
        try:
            body = resp.json()
        except ValueError:
            body = None
        envelope = body if isinstance(body, dict) and "data" in body else None
        self._raise_for_status(resp, envelope)
        if envelope is None:
            raise BackendError("Risposta del backend non valida (manca la busta JSON).", status=resp.status_code,
                               request_id=resp.headers.get("x-request-id"))
        return envelope["data"]

    # ---------------------------------------------------------------- candidati

    def list_candidates(self, *, q: str | None = None, sede: str | None = None, has_cv: bool | None = None,
                        tutti: bool = False, limit: int = 50, offset: int = 0,
                        refresh: bool = False) -> dict[str, Any]:
        params = {
            "q": q, "sede": sede, "limit": limit, "offset": offset,
            "has_cv": None if has_cv is None else str(has_cv).lower(),
            "tutti": "true" if tutti else None,
            "refresh": "true" if refresh else None,
        }
        return self._request("GET", "candidates", params=params)

    def get_candidate(self, candidate_id: str | int) -> dict[str, Any]:
        return self._request("GET", f"candidates/{candidate_id}")

    def candidate_cv(self, candidate_id: str | int) -> tuple[str, bytes]:
        """Il CV indicizzato del candidato: (nome file, byte). Senza busta JSON."""
        return self._file(f"candidates/{candidate_id}/cv", fallback=f"cv_{candidate_id}")

    def cv_file(self, document_id: str) -> tuple[str, bytes]:
        """Un CV dell'archivio indicizzato: (nome file, byte)."""
        return self._file("cv/file", params={"document_id": document_id}, fallback=document_id)

    def _file(self, path: str, *, params: dict | None = None, fallback: str) -> tuple[str, bytes]:
        resp = self._send("GET", path, params=params, timeout=60)
        if resp.status_code >= 400:
            try:
                body = resp.json()
            except ValueError:
                body = None
            self._raise_for_status(resp, body if isinstance(body, dict) else None)
        match = re.search(r'filename="([^"]+)"', resp.headers.get("Content-Disposition", ""))
        return (match.group(1) if match else fallback), resp.content

    def find_cvs(self, *, modo: str = "codice", escludi: list[str] | None = None, **person: Any) -> dict[str, Any]:
        """POST /api/cv-finder: CV dell'archivio probabilmente della persona.
        person: id_mcflash, oppure nome, cognome, ruolo, eta, sede."""
        body = {**{k: v for k, v in person.items() if v not in (None, "")}, "modo": modo, "escludi": escludi or []}
        return self._request("POST", "cv-finder", json=body, timeout=180)

    def link_cv(self, id_mcflash: str | int, document_id: str, *, user: str | None = None) -> dict[str, Any]:
        """POST /api/cv-finder/link: collega un CV dell'archivio a un candidato senza CV."""
        return self._request("POST", "cv-finder/link",
                             json={"id_mcflash": str(id_mcflash), "document_id": document_id, "user": user})

    def hide_candidate(self, candidate_id: str | int, *, user: str | None = None) -> dict[str, Any]:
        """POST /api/candidates/<id>/nascondi: nasconde il candidato su MCFlash."""
        return self._request("POST", f"candidates/{candidate_id}/nascondi", json={"user": user})

    def match_candidate(self, *, nome: str, cognome: str, trittico: str | None = None) -> dict[str, Any]:
        return self._request("POST", "candidates/match",
                             json={"nome": nome, "cognome": cognome, "trittico": trittico})

    # ---------------------------------------------------------------- estrazione e bozze

    def extract(self, data: bytes, filename: str) -> dict[str, Any]:
        """POST /api/extract?profile=mcflash: dati completi per il modello MC, contatti inclusi."""
        return self._request("POST", "extract", params={"profile": "mcflash"},
                             files={"file": (filename, data)}, timeout=EXTRACT_TIMEOUT_SECONDS)

    def save_draft(self, draft_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("PUT", f"drafts/{draft_id}", json=payload)

    def get_draft(self, draft_id: str) -> dict[str, Any]:
        return self._request("GET", f"drafts/{draft_id}")

    def list_drafts(self, *, kind: str | None = None, id_mcflash: str | None = None) -> list[dict[str, Any]]:
        return self._request("GET", "drafts", params={"kind": kind, "id_mcflash": id_mcflash})

    def delete_draft(self, draft_id: str) -> dict[str, Any]:
        return self._request("DELETE", f"drafts/{draft_id}")

    def draft_original(self, draft_id: str) -> bytes:
        """Il CV originale della bozza, come byte (non c'e' busta JSON)."""
        resp = self._send("GET", f"drafts/{draft_id}/original", timeout=60)
        if resp.status_code >= 400:
            try:
                body = resp.json()
            except ValueError:
                body = None
            self._raise_for_status(resp, body if isinstance(body, dict) else None)
        return resp.content

    def render_cv(self, data: dict[str, Any], *, fmt: str = "both") -> dict[str, Any]:
        """POST /api/cv/render: {html?, docx_base64?, docx_bytes?, checks}."""
        return self._request("POST", "cv/render", json={"data": data, "format": fmt}, timeout=60)

    # ---------------------------------------------------------------- conferma e operazioni

    def commit(self, draft_id: str, *, user: str | None = None) -> dict[str, Any]:
        """POST /api/cv/commit: storage, MCFlash, indice, mappa. Restituisce l'operazione."""
        return self._request("POST", "cv/commit", json={"draft_id": draft_id, "user": user}, timeout=120)

    def get_operation(self, op_id: str) -> dict[str, Any]:
        return self._request("GET", f"operations/{op_id}", timeout=60)

    def retry_operation(self, op_id: str) -> dict[str, Any]:
        return self._request("POST", f"operations/{op_id}/retry", timeout=120)

    def list_operations(self, *, stato: str | None = None, utente: str | None = None,
                        da: str | None = None) -> list[dict[str, Any]]:
        return self._request("GET", "operations", params={"stato": stato, "utente": utente, "da": da})

    # ---------------------------------------------------------------- supporto

    def roles(self) -> list[dict[str, Any]]:
        return self._request("GET", "roles")

    def mc_levels(self) -> dict[str, list[str]]:
        return self._request("GET", "mc-levels")

    def cv_filename(self, *, trittico: str, id_mcflash: str | None = None, ext: str = ".pdf") -> dict[str, Any]:
        return self._request("GET", "cv/filename", params={"trittico": trittico, "id_mcflash": id_mcflash, "ext": ext})


def get_client() -> BackendClient:
    """Punto unico di creazione del client: i test lo sostituiscono con un finto."""
    return BackendClient(load_settings())
