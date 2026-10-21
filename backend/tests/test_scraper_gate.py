"""Límite de uso y estado de los trabajos de POST /api/scraper/run: una fuente no puede lanzarse dos veces a la vez
ni repetirse antes de un tiempo de espera (machacar los portales desde tu IP, que te bloqueen
y apilar procesos de Playwright)."""
import sys
import threading
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import main  # noqa: E402
from rate_gate import GateRejected, RunGate  # noqa: E402
from tests.asgi_client import call  # noqa: E402

CLIENT = ("x-jh-client", "dashboard")


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


@pytest.fixture
def clock():
    return FakeClock()


# ── RunGate ──────────────────────────────────────────────────────────────────────────────

def test_concede_la_primera_vez(clock):
    RunGate(300, clock).acquire("indeed")


def test_rechaza_con_409_mientras_se_ejecuta(clock):
    gate = RunGate(300, clock)
    gate.acquire("indeed")
    with pytest.raises(GateRejected) as e:
        gate.acquire("indeed")
    assert e.value.status == 409 and "indeed" in e.value.detail


def test_rechaza_con_429_y_retry_after_dentro_de_la_espera(clock):
    gate = RunGate(300, clock)
    gate.acquire("indeed")
    gate.release("indeed")
    clock.now += 100
    with pytest.raises(GateRejected) as e:
        gate.acquire("indeed")
    assert e.value.status == 429 and e.value.retry_after == 200


def test_la_espera_se_cuenta_desde_que_termina_no_desde_que_empieza(clock):
    gate = RunGate(300, clock)
    gate.acquire("indeed")
    clock.now += 900  # la ejecución dura más que la espera
    gate.release("indeed")
    with pytest.raises(GateRejected) as e:
        gate.acquire("indeed")
    assert e.value.status == 429 and e.value.retry_after == 300


def test_vuelve_a_conceder_pasada_la_espera(clock):
    gate = RunGate(300, clock)
    gate.acquire("indeed")
    gate.release("indeed")
    clock.now += 300
    gate.acquire("indeed")


def test_las_fuentes_son_independientes(clock):
    gate = RunGate(300, clock)
    gate.acquire("indeed")
    gate.acquire("manfred")


def test_espera_cero_desactiva_solo_la_espera(clock):
    gate = RunGate(0, clock)
    gate.acquire("indeed")
    with pytest.raises(GateRejected):
        gate.acquire("indeed")  # sigue sin permitir dos a la vez
    gate.release("indeed")
    gate.acquire("indeed")


def test_cancelar_libera_el_turno_sin_empezar_la_espera(clock):
    gate = RunGate(300, clock)
    gate.acquire("indeed")
    gate.cancel("indeed")
    gate.acquire("indeed")  # no hay 409 ni 429


def test_liberar_lo_que_no_se_adquirio_no_falla(clock):
    RunGate(300, clock).release("nunca")


def test_solo_uno_gana_con_hilos_simultaneos(clock):
    gate = RunGate(300, clock)
    ganadores, barrera = [], threading.Barrier(20)

    def intentar():
        barrera.wait()
        try:
            gate.acquire("indeed")
            ganadores.append(1)
        except GateRejected:
            pass

    hilos = [threading.Thread(target=intentar) for _ in range(20)]
    [h.start() for h in hilos]
    [h.join() for h in hilos]
    assert len(ganadores) == 1


# ── Endpoints (trabajos en procesos reales y muy ligeros) ──────────────────────────────────

import json  # noqa: E402
import subprocess  # noqa: E402

from job_manager import JobManager  # noqa: E402


def _launcher(code, lanzadas):
    def lanzar(source, log):
        lanzadas.append(source)
        return subprocess.Popen([sys.executable, "-c", code], stdout=log, stderr=subprocess.STDOUT)
    return lanzar


@pytest.fixture
def api(clock, monkeypatch, tmp_path):
    lanzadas = []
    gate = RunGate(300, clock)
    monkeypatch.setattr(main, "_scraper_gate", gate)
    monkeypatch.setattr(main, "_jobs", JobManager(gate, launcher=_launcher("print('trabajo hecho')", lanzadas), log_dir=tmp_path))
    return lanzadas


def lanzar(source):
    return call("POST", "/api/scraper/run", headers=[CLIENT], query=f"source={source}")


def terminar(job_id):
    assert main._jobs.get(job_id).done.wait(10)


def test_primera_peticion_arranca_y_devuelve_el_id_del_trabajo(api):
    status, _, body = lanzar("manfred")
    datos = json.loads(body)
    assert status == 200 and datos["status"] == "started" and datos["job_id"]
    assert api == ["manfred"]
    terminar(datos["job_id"])


def test_repetir_enseguida_devuelve_429_con_retry_after_y_no_lanza_nada(api, clock):
    terminar(json.loads(lanzar("manfred")[2])["job_id"])
    clock.now += 60
    status, headers, body = lanzar("manfred")
    assert status == 429
    assert headers["retry-after"] == "240" and "240" in body
    assert api == ["manfred"]


def test_otra_fuente_si_se_puede_lanzar(api):
    a = json.loads(lanzar("manfred")[2])["job_id"]
    b = json.loads(lanzar("tecnoempleo")[2])["job_id"]
    terminar(a), terminar(b)
    assert sorted(api) == ["manfred", "tecnoempleo"]


def test_pasada_la_espera_se_puede_repetir(api, clock):
    terminar(json.loads(lanzar("manfred")[2])["job_id"])
    clock.now += 300
    status, _, body = lanzar("manfred")
    assert status == 200
    terminar(json.loads(body)["job_id"])
    assert api == ["manfred", "manfred"]


def test_mientras_corre_devuelve_409(api):
    main._scraper_gate.acquire("indeed")  # simula una ejecución en curso
    status, _, body = lanzar("indeed")
    assert status == 409 and "ya se está ejecutando" in body


def test_una_fuente_desconocida_da_400_y_no_consume_el_turno(api):
    assert lanzar("bogus")[0] == 400
    assert lanzar("bogus")[0] == 400  # no se queda en 429
    assert api == []


def test_estado_y_log_de_un_trabajo(api):
    job_id = json.loads(lanzar("manfred")[2])["job_id"]
    terminar(job_id)
    lista = json.loads(call("GET", "/api/jobs")[2])
    assert [j["id"] for j in lista] == [job_id] and lista[0]["status"] == "succeeded"
    status, _, body = call("GET", f"/api/jobs/{job_id}")
    detalle = json.loads(body)
    assert status == 200 and detalle["returncode"] == 0 and "trabajo hecho" in detalle["log_tail"]


def test_un_trabajo_inexistente_da_404(api):
    assert call("GET", "/api/jobs/no-existe")[0] == 404


def test_si_el_proceso_falla_queda_registrado_y_libera_el_turno(clock, monkeypatch, tmp_path):
    gate = RunGate(300, clock)
    monkeypatch.setattr(main, "_scraper_gate", gate)
    monkeypatch.setattr(main, "_jobs", JobManager(gate, launcher=_launcher("import sys; print('caída'); sys.exit(2)", []), log_dir=tmp_path))
    job_id = json.loads(lanzar("manfred")[2])["job_id"]
    terminar(job_id)
    assert json.loads(call("GET", f"/api/jobs/{job_id}")[2])["status"] == "failed"
    clock.now += 300
    assert lanzar("manfred")[0] == 200  # no se queda en 409
    terminar(json.loads(call("GET", "/api/jobs")[2])[0]["id"])
