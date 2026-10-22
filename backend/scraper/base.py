"""
scraper/base.py — Base Playwright scraper with stealth headers, rate limiting, and retry.
"""
import asyncio
import random
import logging
from typing import Optional
from playwright.async_api import async_playwright, Browser, BrowserContext, Page

from automation.browser_install import ensure_chromium_async

logger = logging.getLogger(__name__)

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
]

ACCEPT_LANGUAGES = ["es-ES,es;q=0.9,en;q=0.8", "es-ES,es;q=0.8", "es;q=0.9,en-US;q=0.8"]


class BaseScraper:
    def __init__(self, delay_min: float = 3.0, delay_max: float = 8.0, headless: bool = True):
        self.delay_min = delay_min
        self.delay_max = delay_max
        self.headless = headless
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._playwright = None

    async def __aenter__(self):
        import shutil
        await ensure_chromium_async()
        self._playwright = await async_playwright().start()
        system_chromium = shutil.which("chromium") or shutil.which("chromium-browser")
        launch_kwargs: dict = {
            "headless": self.headless,
            "args": [
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
            ],
        }
        if system_chromium:
            launch_kwargs["executable_path"] = system_chromium
        self._browser = await self._playwright.chromium.launch(**launch_kwargs)
        self._context = await self._browser.new_context(
            user_agent=random.choice(USER_AGENTS),
            locale="es-ES",
            timezone_id="Europe/Madrid",
            viewport={"width": 1920, "height": 1080},
            extra_http_headers={
                "Accept-Language": random.choice(ACCEPT_LANGUAGES),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "DNT": "1",
            },
        )
        await self._context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            window.chrome = { runtime: {} };
        """)
        return self

    async def __aexit__(self, *args):
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()

    async def new_page(self) -> Page:
        return await self._context.new_page()

    async def random_delay(self):
        delay = random.uniform(self.delay_min, self.delay_max)
        logger.debug("Sleeping %.1fs...", delay)
        await asyncio.sleep(delay)

    async def fetch_with_retry(self, page: Page, url: str, max_retries: int = 3) -> bool:
        for attempt in range(max_retries):
            try:
                response = await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                if response and response.status < 400:
                    return True
                logger.warning("HTTP %s for %s (attempt %d)", response.status if response else "?", url, attempt + 1)
            except Exception as e:
                logger.warning("Error fetching %s (attempt %d): %s", url, attempt + 1, e)
            if attempt < max_retries - 1:
                backoff = (2 ** attempt) * random.uniform(5, 10)
                logger.info("Retrying in %.1fs...", backoff)
                await asyncio.sleep(backoff)
        return False
