"""Empresas seguidas: normalización de nombres, tier por track y marca al guardar ofertas."""
import sqlite3

import pytest

from database import init_db
from scraper.persist import save_scored_offer
from search_config import FollowedCompany, followed_tier_for, get_config, normalize_company, set_config


def test_normalize_company():
    assert normalize_company("Acme Robotics Spain") == normalize_company("ACME ROBOTICS S.L.") == normalize_company("acme robotics")
    assert normalize_company("Telefonía Acme, S.A.") == "telefonia acme"
    assert normalize_company("  Grupo  Santaluz ") == "grupo santaluz"
    assert normalize_company("Spain") == "spain"  # nunca vacío si solo hay ruido


@pytest.fixture
def cfg():
    base = get_config().model_copy(deep=True)
    sap, ia = base.track("sap"), base.track("ia_dev")
    sap.followed_companies = [FollowedCompany(name="Acme Robotics", tier=2), FollowedCompany(name="Initech Systems", tier=3)]
    ia.followed_companies = [FollowedCompany(name="ACME ROBOTICS S.L.", tier=1)]
    original = get_config()
    set_config(base)
    yield base
    set_config(original)


def test_followed_tier_for_prioriza_el_track_y_cae_a_todos(cfg):
    assert followed_tier_for("Acme Robotics Spain", "sap") == 2
    assert followed_tier_for("Acme Robotics", "ia_dev") == 1
    assert followed_tier_for("Acme Robotics", "generic") == 1  # sin match en el track: mejor de todos
    assert followed_tier_for("Initech Systems", "ia_dev") == 3
    assert followed_tier_for("Desconocida", "sap") is None
    assert followed_tier_for("Acme Robotics", None) == 1


def _conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_db(conn)
    return conn


def test_persist_marca_empresa_seguida(cfg):
    conn = _conn()
    offer = {"title": "SAP S/4HANA Public Cloud Consultant", "company_name": "Initech Systems Spain",
             "url": "https://x/1", "location": "Villanova"}
    oid = save_scored_offer(conn, offer, "test")
    assert conn.execute("SELECT followed_tier FROM job_offers WHERE id=?", (oid,)).fetchone()[0] == 3
    # La empresa sale de la configuración: el tier existente no se borra.
    for t in cfg.tracks:
        t.followed_companies = []
    assert save_scored_offer(conn, offer, "test") == oid
    assert conn.execute("SELECT followed_tier FROM job_offers WHERE id=?", (oid,)).fetchone()[0] == 3
