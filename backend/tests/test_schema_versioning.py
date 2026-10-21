"""Migraciones de esquema con versión (PRAGMA user_version): cada una se ejecuta una sola vez
y de forma atómica."""
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import database  # noqa: E402


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    yield c
    c.close()


def _cols(conn, table):
    return {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}


def test_una_bd_nueva_queda_en_la_ultima_version(conn):
    database.init_db(conn)
    assert database.schema_version(conn) == len(database.MIGRATIONS)
    assert "discard_status" in _cols(conn, "job_offers")


def test_una_bd_anterior_al_versionado_se_actualiza_sin_perder_datos(conn):
    # BD «antigua»: esquema base, versión 0 y sin las columnas que añaden las migraciones.
    conn.executescript(database.CREATE_SCHEMA)
    for table, col in [("job_offers", "followed_tier"), ("job_offers", "generic_score"),
                       ("job_offers", "discard_status"), ("applications", "approved_at")]:
        if col in _cols(conn, table):
            conn.execute(f"ALTER TABLE {table} DROP COLUMN {col}")
    conn.execute("INSERT INTO job_offers (id, title, scraped_at) VALUES ('o1', 'Dev', 'hoy')")
    conn.commit()
    assert database.schema_version(conn) == 0
    assert "followed_tier" not in _cols(conn, "job_offers")
    database.init_db(conn)
    assert database.schema_version(conn) == len(database.MIGRATIONS)
    assert {"followed_tier", "generic_score", "discard_status"} <= _cols(conn, "job_offers")
    assert "approved_at" in _cols(conn, "applications")
    assert conn.execute("SELECT title FROM job_offers WHERE id='o1'").fetchone()["title"] == "Dev"


def test_init_db_repetido_no_vuelve_a_migrar(conn, monkeypatch):
    ejecuciones = []
    monkeypatch.setattr(database, "MIGRATIONS", [lambda c: ejecuciones.append(1)])
    database.init_db(conn)
    database.init_db(conn)
    assert ejecuciones == [1]
    assert database.schema_version(conn) == 1


def test_una_migracion_nueva_se_ejecuta_una_sola_vez(conn, monkeypatch):
    log = []
    m1 = lambda c: log.append("m1")  # noqa: E731
    m2 = lambda c: (log.append("m2"), c.execute("CREATE TABLE extra (x INTEGER)"))  # noqa: E731
    monkeypatch.setattr(database, "MIGRATIONS", [m1])
    database.init_db(conn)
    monkeypatch.setattr(database, "MIGRATIONS", [m1, m2])
    database.init_db(conn)
    database.init_db(conn)
    assert log == ["m1", "m2"]
    assert database.schema_version(conn) == 2
    assert "extra" in {r[0] for r in conn.execute("SELECT name FROM sqlite_master")}


def test_una_migracion_que_falla_se_deshace_entera_y_no_sube_la_version(conn, monkeypatch):
    def rota(c):
        c.execute("CREATE TABLE a_medias (x INTEGER)")
        raise RuntimeError("fallo a mitad")

    monkeypatch.setattr(database, "MIGRATIONS", [lambda c: None])
    database.init_db(conn)
    monkeypatch.setattr(database, "MIGRATIONS", [lambda c: None, rota])
    with pytest.raises(RuntimeError, match="fallo a mitad"):
        database.init_db(conn)
    assert database.schema_version(conn) == 1
    assert "a_medias" not in {r[0] for r in conn.execute("SELECT name FROM sqlite_master")}


def test_una_bd_mas_nueva_que_el_codigo_se_rechaza(conn, monkeypatch):
    monkeypatch.setattr(database, "MIGRATIONS", [lambda c: None])
    conn.execute("PRAGMA user_version = 99")
    with pytest.raises(RuntimeError, match="versión 99"):
        database.init_db(conn)


def test_migracion_002_indices_de_candidaturas(conn):
    database.init_db(conn)
    nombres = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")}
    assert {"idx_apps_offer", "idx_apps_sent"} <= nombres
    # «¿tiene candidatura esta oferta?» y la lista ordenada por fecha ya no recorren la tabla entera
    plan = " ".join(r[3] for r in conn.execute("EXPLAIN QUERY PLAN SELECT id FROM applications WHERE job_offer_id = 'x'"))
    assert "idx_apps_offer" in plan
    plan = " ".join(r[3] for r in conn.execute("EXPLAIN QUERY PLAN SELECT id FROM applications ORDER BY sent_at DESC"))
    assert "idx_apps_sent" in plan


def test_migracion_004_copia_tiers_y_tags(conn):
    # BD en la versión 3 con las columnas SAP/DS antiguas.
    conn.executescript(database.CREATE_SCHEMA)
    for migration in database.MIGRATIONS[:3]:
        migration(conn)
    conn.execute("PRAGMA user_version = 3")
    rows = [
        ("o1", 2, "MM", None, None),
        ("o2", None, None, 1, "NLP"),
        ("o3", 3, "PS", 1, "CV"),
        ("o4", None, None, None, None),
    ]
    for oid, st, sm, dt, dc in rows:
        conn.execute(
            "INSERT INTO job_offers (id, title, scraped_at, sap_tier, sap_module, ds_tier, ds_category) "
            "VALUES (?, 't', 'hoy', ?, ?, ?, ?)", (oid, st, sm, dt, dc))
    conn.commit()
    database.init_db(conn)
    assert database.schema_version(conn) == len(database.MIGRATIONS)
    got = {r["id"]: (r["followed_tier"], r["track_tag"])
           for r in conn.execute("SELECT id, followed_tier, track_tag FROM job_offers")}
    assert got == {"o1": (2, "MM"), "o2": (1, "NLP"), "o3": (1, "PS"), "o4": (None, None)}
    cols = _cols(conn, "job_offers")
    assert not ({"sap_tier", "ds_tier", "sap_module", "ds_category"} & cols)
