"""Los filtros de ubicación de Tecnoempleo/InfoJobs/Computrabajo salen de `sources.<fuente>` (jobhunter.yaml),
no de ids fijados en código."""
import asyncio
from contextlib import contextmanager
from urllib.parse import parse_qs, urlparse

import scraper.infojobs as infojobs
from scraper.computrabajo import _location_param
from scraper.tecnoempleo import build_search_url
from search_config import get_config, set_config


@contextmanager
def _sources(**sources):
    original = get_config()
    set_config(original.model_copy(update={"sources": {**original.sources, **sources}}))
    try:
        yield
    finally:
        set_config(original)


def _query(url: str) -> dict:
    return parse_qs(urlparse(url).query)


# --- Tecnoempleo ---------------------------------------------------------------------------------

def test_tecnoempleo_usa_province_ids_de_la_config():
    with _sources(tecnoempleo={"keywords": ["python"], "locations": ["Villanova"],
                               "province_ids": {"villanova": "999"}}):
        q = _query(build_search_url("python", "Villanova", 1))
    assert q["pr"] == [",999,"]
    assert q["te"] == ["python"]


def test_tecnoempleo_sin_id_configurado_busca_sin_filtro_de_provincia():
    with _sources(tecnoempleo={"keywords": ["python"], "locations": ["Villanova"]}):
        q = _query(build_search_url("python", "Villanova", 2))
    assert "pr" not in q
    assert q["te"] == ["python"] and q["pagina"] == ["2"]


def test_tecnoempleo_no_trae_ids_de_provincia_inventados():
    with _sources(tecnoempleo={}):
        for city in ("Madrid", "Barcelona", "Valencia"):
            assert "pr" not in _query(build_search_url("python", city, 1))


def test_tecnoempleo_remoto_sigue_siendo_keyword():
    with _sources(tecnoempleo={}):
        q = _query(build_search_url("python", "remoto", 1))
    assert "pr" not in q and q["te"] == ["python remoto"]


# --- InfoJobs ------------------------------------------------------------------------------------

def _capture_infojobs(monkeypatch):
    calls = []

    async def fake_scrape(self, keyword, max_pages=3, normalized_location=None, province_id=None, scroll=False):
        calls.append((normalized_location, province_id))
        return []

    monkeypatch.setattr(infojobs.InfoJobsScraper, "scrape_keyword", fake_scrape)
    return calls


def test_infojobs_toma_ubicacion_y_provincia_de_la_config(monkeypatch):
    calls = _capture_infojobs(monkeypatch)
    with _sources(infojobs={"keywords": ["python"], "normalized_location": "villanova", "province_id": "77"}):
        asyncio.run(infojobs.run_infojobs(["python"], 1))
    assert calls == [("villanova", "77")]


def test_infojobs_sin_config_busca_a_nivel_nacional(monkeypatch):
    calls = _capture_infojobs(monkeypatch)
    with _sources(infojobs={"keywords": ["python"]}):
        asyncio.run(infojobs.run_infojobs(["python"], 1))
    assert calls == [(None, None)]


def test_infojobs_respeta_valores_explicitos_del_llamante(monkeypatch):
    calls = _capture_infojobs(monkeypatch)
    with _sources(infojobs={"normalized_location": "villanova", "province_id": "77"}):
        asyncio.run(infojobs.run_infojobs(["python"], 1, None, "12"))
        asyncio.run(infojobs.run_infojobs(["python"], 1, None, None))  # búsqueda nacional pedida a propósito
    assert calls == [(None, "12"), (None, None)]


def test_infojobs_url_usa_provincia_antes_que_ubicacion():
    q = _query(infojobs.build_search_url("python", 1, "villanova", "77"))
    assert q["provinceIds"] == ["77"] and "normalizedLocation" not in q
    q = _query(infojobs.build_search_url("python", 1, "villanova", None))
    assert q["normalizedLocation"] == ["villanova"]


# --- Computrabajo --------------------------------------------------------------------------------

def test_computrabajo_con_location_en_config_anade_parametro():
    with _sources(computrabajo={"location": "Costa Lira"}):
        assert _location_param(None) == "?l=costa-lira"


def test_computrabajo_sin_location_no_anade_parametro():
    with _sources(computrabajo={}):
        assert _location_param(None) == ""


def test_computrabajo_location_explicita_gana_a_la_config():
    with _sources(computrabajo={"location": "Costa Lira"}):
        assert _location_param("Villanova") == "?l=villanova"
