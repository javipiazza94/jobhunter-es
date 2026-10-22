import asyncio
from pathlib import Path
from unittest.mock import patch

import pytest

from scraper import computrabajo
from scraper import robots_gate
from scraper.sources import computrabajo as computrabajo_source


_FIXTURES_DIR = Path(__file__).parent / "fixtures" / "sources"


def test_country_base_url_building():
    assert computrabajo.country_base_url("es") == "https://www.computrabajo.es"
    assert computrabajo.country_base_url("mx") == "https://mx.computrabajo.com"
    assert computrabajo.country_base_url("co") == "https://co.computrabajo.com"
    assert computrabajo.country_base_url("ar") == "https://ar.computrabajo.com"
    assert computrabajo.country_base_url("pe") == "https://pe.computrabajo.com"
    assert computrabajo.country_base_url("cl") == "https://cl.computrabajo.com"
    # Fallback para país no listado expresamente
    assert computrabajo.country_base_url("uy") == "https://uy.computrabajo.com"
    assert computrabajo.country_base_url("") == "https://www.computrabajo.es"
    assert computrabajo.country_base_url(None) == "https://www.computrabajo.es"


def test_source_spec_start_url_for_country():
    spec = computrabajo_source.SPEC
    assert spec.start_url_for({"country": "mx"}) == "https://mx.computrabajo.com"
    assert spec.start_url_for({"country": "co"}) == "https://co.computrabajo.com"
    assert spec.start_url_for({"country": "es"}) == "https://www.computrabajo.es"
    assert spec.start_url_for({}) == "https://www.computrabajo.es"
    assert spec.start_url_for(None) == "https://www.computrabajo.es"


def test_parse_cards_per_country():
    es_html = (_FIXTURES_DIR / "computrabajo_es.html").read_text(encoding="utf-8")
    mx_html = (_FIXTURES_DIR / "computrabajo_mx.html").read_text(encoding="utf-8")
    co_html = (_FIXTURES_DIR / "computrabajo_co.html").read_text(encoding="utf-8")

    card_es = computrabajo._parse_card_html(es_html, base_url=computrabajo.country_base_url("es"))
    assert card_es is not None
    assert card_es["url"] == "https://www.computrabajo.es/oferta-de-trabajo/desarrollador-python-madrid-1001"
    assert card_es["company_name"] == "Tech Iberia SL"
    assert card_es["location"] == "Madrid"

    card_mx = computrabajo._parse_card_html(mx_html, base_url=computrabajo.country_base_url("mx"))
    assert card_mx is not None
    assert card_mx["url"] == "https://mx.computrabajo.com/oferta-de-trabajo/ingeniero-datos-cdmx-2002"
    assert card_mx["company_name"] == "Soluciones Cloud MX"
    assert card_mx["location"] == "Ciudad de México"

    card_co = computrabajo._parse_card_html(co_html, base_url=computrabajo.country_base_url("co"))
    assert card_co is not None
    assert card_co["url"] == "https://co.computrabajo.com/oferta-de-trabajo/desarrollador-backend-bogota-3003"
    assert card_co["company_name"] == "Innovación Andina SAS"
    assert card_co["location"] == "Bogotá D.C."


def test_robots_gate_refusal_and_exemptions():
    with patch("automation.robots_check.gate", return_value=(1, "Disallowed")):
        # URL bloqueada lanza RobotsRefused
        with pytest.raises(robots_gate.RobotsRefused, match="robots.txt no permite"):
            robots_gate.check_robots("https://mx.computrabajo.com", "computrabajo")

        # LinkedIn sin acknowledge también lanza
        with pytest.raises(robots_gate.RobotsRefused):
            robots_gate.check_robots("https://www.linkedin.com/jobs", "linkedin", is_acknowledged=False)

        # LinkedIn con acknowledge está exenta
        assert robots_gate.check_robots("https://www.linkedin.com/jobs", "linkedin", is_acknowledged=True) is True


@pytest.mark.asyncio
async def test_runner_skips_source_on_robots_refusal(caplog):
    from scraper import runner

    with patch("scraper.robots_gate.check_robots", side_effect=robots_gate.RobotsRefused("Disallowed test")):
        # run_source para una fuente html/playwright
        with caplog.at_level("WARNING"):
            await runner.run_source("computrabajo", dry_run=True, max_pages=1)
        assert any("omitida porque" in record.message for record in caplog.records)
