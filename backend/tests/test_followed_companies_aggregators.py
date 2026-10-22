"""Tests de Task 4: empresas seguidas sobre los agregadores, matching de alias, tope de consultas y endpoint de ofertas."""
import sqlite3
from unittest.mock import patch

import pytest

import database
import main
from search_config import (
    FollowedCompany,
    followed_company_queries,
    followed_tier_for,
    get_config,
    set_config,
)


@pytest.fixture
def cfg_with_followed():
    base = get_config().model_copy(deep=True)
    # Nivel superior con aliases (Adecco/Randstad ficticio para pruebas)
    base.followed_companies = [
        FollowedCompany(name="Adecco", tier=1, aliases=["Adecco Group", "The Adecco Group España"]),
        FollowedCompany(name="Manpower", tier=2, aliases=["ManpowerGroup"]),
    ]
    # Track específico con empresa propia existente sin cambios
    sap = base.track("sap")
    if sap:
        sap.followed_companies = [FollowedCompany(name="Acme SAP Partners", tier=3)]
    original = get_config()
    set_config(base)
    yield base
    set_config(original)


def test_alias_matching_and_normalization(cfg_with_followed):
    # Coincidencia exacta y normalizada del nombre principal
    assert followed_tier_for("Adecco", None) == 1
    assert followed_tier_for("ADECCO S.L.", None) == 1

    # Coincidencia de alias
    assert followed_tier_for("Adecco Group", None) == 1
    assert followed_tier_for("The Adecco Group España", None) == 1
    assert followed_tier_for("the adecco group espana s.a.", None) == 1
    assert followed_tier_for("ManpowerGroup", None) == 2

    # Empresa desconocida no tiene tier
    assert followed_tier_for("Empresa Desconocida", None) is None


def test_existing_per_track_followed_companies_unchanged(cfg_with_followed):
    # Empresa seguida específica del track sap conserva su tier en ese track
    assert followed_tier_for("Acme SAP Partners", "sap") == 3
    # Y si no se especifica track o cae a todos, también se encuentra
    assert followed_tier_for("Acme SAP Partners", None) == 3


def test_query_cap_and_deduplication():
    base = get_config().model_copy(deep=True)
    # Creamos 15 empresas y alias para probar el tope de 10
    companies = [
        FollowedCompany(name=f"Empresa {i}", tier=1, aliases=[f"Alias {i}", f"Empresa {i}"])
        for i in range(15)
    ]
    base.followed_companies = companies
    queries = followed_company_queries(cfg=base, max_queries=10)
    assert len(queries) == 10
    # Comprobamos deduplicación
    assert len(queries) == len(set(q.lower() for q in queries))


@pytest.fixture
def conn(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "test_followed.db")
    c = database.get_conn()
    database.init_db(c)
    cid = database.upsert_company(c, {"name": "ACME", "source": "test"})
    # Insertar ofertas: o1 y o2 con followed_tier, o3 y o4 sin followed_tier
    c.execute(
        "INSERT INTO job_offers (id, company_id, title, location, relevance_score, is_relevant, followed_tier, scraped_at) "
        "VALUES ('o1', ?, 'Dev 1', 'Madrid', 0.9, 1, 1, datetime('now'))",
        (cid,),
    )
    c.execute(
        "INSERT INTO job_offers (id, company_id, title, location, relevance_score, is_relevant, followed_tier, scraped_at) "
        "VALUES ('o2', ?, 'Dev 2', 'Barcelona', 0.8, 1, 2, datetime('now'))",
        (cid,),
    )
    c.execute(
        "INSERT INTO job_offers (id, company_id, title, location, relevance_score, is_relevant, followed_tier, scraped_at) "
        "VALUES ('o3', ?, 'Dev 3', 'Remoto', 0.7, 1, NULL, datetime('now'))",
        (cid,),
    )
    c.execute(
        "INSERT INTO job_offers (id, company_id, title, location, relevance_score, is_relevant, followed_tier, scraped_at) "
        "VALUES ('o4', ?, 'Dev 4', 'Remoto', 0.6, 1, NULL, datetime('now'))",
        (cid,),
    )
    c.commit()
    yield c
    c.close()


def test_filter_endpoint_followed_only(conn):
    # Sin filtro followed: devuelve las 4 ofertas
    all_offers = main.get_offers(conn=conn)
    assert [o["id"] for o in all_offers] == ["o1", "o2", "o3", "o4"]

    # Con followed=True: solo devuelve las ofertas con followed_tier no nulo (o1 y o2)
    followed_offers = main.get_offers(followed=True, conn=conn)
    assert [o["id"] for o in followed_offers] == ["o1", "o2"]
