"""
automation/ats_handlers/generic.py — Generic form filler via label/name/placeholder detection.
"""
import logging
from pathlib import Path
from playwright.async_api import Page

logger = logging.getLogger(__name__)

_FIELD_HINTS: dict[str, tuple[str, ...]] = {
    "first_name":   ("first_name", "nombre", "firstname"),
    "last_name":    ("last_name", "apellido", "apellidos", "surname", "lastname"),
    "email":        ("email", "correo", "e-mail"),
    "phone":        ("phone", "teléfono", "telefono", "móvil", "movil", "tel"),
    "linkedin":     ("linkedin",),
    "portfolio":    ("portfolio", "website", "web personal", "github"),
    "address":      ("address", "direccion", "dirección", "street", "calle"),
    "city":         ("city", "ciudad", "localidad"),
    "postal_code":  ("postal_code", "postcode", "zip", "codigo_postal", "código postal", "cp"),
    "country":      ("country", "pais", "país"),
    "dni_nie":      ("dni", "nie", "nationalid", "national_id", "documentnumber", "documento"),
    "birth_date":   ("birth_date", "birthdate", "fecha_nacimiento", "fecha de nacimiento", "fechanacimiento"),
    "availability": ("availab", "disponib", "startdate", "fecha_incorporacion", "fecha de incorporación"),
    "salary":       ("salary", "salario", "compensation", "pretension", "pretensión"),
    "current_position": ("position", "puesto_actual", "puesto actual", "current_title", "currenttitle", "job_title"),
    "current_company":  ("company_name", "currentcompany", "empresa_actual", "empresa actual"),
    "cover_letter": ("cover_letter", "carta", "motivac", "message", "mensaje", "presentation"),
}

# Hint substrings that mean "this is an END/until date", so it must never be
# filled with the availability START date even though it also contains
# "availab"/"disponib" (e.g. availability_end_date, "disponibilidad hasta").
_END_DATE_MARKERS = ("end", "hasta", "_fin", " fin", "final")


def _map_field(field_hint: str, profile: dict) -> str | None:
    hint = field_hint.lower()
    personal = profile.get("personal", {})
    availability = profile.get("availability", {})
    salary = profile.get("salary_expectation", {})
    experience = profile.get("experience") or [{}]
    current_job = experience[0] if isinstance(experience[0], dict) else {}
    name_parts = personal.get("name", "").split(" ", 1)
    for canonical, hints in _FIELD_HINTS.items():
        if canonical == "availability" and any(m in hint for m in _END_DATE_MARKERS):
            continue  # e.g. availability_end_date / "disponibilidad hasta" — never the start date
        if any(h in hint for h in hints):
            if canonical == "first_name":
                return personal.get("first_name") or (name_parts[0] if name_parts else "")
            if canonical == "last_name":
                return personal.get("last_name") or (name_parts[1] if len(name_parts) > 1 else "")
            if canonical == "email":
                return personal.get("email", "")
            if canonical == "phone":
                return personal.get("phone", "")
            if canonical == "linkedin":
                return personal.get("linkedin", "")
            if canonical == "portfolio":
                return personal.get("portfolio", "")
            if canonical == "address":
                return personal.get("address", "")
            if canonical == "city":
                return personal.get("city", "")
            if canonical == "postal_code":
                return personal.get("postal_code", "")
            if canonical == "country":
                return personal.get("country", "")
            if canonical == "dni_nie":
                return personal.get("dni_nie", "")
            if canonical == "birth_date":
                return personal.get("birth_date", "")
            if canonical == "current_position":
                return current_job.get("role", "")
            if canonical == "current_company":
                return current_job.get("company", "")
            if canonical == "availability":
                return availability.get("start_date", "") if isinstance(availability, dict) else ""
            if canonical == "salary":
                amount = salary.get("amount") if isinstance(salary, dict) else None
                return str(amount) if amount else ""
            if canonical == "cover_letter":
                return None  # injected by caller
    return None


async def _dismiss_cookies(page: Page) -> None:
    for sel in [
        "button[id*='accept']", "button[class*='accept']",
        "#onetrust-accept-btn-handler", ".cc-btn.cc-allow",
        "button:text('Aceptar')", "button:text('Accept all')",
    ]:
        try:
            btn = page.locator(sel).first
            if await btn.is_visible(timeout=800):
                await btn.click()
                return
        except Exception:
            continue


async def fill_generic(
    page: Page,
    profile: dict,
    cv_path: Path,
    cover_letter: str,
) -> bool:
    await _dismiss_cookies(page)
    filled = 0
    inputs = await page.query_selector_all(
        "input:not([type='hidden']):not([type='submit']):not([type='button']), textarea"
    )
    for inp in inputs:
        try:
            input_type = (await inp.get_attribute("type") or "text").lower()
            if input_type == "file":
                if cv_path and cv_path.exists():
                    await inp.set_input_files(str(cv_path))
                    filled += 1
                continue
            name = (await inp.get_attribute("name") or "").lower()
            placeholder = (await inp.get_attribute("placeholder") or "").lower()
            aria = (await inp.get_attribute("aria-label") or "").lower()
            hint = name or placeholder or aria
            if not hint:
                continue
            if any(h in hint for h in ("cover_letter", "carta", "motivac", "message", "mensaje")):
                await inp.fill(cover_letter)
                filled += 1
                continue
            value = _map_field(hint, profile)
            if value:
                await inp.fill(value)
                filled += 1
        except Exception as e:
            logger.debug("Field fill error: %s", e)
    logger.info("Generic form: %d fields filled", filled)
    return filled > 0
