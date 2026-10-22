"""scraper/persist.py — único punto donde una oferta scrapeada se puntúa y se guarda."""
from automation.filter_engine import classify_track, score_offer
from automation.offer_review import apply_hard_requirements, review_offer
from search_config import followed_tier_for, get_config
from database import upsert_company, upsert_job_offer


def save_scored_offer(conn, offer: dict, source: str) -> str:
    """Crea la empresa si no existe, puntúa la oferta y la guarda. Devuelve el id de la oferta."""
    company_id = upsert_company(conn, {"name": offer.get("company_name") or "Desconocida", "source": source})
    offer = review_offer(offer)  # descripción limpia + review_flags (posting_guard, idiomas)
    score, offer = apply_hard_requirements(offer, score_offer(offer))  # 0 si incumple un requisito duro (opt-in)
    company_name = offer.get("company_name") or ""
    tier = followed_tier_for(company_name, classify_track(offer)[0])
    return upsert_job_offer(conn, {
        **offer,
        "company_id": company_id,
        "is_relevant": score >= get_config().scoring.min_relevance,
        "relevance_score": score,
        "followed_tier": tier,
    })


def save_scored_offers(conn, offers: list[dict], source: str) -> int:
    """Guarda las ofertas con URL; devuelve cuántas se guardaron."""
    saved = 0
    for offer in offers:
        if offer.get("url"):
            save_scored_offer(conn, offer, source)
            saved += 1
    return saved
