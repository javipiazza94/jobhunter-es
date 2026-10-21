"""
automation/ats_handlers/successfactors.py — SAP SuccessFactors ATS handler.
May embed form in iframes; multi-step flow with Next/Submit buttons. Many
SuccessFactors career portals gate the application form behind a candidate
login/register screen first (e.g. career55.sapsf.eu).

Safety: this handler NEVER clicks the final Submit/Enviar button. It fills every
field it can find, advances intermediate wizard steps (Next/Siguiente/Continue),
and stops on the last screen so a human reviews and submits manually. Logging in
is not treated the same way — it's reversible and doesn't commit to anything —
so if JOBPORTAL_EMAIL/JOBPORTAL_PASSWORD are set in the environment, it fills and
submits the login form to reach the actual application.
"""
import logging
import os
from pathlib import Path
from playwright.async_api import Page
from automation.ats_handlers.generic import _dismiss_cookies

logger = logging.getLogger(__name__)

# Labels that mean "this is the final, irreversible action" — never clicked.
_SUBMIT_LABELS = ("Submit", "Enviar", "Enviar candidatura", "Finalizar", "Finish", "Apply")
# Labels that mean "advance to the next step of the wizard" — safe to click.
_NEXT_LABELS = ("Next", "Siguiente", "Continue", "Continuar")
# Labels for the login button — safe to click, login is reversible.
_LOGIN_LABELS = ("Entrar", "Iniciar sesión", "Log In", "Login", "Sign In", "Sign in")

# input selector -> profile path (dot notation resolved against the loaded profile dict)
_TEXT_FIELDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("input[name*='firstName' i], input[id*='firstName' i]", ("personal", "first_name")),
    ("input[name*='lastName' i], input[id*='lastName' i]", ("personal", "last_name")),
    ("input[type='email'], input[name*='email' i]", ("personal", "email")),
    ("input[type='tel'], input[name*='phone' i]", ("personal", "phone")),
    ("input[name*='address' i], input[name*='street' i]", ("personal", "address")),
    ("input[name*='city' i]", ("personal", "city")),
    ("input[name*='postalCode' i], input[name*='zip' i], input[name*='postcode' i]", ("personal", "postal_code")),
    (
        "input[name*='nationalId' i], input[name*='national_id' i], input[name*='dni' i], "
        "input[name*='documentNumber' i], input[name*='passportNumber' i]",
        ("personal", "dni_nie"),
    ),
    ("input[name*='linkedin' i]", ("personal", "linkedin")),
    ("input[name*='website' i], input[name*='portfolio' i]", ("personal", "portfolio")),
    ("input[name*='availab' i], input[name*='startDate' i], input[name*='earliestStart' i]", ("availability", "start_date")),
    ("input[name*='salary' i], input[name*='compensation' i]", ("salary_expectation", "amount")),
    ("input[name*='currentTitle' i]", ("experience", 0, "role")),
    ("input[name*='currentCompany' i]", ("experience", 0, "company")),
)

_SELECT_FIELDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("select[name*='country' i]", ("personal", "country")),
    ("select[name*='nationality' i]", ("personal", "nationality")),
)


def _resolve(profile: dict, path: tuple):
    node = profile
    for key in path:
        if isinstance(node, dict):
            node = node.get(key)
        elif isinstance(node, list) and isinstance(key, int):
            node = node[key] if 0 <= key < len(node) else None
        else:
            return None
    return node


async def _expand_accordion_sections(page: Page) -> None:
    """
    Candidate-profile fields (firstName, cellPhone, cust_national_id, ...) live
    inside collapsed accordion sections that must be opened before their inputs
    become visible/fillable. SuccessFactors marks these with the standard
    aria-expanded="false" attribute regardless of tenant, so this is generic.
    """
    # Re-query live on every iteration instead of snapshotting once: clicking a
    # section can re-render the whole accordion and detach earlier handles.
    for _ in range(20):
        try:
            btn = page.locator("button[aria-expanded='false']").first
            if await btn.count() == 0:
                break
            await btn.click(timeout=1500)
            await page.wait_for_timeout(400)
        except Exception as e:
            logger.debug("SuccessFactors accordion expand: %s", e)
            break


async def _maybe_login(page: Page) -> bool:
    """
    If this looks like a SuccessFactors candidate login screen and
    JOBPORTAL_EMAIL/JOBPORTAL_PASSWORD are set, log in and return True.
    Never invents credentials — silently does nothing if either is missing.
    """
    email = os.getenv("JOBPORTAL_EMAIL")
    password = os.getenv("JOBPORTAL_PASSWORD")
    if not email or not password:
        return False

    try:
        user_field = page.locator(
            "input[name='username' i], input[id='username' i], input[type='email']"
        ).first
        pass_field = page.locator("input[type='password']").first
        if not (await user_field.is_visible(timeout=1500) and await pass_field.is_visible(timeout=1500)):
            return False

        await user_field.fill(email)
        await pass_field.fill(password)

        for label in _LOGIN_LABELS:
            btn = page.locator(f"button:text('{label}'), input[value='{label}']").first
            try:
                if await btn.is_visible(timeout=1000):
                    await btn.click()
                    await page.wait_for_load_state("networkidle", timeout=15000)
                    logger.info("SuccessFactors: login realizado con JOBPORTAL_EMAIL.")
                    return True
            except Exception:
                continue
    except Exception as e:
        logger.debug("SuccessFactors login: %s", e)
    return False


async def fill_successfactors(page: Page, profile: dict, cv_path: Path, cover_letter: str) -> bool:
    await _dismiss_cookies(page)
    await _maybe_login(page)
    await _dismiss_cookies(page)  # post-login page may show its own cookie banner
    await _expand_accordion_sections(page)
    filled = 0

    target = page
    for frame in page.frames:
        if "successfactors" in (frame.url or "").lower():
            target = frame  # type: ignore[assignment]
            break

    for sel, path in _TEXT_FIELDS:
        value = _resolve(profile, path)
        if not value:
            continue
        try:
            el = target.locator(sel).first
            if await el.is_visible(timeout=1500):
                await el.fill(str(value))
                filled += 1
        except Exception as e:
            logger.debug("SuccessFactors field %s: %s", sel, e)

    for sel, path in _SELECT_FIELDS:
        value = _resolve(profile, path)
        if not value:
            continue
        try:
            el = target.locator(sel).first
            if await el.is_visible(timeout=1500):
                await el.select_option(label=str(value))
                filled += 1
        except Exception as e:
            logger.debug("SuccessFactors select %s: %s (probablemente un dropdown custom, no <select>)", sel, e)

    if cv_path and cv_path.exists():
        try:
            fi = target.locator("input[type='file']").first
            if await fi.is_visible(timeout=2000):
                await fi.set_input_files(str(cv_path))
                filled += 1
        except Exception as e:
            logger.debug("SuccessFactors CV: %s", e)

    try:
        ta = target.locator("textarea").first
        if await ta.is_visible(timeout=1500):
            await ta.fill(cover_letter)
            filled += 1
    except Exception:
        pass

    # Advance intermediate wizard steps, but never click the final submit action.
    for _ in range(10):
        advanced = False
        for btn_text in _NEXT_LABELS:
            try:
                btn = target.locator(f"button:text('{btn_text}'), input[value='{btn_text}']").first
                if await btn.is_visible(timeout=1200):
                    await btn.click()
                    await page.wait_for_timeout(1200)
                    advanced = True
                    break
            except Exception:
                continue
        if not advanced:
            break

    for btn_text in _SUBMIT_LABELS:
        try:
            btn = target.locator(f"button:text('{btn_text}'), input[value='{btn_text}']").first
            if await btn.is_visible(timeout=1200):
                logger.info(
                    "SuccessFactors: formulario listo (%d campos rellenados). "
                    "Pantalla final detectada ('%s') — NO se pulsa, revisión manual requerida.",
                    filled, btn_text,
                )
                break
        except Exception:
            continue

    if filled == 0:
        logger.warning("SuccessFactors: no se rellenó ningún campo — needs_manual_review")
    return filled > 0
