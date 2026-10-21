import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

SAMPLE_CARD = """
<article class="box_offer">
  <h2><a href="/oferta-de-trabajo/sap-consultant-villanova-12345">Consultor SAP BTP</a></h2>
  <p class="fs16">Consultora SAP España SL</p>
  <span class="fs13">Villanova</span>
  <p class="description">Proyecto S/4HANA público, viajes ocasionales</p>
</article>
"""

def test_slugify_spaces_and_special_chars():
    from scraper.computrabajo import _slugify
    assert _slugify("SAP Public Cloud") == "sap-public-cloud"
    assert _slugify("S/4HANA") == "s-4hana"

def test_parse_card_returns_expected_fields():
    from scraper.computrabajo import _parse_card_html
    result = _parse_card_html(SAMPLE_CARD, base_url="https://www.computrabajo.es")
    assert result is not None
    assert result["title"] == "Consultor SAP BTP"
    assert result["company_name"] == "Consultora SAP España SL"
    assert result["location"] == "Villanova"
    assert result["source"] == "computrabajo"

def test_parse_card_returns_none_without_link():
    from scraper.computrabajo import _parse_card_html
    result = _parse_card_html("<article></article>", base_url="https://www.computrabajo.es")
    assert result is None
