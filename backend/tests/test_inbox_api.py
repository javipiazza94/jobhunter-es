"""Endpoints del inbox: estado para el dashboard y sincronización a demanda."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from asgi_client import call  # noqa: E402
import main  # noqa: E402

CLIENT = [("x-jh-client", "dashboard")]


class FakeWatcher:
    def __init__(self, report=None):
        self.report, self.forced = report, []

    def status(self):
        return {"pending": [{"name": "candidaturas_a.txt", "rows": 3}], "last": self.report, "changes": 2, "automatic": True}

    def run_once(self, force=False):
        self.forced.append(force)
        return self.report


REPORT = {"at": "2026-10-07T12:00:00", "files": ["candidaturas_a.txt"], "new": 2, "updated": 1, "doubtful": 0,
          "invalid": 0, "to_review": 1, "error": False, "output": "ok"}


@pytest.fixture
def watcher(monkeypatch):
    w = FakeWatcher(REPORT)
    monkeypatch.setattr(main, "inbox_watcher", w)
    return w


def test_estado_del_inbox(watcher):
    status, _, body = call("GET", "/api/inbox/status")
    data = json.loads(body)
    assert status == 200
    assert data["pending"] == [{"name": "candidaturas_a.txt", "rows": 3}]
    assert data["changes"] == 2 and data["automatic"] is True and data["last"]["new"] == 2


def test_sincronizar_exige_la_cabecera_del_dashboard(watcher):
    status, _, _ = call("POST", "/api/inbox/sync")
    assert status == 403 and watcher.forced == []


def test_sincronizar_fuerza_la_carga_y_devuelve_el_informe(watcher):
    status, _, body = call("POST", "/api/inbox/sync", headers=CLIENT)
    assert status == 200 and watcher.forced == [True]
    assert json.loads(body)["to_review"] == 1


def test_sincronizar_sin_nada_pendiente_devuelve_null(monkeypatch):
    monkeypatch.setattr(main, "inbox_watcher", FakeWatcher(None))
    status, _, body = call("POST", "/api/inbox/sync", headers=CLIENT)
    assert status == 200 and json.loads(body) is None
