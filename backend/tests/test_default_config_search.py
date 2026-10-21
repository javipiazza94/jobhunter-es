"""Con la configuración por defecto (y los ejemplos) los scrapers buscan algo; sin parámetros avisan."""
import asyncio
from pathlib import Path

import pytest

import scraper.company_direct
import scraper.computrabajo
import scraper.indeed
import scraper.infojobs
import scraper.linkedin_jobs
import scraper.runner as runner
import scraper.tecnoempleo
import search_config
from search_config import get_config, load_config, set_config

ROOT = Path(__file__).resolve().parents[2]
CONFIGS = [Path(search_config.__file__).parent / "defaults" / "jobhunter.yaml", *sorted((ROOT / "examples").glob("*.yaml"))]


@pytest.fixture
def seen(monkeypatch):
    calls = []

    class FakeTecnoempleo:
        async def scrape_keyword(self, kw, loc, pages):
            calls.append(("tecnoempleo", kw, loc))
            return []

    async def infojobs(keywords, *a, **k):
        calls.append(("infojobs", list(keywords)))
        return []

    async def computrabajo(keywords, *a, **k):
        calls.append(("computrabajo", list(keywords)))
        return []

    async def company_direct(dry_run):
        return 0, 0

    async def linkedin(*a, **k):
        return []

    monkeypatch.setattr(scraper.tecnoempleo, "TecnoempleoScraper", FakeTecnoempleo)
    monkeypatch.setattr(scraper.infojobs, "run_infojobs", infojobs)
    monkeypatch.setattr(scraper.computrabajo, "run_computrabajo", computrabajo)
    monkeypatch.setattr(scraper.company_direct, "run_company_direct", company_direct)
    monkeypatch.setattr(scraper.linkedin_jobs, "run_linkedin_jobs", linkedin)
    return calls


@pytest.fixture
def pinned():
    original = get_config()
    yield set_config
    set_config(original)


def test_config_por_defecto_lanza_tecnoempleo_con_keywords_no_vacias(seen, pinned):
    cfg = load_config(CONFIGS[0])
    pinned(cfg)
    asyncio.run(runner.run_track_source("developer", True, 1))
    tecno = [c for c in seen if c[0] == "tecnoempleo"]
    assert tecno and all(kw and loc for _, kw, loc in tecno)
    assert ("infojobs", cfg.track("developer").search_keywords) in seen


@pytest.mark.parametrize("path", CONFIGS, ids=lambda p: p.name)
def test_cada_config_tiene_fuentes_con_keywords_y_ubicaciones(path):
    cfg = load_config(path)
    for track in cfg.standard_tracks():
        assert track.search_keywords, f"{path.name}: el track '{track.id}' no tiene search_keywords"
    for source in ("tecnoempleo", "indeed"):
        assert cfg.sources[source]["keywords"] and cfg.sources[source]["locations"], f"{path.name}: {source}"
    assert cfg.sources["infojobs"]["keywords"], path.name


def test_track_sin_keywords_ni_ubicaciones_avisa(seen, pinned, caplog):
    cfg = load_config(CONFIGS[0])
    empty = cfg.track("developer").model_copy(update={"search_keywords": []})
    pinned(cfg.model_copy(update={"tracks": [empty], "sources": {}}))
    with caplog.at_level("WARNING"):
        asyncio.run(runner.run_track_source("developer", True, 1))
    assert "search_keywords" in caplog.text and "developer" in caplog.text
    assert "tecnoempleo" in caplog.text and "locations" in caplog.text


def test_fuente_sin_parametros_avisa(pinned, caplog, monkeypatch):
    pinned(load_config(CONFIGS[0]).model_copy(update={"sources": {}}))
    monkeypatch.setattr("config.SCRAPERAPI_KEY", "k", raising=False)
    with caplog.at_level("WARNING"):
        assert asyncio.run(scraper.tecnoempleo.run_tecnoempleo(max_pages=1)) == []
        assert asyncio.run(scraper.indeed.run_indeed(max_pages=1)) == []
    assert "sources.tecnoempleo" in caplog.text
    assert "sources.indeed" in caplog.text
