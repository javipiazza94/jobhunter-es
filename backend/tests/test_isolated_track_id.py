"""Un track aislado funciona con cualquier id (no solo `generic`): guardado, dedupe, stats y pestaña."""
import asyncio
import sqlite3

import pytest

import database
import main
import scraper.generic as generic
import scraper.indeed
import scraper.infojobs
from search_config import get_config, set_config

TRACK_ID = "puente"
KEYWORDS = ["atención al cliente", "camarero"]
REMOTE_KEYWORDS = ["teleoperador"]


@pytest.fixture
def bridge_cfg():
    original = get_config()
    legacy = original.track("generic")
    track = legacy.model_copy(update={"id": TRACK_ID, "search_keywords": KEYWORDS,
                                       "remote_search_keywords": REMOTE_KEYWORDS})
    cfg = original.model_copy(update={
        "tracks": [t for t in original.tracks if t.id != "generic"] + [track],
    })
    set_config(cfg)
    yield cfg
    set_config(original)


@pytest.fixture
def conn(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "t.db")
    c = database.get_conn()
    database.init_db(c)
    yield c
    c.close()


OFFER = {
    "title": "Agente de atención al cliente", "company_name": "Vexcorp", "location": "Villanova",
    "url": "https://x/1", "description": "Atención telefónica", "source": "infojobs",
    "posted_at": None, "salary_min": None,
}


def test_upsert_usa_el_id_del_track_en_insert_y_dedupe(conn):
    cid = database.upsert_company(conn, {"name": "Vexcorp", "source": "generic"})
    base = {"company_id": cid, "title": "Camarero", "location": "Villanova", "source": "indeed", "generic_score": 0.9}
    first = database.upsert_generic_offer(conn, {**base, "url": "https://to.indeed.com/a"}, TRACK_ID)
    second = database.upsert_generic_offer(conn, {**base, "url": "https://to.indeed.com/b"}, TRACK_ID)
    assert first == second
    assert conn.execute("SELECT job_kind FROM job_offers").fetchone()[0] == TRACK_ID


def test_stats_cuenta_las_ofertas_de_cualquier_track_aislado(conn):
    cid = database.upsert_company(conn, {"name": "Vexcorp", "source": "generic"})
    database.upsert_generic_offer(conn, {"company_id": cid, "title": "Camarero", "url": "https://x/9",
                                         "generic_score": 0.9}, TRACK_ID)
    assert database.stats(conn)["generic_offers"] == 1


def test_guardado_real_y_pestana_del_track(conn, bridge_cfg, monkeypatch):
    async def infojobs(keywords, max_pages, normalized_location, province_id, scroll=False):
        return [dict(OFFER)]

    monkeypatch.setattr(scraper.infojobs, "run_infojobs", infojobs)
    monkeypatch.setattr(generic, "scraperapi_credits", lambda key: None)
    asyncio.run(generic.run_generic_source(False, 1, ["infojobs"], 10**9))
    rows = main.get_offers(track=TRACK_ID, conn=conn)
    assert [r["title"] for r in rows] == [OFFER["title"]]
    assert conn.execute("SELECT job_kind FROM job_offers").fetchone()[0] == TRACK_ID


@pytest.fixture
def search_fakes(monkeypatch):
    calls = {"infojobs": [], "indeed": []}

    async def infojobs(keywords, max_pages, normalized_location, province_id, scroll=False):
        calls["infojobs"].append((list(keywords), province_id))
        return []

    async def indeed(keywords, locations, max_pages):
        calls["indeed"].append((list(keywords), list(locations)))
        return []

    monkeypatch.setattr(scraper.infojobs, "run_infojobs", infojobs)
    monkeypatch.setattr(scraper.indeed, "run_indeed", indeed)
    monkeypatch.setattr(generic, "scraperapi_credits", lambda key: None)
    return calls


def test_las_keywords_salen_del_track_y_la_remota_de_remote_search_keywords(conn, bridge_cfg, search_fakes):
    asyncio.run(generic.run_generic_source(False, 1, ["infojobs", "indeed"], 10**9))
    assert search_fakes["infojobs"] == [(KEYWORDS, "99"), ([f"{k} teletrabajo" for k in REMOTE_KEYWORDS], None)]
    assert search_fakes["indeed"] == [(KEYWORDS, ["Villanova", "Remoto"])]


def test_varios_tracks_aislados_se_buscan_todos(conn, bridge_cfg, search_fakes):
    other = bridge_cfg.track(TRACK_ID).model_copy(update={"id": "otro", "search_keywords": ["jardinero"],
                                                           "remote_search_keywords": []})
    set_config(bridge_cfg.model_copy(update={"tracks": [*bridge_cfg.tracks, other]}))
    asyncio.run(generic.run_generic_source(False, 1, ["indeed"], 10**9))
    assert [kw for kw, _ in search_fakes["indeed"]] == [KEYWORDS, ["jardinero"]]


def test_track_sin_search_keywords_avisa_y_se_omite(conn, bridge_cfg, search_fakes, caplog):
    empty = bridge_cfg.track(TRACK_ID).model_copy(update={"search_keywords": []})
    set_config(bridge_cfg.model_copy(update={"tracks": [empty]}))
    with caplog.at_level("WARNING"):
        asyncio.run(generic.run_generic_source(False, 1, ["infojobs", "indeed"], 10**9))
    assert search_fakes == {"infojobs": [], "indeed": []}
    assert "search_keywords" in caplog.text and TRACK_ID in caplog.text
