"""
scraper/linkedin_jobs.py — LinkedIn Jobs scraper using persistent cookie session.

First-time setup (opens Chromium for manual login):
  python -m scraper.runner --source linkedin-login

Subsequent runs load the saved session (~30 days validity).
Uses headful Chromium + feed warmup to avoid LinkedIn checkpoint detection.
"""
import asyncio
import json
import logging
import random
import shutil
from pathlib import Path
from urllib.parse import urlencode
from playwright.async_api import async_playwright, Page
from scraper.base import USER_AGENTS
from config import LINKEDIN_SESSION_PATH
from search_config import source_settings

logger = logging.getLogger(__name__)

LINKEDIN_BASE = "https://www.linkedin.com"
_CHECKPOINT_HINTS = ["/checkpoint/", "/authwall", "/login?", "verify your identity"]


def linkedin_searches(track: str | None = None) -> list[dict]:
    """Búsquedas de `sources.linkedin.searches`; con `track`, las de ese track y las que no declaran track."""
    searches = source_settings("linkedin").get("searches", [])
    if not searches:
        logger.warning("LinkedIn: sources.linkedin.searches está vacío en jobhunter.yaml; no hay nada que buscar")
    if track is None:
        return list(searches)
    return [s for s in searches if s.get("track") in (None, track)]


def save_linkedin_session(cookies: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cookies, indent=2), encoding="utf-8")
    logger.info("LinkedIn session saved: %s", path)


def load_linkedin_session(path: Path) -> list[dict] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def _is_checkpoint(url: str, html: str) -> bool:
    url_lower = url.lower()
    html_lower = html.lower()
    return any(hint in url_lower or hint in html_lower for hint in _CHECKPOINT_HINTS)


async def run_linkedin_login() -> None:
    """Open headful Chromium — user logs in manually, then cookies are saved."""
    system_chromium = shutil.which("chromium") or shutil.which("chromium-browser")
    playwright = await async_playwright().start()
    launch_kwargs: dict = {"headless": False}
    if system_chromium:
        launch_kwargs["executable_path"] = system_chromium

    browser = await playwright.chromium.launch(**launch_kwargs)
    context = await browser.new_context(
        user_agent=random.choice(USER_AGENTS),
        locale="es-ES",
        timezone_id="Europe/Madrid",
    )
    page = await context.new_page()
    await page.goto(f"{LINKEDIN_BASE}/login", wait_until="domcontentloaded")
    logger.info("Browser open — please log in to LinkedIn manually.")
    logger.info("Waiting for /feed (max 2 minutes)...")
    try:
        await page.wait_for_url("**/feed**", timeout=120_000)
        cookies = await context.cookies()
        save_linkedin_session(list(cookies), LINKEDIN_SESSION_PATH)
        logger.info("Login successful. Session saved.")
    except Exception:
        logger.error("Login timeout — session not saved. Try again.")
    finally:
        await browser.close()
        await playwright.stop()


async def _scroll_to_load_cards(page: Page) -> None:
    """Scroll the results list to trigger lazy loading of all job cards."""
    for _ in range(6):
        await page.evaluate("window.scrollBy(0, 600)")
        await asyncio.sleep(0.8)
    await asyncio.sleep(1.5)


async def _parse_cards(page: Page, keywords: str, max_offers: int) -> list[dict]:
    """Parse job cards from the current LinkedIn jobs search page."""
    await _scroll_to_load_cards(page)

    cards = await page.query_selector_all("[data-job-id]")
    logger.info("LinkedIn '%s': %d cards found", keywords, len(cards))
    offers = []
    for card in cards[:max_offers]:
        try:
            link_el = await card.query_selector("a[class*='job-card-list__title']")
            title_el = await card.query_selector("a[class*='job-card-list__title'] strong")
            company_el = await card.query_selector(".artdeco-entity-lockup__subtitle")
            location_el = await card.query_selector(".job-card-container__metadata-wrapper li")

            title = (await title_el.inner_text()).strip() if title_el else None
            if not title:
                # fallback: text content of the link itself
                title = (await link_el.inner_text()).strip() if link_el else None
            if not title:
                continue

            company_name = (await company_el.inner_text()).strip() if company_el else None
            location_text = (await location_el.inner_text()).strip() if location_el else None
            href = await link_el.get_attribute("href") if link_el else None
            offer_url = (
                href if href and href.startswith("http")
                else (LINKEDIN_BASE + href if href else None)
            )
            offers.append({
                "title": title,
                "url": offer_url,
                "company_name": company_name,
                "location": location_text,
                "description": None,
                "salary_min": None,
                "salary_max": None,
                "tech_stack": None,
                "source": "linkedin",
            })
        except Exception as e:
            logger.debug("LinkedIn card parse error: %s", e)
    return offers


async def run_linkedin_jobs(max_per_search: int = 25, track: str | None = None) -> list[dict]:
    """Run all LinkedIn SAP searches in a single headful browser session."""
    cookies = load_linkedin_session(LINKEDIN_SESSION_PATH)
    if not cookies:
        logger.error("No LinkedIn session. Run: python -m scraper.runner --source linkedin-login")
        return []

    system_chromium = shutil.which("chromium") or shutil.which("chromium-browser")
    playwright = await async_playwright().start()
    launch_kwargs: dict = {
        "headless": False,
        "args": ["--no-sandbox", "--disable-blink-features=AutomationControlled"],
    }
    if system_chromium:
        launch_kwargs["executable_path"] = system_chromium

    browser = await playwright.chromium.launch(**launch_kwargs)
    context = await browser.new_context(
        user_agent=random.choice(USER_AGENTS),
        locale="es-ES",
        timezone_id="Europe/Madrid",
        viewport={"width": 1920, "height": 1080},
    )
    await context.add_init_script(
        "Object.defineProperty(navigator, 'webdriver', { get: () => undefined });"
    )
    await context.add_cookies(cookies)
    page = await context.new_page()

    seen: set[str] = set()
    all_offers: list[dict] = []

    try:
        # Warm up via feed to avoid checkpoint on first navigation
        logger.info("LinkedIn: warming up session via feed...")
        try:
            await page.goto(f"{LINKEDIN_BASE}/feed", wait_until="networkidle", timeout=45_000)
        except Exception:
            await asyncio.sleep(3)
        await asyncio.sleep(random.uniform(3, 5))
        html = await page.content()
        if _is_checkpoint(page.url, html):
            logger.warning("LinkedIn checkpoint at feed — re-run: python -m scraper.runner --source linkedin-login")
            return []
        logger.info("LinkedIn: session active, starting searches")

        for search in linkedin_searches(track):
            try:
                params = urlencode({
                    "keywords": search["keywords"],
                    "location": search["location"],
                    "f_TPR": "r2592000",
                    "position": 1,
                    "pageNum": 0,
                })
                url = f"{LINKEDIN_BASE}/jobs/search?{params}"
                logger.info("LinkedIn: %s @ %s", search["keywords"], search["location"])
                try:
                    await page.goto(url, wait_until="networkidle", timeout=45_000)
                except Exception:
                    await asyncio.sleep(3)
                await asyncio.sleep(random.uniform(2, 4))

                html = await page.content()
                if _is_checkpoint(page.url, html):
                    # LinkedIn's SPA can briefly sit in a transitional/auth-check
                    # state right after navigation — give it one more chance
                    # before treating it as a real checkpoint.
                    await asyncio.sleep(8)
                    html = await page.content()
                    if _is_checkpoint(page.url, html):
                        logger.warning("LinkedIn checkpoint during search — stopping")
                        break

                for offer in await _parse_cards(page, search["keywords"], max_per_search):
                    if offer.get("url") and offer["url"] not in seen:
                        seen.add(offer["url"])
                        all_offers.append(offer)

                await asyncio.sleep(random.uniform(4, 8))
            except Exception as e:
                logger.error("LinkedIn search '%s' failed: %s", search["keywords"], e)

    finally:
        await browser.close()
        await playwright.stop()

    logger.info("LinkedIn total: %d unique offers", len(all_offers))
    return all_offers
