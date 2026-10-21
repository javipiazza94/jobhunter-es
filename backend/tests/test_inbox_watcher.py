"""Vigilante del inbox: carga solo lo que Cowork o n8n dejan en backend/inbox/, con copia previa de la BD,
sin reprocesar ficheros que no han cambiado y sin tocar ficheros que aún se están escribiendo."""
import os
import sqlite3
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from inbox_watcher import BACKUP_PREFIX, InboxWatcher  # noqa: E402

SALIDA_APPS = """
== nuevas: 2
  - ACME | Consultor SAP (sent)
  - Foo | Dev (sent)

== actualizadas: 1
  - Bar | PM: sent → interview

== sin_cambio: 4

== dudosas: 1
  - Baz | Algo: parecida a otra → no creo ni toco

== invalidas: 0

== Por revisar: 1
  - Sin confirmar | Camarero (sent)

GUARDADO en job_hunter.db
"""
SALIDA_OFERTAS = "{'sap': 3, 'ia': 1} -> a cargar: 4\nguardadas=4 omitidas=0\n"


class FakeRunner:
    def __init__(self, outputs=None, returncode=0, on_call=None):
        self.calls, self.outputs, self.returncode, self.on_call = [], outputs or {}, returncode, on_call

    def __call__(self, cmd, cwd=None, capture_output=True, text=True, timeout=None):
        self.calls.append(cmd)
        if self.on_call:
            self.on_call(cmd)
        script = Path(cmd[1]).name
        return subprocess.CompletedProcess(cmd, self.returncode, stdout=self.outputs.get(script, ""), stderr="")


@pytest.fixture
def env(tmp_path):
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    db = tmp_path / "job_hunter.db"
    c = sqlite3.connect(db)
    c.execute("CREATE TABLE t (x)")
    c.execute("INSERT INTO t VALUES (1)")
    c.commit()
    c.close()
    return inbox, db


def watcher(env, runner, **kw):
    inbox, db = env
    return InboxWatcher(inbox, db, runner=runner, settle_seconds=0, now=lambda: datetime(2026, 10, 7, 12, 0, 0), **kw)


def deja(inbox, name, text="2026-10-06|ACME|SAP||sent|abc\n"):
    f = inbox / name
    f.write_text(text, encoding="utf-8")
    return f


def backups(db):
    return sorted((db.parent / "backups").glob(BACKUP_PREFIX + "*"))


def test_sin_ficheros_no_hace_nada_ni_copia_la_bd(env):
    runner = FakeRunner()
    assert watcher(env, runner).run_once() is None
    assert runner.calls == [] and backups(env[1]) == []


def test_carga_candidaturas_con_copia_previa_y_saca_el_informe(env):
    inbox, db = env
    deja(inbox, "candidaturas_cowork.txt")
    runner = FakeRunner({"load_inbox_applications.py": SALIDA_APPS})
    informe = watcher(env, runner).run_once()
    assert len(runner.calls) == 1 and "--save" in runner.calls[0]
    assert Path(runner.calls[0][1]).name == "load_inbox_applications.py"
    assert len(backups(db)) == 1
    # la copia es una BD de SQLite válida con los datos
    assert sqlite3.connect(backups(db)[0]).execute("SELECT x FROM t").fetchone() == (1,)
    assert (informe["new"], informe["updated"], informe["doubtful"], informe["to_review"]) == (2, 1, 1, 1)
    assert informe["files"] == ["candidaturas_cowork.txt"] and informe["error"] is False


def test_las_ofertas_usan_su_propio_cargador(env):
    inbox, _ = env
    deja(inbox, "ofertas_20261007.txt", "sap|Consultor SAP|ACME|Villanova|http://x|2026-10-07|indef|\n")
    runner = FakeRunner({"load_inbox_offers.py": SALIDA_OFERTAS})
    informe = watcher(env, runner).run_once()
    assert Path(runner.calls[0][1]).name == "load_inbox_offers.py"
    assert informe["new"] == 4


def test_candidaturas_y_ofertas_a_la_vez_hacen_una_sola_copia(env):
    inbox, db = env
    deja(inbox, "candidaturas_a.txt")
    deja(inbox, "ofertas_a.txt", "sap|x|y|z|u|2026-10-07||\n")
    runner = FakeRunner({"load_inbox_applications.py": SALIDA_APPS, "load_inbox_offers.py": SALIDA_OFERTAS})
    informe = watcher(env, runner).run_once()
    assert len(runner.calls) == 2 and len(backups(db)) == 1
    assert informe["new"] == 6


def test_ignora_ficheros_que_no_son_del_inbox(env):
    inbox, _ = env
    deja(inbox, "notas.txt")
    deja(inbox, "candidaturas_a.csv")
    runner = FakeRunner()
    assert watcher(env, runner).run_once() is None and runner.calls == []


def test_un_fichero_conservado_no_se_reprocesa_hasta_que_cambia(env):
    inbox, _ = env
    f = deja(inbox, "candidaturas_a.txt")
    w = watcher(env, FakeRunner({"load_inbox_applications.py": SALIDA_APPS}))
    assert w.run_once() is not None          # el cargador lo deja ahí (hay filas dudosas)
    assert w.run_once() is None              # sin cambios: no se repite ni se copia otra vez la BD
    f.write_text(f.read_text() + "2026-10-07|Otra|SAP||sent|def\n", encoding="utf-8")
    os.utime(f, (f.stat().st_atime, f.stat().st_mtime + 10))
    assert w.run_once() is not None


def test_si_el_cargador_borra_el_fichero_un_nuevo_fichero_con_el_mismo_nombre_se_procesa(env):
    inbox, _ = env
    runner = FakeRunner({"load_inbox_applications.py": SALIDA_APPS},
                        on_call=lambda cmd: Path(cmd[2]).unlink())
    w = watcher(env, runner)
    deja(inbox, "candidaturas_n8n_auto.txt")
    assert w.run_once() is not None
    deja(inbox, "candidaturas_n8n_auto.txt", "2026-10-07|Nueva|SAP||sent|zzz\n")
    assert w.run_once() is not None
    assert len(runner.calls) == 2


def test_no_toca_un_fichero_que_aun_se_esta_escribiendo(env):
    inbox, _ = env
    deja(inbox, "candidaturas_a.txt")
    runner = FakeRunner({"load_inbox_applications.py": SALIDA_APPS})
    w = InboxWatcher(*env, runner=runner, settle_seconds=60)
    assert w.run_once() is None and runner.calls == []
    assert w.run_once(force=True) is not None   # «Sincronizar ahora» no espera


def test_error_del_cargador_se_informa_y_no_se_repite_en_bucle(env):
    inbox, _ = env
    deja(inbox, "candidaturas_a.txt")
    runner = FakeRunner(returncode=1)
    w = watcher(env, runner)
    informe = w.run_once()
    assert informe["error"] is True
    assert w.run_once() is None and len(runner.calls) == 1
    assert w.run_once(force=True) is not None   # el usuario puede reintentar


def test_solo_conserva_las_ultimas_copias(env):
    inbox, db = env
    for i in range(4):
        deja(inbox, f"candidaturas_{i}.txt", f"2026-10-0{i + 1}|ACME|SAP||sent|abc\n")
        InboxWatcher(inbox, db, runner=FakeRunner(), settle_seconds=0, keep=2,
                     now=lambda i=i: datetime(2026, 10, 7, 12, 0, i)).run_once(force=True)
    assert len(backups(db)) == 2


def test_estado_lista_ficheros_pendientes_con_sus_filas_y_el_ultimo_informe(env):
    inbox, _ = env
    deja(inbox, "candidaturas_a.txt", "# comentario\n2026-10-06|ACME|SAP||sent|abc\n\n2026-10-06|Foo|Dev||sent|def\n")
    w = watcher(env, FakeRunner({"load_inbox_applications.py": SALIDA_APPS}))
    antes = w.status()
    assert antes["last"] is None and antes["changes"] == 0
    assert antes["pending"] == [{"name": "candidaturas_a.txt", "rows": 2}]
    w.run_once()
    despues = w.status()
    assert despues["changes"] == 1 and despues["last"]["new"] == 2


def test_sin_cambios_en_la_bd_no_sube_el_contador(env):
    inbox, _ = env
    deja(inbox, "candidaturas_a.txt")
    w = watcher(env, FakeRunner({"load_inbox_applications.py": "== nuevas: 0\n== actualizadas: 0\n== dudosas: 0\n"}))
    w.run_once()
    assert w.status()["changes"] == 0
