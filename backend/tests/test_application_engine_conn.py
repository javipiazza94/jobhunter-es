"""create_drafts / fill_forms / send_approved cierran siempre su conexión, también si fallan."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import database  # noqa: E402
from automation import application_engine as engine  # noqa: E402


class _ConnProxy:
    """Delega en una conexión real y recuerda si se cerró."""

    def __init__(self, conn):
        self._conn = conn
        self.closed = False

    def close(self):
        self.closed = True
        self._conn.close()

    def __getattr__(self, name):
        return getattr(self._conn, name)


@pytest.fixture
def proxy(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "t.db")
    real = database.get_conn()
    database.init_db(real)
    p = _ConnProxy(real)
    monkeypatch.setattr(engine, "get_conn", lambda: p)
    monkeypatch.setattr(engine, "_load_profile", lambda: {})  # no depender de backend/profile.json (ignorado por git)
    return p


def test_create_drafts_cierra_la_conexion(proxy):
    result = engine.create_drafts()
    assert result["drafts_created"] == 0
    assert proxy.closed


def test_create_drafts_cierra_la_conexion_si_falla(proxy, monkeypatch):
    def boom(conn):
        raise RuntimeError("fallo inesperado")
    monkeypatch.setattr(engine, "get_pending_offers", boom)
    with pytest.raises(RuntimeError):
        engine.create_drafts()
    assert proxy.closed


def test_fill_forms_cierra_la_conexion(proxy):
    engine.fill_forms(dry_run=True)
    assert proxy.closed


def test_send_approved_inexistente_lanza_valueerror_y_cierra(proxy):
    with pytest.raises(ValueError, match="not found"):
        engine.send_approved("no-existe")
    assert proxy.closed


def test_send_approved_con_limite_diario_agotado_lanza_valueerror_y_cierra(proxy, monkeypatch):
    monkeypatch.setattr(engine, "MAX_EMAILS_PER_DAY", 0)
    with pytest.raises(ValueError, match="Daily email limit"):
        engine.send_approved("lo-que-sea")
    assert proxy.closed
