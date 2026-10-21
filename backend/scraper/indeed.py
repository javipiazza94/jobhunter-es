"""
scraper/indeed.py — Scrapes Indeed Spain via ScraperAPI.

Indeed blocks headless browsers with JS-level detection. ScraperAPI with
render=true handles the anti-bot layer and returns fully rendered HTML.

Free tier: 5000 credits/month. render=true costs 5 credits per request,
so ~1000 rendered pages/month.

API docs: https://docs.scraperapi.com/making-requests/render-javascript
"""
import re
import logging
import time
from urllib.parse import urlencode

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

INDEED_BASE = "https://es.indeed.com"
SCRAPERAPI_ENDPOINT = "http://api.scraperapi.com"

SALARY_PATTERN = re.compile(
    r"([\d.,]+)\s*€?\s*(?:[-–a]\s*([\d.,]+)\s*€?)?\s*(?:/?(?:año|mes|hora|year|month))?",
    re.IGNORECASE,
)


def _parse_salary(text: str) -> tuple[int | None, int | None]:
    if not text:
        return None, None
    text_clean = text.strip().lower()
    m = SALARY_PATTERN.search(text_clean)
    if not m:
        return None, None
    try:
        lo = int(m.group(1).replace(".", "").replace(",", ""))
        hi = int(m.group(2).replace(".", "").replace(",", "")) if m.group(2) else None
    except (ValueError, AttributeError):
        return None, None
    if "mes" in text_clean or "month" in text_clean:
        lo *= 12
        if hi:
            hi *= 12
    elif "hora" in text_clean or "hour" in text_clean:
        lo *= 1760
        if hi:
            hi *= 1760
    return lo, hi


def _fetch_via_scraperapi(url: str, api_key: str) -> str | None:
    """Fetch a URL through ScraperAPI with JS rendering enabled."""
    params = {
        "api_key": api_key,
        "url": url,
        "render": "true",
        "country_code": "es",
    }
    try:
        resp = requests.get(
            SCRAPERAPI_ENDPOINT,
            params=params,
            timeout=60,
        )
        if resp.status_code == 200:
            return resp.text
        logger.warning("ScraperAPI returned %d for %s", resp.status_code, url)
        return None
    except requests.RequestException as e:
        logger.error("ScraperAPI request error: %s", e)
        return None


def _parse_card(card) -> dict | None:
    """Parse a BeautifulSoup job card element."""
    try:
        # Title
        title_el = (
            card.select_one("h2.jobTitle a span[id]")
            or card.select_one("h2.jobTitle a")
            or card.select_one("h2 a")
        )
        if not title_el:
            return None
        title = title_el.get_text(strip=True)
        if not title or title.lower() == "new":
            return None

        # URL
        link = card.select_one("h2.jobTitle a, h2 a[data-jk], a[data-jk]")
        url = None
        if link and link.get("href"):
            href = link["href"]
            url = href if href.startswith("http") else INDEED_BASE + href

        # Company
        company_el = card.select_one(
            "[data-testid='company-name'], span.companyName, span.company"
        )
        company_name = company_el.get_text(strip=True) if company_el else None

        # Location
        loc_el = card.select_one(
            "[data-testid='text-location'], div.companyLocation, div.company_location"
        )
        location = loc_el.get_text(strip=True) if loc_el else None

        # Salary
        salary_el = card.select_one(
            "div.salary-snippet-container, "
            "div.metadata.salary-snippet-container, "
            "[data-testid='attribute_snippet_testid']"
        )
        salary_text = salary_el.get_text(strip=True) if salary_el else ""
        salary_min, salary_max = _parse_salary(salary_text)

        # Description snippet
        desc_el = card.select_one("div.job-snippet, ul[style]")
        description = desc_el.get_text(strip=True) if desc_el else None

        return {
            "title": title,
            "url": url,
            "company_name": company_name,
            "location": location,
            "description": description,
            "salary_min": salary_min,
            "salary_max": salary_max,
            "salary_text": salary_text,
            "tech_stack": None,
            "source": "indeed",
        }
    except Exception as e:
        logger.debug("Indeed card parse error: %s", e)
        return None


def scrape_indeed_keyword(
    keyword: str,
    location: str,
    api_key: str,
    max_pages: int = 3,
) -> list[dict]:
    """Scrape Indeed for one keyword+location combo via ScraperAPI."""
    offers: list[dict] = []
    seen_urls: set[str] = set()

    for page_num in range(max_pages):
        params = {
            "q": keyword,
            "l": location,
            "fromage": "14",
            "sort": "date",
            "start": page_num * 10,
        }
        target_url = f"{INDEED_BASE}/jobs?{urlencode(params)}"
        logger.info("Indeed (ScraperAPI) page %d: %s", page_num + 1, target_url)

        html = _fetch_via_scraperapi(target_url, api_key)
        if not html:
            logger.warning("Indeed: no response on page %d", page_num + 1)
            break

        soup = BeautifulSoup(html, "html.parser")
        cards = soup.select("div.job_seen_beacon, div.cardOutline, td.resultContent")

        if not cards:
            # Check if it's a bot-block or no-results
            if "captcha" in html.lower() or "blocked" in soup.title.get_text().lower() if soup.title else False:
                logger.warning("Indeed: blocked by ScraperAPI — check API key / credits")
            else:
                logger.info("Indeed: no cards on page %d (no more results)", page_num + 1)
            break

        page_new = 0
        for card in cards:
            offer = _parse_card(card)
            if offer and offer.get("url") and offer["url"] not in seen_urls:
                seen_urls.add(offer["url"])
                offers.append(offer)
                page_new += 1

        logger.info("  Indeed page %d: %d offers (total %d)", page_num + 1, page_new, len(offers))

        # Check next page
        next_btn = soup.select_one(
            "a[data-testid='pagination-page-next'], a[aria-label='Siguiente']"
        )
        if not next_btn:
            break

        time.sleep(2)  # be polite between pages

    return offers


async def run_indeed(
    keywords: list[str] | None = None,
    locations: list[str] | None = None,
    max_pages: int = 3,
) -> list[dict]:
    """Run Indeed scraper for all keyword+location combos via ScraperAPI."""
    from config import SCRAPERAPI_KEY
    from search_config import source_settings

    settings = source_settings("indeed")
    keywords = keywords or settings.get("keywords", [])
    locations = locations or settings.get("locations", [])
    if not keywords or not locations:
        logger.warning("Indeed: sources.indeed.keywords y/o locations vacíos en jobhunter.yaml; "
                       "no hay nada que buscar")
        return []

    if not SCRAPERAPI_KEY or SCRAPERAPI_KEY == "your_scraperapi_key_here":
        logger.error(
            "Indeed: SCRAPERAPI_KEY not set. "
            "Get a free key at https://www.scraperapi.com and set it in backend/.env"
        )
        return []

    seen: set[str] = set()
    all_offers: list[dict] = []

    for kw in keywords:
        for loc in locations:
            logger.info("Indeed: keyword=%s location=%s", kw, loc)
            try:
                for offer in scrape_indeed_keyword(kw, loc, SCRAPERAPI_KEY, max_pages):
                    if offer.get("url") and offer["url"] not in seen:
                        seen.add(offer["url"])
                        all_offers.append(offer)
            except Exception as e:
                logger.error("Indeed keyword '%s' @ '%s' failed: %s", kw, loc, e)

    logger.info("Indeed total: %d unique offers", len(all_offers))
    return all_offers
