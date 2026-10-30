"""
scraper/infojobs.py — Scrapes job offers from InfoJobs.net.
URL: /jobsearch/search-results/list.xhtml?keyword={kw}

Primary card selector: .ij-OfferCardContent
If selectors stop working, inspect with:
  chromium --headless --dump-dom 'https://www.infojobs.net/jobsearch/...'
"""
import re
import asyncio
import logging
from bs4 import BeautifulSoup
from urllib.parse import urlencode
from scraper.base import BaseScraper, raise_if_all_failed
from search_config import source_settings

logger = logging.getLogger(__name__)

INFOJOBS_BASE = "https://www.infojobs.net"
SALARY_PATTERN = re.compile(r"(\d[\d.,]+)\s*€")


def _parse_card_html(html: str, base_url: str = INFOJOBS_BASE) -> dict | None:
    soup = BeautifulSoup(html, "html.parser")

    title_el = soup.select_one("h2.ij-OfferCardContent-description-title a")
    if not title_el:
        return None
    title = title_el.get_text(strip=True)
    href = title_el.get("href", "")
    # InfoJobs uses protocol-relative URLs like //www.infojobs.net/...
    if href.startswith("//"):
        href = "https:" + href
    url = href if href.startswith("http") else None
    if not url:
        return None

    company_el = soup.select_one("h3.ij-OfferCardContent-description-subtitle a")
    company_name = company_el.get_text(strip=True) if company_el else None

    # Location is the first <li> in the first description list
    loc_el = soup.select_one("ul.ij-OfferCardContent-description-list li:first-child")
    location = loc_el.get_text(strip=True) if loc_el else None

    desc_el = soup.select_one("p[class*='ij-OfferCardContent-description-description']")
    description = desc_el.get_text(strip=True) if desc_el else None

    salary_match = SALARY_PATTERN.search(soup.get_text())
    salary_min = int(salary_match.group(1).replace(".", "").replace(",", "")) if salary_match else None

    return {
        "title": title,
        "url": url,
        "company_name": company_name,
        "location": location,
        "description": description,
        "salary_min": salary_min,
        "salary_max": None,
        "tech_stack": None,
        "source": "infojobs",
    }


_UNSET = object()  # "not passed by the caller" (None = national search on purpose)


def build_search_url(keyword: str, page_num: int, normalized_location: str | None,
                     province_id: str | None) -> str:
    params = {"keyword": keyword, "page": page_num}
    # normalizedLocation NO filtra de verdad en InfoJobs (devuelve toda España);
    # provinceIds sí. Sin ninguno: búsqueda nacional.
    if province_id:
        params["provinceIds"] = province_id
    elif normalized_location:
        params["normalizedLocation"] = normalized_location
    return f"{INFOJOBS_BASE}/jobsearch/search-results/list.xhtml?{urlencode(params)}"


class InfoJobsScraper(BaseScraper):
    def __init__(self):
        super().__init__(delay_min=3.0, delay_max=8.0)

    async def scrape_keyword(
        self,
        keyword: str,
        max_pages: int = 3,
        normalized_location: str | None = None,
        province_id: str | None = None,
        scroll: bool = False,
    ) -> list[dict]:
        offers = []
        async with self as scraper:
            page = await scraper.new_page()
            for page_num in range(1, max_pages + 1):
                url = build_search_url(keyword, page_num, normalized_location, province_id)
                logger.info("InfoJobs page %d: %s", page_num, url)
                if not await scraper.fetch_with_retry(page, url):
                    break

                # Wait for JS-rendered cards (InfoJobs is a SPA)
                try:
                    await page.wait_for_selector(".ij-OfferCardContent", timeout=15000)
                except Exception:
                    logger.info("InfoJobs: no cards on page %d (timeout waiting for selector)", page_num)
                    break

                if scroll:  # la lista carga las tarjetas de forma perezosa
                    for _ in range(6):
                        await page.mouse.wheel(0, 4000)
                        await asyncio.sleep(1.2)
                cards = await page.query_selector_all(
                    ".ij-OfferCardContent, div[class*='OfferCard'], article[class*='offer']"
                )
                if not cards:
                    logger.info("InfoJobs: no cards on page %d", page_num)
                    break

                for card in cards:
                    html = await card.inner_html()
                    offer = _parse_card_html(html)
                    if offer:
                        offers.append(offer)

                logger.info("InfoJobs page %d: %d cards", page_num, len(cards))
                await scraper.random_delay()

                next_btn = await page.query_selector(
                    "a[rel='next'], .pagination-next a, [aria-label*='siguiente']"
                )
                if not next_btn:
                    break
        return offers


async def run_infojobs(
    keywords: list[str],
    max_pages: int = 3,
    normalized_location=_UNSET,
    province_id=_UNSET,
    scroll: bool = False,
) -> list[dict]:
    """Location filters not passed by the caller come from `sources.infojobs`
    (`normalized_location`, `province_id`); an explicit None means national search."""
    settings = source_settings("infojobs")
    if normalized_location is _UNSET:
        normalized_location = settings.get("normalized_location")
    if province_id is _UNSET:
        province_id = settings.get("province_id")
    if province_id is not None:
        province_id = str(province_id)
    scraper = InfoJobsScraper()
    seen: set[str] = set()
    all_offers: list[dict] = []
    if not keywords:
        logger.warning("InfoJobs: sin keywords (sources.infojobs.keywords o search_keywords del track en "
                       "jobhunter.yaml); no hay nada que buscar")
    failures = 0
    for kw in keywords:
        logger.info("InfoJobs keyword: %s", kw)
        try:
            for offer in await scraper.scrape_keyword(kw, max_pages, normalized_location, province_id, scroll):
                if offer.get("url") and offer["url"] not in seen:
                    seen.add(offer["url"])
                    all_offers.append(offer)
        except Exception as e:
            failures += 1
            logger.error("InfoJobs keyword '%s' failed: %s", kw, e)
    raise_if_all_failed("InfoJobs", len(keywords), failures)
    logger.info("InfoJobs total: %d unique offers", len(all_offers))
    return all_offers
