"""Un scraper que falla del todo no se confunde con «no hay ofertas»; los fallos parciales se siguen tolerando."""
import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from scraper import computrabajo, indeed, infojobs, runner  # noqa: E402
from scraper.base import SourceUnavailable, raise_if_all_failed  # noqa: E402

from tests.test_runner_dispatch import _fake_track_sources  # noqa: E402

OFFER = {"url": "https://example.com/oferta-1", "title": "Dev"}


def test_si_fallan_todas_las_busquedas_se_lanza_source_unavailable():
    with pytest.raises(SourceUnavailable, match="Demo.*3"):
        raise_if_all_failed("Demo", attempts=3, failures=3)


@pytest.mark.parametrize("attempts,failures", [(0, 0), (3, 0), (3, 2)])
def test_sin_intentos_o_con_fallos_parciales_no_se_lanza(attempts, failures):
    raise_if_all_failed("Demo", attempts=attempts, failures=failures)


@pytest.mark.parametrize("module,runner_name,scraper_cls", [
    (computrabajo, "run_computrabajo", "ComputrabajoScraper"),
    (infojobs, "run_infojobs", "InfoJobsScraper"),
])
def test_scraper_de_palabras_clave_falla_si_todas_fallan(monkeypatch, module, runner_name, scraper_cls):
    async def always_down(self, *_args, **_kwargs):
        raise RuntimeError("portal caído")

    monkeypatch.setattr(getattr(module, scraper_cls), "scrape_keyword", always_down)

    with pytest.raises(SourceUnavailable):
        asyncio.run(getattr(module, runner_name)(["python", "sap"]))


@pytest.mark.parametrize("module,runner_name,scraper_cls", [
    (computrabajo, "run_computrabajo", "ComputrabajoScraper"),
    (infojobs, "run_infojobs", "InfoJobsScraper"),
])
def test_scraper_de_palabras_clave_tolera_un_fallo_parcial(monkeypatch, module, runner_name, scraper_cls):
    async def first_fails(self, keyword, *_args, **_kwargs):
        if keyword == "python":
            raise RuntimeError("una búsqueda falla")
        return [OFFER]

    monkeypatch.setattr(getattr(module, scraper_cls), "scrape_keyword", first_fails)

    offers = asyncio.run(getattr(module, runner_name)(["python", "sap"]))

    assert offers == [OFFER]


def test_indeed_falla_si_todas_las_busquedas_fallan(monkeypatch):
    def down(*_args, **_kwargs):
        raise RuntimeError("ScraperAPI caído")

    monkeypatch.setattr(indeed, "scrape_indeed_keyword", down)
    monkeypatch.setattr("secrets_store.get_secret", lambda _name: "clave-valida")

    with pytest.raises(SourceUnavailable):
        asyncio.run(indeed.run_indeed(["python"], ["Madrid"]))


def test_indeed_sin_clave_de_api_falla_en_vez_de_devolver_vacio(monkeypatch):
    monkeypatch.setattr("secrets_store.get_secret", lambda _name: "")
    monkeypatch.setattr("config.SCRAPERAPI_KEY", "")

    with pytest.raises(SourceUnavailable, match="SCRAPERAPI_KEY"):
        asyncio.run(indeed.run_indeed(["python"], ["Madrid"]))


def test_run_track_source_sigue_con_las_demas_fuentes_y_al_final_avisa_de_la_que_fallo(monkeypatch):
    seen = []
    _fake_track_sources(monkeypatch, seen, infojobs_falla=True)

    with pytest.raises(runner.SourcesFailed) as caught:
        asyncio.run(runner.run_track_source("sap", True, 1))

    assert {"computrabajo", "company_direct", "linkedin"} <= {call[0] for call in seen}  # el aislamiento se mantiene
    assert caught.value.labels == ["InfoJobs"]


def test_run_track_source_sin_fallos_no_lanza(monkeypatch):
    seen = []
    _fake_track_sources(monkeypatch, seen)

    asyncio.run(runner.run_track_source("sap", True, 1))
