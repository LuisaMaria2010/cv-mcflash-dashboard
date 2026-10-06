"""Configurazione della dashboard: indirizzo e chiave del backend.

Ordine di lettura: variabili d'ambiente (anche da .env), poi i secrets di
Streamlit (.streamlit/secrets.toml in locale, oppure i secrets dell'app se la
dashboard viene pubblicata su un hosting gratuito come Streamlit Community Cloud).
"""
from __future__ import annotations

import getpass
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

DEFAULT_BACKEND_URL = "http://localhost:7071"


def _secret(name: str) -> str | None:
    try:
        import streamlit as st

        value = st.secrets.get(name)
    except Exception:  # nessun secrets.toml, oppure fuori da Streamlit
        return None
    return None if value is None else str(value)


def _value(name: str, default: str = "") -> str:
    value = os.getenv(name)
    if value is None or not value.strip():
        value = _secret(name)
    return (value if value is not None else default).strip()


def _login_name() -> str:
    try:
        return getpass.getuser()
    except Exception:
        return ""


@dataclass(frozen=True)
class Settings:
    backend_url: str
    function_key: str
    timeout_seconds: float
    user: str


def load_settings() -> Settings:
    try:
        timeout = float(_value("BACKEND_TIMEOUT_SECONDS", "30"))
    except ValueError:
        timeout = 30.0
    return Settings(
        backend_url=_value("BACKEND_URL", DEFAULT_BACKEND_URL).rstrip("/"),
        function_key=_value("FUNCTION_KEY"),
        timeout_seconds=timeout,
        user=_value("DASHBOARD_USER") or _login_name(),
    )
