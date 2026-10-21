"""
scraper/company_direct.py — Scrapes career pages of known SAP consulting firms.
For each company in `sources.company_direct.companies` (jobhunter.yaml): extracts SAP job links + emails/forms.
"""
import logging
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from scraper.base import BaseScraper
from scraper.contact_extractor import ContactExtractorScraper
from database import get_conn, upsert_company, upsert_job_offer, upsert_contact
from automation.filter_engine import score_offer
from search_config import get_config, source_settings

logger = logging.getLogger(__name__)

_JOB_URL_HINTS = ["/job", "/oferta", "/empleo", "/vacante", "/position", "/career", "/oportunidad"]


def _is_sap_offer(title: str, description: str) -> bool:
    combined = (title + " " + description).lower()
    return any(kw.lower() in combined for kw in source_settings("company_direct").get("keywords", []))


def _parse_job_links(html: str, base_url: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    results = []
    seen: set[str] = set()
    for a in soup.find_all("a", href=True):
        href = a["href"]
        text = a.get_text(strip=True)
        if not text or len(text) < 5:
            continue
        if any(hint in href.lower() for hint in _JOB_URL_HINTS):
            full_url = urljoin(base_url, href)
            if full_url not in seen:
                seen.add(full_url)
                results.append({"title": text, "url": full_url})
    return results


class CompanyDirectScraper(BaseScraper):
    def __init__(self):
        super().__init__(delay_min=3.0, delay_max=8.0)

    async def scrape_company(self, company: dict) -> list[dict]:
        offers = []
        async with self as scraper:
            page = await scraper.new_page()
            if not await scraper.fetch_with_retry(page, company["careers_url"]):
                logger.warning("Could not fetch %s", company["name"])
                return offers
            html = await page.content()
            for link in _parse_job_links(html, company["careers_url"]):
                if _is_sap_offer(link["title"], ""):
                    offers.append({
                        "title": link["title"],
                        "url": link["url"],
                        "company_name": company["name"],
                        "location": None,
                        "description": None,
                        "salary_min": None,
                        "salary_max": None,
                        "tech_stack": None,
                        "source": "company_direct",
                    })
            await scraper.random_delay()
        return offers


async def run_company_direct(dry_run: bool = False) -> tuple[int, int]:
    total_offers = 0
    total_contacts = 0
    conn = get_conn()
    scraper = CompanyDirectScraper()
    extractor = ContactExtractorScraper()

    for company in source_settings("company_direct").get("companies", []):
        logger.info("Company direct: %s", company["name"])
        try:
            cid = upsert_company(conn, {
                "name": company["name"],
                "careers_url": company["careers_url"],
                "source": "company_direct",
            })

            offers = await scraper.scrape_company(company)
            if not dry_run:
                for offer in offers:
                    sc = score_offer(offer)
                    upsert_job_offer(conn, {
                        **offer,
                        "company_id": cid,
                        "is_relevant": sc >= get_config().scoring.min_relevance,
                        "relevance_score": sc,
                    })
            total_offers += len(offers)
            logger.info("  %s: %d SAP offers", company["name"], len(offers))

            if not dry_run:
                contacts = await extractor.extract_for_company(
                    cid, company["careers_url"], company["careers_url"]
                )
                for c in contacts:
                    upsert_contact(conn, c)
                total_contacts += len(contacts)
        except Exception as e:
            logger.error("company_direct failed for %s: %s", company["name"], e)

    conn.close()
    return total_offers, total_contacts
