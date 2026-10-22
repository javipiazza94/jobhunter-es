"""Arranque de escritorio (desktop_main.py): entorno, puerto libre, vigilancia de la app y protecciones de la API.

Las protecciones se comprueban en un proceso aparte con el entorno de escritorio, porque `main` lee
CORS_ORIGINS y ALLOWED_HOSTS al importarse.
"""
import io
import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

BACKEND = Path(__file__).parent.parent
sys.path.insert(0, str(BACKEND))

import desktop_main  # noqa: E402


@pytest.fixture
def fake_home(tmp_path, monkeypatch):
    monkeypatch.setattr(desktop_main, "default_home", lambda: tmp_path / "sistema" / "jobhunter")
    return tmp_path / "sistema" / "jobhunter"


# ── Entorno ──────────────────────────────────────────────────────────────────────────

def test_sin_jh_home_usa_la_carpeta_de_datos_del_sistema(fake_home):
    env = {"PATH": "/usr/bin"}
    desktop_main.prepare_environment(env)
    assert env["JH_HOME"] == str(fake_home)
    assert env["PLAYWRIGHT_BROWSERS_PATH"] == str(fake_home / "browsers")
    assert env["JH_DESKTOP"] == "1"


def test_respeta_un_jh_home_y_un_directorio_de_navegadores_ya_definidos(fake_home, tmp_path):
    env = {"JH_HOME": str(tmp_path / "mis_datos"), "PLAYWRIGHT_BROWSERS_PATH": str(tmp_path / "nav")}
    desktop_main.prepare_environment(env)
    assert env["JH_HOME"] == str(tmp_path / "mis_datos")
    assert env["PLAYWRIGHT_BROWSERS_PATH"] == str(tmp_path / "nav")


def test_cors_y_hosts_son_los_de_tauri_aunque_el_entorno_diga_otra_cosa(fake_home):
    env = {"CORS_ORIGINS": "http://evil.example", "ALLOWED_HOSTS": "evil.example"}
    desktop_main.prepare_environment(env)
    assert env["CORS_ORIGINS"].split(",") == ["tauri://localhost", "http://tauri.localhost", "https://tauri.localhost"]
    assert env["ALLOWED_HOSTS"] == "localhost,127.0.0.1"


def test_origenes_extra_solo_si_se_piden_expresamente(fake_home):
    env = {"JH_DESKTOP_EXTRA_ORIGINS": " http://localhost:3010 , "}
    desktop_main.prepare_environment(env)
    assert env["CORS_ORIGINS"].split(",")[-1] == "http://localhost:3010"
    assert "" not in env["CORS_ORIGINS"].split(",")


def test_los_binarios_incluidos_van_delante_en_el_path(fake_home, tmp_path):
    env = {"PATH": "/usr/bin", "JH_BUNDLED_BIN": str(tmp_path / "bin")}
    desktop_main.prepare_environment(env)
    assert env["PATH"] == str(tmp_path / "bin") + os.pathsep + "/usr/bin"


def test_sin_binarios_incluidos_el_path_no_cambia(fake_home):
    env = {"PATH": "/usr/bin"}
    desktop_main.prepare_environment(env)
    assert env["PATH"] == "/usr/bin"


def test_default_home_termina_en_jobhunter():
    assert desktop_main.default_home().name == "jobhunter"


# ── Puerto ──────────────────────────────────────────────────────────────────────────

def test_el_puerto_se_abre_en_loopback_y_lo_asigna_el_sistema():
    sock = desktop_main.open_listener()
    try:
        host, port = sock.getsockname()
        assert host == "127.0.0.1" and port > 0
    finally:
        sock.close()


def test_dos_arranques_no_comparten_puerto():
    a, b = desktop_main.open_listener(), desktop_main.open_listener()
    try:
        assert a.getsockname()[1] != b.getsockname()[1]
    finally:
        a.close()
        b.close()


def test_announce_ready_imprime_una_linea_que_la_app_sabe_leer():
    out = io.StringIO()
    desktop_main.announce_ready(54321, out)
    assert out.getvalue() == "JH_READY port=54321\n"
    assert out.getvalue().startswith(desktop_main.READY_PREFIX)


# ── Vigilancia de la app ─────────────────────────────────────────────────────────────

def test_el_cierre_de_stdin_dispara_la_parada():
    called = []
    desktop_main.watch_stdin(io.BytesIO(b"datos que se descartan"), lambda: called.append(1)).join(5)
    assert called == [1]


def test_un_stdin_roto_tambien_dispara_la_parada():
    class Roto:
        def read(self, n):
            raise OSError("pipe cerrada")

    called = []
    desktop_main.watch_stdin(Roto(), lambda: called.append(1)).join(5)
    assert called == [1]


# ── `-m` como python -m ───────────────────────────────────────────────────────────────

def test_dash_m_ejecuta_un_modulo_con_sus_argumentos(tmp_path, monkeypatch, fake_home):
    salida = tmp_path / "salida.json"
    (tmp_path / "jh_modulo_de_prueba.py").write_text(
        "import json, sys\n"
        f"open({str(salida)!r}, 'w').write(json.dumps([__name__, sys.argv]))\n",
        encoding="utf-8",
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.setattr(sys, "argv", list(sys.argv))
    assert desktop_main.main(["-m", "jh_modulo_de_prueba", "tecnoempleo", "--x"]) == 0
    nombre, argv = json.loads(salida.read_text())
    assert nombre == "__main__" and argv[1:] == ["tecnoempleo", "--x"]  # argv[0] es la ruta, como en python -m


# ── config congelado ───────────────────────────────────────────────────────────────────

def _python(code: str, env_extra: dict[str, str], tmp_path: Path) -> str:
    env = {k: v for k, v in os.environ.items() if not k.startswith("JH_")}
    env.update(env_extra)
    env["JH_HOME"] = str(tmp_path / "home")
    env["PYTHONPATH"] = str(BACKEND)
    res = subprocess.run([sys.executable, "-c", textwrap.dedent(code)], capture_output=True, text=True,
                         env=env, cwd=tmp_path, timeout=120)
    assert res.returncode == 0, res.stderr
    return res.stdout.strip()


def test_congelado_la_raiz_de_recursos_es_la_carpeta_del_codigo(tmp_path):
    out = _python("import sys; sys.frozen = True; import config; "
                  "print(config.REPO_ROOT == config.BASE_DIR)", {}, tmp_path)
    assert out == "True"


def test_en_el_repositorio_la_raiz_sigue_siendo_la_carpeta_superior(tmp_path):
    out = _python("import config; print(config.REPO_ROOT == config.BASE_DIR.parent)", {}, tmp_path)
    assert out == "True"


# ── Protecciones de la API con puerto dinámico y origen de Tauri ───────────────────────

PROTECTIONS_SCRIPT = """
    import json, os
    import desktop_main
    desktop_main.prepare_environment(os.environ)
    import config; config.ensure_data_dirs()  # lo que hace el lifespan al arrancar
    import database
    conn = database.get_conn(); database.init_db(conn); conn.close()
    from tests.asgi_client import call

    host = "127.0.0.1:53211"
    tauri = ("origin", "tauri://localhost")
    client = ("x-jh-client", "dashboard")
    out = {}
    s, h, _ = call("GET", "/api/stats", headers=[tauri], host=host)
    out["get_tauri"] = [s, h.get("access-control-allow-origin")]
    s, h, _ = call("GET", "/api/stats", headers=[("origin", "http://tauri.localhost")], host=host)
    out["get_tauri_windows"] = [s, h.get("access-control-allow-origin")]
    s, _, _ = call("GET", "/api/stats", headers=[tauri], host="evil.example:53211")
    out["host_ajeno"] = s
    s, _, _ = call("GET", "/api/stats", headers=[tauri], host="192.168.1.20:53211")
    out["host_lan"] = s
    s, h, _ = call("GET", "/api/stats", headers=[("origin", "http://evil.example")], host=host)
    out["origen_ajeno"] = [s, h.get("access-control-allow-origin")]
    s, h, _ = call("GET", "/api/stats", headers=[("origin", "http://localhost:3010")], host=host)
    out["origen_dev_web"] = h.get("access-control-allow-origin")
    s, _, _ = call("POST", "/api/scraper/run", headers=[tauri], host=host)
    out["post_sin_cabecera"] = s
    s, h, _ = call("OPTIONS", "/api/applications/x", host=host, headers=[
        tauri, ("access-control-request-method", "DELETE"), ("access-control-request-headers", "x-jh-client")])
    out["preflight_tauri"] = [s, h.get("access-control-allow-origin")]
    s, h, _ = call("OPTIONS", "/api/applications/x", host=host, headers=[
        ("origin", "http://evil.example"), ("access-control-request-method", "DELETE")])
    out["preflight_ajeno"] = [s, h.get("access-control-allow-origin")]
    print(json.dumps(out))
"""


@pytest.fixture(scope="module")
def protections(tmp_path_factory):
    out = _python(PROTECTIONS_SCRIPT, {}, tmp_path_factory.mktemp("proteccion"))
    return json.loads(out.splitlines()[-1])


def test_el_dashboard_de_tauri_puede_leer_la_api_en_cualquier_puerto(protections):
    assert protections["get_tauri"] == [200, "tauri://localhost"]
    assert protections["get_tauri_windows"] == [200, "http://tauri.localhost"]


def test_un_host_ajeno_sigue_rechazado_aunque_el_puerto_cambie(protections):
    assert protections["host_ajeno"] == 400
    assert protections["host_lan"] == 400


def test_un_origen_ajeno_no_recibe_permiso_cors(protections):
    assert protections["origen_ajeno"][1] is None
    assert protections["origen_dev_web"] is None
    assert protections["preflight_ajeno"][1] is None


def test_los_metodos_que_modifican_siguen_exigiendo_la_cabecera_propia(protections):
    assert protections["post_sin_cabecera"] == 403


def test_el_preflight_de_tauri_se_acepta(protections):
    assert protections["preflight_tauri"] == [200, "tauri://localhost"]


# ── Arranque real: puerto, línea de aviso y parada al cerrar stdin ───────────────────────────

def test_arranque_real_anuncia_el_puerto_responde_y_se_para_al_cerrar_stdin(tmp_path):
    import urllib.request

    env = {k: v for k, v in os.environ.items() if not k.startswith("JH_")}
    env.update(JH_HOME=str(tmp_path / "home"), JH_PARENT_WATCH="1", JH_INBOX_POLL_SECONDS="0")
    proc = subprocess.Popen([sys.executable, str(BACKEND / "desktop_main.py")], cwd=tmp_path, env=env,
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    try:
        line = proc.stdout.readline().strip()
        assert line.startswith(desktop_main.READY_PREFIX), line
        port = int(line.removeprefix(desktop_main.READY_PREFIX))
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/stats", timeout=20) as res:
            assert res.status == 200
        proc.stdin.close()  # la app «ha muerto»
        assert proc.wait(timeout=30) == 0
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()
