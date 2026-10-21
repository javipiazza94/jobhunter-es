"""Trabajo `inbox`: simulacro del cargador sobre lo que deja n8n; `inbox-apply`: copia de la BD y carga."""
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from inbox_job import BACKUP_PREFIX, INBOX_FILE, run_inbox  # noqa: E402
from rate_gate import RunGate  # noqa: E402

EVENTO = "2026-10-06|ACME ROBOTICS|Consultor/a SAP FICO||rejected|1a111c3e2e51b88c\n"


class FakeRunner:
    def __init__(self, returncode=0, on_call=None):
        self.calls, self.returncode, self.on_call = [], returncode, on_call

    def __call__(self, cmd, cwd=None):
        self.calls.append(cmd)
        if self.on_call:
            self.on_call()
        return subprocess.CompletedProcess(cmd, self.returncode)


@pytest.fixture
def env(tmp_path):
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    db = tmp_path / "job_hunter.db"
    db.write_bytes(b"contenido de la bd")
    return inbox, db


def backups(db):
    return sorted((db.parent / "backups").glob(BACKUP_PREFIX + "*"))


def test_sin_fichero_no_hay_nada_que_hacer(env, capsys):
    inbox, db = env
    runner = FakeRunner()
    assert run_inbox(False, inbox, db, runner) == 0
    assert "No hay eventos pendientes" in capsys.readouterr().out
    assert runner.calls == []


def test_fichero_vacio_o_solo_comentarios_tampoco(env):
    inbox, db = env
    (inbox / INBOX_FILE).write_text("# solo un comentario\n\n")
    runner = FakeRunner()
    assert run_inbox(False, inbox, db, runner) == 0
    assert runner.calls == []


def test_simulacro_no_guarda_ni_hace_copia(env, capsys):
    inbox, db = env
    (inbox / INBOX_FILE).write_text(EVENTO)
    runner = FakeRunner()
    assert run_inbox(False, inbox, db, runner) == 0
    (cmd,) = runner.calls
    assert cmd[-1].endswith(INBOX_FILE) and "--save" not in cmd
    assert backups(db) == []
    assert "1 evento" in capsys.readouterr().out


def test_aplicar_hace_la_copia_antes_de_cargar(env):
    inbox, db = env
    (inbox / INBOX_FILE).write_text(EVENTO)
    vistas = []
    runner = FakeRunner(on_call=lambda: vistas.append(backups(db)))
    assert run_inbox(True, inbox, db, runner, now=lambda: datetime(2026, 10, 7, 12, 0, 0)) == 0
    assert "--save" in runner.calls[0]
    assert len(vistas[0]) == 1, "la copia debe existir ANTES de ejecutar el cargador"
    assert vistas[0][0].name == BACKUP_PREFIX + "20261007-120000"
    assert vistas[0][0].read_bytes() == b"contenido de la bd"


def test_aplicar_conserva_solo_las_ultimas_copias_y_no_toca_otras(env):
    inbox, db = env
    (inbox / INBOX_FILE).write_text(EVENTO)
    for i in range(12):
        (db.parent / "backups").mkdir(exist_ok=True)
        (db.parent / "backups" / f"{BACKUP_PREFIX}2026010{i % 10}-0000{i:02d}").write_bytes(b"x")
    otra = db.parent / "job_hunter.db.bak3"
    otra.write_bytes(b"a mano")
    run_inbox(True, inbox, db, FakeRunner(), keep=10, now=lambda: datetime(2026, 10, 7, 12, 0, 0))
    assert len(backups(db)) == 10
    assert backups(db)[-1].name == BACKUP_PREFIX + "20261007-120000"
    assert otra.exists()


def test_si_el_cargador_falla_se_propaga_el_codigo_y_se_conserva_la_copia(env):
    inbox, db = env
    (inbox / INBOX_FILE).write_text(EVENTO)
    assert run_inbox(True, inbox, db, FakeRunner(returncode=2)) == 2
    assert len(backups(db)) == 1


def test_aplicar_sin_bd_falla_sin_ejecutar_el_cargador(env, capsys):
    inbox, db = env
    db.unlink()
    (inbox / INBOX_FILE).write_text(EVENTO)
    runner = FakeRunner()
    assert run_inbox(True, inbox, db, runner) == 1
    assert runner.calls == []


def test_la_espera_puede_desactivarse_por_fuente():
    t = [1000.0]
    gate = RunGate(300, lambda: t[0], overrides={"inbox": 0})
    gate.acquire("inbox")
    gate.release("inbox")
    gate.acquire("inbox")  # sin espera: el simulacro es local y barato
    gate.acquire("manfred")
    gate.release("manfred")
    with pytest.raises(Exception):
        gate.acquire("manfred")  # el resto conserva su espera
