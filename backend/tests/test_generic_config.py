"""El scraper de trabajos puente lee sus ubicaciones de sources.generic (jobhunter.yaml)."""
import asyncio

import pytest

import database
import scraper.generic as generic
import scraper.indeed
import scraper.infojobs
from search_config import get_config, set_config


@pytest.fixture
def fakes(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "t.db")
    database.init_db(database.get_conn())
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


def _run():
    asyncio.run(generic.run_generic_source(False, 1, ["infojobs", "indeed"], 10**9))


def test_valores_legacy_llegan_a_los_scrapers(fakes):
    _run()
    provincias = [p for _, p in fakes["infojobs"]]
    assert provincias == ["99", None]  # provincia configurada + búsqueda remota nacional
    assert fakes["indeed"] == [(get_config().track("generic").search_keywords, ["Villanova", "Remoto"])]


def test_sin_config_generic_omite_esas_busquedas_con_aviso(fakes, caplog):
    original = get_config()
    set_config(original.model_copy(update={"sources": {}}))
    try:
        with caplog.at_level("WARNING"):
            _run()
    finally:
        set_config(original)
    assert fakes["indeed"] == []
    assert [p for _, p in fakes["infojobs"]] == [None]  # solo la remota; sin provincia configurada
    assert "infojobs_province_ids" in caplog.text and "indeed_locations" in caplog.text
