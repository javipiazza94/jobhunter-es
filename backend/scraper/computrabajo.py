"""
scraper/computrabajo.py — Scrapes job offers from Computrabajo.es.
URL: /trabajo-de-{keyword-slug}?l={location}
Falls back to national search if location search fails.

Primary card selector: article.box_offer
"""
import re
import logging
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from scraper.base import BaseScraper
from search_config import source_settings

logger = logging.getLogger(__name__)

COMPUTRABAJO_BASE = "https://www.computrabajo.es"

COUNTRY_DOMAINS: dict[str, str] = {
    "es": "https://www.computrabajo.es",
    "mx": "https://mx.computrabajo.com",
    "co": "https://co.computrabajo.com",
    "ar": "https://ar.computrabajo.com",
    "pe": "https://pe.computrabajo.com",
    "cl": "https://cl.computrabajo.com",
    "uy": "https://uy.computrabajo.com",
    "ve": "https://ve.computrabajo.com",
    "ec": "https://ec.computrabajo.com",
    "cr": "https://cr.computrabajo.com",
    "pa": "https://pa.computrabajo.com",
    "gt": "https://gt.computrabajo.com",
    "sv": "https://sv.computrabajo.com",
    "hn": "https://hn.computrabajo.com",
    "ni": "https://ni.computrabajo.com",
    "do": "https://do.computrabajo.com",
}


def country_base_url(country: str = "es") -> str:
    c = (country or "es").strip().lower()
    return COUNTRY_DOMAINS.get(c, f"https://{c}.computrabajo.com")


def _slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def _parse_card_html(html: str, base_url: str = COMPUTRABAJO_BASE) -> dict | None:
    soup = BeautifulSoup(html, "html.parser")

    link_el = soup.select_one("h2 a, h3 a, .title_offer a")
    if not link_el:
        return None
    title = link_el.get_text(strip=True)
    href = link_el.get("href", "")
    url = urljoin(base_url, href) if href else None
    if not url:
        return None

    company_el = soup.select_one(".fs16, .company, [class*='company']")
    company_name = company_el.get_text(strip=True) if company_el else None

    location_el = soup.select_one(".fs13, .location, [class*='location']")
    location = location_el.get_text(strip=True) if location_el else None

    desc_el = soup.select_one(".description, p:not(.fs16):not(.fs13)")
    description = desc_el.get_text(strip=True) if desc_el else None

    return {
        "title": title,
        "url": url,
        "company_name": company_name,
        "location": location,
        "description": description,
        "salary_min": None,
        "salary_max": None,
        "tech_stack": None,
        "source": "computrabajo",
    }


def _location_param(location: str | None) -> str:
    """`?l=<slug>` from the explicit location or `sources.computrabajo.location`; "" = national search."""
    loc = location or source_settings("computrabajo").get("location")
    return f"?l={_slugify(loc)}" if loc else ""


class ComputrabajoScraper(BaseScraper):
    def __init__(self, country: str = "es"):
        super().__init__(delay_min=3.0, delay_max=8.0)
        self.country = (country or "es").strip().lower()
        self.base_url = country_base_url(self.country)

    async def scrape_keyword(self, keyword: str, max_pages: int = 3, location: str | None = None) -> list[dict]:
        offers = []
        slug = _slugify(keyword)
        loc_param = _location_param(location)
        async with self as scraper:
            page = await scraper.new_page()
            for page_num in range(1, max_pages + 1):
                page_suffix = f"-p{page_num}" if page_num > 1 else ""
                url = f"{self.base_url}/trabajo-de-{slug}{page_suffix}{loc_param}"
                logger.info("Computrabajo page %d: %s", page_num, url)
                ok = await scraper.fetch_with_retry(page, url)
                if not ok and loc_param:
                    url_national = f"{self.base_url}/trabajo-de-{slug}{page_suffix}"
                    if not await scraper.fetch_with_retry(page, url_national):
                        break
                elif not ok:
                    break

                cards = await page.query_selector_all(
                    "article.box_offer, div[class*='offer_box'], article[class*='offer']"
                )
                if not cards:
                    break

                for card in cards:
                    offer = _parse_card_html(await card.inner_html(), base_url=self.base_url)
                    if offer:
                        offers.append(offer)

                logger.info("Computrabajo page %d: %d cards", page_num, len(cards))
                await scraper.random_delay()

                next_btn = await page.query_selector("a[rel='next'], .next a")
                if not next_btn:
                    break
        return offers


async def run_computrabajo(
    keywords: list[str], max_pages: int = 3, location: str | None = None, country: str = "es"
) -> list[dict]:
    scraper = ComputrabajoScraper(country=country)
    seen: set[str] = set()
    all_offers: list[dict] = []
    if not keywords:
        logger.warning("Computrabajo: sin keywords (search_keywords del track en jobhunter.yaml); "
                       "no hay nada que buscar")
    for kw in keywords:
        logger.info("Computrabajo keyword: %s", kw)
        try:
            for offer in await scraper.scrape_keyword(kw, max_pages, location=location):
                if offer.get("url") and offer["url"] not in seen:
                    seen.add(offer["url"])
                    all_offers.append(offer)
        except Exception as e:
            logger.error("Computrabajo keyword '%s' failed: %s", kw, e)
    logger.info("Computrabajo total: %d unique offers", len(all_offers))
    return all_offers
