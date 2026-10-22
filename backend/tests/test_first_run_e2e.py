"""Finish line de SP2: de un JH_HOME vacío a ofertas puntuadas usando solo la API del asistente.

Se repite con cada proveedor de IA (con dobles de red/subprocesos) y con `none`. Datos inventados.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest
import requests

sys.path.insert(0, str(Path(__file__).parent.parent))

import database  # noqa: E402
import secrets_store  # noqa: E402
from ai import cli_providers  # noqa: E402
from tests.asgi_client import call  # noqa: E402
from scraper.persist import save_scored_offer  # noqa: E402
from tests import test_setup_api as setup_api  # noqa: E402

_answers, _get, _send = setup_api._answers, setup_api._get, setup_api._send
home = setup_api.home  # fixture de JH_HOME vacío + llavero en memoria

CV_TEXT = "Ana Prueba Ejemplo. Data Engineer en Villanova. Python, SQL, Spark. Inglés B2."
DRAFT = {  # incluye todas las claves del esquema: el proveedor exige las requeridas
    "email": "", "phone": "", "years_experience": 4, "experience": [],
    "eligibility": {"work_permit_countries": [], "needs_sponsorship": None, "driving_license": None},
    "full_name": "Ana Prueba Ejemplo",
    "city": "Villanova",
    "country": "España",
    "targets": [{"title": "Data Engineer", "keywords": ["data engineer", "spark"]}],
    "tools": ["Python", "SQL"],
    "languages": [{"language": "English", "level": "B2"}],
    "modality": ["remote"],
}
KEY = "sk-e2e-NO-DEVOLVER-789"  # gitleaks:allow (clave falsa de test)
PROVIDERS = ["none", "ollama", "anthropic", "openai", "claude_cli", "codex_cli"]

MATCHING = {
    "title": "Data Engineer (Spark, Python)", "company_name": "Acme Robotics", "url": "https://example.com/jobs/1",
    "location": "Villanova", "description": "Buscamos data engineer con Spark, Python y SQL para plataforma de datos.",
}
OTHERS = [
    {"title": "Camarero de sala", "company_name": "Globex Data", "url": "https://example.com/jobs/2",
     "location": "Villanova", "description": "Atención al cliente en restaurante, turno de noche."},
    {"title": "Conductor de reparto", "company_name": "Globex Data", "url": "https://example.com/jobs/3",
     "location": "Villanova", "description": "Reparto de paquetería con furgoneta propia."},
]


class _Resp:
    status_code = 200

    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


def _install_double(provider, monkeypatch):
    """Sustituye la red/el subproceso del proveedor por una respuesta fija con el borrador JSON."""
    text = json.dumps(DRAFT)
    if provider == "ollama":
        monkeypatch.setattr(requests, "post", lambda url, **kw: _Resp({"message": {"content": text}}))
    elif provider == "anthropic":
        monkeypatch.setattr(requests, "post", lambda url, **kw: _Resp({"content": [{"type": "text", "text": text}]}))
    elif provider == "openai":
        monkeypatch.setattr(requests, "post", lambda url, **kw: _Resp({"choices": [{"message": {"content": text}}]}))
    elif provider in ("claude_cli", "codex_cli"):
        monkeypatch.setattr(cli_providers.shutil, "which", lambda name: f"/usr/bin/{name}")
        monkeypatch.setattr(
            cli_providers.subprocess, "run",
            lambda cmd, **kw: subprocess.CompletedProcess(cmd, 0, stdout=text, stderr=""),
        )


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "e2e.db")
    conn = database.get_conn()
    database.init_db(conn)
    yield conn
    conn.close()


@pytest.mark.parametrize("provider", PROVIDERS)
def test_jh_home_vacio_a_ofertas_puntuadas(provider, home, db, monkeypatch):
    # 1. JH_HOME vacío: el asistente es obligatorio.
    assert _get("/api/setup/status")[1] == {"needs_setup": True, "has_profile": False, "has_config": False}
    assert not (home / "jobhunter.yaml").exists() and not (home / "profile.json").exists()

    # 2. Proponer perfil con el proveedor elegido (clave en el llavero, sin tocar ficheros).
    ai_settings = {"provider": provider, "timeout_seconds": 30}
    if provider in ("anthropic", "openai"):
        status, _ = _send("POST", "/api/settings/ai/key", {"provider": provider, "api_key": KEY})
        assert status == 200
    _install_double(provider, monkeypatch)
    status, proposal = _send("POST", "/api/setup/propose", {"text": CV_TEXT, "ai": ai_settings})
    assert status == 200
    if provider == "none":
        assert proposal["source"] == "empty" and proposal["draft"]["targets"] == []
        draft = DRAFT  # sin IA, el usuario rellena el formulario a mano
    else:
        assert proposal["source"] == "ai"
        assert proposal["draft"]["targets"][0]["title"] == "Data Engineer"
        draft = proposal["draft"]

    # 3. Aplicar: se escriben perfil y config, y el asistente deja de pedirse.
    status, applied = _send("POST", "/api/setup/apply", _answers(draft=draft, ai=ai_settings))
    assert status == 200
    track = applied["tracks"][0]
    assert _get("/api/setup/status")[1]["needs_setup"] is False
    assert track in [t["id"] for t in _get("/api/tracks")[1]]
    assert _get("/api/profile")[1]["personal"]["city"] == "Villanova"

    # Ningún secreto en disco ni en respuestas.
    for f in (home / "jobhunter.yaml", home / "profile.json"):
        assert KEY not in f.read_text(encoding="utf-8")
    assert _get("/api/settings/ai")[1]["provider"] == provider

    # 4. Ofertas por la misma ruta que los scrapers (puntúa y clasifica).
    for offer in [MATCHING, *OTHERS]:
        save_scored_offer(db, dict(offer), "test")
    db.commit()

    status, _, body = call("GET", "/api/offers", query=f"track={track}")
    assert status == 200
    offers = json.loads(body)
    by_url = {o["url"]: o for o in offers}
    assert MATCHING["url"] in by_url
    hit = by_url[MATCHING["url"]]
    assert hit["relevance_score"] > 0 and hit["is_relevant"] and hit["cv_profile"] == track
    assert not any(o["url"] in {x["url"] for x in OTHERS} for o in offers)  # no son del track

    all_offers = {o["url"]: o for o in _get("/api/offers")[1]}
    for other in OTHERS:
        assert not all_offers[other["url"]]["is_relevant"]
        assert all_offers[other["url"]]["relevance_score"] < hit["relevance_score"]


def test_la_clave_no_se_escribe_en_disco(home):
    assert _send("POST", "/api/settings/ai/key", {"provider": "openai", "api_key": KEY})[0] == 200
    assert secrets_store.get_secret("openai_api_key") == KEY
    assert not any(KEY in p.read_text(errors="ignore") for p in home.rglob("*") if p.is_file())
