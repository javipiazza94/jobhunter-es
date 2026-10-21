"""
automation/form_filler.py — Orchestrates Playwright form filling for job applications.
Detects ATS by URL, dispatches to the appropriate handler.
"""
import asyncio
import importlib
import logging
import random
import shutil
from pathlib import Path
from playwright.async_api import async_playwright
from scraper.base import USER_AGENTS
from automation.ats_handlers import detect_ats

logger = logging.getLogger(__name__)

_HANDLER_MAP = {
    "workday":        ("automation.ats_handlers.workday",        "fill_workday"),
    "greenhouse":     ("automation.ats_handlers.greenhouse",     "fill_greenhouse"),
    "lever":          ("automation.ats_handlers.lever",          "fill_lever"),
    "successfactors": ("automation.ats_handlers.successfactors", "fill_successfactors"),
    "generic":        ("automation.ats_handlers.generic",        "fill_generic"),
}


async def _run_fill(
    form_url: str,
    profile: dict,
    cv_path: Path | None,
    cover_letter: str,
    headless: bool = True,
    pause_for_review: bool = False,
) -> bool:
    ats = detect_ats(form_url)
    module_name, func_name = _HANDLER_MAP[ats]
    handler = getattr(importlib.import_module(module_name), func_name)
    logger.info("Form filler: ATS=%s URL=%s headless=%s", ats, form_url, headless)

    system_chromium = shutil.which("chromium") or shutil.which("chromium-browser")
    launch_kwargs: dict = {
        "headless": headless,
        "args": ["--no-sandbox", "--disable-blink-features=AutomationControlled", "--disable-dev-shm-usage"],
    }
    if system_chromium:
        launch_kwargs["executable_path"] = system_chromium

    playwright = await async_playwright().start()
    try:
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
        page = await context.new_page()
        response = await page.goto(form_url, wait_until="domcontentloaded", timeout=30000)
        if not response or response.status >= 400:
            logger.warning("Form URL returned %s", response.status if response else "no response")
            return False
        result = await handler(page, profile, cv_path or Path("/nonexistent"), cover_letter)
        if pause_for_review and result and not headless:
            # Never auto-submits: the browser window stays open with the filled
            # form until the human reviews it and confirms here in the terminal.
            input(
                "\n>>> Formulario rellenado. Revisa la ventana del navegador y, si todo "
                "está bien, pulsa Enviar tú mismo/a.\n"
                ">>> Pulsa Enter aquí cuando hayas terminado para cerrar el navegador... "
            )
        return result
    except Exception as e:
        logger.error("Form filler error (%s): %s", ats, e)
        return False
    finally:
        await playwright.stop()


def fill_form(
    form_url: str,
    profile: dict,
    cv_path: Path | None,
    cover_letter: str,
    dry_run: bool = False,
    headless: bool = True,
    pause_for_review: bool = False,
) -> bool:
    if dry_run:
        ats = detect_ats(form_url)
        logger.info("[DRY-RUN] Would fill form: ATS=%s URL=%s", ats, form_url)
        return True
    return asyncio.run(_run_fill(form_url, profile, cv_path, cover_letter, headless, pause_for_review))
