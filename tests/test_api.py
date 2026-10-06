"""Tests per il client HTTP verso il backend (dashboard/api.py)."""
from __future__ import annotations

import pytest
import requests

from dashboard.api import BackendClient, BackendError
from dashboard.config import Settings


class _Resp:
    def __init__(self, status, body, headers=None):
        self.status_code, self._body, self.headers = status, body, headers or {}
        self.text = "" if body is None else str(body)
        self.reason = "reason"

    def json(self):
        if self._body is None:
            raise ValueError("no json")
        return self._body


class _Session:
    def __init__(self, resp=None, exc=None):
        self.resp, self.exc, self.calls = resp, exc, []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        if self.exc:
            raise self.exc
        return self.resp


def _client(session, key=""):
    return BackendClient(Settings("http://backend:7071", key, 5, "tester"), session=session)


def test_unwraps_envelope_and_sends_key_and_params():
    session = _Session(_Resp(200, {"data": {"total": 0, "items": []}, "error": None, "request_id": "r1"}))
    out = _client(session, key="k").list_candidates(q="rossi", has_cv=False, tutti=True, limit=25, offset=50)
    assert out == {"total": 0, "items": []}
    method, url, kwargs = session.calls[0]
    assert (method, url) == ("GET", "http://backend:7071/api/candidates")
    assert kwargs["headers"]["x-functions-key"] == "k"
    assert kwargs["params"] == {"q": "rossi", "has_cv": "false", "tutti": "true", "limit": 25, "offset": 50}


def test_no_key_header_when_key_is_empty():
    session = _Session(_Resp(200, {"data": [], "error": None}))
    _client(session).roles()
    assert "x-functions-key" not in session.calls[0][2]["headers"]


def test_match_posts_json():
    session = _Session(_Resp(200, {"data": {"esito": "nuovo"}, "error": None}))
    assert _client(session).match_candidate(nome="Mario", cognome="Rossi")["esito"] == "nuovo"
    method, url, kwargs = session.calls[0]
    assert method == "POST" and url.endswith("/api/candidates/match")
    assert kwargs["json"] == {"nome": "Mario", "cognome": "Rossi", "trittico": None}


def test_backend_error_message_and_request_id():
    session = _Session(_Resp(404, {"data": None, "error": "Candidato MCFlash 9 non trovato", "request_id": "r9"}))
    with pytest.raises(BackendError) as info:
        _client(session).get_candidate(9)
    assert "Candidato MCFlash 9 non trovato" in str(info.value)
    assert info.value.status == 404 and info.value.request_id == "r9"


def test_unauthorized_explains_function_key():
    session = _Session(_Resp(401, None))
    with pytest.raises(BackendError, match="FUNCTION_KEY"):
        _client(session).roles()


def test_connection_error_is_readable():
    session = _Session(exc=requests.ConnectionError("refused"))
    with pytest.raises(BackendError, match="func start"):
        _client(session).roles()


def test_missing_envelope_is_an_error():
    session = _Session(_Resp(200, [1, 2]))
    with pytest.raises(BackendError, match="busta"):
        _client(session).roles()
