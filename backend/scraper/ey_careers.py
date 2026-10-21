"""
scraper/ey_careers.py — Scrapes EY's SuccessFactors-based careers site directly.

Verified 2026-09-15 against the live site (careers.ey.com/ey/search/):
  - The combined search box and #title/#location form fields do NOT reliably
    take effect when filled via automation (their JS state doesn't pick up
    programmatic .fill()) — navigating directly to the URL with `q` and
    `location` query params DOES work correctly.
  - `location=Spain` is unusable: it text-matches "Port Of Spain, TT"
    (Trinidad & Tobago) before any real Spain result — search by real Spanish
    city names instead (EY roles are concentrated in regional hubs; general
    EY consulting roles also show up in Madrid/Barcelona).
  - Cookie consent banner must be accepted once per page load or the page
    stays on the consent screen.
  - Result rows: tr.data-row > td.colTitle a.jobTitle-link (title/href) and
    td.colLocation span.jobLocation (location text, e.g. "Malaga, ES, 29590").
"""
import logging
from urllib.parse import quote

from scraper.base import BaseScraper

logger = logging.getLogger(__name__)

EY_SEARCH_BASE = "https://careers.ey.com/ey/search/"
EY_LOCATIONS = ["Malaga", "Madrid", "Barcelona"]

_COOKIE_BUTTON_TEXTS = ["Accept All Cookies", "Aceptar todas"]


async def _accept_cookies(page) -> None:
    for text in _COOKIE_BUTTON_TEXTS:
        try:
            btn = page.get_by_text(text, exact=False)
            if await btn.count() > 0:
                await btn.first.click(timeout=3000)
                return
        except Exception:
            continue


async def _scrape_location(scraper: BaseScraper, keyword: str, location: str) -> list[dict]:
    page = await scraper.new_page()
    url = f"{EY_SEARCH_BASE}?q={quote(keyword)}&location={quote(location)}"
    if not await scraper.fetch_with_retry(page, url):
        await page.close()
        return []

    await _accept_cookies(page)
    await page.wait_for_timeout(3000)

    offers = []
    rows = await page.query_selector_all("tr.data-row")
    for row in rows:
        link = await row.query_selector("a.jobTitle-link")
        loc_el = await row.query_selector("span.jobLocation")
        if not link:
            continue
        title = (await link.inner_text()).strip()
        href = await link.get_attribute("href")
        loc_text = (await loc_el.inner_text()).strip() if loc_el else location
        if not title or not href:
            continue
        offers.append({
            "title": title,
            "company_name": "EY GDS Spain" if "malaga" in loc_text.lower() else "EY",
            "location": loc_text,
            "url": f"https://careers.ey.com{href}" if href.startswith("/") else href,
            "description": None,
            "salary_min": None,
            "salary_max": None,
            "tech_stack": None,
            "source": "ey_careers",
        })
    await page.close()
    return offers


async def run_ey_careers(keyword: str = "SAP", locations: list[str] | None = None) -> list[dict]:
    locations = locations or EY_LOCATIONS
    all_offers: dict[str, dict] = {}
    async with BaseScraper(delay_min=3.0, delay_max=6.0) as scraper:
        for loc in locations:
            logger.info("EY careers: q=%s location=%s", keyword, loc)
            try:
                offers = await _scrape_location(scraper, keyword, loc)
            except Exception as e:
                logger.error("EY careers failed for location=%s: %s", loc, e)
                offers = []
            logger.info("  EY careers %s: %d offers", loc, len(offers))
            for o in offers:
                all_offers[o["url"]] = o
            await scraper.random_delay()
    return list(all_offers.values())
