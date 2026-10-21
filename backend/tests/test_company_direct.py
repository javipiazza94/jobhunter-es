import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))


def test_is_sap_offer_detects_keywords():
    from scraper.company_direct import _is_sap_offer
    assert _is_sap_offer("SAP BTP consultant role", "") is True
    assert _is_sap_offer("ABAP developer needed", "") is True
    assert _is_sap_offer("Java backend engineer", "") is False
    assert _is_sap_offer("", "Experience with S/4HANA required") is True

def test_is_sap_offer_case_insensitive():
    from scraper.company_direct import _is_sap_offer
    assert _is_sap_offer("sap fiori consultant", "") is True
    assert _is_sap_offer("Consultor SAP MM", "") is True

def test_parse_job_links_filters_by_hint():
    from scraper.company_direct import _parse_job_links
    html = """
    <a href="/job/sap-consultant">SAP Consultant</a>
    <a href="/blog/news">Blog post</a>
    <a href="/vacante/abap-developer">ABAP Developer</a>
    """
    links = _parse_job_links(html, "https://example.com")
    urls = [l["url"] for l in links]
    assert any("sap-consultant" in u for u in urls)
    assert any("abap-developer" in u for u in urls)
    assert not any("blog" in u for u in urls)
