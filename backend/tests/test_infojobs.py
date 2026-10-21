import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

SAMPLE_CARD = """
<div class="ij-OfferCardContent">
  <h2 class="ij-OfferCardContent-description-title">
    <a href="//www.infojobs.net/empleo/sap-consultant_oferta_12345.aspx">SAP Consultant</a>
  </h2>
  <h3 class="ij-OfferCardContent-description-subtitle"><a>Empresa Tech SL</a></h3>
  <ul class="ij-OfferCardContent-description-list"><li>Villanova</li><li>Jornada completa</li></ul>
  <p class="ij-OfferCardContent-description-description">Buscamos consultor SAP BTP con experiencia en S/4HANA</p>
</div>
"""

def test_parse_card_returns_expected_fields():
    from scraper.infojobs import _parse_card_html
    result = _parse_card_html(SAMPLE_CARD, base_url="https://www.infojobs.net")
    assert result is not None
    assert result["title"] == "SAP Consultant"
    assert result["company_name"] == "Empresa Tech SL"
    assert result["location"] == "Villanova"
    assert "SAP BTP" in result["description"]
    assert result["url"].startswith("https://")
    assert result["source"] == "infojobs"

def test_parse_card_returns_none_on_missing_title():
    from scraper.infojobs import _parse_card_html
    result = _parse_card_html("<div></div>", base_url="https://www.infojobs.net")
    assert result is None
