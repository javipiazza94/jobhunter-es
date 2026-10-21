"""job_key: clave canónica empresa+título en job_offers (migración 005) y dedupe entre fuentes."""
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import database  # noqa: E402
from automation.job_key import make_key  # noqa: E402


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    database.init_db(c)
    yield c
    c.close()


def _offer(conn, company, title, url, location=None, source="tecnoempleo"):
    cid = database.upsert_company(conn, {"name": company, "source": source})
    oid = database.upsert_job_offer(conn, {
        "company_id": cid, "title": title, "url": url, "source": source,
        "location": location, "relevance_score": 0.5, "is_relevant": 1,
    })
    return oid


def _count(conn):
    return conn.execute("SELECT COUNT(*) FROM job_offers").fetchone()[0]


def test_migracion_005_rellena_job_key_de_las_ofertas_existentes():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.executescript(database.CREATE_SCHEMA)
    for migration in database.MIGRATIONS[:4]:
        migration(c)
    c.execute("PRAGMA user_version = 4")
    c.execute("INSERT INTO companies (id, name, source, created_at) VALUES ('c1', 'Acme Corp', 's', 'hoy')")
    c.execute("INSERT INTO job_offers (id, company_id, title, url, scraped_at) "
              "VALUES ('o1', 'c1', 'SOC Analyst (L2)', 'https://x/1', 'hoy')")
    c.execute("INSERT INTO job_offers (id, title, url, scraped_at) VALUES ('o2', 'Dev', 'https://x/2', 'hoy')")
    c.commit()
    database.init_db(c)
    assert database.schema_version(c) == len(database.MIGRATIONS) >= 5
    got = {r["id"]: r["job_key"] for r in c.execute("SELECT id, job_key FROM job_offers")}
    assert got["o1"] == make_key("Acme Corp", "SOC Analyst (L2)", "https://x/1")
    assert got["o2"] == make_key("", "Dev", "https://x/2")  # sin empresa: no revienta
    c.close()


def test_una_oferta_nueva_guarda_su_job_key(conn):
    oid = _offer(conn, "Acme Corp", "Backend Developer", "https://a/1")
    key = conn.execute("SELECT job_key FROM job_offers WHERE id=?", (oid,)).fetchone()["job_key"]
    assert key == "acme-corp_backend-developer"


def test_la_misma_oferta_por_otra_fuente_no_se_duplica(conn):
    a = _offer(conn, "Acme Corp", "Backend Developer", "https://tecnoempleo/1", "Madrid", "tecnoempleo")
    b = _offer(conn, "ACME CORP", "Backend  Developer", "https://linkedin/9", "Madrid", "linkedin")
    assert a == b and _count(conn) == 1
    # la URL original se conserva (la primera que se vio)
    assert conn.execute("SELECT url FROM job_offers").fetchone()["url"] == "https://tecnoempleo/1"


def test_sin_ubicacion_en_una_de_las_dos_se_considera_la_misma(conn):
    a = _offer(conn, "Acme", "Data Engineer", "https://a/1", None)
    b = _offer(conn, "Acme", "Data Engineer", "https://b/2", "Barcelona")
    assert a == b and _count(conn) == 1


def test_mismo_puesto_en_ciudades_distintas_son_ofertas_distintas(conn):
    a = _offer(conn, "Acme Robotics", "Consultor SAP", "https://a/1", "Madrid")
    b = _offer(conn, "Acme Robotics", "Consultor SAP", "https://b/2", "Villanova")
    assert a != b and _count(conn) == 2


def test_misma_oferta_otra_empresa_o_titulo_son_distintas(conn):
    _offer(conn, "Acme", "Backend Developer", "https://a/1", "Madrid")
    _offer(conn, "Globex", "Backend Developer", "https://a/2", "Madrid")
    _offer(conn, "Acme", "Frontend Developer", "https://a/3", "Madrid")
    assert _count(conn) == 3


def test_misma_url_sigue_actualizando_la_misma_fila(conn):
    a = _offer(conn, "Acme", "Backend Developer", "https://a/1", "Madrid")
    b = _offer(conn, "Acme", "Backend Developer", "https://a/1", "Madrid")
    assert a == b and _count(conn) == 1


def test_el_trabajo_puente_no_se_fusiona_con_ofertas_normales(conn):
    cid = database.upsert_company(conn, {"name": "Acme", "source": "s"})
    gid = database.upsert_generic_offer(conn, {
        "company_id": cid, "title": "Atención al cliente", "url": "https://g/1",
        "source": "infojobs", "generic_score": 0.7,
    }, "generic")
    nid = _offer(conn, "Acme", "Atención al cliente", "https://n/1")
    assert gid is not None and gid != nid and _count(conn) == 2
