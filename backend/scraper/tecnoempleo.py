"""
scraper/tecnoempleo.py — Scrapes tech job offers from Tecnoempleo.com.
Targets: /ofertas-trabajo/ with keyword + province ID filters.

Selectors verified 2026-06-24 against live site structure:
  Card: div.p-3.border.rounded.mb-3.bg-white
  Title link: h3 a.font-weight-bold
  Company: a.text-primary.link-muted
  Location: div.col-12.col-lg-3.text-gray-700
  Description: span.hidden-md-down
"""
import json
import re
import logging
from urllib.parse import urlencode
from playwright.async_api import Page
from scraper.base import BaseScraper
from automation.experience_classifier import classify_experience, classify_contract
from automation.filter_engine import score_offer
from search_config import get_config, source_settings
from config import TECNOEMPLEO_BASE

logger = logging.getLogger(__name__)

SALARY_PATTERN = re.compile(r"(\d[\d.,]+)\s*[€$]?\s*[-–]\s*(\d[\d.,]+)")

# Province IDs (pr= parameter) come from `sources.tecnoempleo.province_ids` in jobhunter.yaml
# (location name -> id shown in Tecnoempleo's filter sidebar). Only "remoto" is built in:
# it is a keyword filter, not a province.
PROVINCE_IDS: dict[str, str | None] = {
    "remoto": None,
}


def province_ids() -> dict[str, str | None]:
    """Built-in ids merged with the configured ones; keys are lower-cased location names."""
    configured = source_settings("tecnoempleo").get("province_ids") or {}
    return {**PROVINCE_IDS, **{str(k).strip().lower(): (str(v) if v is not None else None)
                               for k, v in configured.items()}}


def build_search_url(keyword: str, location: str, page_num: int) -> str:
    """Listing URL for one keyword/location/page. A location without a configured id is searched
    nationally (no province filter); the caller deduplicates."""
    loc = location.strip().lower()
    pr_id = province_ids().get(loc)
    params: dict = {"te": keyword, "pagina": page_num}
    if pr_id:
        params["pr"] = f",{pr_id},"
    elif loc == "remoto":
        params["te"] = f"{keyword} remoto"
    return f"{TECNOEMPLEO_BASE}/ofertas-trabajo/?{urlencode(params)}"


def _parse_salary(text: str) -> tuple[int | None, int | None]:
    m = SALARY_PATTERN.search(text)
    if not m:
        return None, None
    try:
        lo = int(m.group(1).replace(".", "").replace(",", ""))
        hi = int(m.group(2).replace(".", "").replace(",", ""))
        return lo, hi
    except ValueError:
        return None, None


class TecnoempleoScraper(BaseScraper):
    def __init__(self):
        super().__init__(delay_min=3.0, delay_max=7.0)

    async def _parse_offer_card(self, card) -> dict | None:
        try:
            # URL from onclick attribute on the card div
            onclick = await card.get_attribute("onclick") or ""
            url = None
            m = re.search(r"location\.href='([^']+)'", onclick)
            if m:
                url = m.group(1)
                if not url.startswith("http"):
                    url = TECNOEMPLEO_BASE + url

            # Title and URL also available from the h3 > a link
            title_el = await card.query_selector("h3 a, h2 a")
            if not title_el:
                return None
            title = (await title_el.inner_text()).strip()
            if not url:
                href = await title_el.get_attribute("href")
                if href:
                    url = href if href.startswith("http") else TECNOEMPLEO_BASE + href

            # Company
            company_el = await card.query_selector("a.text-primary, a.link-muted")
            company_name = (await company_el.inner_text()).strip() if company_el else None

            # Location — desktop column
            loc_el = await card.query_selector(".col-12.col-lg-3.text-gray-700, .col-lg-3.text-gray-700")
            if loc_el:
                loc_text = (await loc_el.inner_text()).strip()
                # First line is date, second is location
                lines = [l.strip() for l in loc_text.splitlines() if l.strip()]
                location = lines[1] if len(lines) > 1 else lines[0] if lines else None
            else:
                # Mobile fallback
                mob_el = await card.query_selector("span.d-block.d-lg-none, .d-block.d-lg-none")
                location = (await mob_el.inner_text()).strip() if mob_el else None

            # Salary
            salary_el = await card.query_selector(".salario, .salary, [class*='salary']")
            salary_text = (await salary_el.inner_text()).strip() if salary_el else ""
            salary_min, salary_max = _parse_salary(salary_text)

            # Description
            desc_el = await card.query_selector(".hidden-md-down, span.hidden-md-down")
            description = (await desc_el.inner_text()).strip() if desc_el else None

            # Tech stack badges
            badge_els = await card.query_selector_all("span.badge")
            tech_tags = []
            for b in badge_els:
                t = (await b.inner_text()).strip()
                if t and t not in ("Nueva", "Urgente", "Destacada"):
                    tech_tags.append(t)

            return {
                "title": title,
                "url": url,
                "company_name": company_name,
                "location": location,
                "salary_min": salary_min,
                "salary_max": salary_max,
                "description": description,
                "tech_stack": ", ".join(tech_tags) if tech_tags else None,
                "source": "tecnoempleo",
            }
        except Exception as e:
            logger.debug("Card parse error: %s", e)
            return None

    async def fetch_offer_detail(self, page: Page, url: str) -> dict | None:
        """
        Fetch the full offer page (ficha completa): clean description, tech stack,
        experience level, contract type, posted date and (rarely disclosed) salary.
        Uses the page's JobPosting JSON-LD when present, falling back to the
        visible sidebar summary (Ubicación/Funciones/Jornada/Experiencia/Tipo contrato).
        """
        if not await self.fetch_with_retry(page, url):
            return None

        result: dict = {}

        ld_data: dict = {}
        ld_el = await page.query_selector('script[type="application/ld+json"]')
        if ld_el:
            try:
                ld_data = json.loads((await ld_el.text_content()) or "{}")
            except json.JSONDecodeError:
                ld_data = {}

        description = ld_data.get("description")
        if not description:
            desc_el = await page.query_selector('div[itemprop="description"]')
            description = (await desc_el.inner_text()).strip() if desc_el else None
        if description:
            result["description"] = description.strip()

        if ld_data.get("datePosted"):
            result["posted_date"] = ld_data["datePosted"]

        base_salary = ld_data.get("baseSalary")
        salary_value = base_salary.get("value") if isinstance(base_salary, dict) else None
        if isinstance(salary_value, dict):
            if salary_value.get("minValue"):
                result["salary_min"] = int(salary_value["minValue"])
            if salary_value.get("maxValue"):
                result["salary_max"] = int(salary_value["maxValue"])

        # Sidebar summary: each li has a label (Ubicación/Funciones/Jornada/Experiencia/
        # Tipo contrato) and a value; the last li holds the tech-stack tag buttons.
        items = await page.query_selector_all("ul.list-unstyled li.list-item")
        tech_tags: list[str] = []
        for li in items:
            label_el = await li.query_selector("span.d-inline-block")
            value_el = await li.query_selector("span.float-end")
            if label_el and value_el:
                label = (await label_el.inner_text()).strip()
                value = (await value_el.inner_text()).strip()
                if label == "Experiencia":
                    level = classify_experience("", value)
                    if level:
                        result["experience_level"] = level
                elif label == "Tipo contrato":
                    contract = classify_contract("", value)
                    if contract:
                        result["contract_type"] = contract
            for btn in await li.query_selector_all("a button"):
                t = (await btn.inner_text()).strip()
                if t:
                    tech_tags.append(t)

        if tech_tags:
            result["tech_stack"] = ", ".join(dict.fromkeys(tech_tags))

        return result

    async def scrape_keyword(self, keyword: str, location: str, max_pages: int = 5) -> list[dict]:
        offers = []

        async with self as scraper:
            page = await scraper.new_page()
            for page_num in range(1, max_pages + 1):
                url = build_search_url(keyword, location, page_num)
                logger.info("Fetching page %d: %s", page_num, url)
                if not await scraper.fetch_with_retry(page, url):
                    break

                cards = await page.query_selector_all("div.p-3.border.rounded.mb-3.bg-white")
                if not cards:
                    logger.info("No offers on page %d", page_num)
                    break

                page_offers = []
                for card in cards:
                    offer = await self._parse_offer_card(card)
                    if offer:
                        page_offers.append(offer)
                        offers.append(offer)

                logger.info("  Page %d: %d offers found (total %d)", page_num, len(page_offers), len(offers))
                await scraper.random_delay()

                # Check for next page
                next_btn = await page.query_selector("a[rel='next'], a.next, [aria-label*='siguiente'], li.next a")
                if not next_btn:
                    break
        return offers


async def run_tecnoempleo(max_pages: int = 3) -> list[dict]:
    all_offers = []
    scraper = TecnoempleoScraper()
    seen_urls: set[str] = set()
    settings = source_settings("tecnoempleo")
    if not settings.get("keywords") or not settings.get("locations"):
        logger.warning("Tecnoempleo: sources.tecnoempleo.keywords y/o locations vacíos en jobhunter.yaml; "
                       "no hay nada que buscar")
    for keyword in settings.get("keywords", []):
        for location in settings.get("locations", []):
            logger.info("Tecnoempleo: keyword=%s location=%s", keyword, location)
            offers = await scraper.scrape_keyword(keyword, location, max_pages)
            for o in offers:
                if o.get("url") and o["url"] not in seen_urls:
                    seen_urls.add(o["url"])
                    all_offers.append(o)
    logger.info("Tecnoempleo total: %d unique offers", len(all_offers))
    all_offers = await _enrich_with_details(all_offers)
    return all_offers


async def _enrich_with_details(offers: list[dict]) -> list[dict]:
    """
    Fetch the full offer page only for offers that already look promising from the
    listing card (score_offer >= detail_fetch_min_score) — avoids hammering the site
    with a detail request per offer when most of them are clearly irrelevant.
    """
    candidates = [o for o in offers if o.get("url") and score_offer(o) >= get_config().scoring.detail_fetch_min_score]
    logger.info(
        "Tecnoempleo: fetching full detail for %d/%d offers (card score >= %.2f)",
        len(candidates), len(offers), get_config().scoring.detail_fetch_min_score,
    )
    if not candidates:
        return offers

    scraper = TecnoempleoScraper()
    async with scraper as s:
        page = await s.new_page()
        for offer in candidates:
            try:
                detail = await s.fetch_offer_detail(page, offer["url"])
            except Exception as e:
                logger.debug("Detail fetch failed for %s: %s", offer["url"], e)
                detail = None
            if detail:
                offer.update(detail)
            await s.random_delay()
    return offers
