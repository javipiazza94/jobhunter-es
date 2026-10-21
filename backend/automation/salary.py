"""
automation/salary.py — Decide qué pretensión salarial pedir según la oferta.

Regla:
  - Ciudad objetivo (cualquier modalidad) o 100% remoto (esté donde esté la empresa):
    salary_expectation.amount_remote_or_target_city.
  - Presencial o híbrido FUERA de la ciudad objetivo (hay que desplazarse):
    salary_expectation.amount_onsite_or_hybrid_outside_target_city.
  - Se aceptan también las claves antiguas de LEGACY_SALARY_KEYS (con aviso en el log).
  - Ubicación desconocida: se usa el valor por defecto (salary_expectation.amount) y se registra
    en el log — nunca se adivina al alza.
"""
import copy
import logging

from automation.location import in_target_area, parse_modality

logger = logging.getLogger(__name__)

NEW_TARGET_KEY = "amount_remote_or_target_city"
NEW_OUTSIDE_KEY = "amount_onsite_or_hybrid_outside_target_city"

# compat: claves antiguas (perfiles creados antes de generalizar la ciudad objetivo) -> clave nueva
LEGACY_SALARY_KEYS = {
    "amount_remote_or_sevilla": NEW_TARGET_KEY,
    "amount_onsite_or_hybrid_outside_sevilla": NEW_OUTSIDE_KEY,
}


def classify_offer_location(location: str | None, title: str | None = None) -> str:
    """Devuelve 'target_city', 'remote', 'onsite_elsewhere' o 'unknown'."""
    modality = parse_modality(location, title)
    if modality is None:
        return "unknown"
    if in_target_area(location):
        return "target_city"
    return "remote" if modality == "remoto" else "onsite_elsewhere"


def resolve_salary(profile: dict, offer: dict | None) -> tuple[int | None, str]:
    """Devuelve (importe, motivo). El importe es None si el perfil no define ninguno."""
    sal = profile.get("salary_expectation") or {}
    if not isinstance(sal, dict):
        return None, "sin salary_expectation"
    default = sal.get("amount")

    offer = offer or {}
    kind = classify_offer_location(offer.get("location"), offer.get("title"))

    legacy_used = [old for old in LEGACY_SALARY_KEYS if old in sal]
    if legacy_used:
        logger.warning(
            "profile.json usa claves de salary_expectation antiguas; renómbralas: %s",
            ", ".join(f"{old} -> {LEGACY_SALARY_KEYS[old]}" for old in legacy_used),
        )

    def _pick(new_key: str):
        legacy = next((sal[old] for old, new in LEGACY_SALARY_KEYS.items() if new == new_key and old in sal), None)
        return sal.get(new_key) or legacy or default

    amt_target = _pick(NEW_TARGET_KEY)
    amt_outside = _pick(NEW_OUTSIDE_KEY)

    if kind == "onsite_elsewhere":
        return amt_outside, "presencial/híbrido fuera de la ciudad objetivo"
    if kind == "target_city":
        return amt_target, "ciudad objetivo"
    if kind == "remote":
        return amt_target, "100% remoto"
    return default, "ubicación desconocida -> valor por defecto"


def profile_for_offer(profile: dict, offer: dict | None) -> dict:
    """Copia del perfil con salary_expectation.amount ajustado a esta oferta.

    Los handlers de formularios leen salary_expectation.amount; así no hay que tocarlos.
    """
    amount, reason = resolve_salary(profile, offer)
    adjusted = copy.deepcopy(profile)
    if isinstance(adjusted.get("salary_expectation"), dict):
        adjusted["salary_expectation"]["amount"] = amount
    logger.info(
        "Pretensión salarial: %s EUR (%s) — %s",
        amount, reason, (offer or {}).get("location") or "sin ubicación",
    )
    return adjusted
