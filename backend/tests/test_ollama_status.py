"""Detección de Ollama (ollama_status.py) y su ruta /api/ai/ollama. Sin red: la petición HTTP va simulada."""
import json
import sys
from pathlib import Path

import pytest
import requests

sys.path.insert(0, str(Path(__file__).parent.parent))

import ollama_status as om  # noqa: E402
from tests.asgi_client import call  # noqa: E402


class Resp:
    def __init__(self, payload, status=200):
        self._payload, self.status = payload, status

    def raise_for_status(self):
        if self.status >= 400:
            raise requests.HTTPError(str(self.status))

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


@pytest.fixture(autouse=True)
def sin_ollama_en_disco(monkeypatch):
    monkeypatch.setattr(om.shutil, "which", lambda name: None)
    monkeypatch.setattr(om, "_known_locations", lambda: [])


def test_en_marcha_lista_los_modelos():
    urls = []

    def get(url, timeout):
        urls.append(url)
        return Resp({"models": [{"name": "llama3.1:8b"}, {"name": "qwen2.5"}, {"sin": "nombre"}]})

    st = om.ollama_status(http_get=get)
    assert (st.installed, st.running, st.models) == (True, True, ["llama3.1:8b", "qwen2.5"])
    assert urls == ["http://127.0.0.1:11434/api/tags"] and st.install_url == "https://ollama.com/download"


def test_instalado_pero_apagado(monkeypatch):
    monkeypatch.setattr(om.shutil, "which", lambda name: "/usr/local/bin/ollama")

    def get(url, timeout):
        raise requests.ConnectionError("rechazada")

    st = om.ollama_status(http_get=get)
    assert (st.installed, st.running, st.models) == (True, False, [])


def test_no_instalado():
    def get(url, timeout):
        raise requests.ConnectionError("rechazada")

    st = om.ollama_status(http_get=get)
    assert (st.installed, st.running) == (False, False)


def test_ruta_conocida_cuenta_como_instalado(monkeypatch, tmp_path):
    exe = tmp_path / "ollama.exe"
    exe.write_text("")
    monkeypatch.setattr(om, "_known_locations", lambda: [exe])
    st = om.ollama_status(http_get=lambda url, timeout: (_ for _ in ()).throw(requests.Timeout()))
    assert st.installed and not st.running


@pytest.mark.parametrize("respuesta", [Resp({}, 500), Resp(ValueError("no es json")), Resp([1, 2]), Resp({"models": 7})])
def test_respuestas_raras_nunca_lanzan(respuesta):
    st = om.ollama_status(http_get=lambda url, timeout: respuesta)
    assert st.models == []


def test_la_url_personalizada_se_respeta():
    urls = []
    om.ollama_status("http://127.0.0.1:9999/", http_get=lambda url, timeout: urls.append(url) or Resp({"models": []}))
    assert urls == ["http://127.0.0.1:9999/api/tags"]


def test_la_ruta_responde_sin_parametros_de_url(monkeypatch):
    import main

    visto = []
    monkeypatch.setattr(main, "ollama_status", lambda base=None: visto.append(base) or om.OllamaStatus(
        installed=False, running=False, models=[], install_url=om.INSTALL_URL))
    status, _, body = call("GET", "/api/ai/ollama", query="base_url=http://169.254.169.254")
    assert status == 200 and json.loads(body)["installed"] is False
    assert visto and visto[0] != "http://169.254.169.254"  # la petición no puede dirigir la consulta (SSRF)
