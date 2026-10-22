"""
automation/offer_review.py — Revisión de una oferta antes de guardarla.

Un único paso para todos los puntos de entrada (scrapers vía scraper/persist.py e inbox vía
scripts/load_inbox_offers.py):
  * posting_guard limpia la descripción (caracteres invisibles) y detecta manipulación;
  * language_gate avisa de idiomas exigidos que no tienes o a más nivel del tuyo.
Los avisos se guardan en job_offers.review_flags (JSON); nunca bloquean nada.
"""
import json

from automation.eligibility_gate import eligibility_gate
from automation.posting_guard import alarms, guard
from search_config import get_config


def review_offer(offer: dict) -> dict:
    """Copia de la oferta con la descripción limpia y `review_flags` (JSON o None)."""
    flags = []
    reviewed = dict(offer)
    for field in ("title", "description"):
        value = offer.get(field)
        if not value:
            continue
        cleaned, findings = guard(value, "text")
        reviewed[field] = cleaned or value
        flags += [f for f in alarms(findings) if f not in flags]
    _, elig_reasons = eligibility_gate(reviewed)
    flags += elig_reasons
    reviewed["review_flags"] = json.dumps(flags, ensure_ascii=False) if flags else None
    return reviewed


def apply_hard_requirements(reviewed: dict, score: float) -> tuple[float, dict]:
    """Único punto donde un requisito duro de elegibilidad deja la oferta a 0.

    Se llama tras puntuar y antes de calcular `is_relevant`, desde el scraper (scraper/persist.py) y desde el
    cargador del inbox. Con `scoring.eligibility_hard_reject` en False (por defecto) no toca nada. Con True y
    veredicto `reject` devuelve puntuación 0 y asegura el aviso `elegibilidad: <motivo>` en `review_flags`;
    un `flag` solo avisa (ya lo hace review_offer). Devuelve (puntuación, oferta con review_flags)."""
    if not get_config().scoring.eligibility_hard_reject:
        return score, reviewed
    verdict, reasons = eligibility_gate(reviewed, extended=True)
    if verdict != "reject":
        return score, reviewed
    flags = json.loads(reviewed.get("review_flags") or "[]")
    for reason in reasons:
        text = reason if reason.startswith("elegibilidad:") else f"elegibilidad: {reason}"
        if text not in flags:
            flags.append(text)
    return 0.0, {**reviewed, "review_flags": json.dumps(flags, ensure_ascii=False)}
