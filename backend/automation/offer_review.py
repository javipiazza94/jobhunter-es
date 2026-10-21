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
