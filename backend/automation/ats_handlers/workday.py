"""
automation/ats_handlers/workday.py — Workday ATS multi-step handler.
Handles iframe-embedded forms and multi-step navigation.

Safety: NEVER clicks the final Submit button. Advances intermediate wizard
steps (the "Next" button, keyed off Workday's stable data-automation-id) and
stops on the last screen for manual review — same rule as every other handler.
"""
import logging
from pathlib import Path
from playwright.async_api import Page
from automation.ats_handlers.generic import _dismiss_cookies, _map_field

logger = logging.getLogger(__name__)

# Labels that mean "final, irreversible action" — never clicked.
_SUBMIT_LABELS = ("Submit", "Enviar", "Submit Application", "Review and Submit")
# Labels that mean "advance the wizard" — safe to click.
_NEXT_LABELS = ("Next", "Siguiente", "Continue", "Save and Continue")

# Workday field automation-ids vary per tenant (it's a highly configurable
# platform), so this list covers the common ones seen across public tenants.
# Unvalidated against a live Workday form — improve against a real URL if one
# turns up false negatives.
_FIELDS = [
    ("firstName", "first_name"),
    ("lastName", "last_name"),
    ("email", "email"),
    ("phone", "phone"),
    ("linkedIn", "linkedin"),
    ("addressLine1", "address"),
    ("city", "city"),
    ("postalCode", "postal_code"),
    ("countryRegion", "country"),
]


async def fill_workday(page: Page, profile: dict, cv_path: Path, cover_letter: str) -> bool:
    await _dismiss_cookies(page)

    target = page
    for frame in page.frames:
        if "myworkdayjobs" in (frame.url or "").lower():
            target = frame  # type: ignore[assignment]
            break

    filled = 0
    for field_name, hint in _FIELDS:
        value = _map_field(hint, profile)
        if not value:
            continue
        for sel in [
            f"input[data-automation-id='{field_name}']",
            f"input[name='{field_name}']",
            f"input[id*='{field_name}' i]",
        ]:
            try:
                el = target.locator(sel).first
                if await el.is_visible(timeout=1200):
                    await el.fill(str(value))
                    filled += 1
                    break
            except Exception:
                continue

    if cv_path and cv_path.exists():
        try:
            fi = target.locator("input[type='file']").first
            if await fi.is_visible(timeout=2000):
                await fi.set_input_files(str(cv_path))
                filled += 1
        except Exception as e:
            logger.debug("Workday CV upload: %s", e)

    try:
        for ta in await target.query_selector_all("textarea"):
            await ta.fill(cover_letter)
            filled += 1
    except Exception:
        pass

    # Advance intermediate wizard steps, but never click the final submit action.
    for _ in range(10):
        advanced = False
        for btn_text in _NEXT_LABELS:
            try:
                btn = target.locator(
                    f"button[data-automation-id='bottom-navigation-next-btn'], button:text('{btn_text}')"
                ).first
                if await btn.is_visible(timeout=1200):
                    await btn.click()
                    await page.wait_for_timeout(1500)
                    advanced = True
                    break
            except Exception:
                continue
        if not advanced:
            break

    for btn_text in _SUBMIT_LABELS:
        try:
            btn = target.locator(f"button:text('{btn_text}')").first
            if await btn.is_visible(timeout=1200):
                logger.info(
                    "Workday: formulario listo (%d campos rellenados). "
                    "Pantalla final detectada ('%s') — NO se pulsa, revisión manual requerida.",
                    filled, btn_text,
                )
                break
        except Exception:
            continue

    if filled == 0:
        logger.warning("Workday: no fields filled — needs_manual_review")
    return filled > 0
