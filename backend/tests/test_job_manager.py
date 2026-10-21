"""JobManager: los trabajos pesados corren en un proceso aparte, con estado, log y tiempo límite."""
import subprocess
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from job_manager import JobManager  # noqa: E402
from rate_gate import GateRejected, RunGate  # noqa: E402


def launcher(code: str):
    return lambda source, log: subprocess.Popen([sys.executable, "-c", code], stdout=log, stderr=subprocess.STDOUT)


class FakeClock:
    now = 1000.0

    def __call__(self):
        return self.now


@pytest.fixture
def clock():
    return FakeClock()


def manager(tmp_path, clock, code="print('hola')", timeout=30, max_history=50):
    return JobManager(RunGate(300, clock), launcher=launcher(code), log_dir=tmp_path, timeout=timeout, max_history=max_history)


def test_un_trabajo_que_termina_bien(tmp_path, clock):
    m = manager(tmp_path, clock, "print('hola desde el trabajo')")
    job = m.start("manfred")
    assert job.status == "running"
    assert job.done.wait(10)
    assert (job.status, job.returncode) == ("succeeded", 0)
    assert job.finished_at
    assert "hola desde el trabajo" in m.tail(job)


def test_un_trabajo_que_falla_guarda_el_codigo_y_el_error(tmp_path, clock):
    m = manager(tmp_path, clock, "import sys; print('boom'); sys.exit(3)")
    job = m.start("manfred")
    assert job.done.wait(10)
    assert (job.status, job.returncode) == ("failed", 3)
    assert "boom" in m.tail(job)


def test_un_trabajo_colgado_se_mata_por_tiempo_limite(tmp_path, clock):
    m = manager(tmp_path, clock, "import time; time.sleep(60)", timeout=0.5)
    inicio = time.monotonic()
    job = m.start("manfred")
    assert job.done.wait(10)
    assert job.status == "timeout"
    assert time.monotonic() - inicio < 10  # no esperó al sleep(60)


def test_no_se_lanza_la_misma_fuente_dos_veces_a_la_vez(tmp_path, clock):
    m = manager(tmp_path, clock, "import time; time.sleep(1.5)")
    job = m.start("manfred")
    with pytest.raises(GateRejected) as e:
        m.start("manfred")
    assert e.value.status == 409
    assert job.done.wait(10)


def test_otra_fuente_si_se_puede_lanzar_a_la_vez(tmp_path, clock):
    m = manager(tmp_path, clock, "import time; time.sleep(1)")
    a, b = m.start("manfred"), m.start("indeed")
    assert a.done.wait(10) and b.done.wait(10)


def test_tras_terminar_hay_que_esperar_la_espera(tmp_path, clock):
    m = manager(tmp_path, clock)
    job = m.start("manfred")
    assert job.done.wait(10)
    with pytest.raises(GateRejected) as e:
        m.start("manfred")
    assert e.value.status == 429
    clock.now += 300
    assert m.start("manfred").done.wait(10)


def test_si_no_se_puede_lanzar_el_proceso_se_libera_el_turno(tmp_path, clock):
    def no_arranca(source, log):
        raise OSError("sin permisos")

    m = JobManager(RunGate(300, clock), launcher=no_arranca, log_dir=tmp_path)
    with pytest.raises(OSError):
        m.start("manfred")
    m2 = JobManager(m._gate, launcher=launcher("pass"), log_dir=tmp_path)
    assert m2.start("manfred").done.wait(10)  # no se quedó bloqueado en 409


def test_listado_mas_reciente_primero_y_limite_de_historial(tmp_path, clock):
    m = manager(tmp_path, clock, max_history=2)
    jobs = [m.start(s) for s in ("a", "b", "c")]
    assert all(j.done.wait(10) for j in jobs)
    assert [j.source for j in m.list()] == ["c", "b"]
    assert m.get(jobs[0].id) is None  # el más antiguo se descartó
    assert m.get("no-existe") is None
