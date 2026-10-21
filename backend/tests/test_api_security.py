"""ADR-001: la API local no tiene login, así que se protege con tres capas.

1. Solo atiende peticiones cuyo Host sea el propio equipo (frena el DNS rebinding).
2. POST/PUT/PATCH/DELETE exigen la cabecera X-JH-Client: al no ser una cabecera «simple»,
   el navegador hace preflight y CORS lo rechaza para webs ajenas (frena el CSRF).
3. Se enlaza solo a 127.0.0.1 (comprobado sobre el código, no sobre un socket).
"""
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import database  # noqa: E402
import main  # noqa: E402
from tests.asgi_client import call  # noqa: E402

ALLOWED_ORIGIN = "http://localhost:3010"
EVIL_ORIGIN = "http://evil.example"
CLIENT = ("x-jh-client", "dashboard")


@pytest.fixture(autouse=True)
def tmp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "t.db")
    conn = database.get_conn()
    database.init_db(conn)
    conn.close()


# ── Capa 2: cabecera obligatoria en métodos que modifican ───────────────────────────────

@pytest.mark.parametrize("method, path", [
    ("POST", "/api/scraper/run"),
    ("POST", "/api/applications/run"),
    ("POST", "/api/applications/create-drafts"),
    ("POST", "/api/applications/x/approve"),
    ("PATCH", "/api/applications/x/status"),
    ("DELETE", "/api/offers/x/mark-sent"),
])
def test_los_metodos_que_modifican_exigen_la_cabecera(method, path):
    status, _, body = call(method, path)
    assert status == 403
    assert "X-JH-Client" in body


def test_post_con_la_cabecera_llega_al_handler():
    # Fuente inexistente: el 400 lo da el handler, así que la petición pasó el middleware.
    status, _, body = call("POST", "/api/scraper/run", headers=[CLIENT], query="source=bogus")
    assert status == 400 and "Unknown source" in body


def test_una_cabecera_con_otro_valor_no_vale():
    assert call("POST", "/api/scraper/run", headers=[("x-jh-client", "otra-cosa")])[0] == 403


def test_get_no_necesita_la_cabecera():
    assert call("GET", "/api/stats")[0] == 200


# ── Capa 1: Host de confianza ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("host", ["localhost:8020", "127.0.0.1:8020", "localhost"])
def test_hosts_propios_permitidos(host):
    assert call("GET", "/api/stats", host=host)[0] == 200


@pytest.mark.parametrize("host", ["evil.example", "evil.example:8020", "192.168.1.61:8020"])
def test_hosts_ajenos_rechazados(host):
    assert call("GET", "/api/stats", host=host)[0] == 400


# ── CORS: el dashboard sigue funcionando, las webs ajenas no ────────────────────────────

def test_preflight_del_dashboard_permite_la_cabecera_propia():
    status, h, _ = call("OPTIONS", "/api/offers/x/mark-sent", headers=[
        ("origin", ALLOWED_ORIGIN), ("access-control-request-method", "DELETE"),
        ("access-control-request-headers", "x-jh-client"),
    ])
    assert status == 200
    assert h["access-control-allow-origin"] == ALLOWED_ORIGIN
    assert "x-jh-client" in h["access-control-allow-headers"].lower() or h["access-control-allow-headers"] == "*"


def test_preflight_de_una_web_ajena_se_rechaza():
    status, h, _ = call("OPTIONS", "/api/offers/x/mark-sent", headers=[
        ("origin", EVIL_ORIGIN), ("access-control-request-method", "DELETE"),
        ("access-control-request-headers", "x-jh-client"),
    ])
    assert status == 400
    assert "access-control-allow-origin" not in h


def test_cada_origen_de_loopback_incluye_a_su_gemelo():
    import config
    assert config._with_loopback_twins(["http://localhost:3010"]) == ["http://localhost:3010", "http://127.0.0.1:3010"]
    assert config._with_loopback_twins(["http://127.0.0.1:3000"]) == ["http://127.0.0.1:3000", "http://localhost:3000"]
    assert config._with_loopback_twins([" https://mi.dominio.dev ", ""]) == ["https://mi.dominio.dev"]  # lo ajeno no se toca


@pytest.mark.parametrize("origin", ["http://localhost:3010", "http://127.0.0.1:3010"])
def test_el_dashboard_funciona_abierto_por_localhost_o_por_la_ip(origin):
    # Abrir http://127.0.0.1:3010 dejaba el dashboard vacío: la API solo permitía «localhost».
    status, h, _ = call("GET", "/api/stats", headers=[("origin", origin)])
    assert status == 200 and h["access-control-allow-origin"] == origin
    status, h, _ = call("OPTIONS", "/api/offers/x/mark-sent", headers=[
        ("origin", origin), ("access-control-request-method", "DELETE"),
        ("access-control-request-headers", "x-jh-client"),
    ])
    assert status == 200 and h["access-control-allow-origin"] == origin


def test_el_403_lleva_cabeceras_cors_para_que_el_dashboard_lea_el_error():
    _, h, _ = call("POST", "/api/scraper/run", headers=[("origin", ALLOWED_ORIGIN)])
    assert h.get("access-control-allow-origin") == ALLOWED_ORIGIN


# ── Capa 3: solo loopback ───────────────────────────────────────────────────────────────

def test_el_arranque_directo_escucha_solo_en_loopback():
    src = (Path(__file__).parent.parent / "main.py").read_text(encoding="utf-8")
    assert "0.0.0.0" not in src
    assert re.search(r'host="127\.0\.0\.1"', src)
