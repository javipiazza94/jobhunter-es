"""
automation/ats_handlers/generic.py — Generic form filler via label/name/placeholder detection.
"""
import logging
from pathlib import Path
from playwright.async_api import Page

from automation import screening

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


async def _is_empty(inp) -> bool:
    """El campo no tiene ya un valor (lo escrito por el usuario o por la página nunca se pisa)."""
    try:
        return not (await inp.input_value() or "").strip()
    except Exception:  # noqa: BLE001 — si no se puede leer, no se arriesga a pisar
        return False


async def _question_text(page: Page, inp) -> str:
    """Texto de la pregunta de un campo: `<label for>` asociada, `aria-label` o placeholder ('' si no hay)."""
    field_id = await inp.get_attribute("id")
    if field_id:
        try:
            label = await page.query_selector(f"label[for='{field_id}']")
            text = (await label.inner_text()) if label else ""
            if text and text.strip():
                return text.strip()
        except Exception:  # noqa: BLE001 — sin etiqueta asociada
            pass
    return (await inp.get_attribute("aria-label") or await inp.get_attribute("placeholder") or "").strip()


async def _fill_screening(page: Page, inp, profile: dict) -> bool:
    """Rellena una pregunta de cribado solo si hay una respuesta guardada en el perfil (nunca inventa)."""
    question = await _question_text(page, inp)
    if not question:
        return False
    maxlength = await inp.get_attribute("maxlength")
    answer = screening.saved_answer(question, profile, int(maxlength) if maxlength and maxlength.isdigit() else None)
    if not answer:
        return False
    await inp.fill(answer)
    return True


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
            if not await _is_empty(inp):
                continue
            name = (await inp.get_attribute("name") or "").lower()
            placeholder = (await inp.get_attribute("placeholder") or "").lower()
            aria = (await inp.get_attribute("aria-label") or "").lower()
            hint = name or placeholder or aria
            if not hint:
                filled += await _fill_screening(page, inp, profile)
                continue
            if any(h in hint for h in ("cover_letter", "carta", "motivac", "message", "mensaje")):
                await inp.fill(cover_letter)
                filled += 1
                continue
            value = _map_field(hint, profile)
            if value:
                await inp.fill(value)
                filled += 1
            elif value is None:
                filled += await _fill_screening(page, inp, profile)
        except Exception as e:
            logger.debug("Field fill error: %s", e)
    logger.info("Generic form: %d fields filled", filled)
    return filled > 0
