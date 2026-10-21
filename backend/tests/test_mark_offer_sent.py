"""Marcar una oferta como enviada guarda el perfil de CV calculado, no la columna legado
job_offers.cv_profile (casi siempre NULL), para que cuente en las proporciones SAP/IA del dashboard."""
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import database  # noqa: E402
import main  # noqa: E402
from automation.filter_engine import classify_track  # noqa: E402


@pytest.fixture
def conn(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "t.db")
    c = database.get_conn()
    database.init_db(c)
    cid = database.upsert_company(c, {"name": "ACME", "source": "test"})
    c.execute("INSERT INTO job_offers (id, company_id, title, description, scraped_at) "
              "VALUES ('sap1', ?, 'Consultor SAP S/4HANA Public Cloud PS', 'SAP S/4HANA, módulo PS y MM', datetime('now'))", (cid,))
    c.execute("INSERT INTO job_offers (id, company_id, title, description, cv_profile, scraped_at) "
              "VALUES ('viejo', ?, 'Consultor SAP S/4HANA', 'SAP S/4HANA', 'ia_dev', datetime('now'))", (cid,))
    c.commit()
    yield c
    c.close()


def _perfil_guardado(conn, offer_id):
    return conn.execute("SELECT cv_profile FROM applications WHERE job_offer_id=?", (offer_id,)).fetchone()["cv_profile"]


def test_si_la_columna_esta_vacia_se_calcula_el_perfil(conn):
    esperado = classify_track(dict(conn.execute("SELECT * FROM job_offers WHERE id='sap1'").fetchone()))[0]
    main.mark_offer_sent("sap1", conn)
    assert _perfil_guardado(conn, "sap1") == esperado
    assert esperado == "sap"  # el caso de prueba es inequívocamente SAP


def test_un_valor_guardado_antes_se_respeta(conn):
    main.mark_offer_sent("viejo", conn)
    assert _perfil_guardado(conn, "viejo") == "ia_dev"
