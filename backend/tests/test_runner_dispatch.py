"""runner.main(): qué se ejecuta para cada --source (caracterización del CLI)."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import database  # noqa: E402
import scraper.runner as runner  # noqa: E402


@pytest.fixture
def calls(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "t.db")
    log: list = []

    monkeypatch.setattr(runner, "load_seed", lambda: log.append("seed"))

    async def tecnoempleo(dry, pages): log.append(("tecnoempleo", dry, pages))
    async def indeed(dry, pages): log.append(("indeed", dry, pages))
    async def contacts(dry): log.append(("contacts", dry))
    async def track(track_id, dry, pages): log.append(("track", track_id, dry, pages))
    async def generic(dry, pages, sources, credits): log.append(("generic", dry, pages, sources, credits))
    async def login(): log.append("login")

    monkeypatch.setattr(runner, "run_tecnoempleo_source", tecnoempleo)
    monkeypatch.setattr(runner, "run_indeed_source", indeed)
    monkeypatch.setattr(runner, "run_manfred_source", lambda dry: log.append(("manfred", dry)))
    monkeypatch.setattr(runner, "run_contacts_source", contacts)
    monkeypatch.setattr(runner, "run_track_source", track)
    monkeypatch.setattr(runner, "run_resolve_websites_source", lambda dry, limit: log.append(("resolve", dry, limit)))
    monkeypatch.setattr(runner, "print_stats", lambda: log.append("stats"))
    import scraper.generic
    import scraper.linkedin_jobs
    monkeypatch.setattr(scraper.generic, "run_generic_source", generic)
    monkeypatch.setattr(scraper.linkedin_jobs, "run_linkedin_login", login)
    return log


def _run(monkeypatch, *argv):
    monkeypatch.setattr(sys, "argv", ["runner", *argv])
    runner.main()


def test_seed(calls, monkeypatch):
    _run(monkeypatch, "--source", "seed")
    assert calls == ["seed", "stats"]


def test_seed_dry_run_no_carga(calls, monkeypatch):
    _run(monkeypatch, "--source", "seed", "--dry-run")
    assert calls == ["stats"]


def test_tecnoempleo(calls, monkeypatch):
    _run(monkeypatch, "--source", "tecnoempleo", "--max-pages", "5", "--dry-run")
    assert calls == [("tecnoempleo", True, 5), "stats"]


def test_indeed_y_manfred_y_contacts(calls, monkeypatch):
    _run(monkeypatch, "--source", "indeed")
    _run(monkeypatch, "--source", "manfred")
    _run(monkeypatch, "--source", "contacts", "--dry-run")
    assert calls == [("indeed", False, 3), "stats", ("manfred", False), "stats", ("contacts", True), "stats"]


def test_all_en_orden_y_sin_sap_ni_generic(calls, monkeypatch):
    _run(monkeypatch, "--source", "all")
    assert calls == [
        "seed", ("tecnoempleo", False, 3), ("indeed", False, 3), ("manfred", False), ("contacts", False), "stats",
    ]


def test_track(calls, monkeypatch):
    _run(monkeypatch, "--track", "sap", "--max-pages", "2")
    assert calls == [("track", "sap", False, 2), "stats"]


def test_source_sap_da_error_con_alternativa(calls, monkeypatch, capsys):
    with pytest.raises(SystemExit) as exc:
        _run(monkeypatch, "--source", "sap")
    assert exc.value.code != 0
    assert "--track sap" in capsys.readouterr().err
    assert calls == []


def test_track_desconocido_da_error_con_los_disponibles(calls, monkeypatch, capsys):
    with pytest.raises(SystemExit):
        _run(monkeypatch, "--track", "nada")
    err = capsys.readouterr().err
    assert "nada" in err and "sap" in err and "ia_dev" in err
    assert calls == []


def test_track_aislado_no_se_puede_lanzar_con_track(calls, monkeypatch, capsys):
    with pytest.raises(SystemExit):
        _run(monkeypatch, "--track", "generic")
    assert "generic" in capsys.readouterr().err


def test_track_y_source_a_la_vez_da_error(calls, monkeypatch):
    with pytest.raises(SystemExit):
        _run(monkeypatch, "--track", "sap", "--source", "seed")


def test_generic_con_sus_opciones(calls, monkeypatch):
    _run(monkeypatch, "--source", "generic", "--generic-sources", "infojobs, indeed", "--max-indeed-credits", "50")
    assert calls == [("generic", False, 3, ["infojobs", "indeed"], 50), "stats"]


def test_resolve_websites(calls, monkeypatch):
    _run(monkeypatch, "--source", "resolve-websites", "--limit", "10", "--dry-run")
    assert calls == [("resolve", True, 10), "stats"]


def test_linkedin_login_termina_sin_estadisticas(calls, monkeypatch):
    _run(monkeypatch, "--source", "linkedin-login")
    assert calls == ["login"]


def _fake_track_sources(monkeypatch, seen, infojobs_falla=False):
    import scraper.company_direct
    import scraper.computrabajo
    import scraper.infojobs
    import scraper.linkedin_jobs
    import scraper.tecnoempleo

    class FakeTecnoempleo:
        async def scrape_keyword(self, kw, loc, pages):
            seen.append(("tecnoempleo", kw, loc, pages))
            return []

    async def infojobs(keywords, *a, **k):
        seen.append(("infojobs", list(keywords)))
        if infojobs_falla:
            raise RuntimeError("caída de InfoJobs")
        return []

    async def computrabajo(keywords, *a, **k):
        seen.append(("computrabajo", list(keywords)))
        return []

    async def company_direct(dry_run):
        seen.append(("company_direct",))
        return 0, 0

    async def linkedin(*a, **k):
        seen.append(("linkedin", k.get("track")))
        return []

    monkeypatch.setattr(scraper.tecnoempleo, "TecnoempleoScraper", FakeTecnoempleo)
    monkeypatch.setattr(scraper.infojobs, "run_infojobs", infojobs)
    monkeypatch.setattr(scraper.computrabajo, "run_computrabajo", computrabajo)
    monkeypatch.setattr(scraper.company_direct, "run_company_direct", company_direct)
    monkeypatch.setattr(scraper.linkedin_jobs, "run_linkedin_jobs", linkedin)


def test_track_lanza_las_fuentes_con_las_keywords_del_track(monkeypatch):
    import asyncio
    from search_config import get_config

    seen = []
    _fake_track_sources(monkeypatch, seen)
    asyncio.run(runner.run_track_source("sap", True, 2))

    cfg = get_config()
    keywords = cfg.track("sap").search_keywords
    locations = cfg.sources["tecnoempleo"]["locations"]
    tecno = [c for c in seen if c[0] == "tecnoempleo"]
    assert tecno == [("tecnoempleo", kw, loc, 2) for kw in keywords for loc in locations]
    assert ("infojobs", keywords) in seen
    assert ("computrabajo", keywords) in seen
    assert ("company_direct",) in seen
    assert ("linkedin", "sap") in seen


def test_track_un_fallo_en_una_fuente_no_frena_a_las_demas(monkeypatch, caplog):
    import asyncio

    seen = []
    _fake_track_sources(monkeypatch, seen, infojobs_falla=True)
    with caplog.at_level("ERROR"):
        asyncio.run(runner.run_track_source("sap", True, 1))

    names = {c[0] for c in seen}
    assert {"infojobs", "computrabajo", "company_direct", "linkedin"} <= names
    assert "InfoJobs failed: caída de InfoJobs" in caplog.text


def test_fuente_sin_config_usa_vacio_y_no_rompe(monkeypatch):
    import asyncio
    import copy
    import scraper.company_direct
    import scraper.tecnoempleo
    from search_config import get_config, set_config, source_settings

    original = get_config()
    set_config(original.model_copy(update={"sources": {}}))
    try:
        assert source_settings("tecnoempleo") == {}

        class FakeScraper:
            async def scrape_keyword(self, *a):
                raise AssertionError("sin keywords no debe scrapear")

        monkeypatch.setattr(scraper.tecnoempleo, "TecnoempleoScraper", FakeScraper)
        assert asyncio.run(scraper.tecnoempleo.run_tecnoempleo(max_pages=1)) == []
        assert asyncio.run(scraper.company_direct.run_company_direct(dry_run=True)) == (0, 0)
        assert not scraper.company_direct._is_sap_offer("SAP BTP", "")
    finally:
        set_config(original)


def test_linkedin_searches_filtra_por_track():
    from scraper.linkedin_jobs import linkedin_searches

    todas = linkedin_searches()
    sap = linkedin_searches("sap")
    ia = linkedin_searches("ia_dev")
    assert len(todas) == 13 and len(sap) == 7 and len(ia) == 6
    assert all(s["track"] == "sap" for s in sap)


def test_linkedin_search_sin_track_aplica_a_todos():
    from search_config import get_config, set_config
    from scraper.linkedin_jobs import linkedin_searches

    original = get_config()
    srcs = {"linkedin": {"searches": [{"keywords": "a", "location": "x"}, {"keywords": "b", "location": "y", "track": "sap"}]}}
    set_config(original.model_copy(update={"sources": srcs}))
    try:
        assert [s["keywords"] for s in linkedin_searches("ia_dev")] == ["a"]
        assert [s["keywords"] for s in linkedin_searches("sap")] == ["a", "b"]
    finally:
        set_config(original)
