"""
automation/filter_engine.py — Scores job offers and classifies them into a configured track (or manual_review).

Pesos, grupos de keywords, ubicación, experiencia y salario viven en `jobhunter.yaml` (`scoring:`),
no en `config.py`. El score suma, con su peso:
1. cada grupo de `keyword_groups` — min(hits, 5) / 5 de sus keywords
2. location   — remoto/ciudad objetivo = máxima; híbrido o presencial fuera puntúa menos pero no descarta
3. experience — prioridad a niveles junior (`scores` por nivel)
4. salary     — salario base >= `min_base`
"""
import re

from automation.eligibility_gate import eligibility_gate
from automation.experience_classifier import classify_experience
from automation.location import parse_modality
from search_config import JobHunterConfig, get_config


def _location_score(location: str, cfg: JobHunterConfig | None = None) -> float:
    """Remoto/ciudad objetivo es la prioridad; presencial fuera puntúa `other_score`
    (no se descarta), híbrido fuera `hybrid_score`; sin ubicación `unknown_score`."""
    rule = (cfg or get_config()).scoring.location
    if not location:
        return rule.unknown_score  # ubicación desconocida — no penalizar del todo
    modality = parse_modality(location)
    if modality == "remoto":
        return rule.remote_score
    if rule.city and rule.city.lower() in location.lower():
        return rule.city_score
    if modality == "hibrido":
        return rule.hybrid_score
    return rule.other_score


def _kw_hit(kw: str, text: str) -> bool:
    """Substring match; keywords cortos de una palabra (rag, llm, git, sql...) exigen
    límites de palabra para no acertar dentro de 'storage', 'digital', etc."""
    kw = kw.lower()
    if len(kw) <= 4 and kw.isalnum():
        return re.search(rf"(?<![a-z0-9]){re.escape(kw)}(?![a-z0-9])", text) is not None
    return kw in text


def _experience_score(title: str, description: str, cfg: JobHunterConfig | None = None) -> float:
    """Puntúa el nivel de experiencia según `scoring.experience.scores`."""
    scores = (cfg or get_config()).scoring.experience.scores
    level = classify_experience(title, description)
    return scores.get(level, scores["unknown"]) if level else scores["unknown"]


def _salary_score(offer: dict, cfg: JobHunterConfig | None = None) -> float:
    """Salario base >= `scoring.salary.min_base`."""
    rule = (cfg or get_config()).scoring.salary
    salary_min = offer.get("salary_min")
    salary_max = offer.get("salary_max")
    if salary_min:
        return 1.0 if salary_min >= rule.min_base else 0.0
    if salary_max:
        return rule.max_only_score if salary_max >= rule.min_base else 0.0
    return rule.unknown_score  # salario no publicado — no penalizar del todo


def score_offer(offer: dict, cfg: JobHunterConfig | None = None) -> float:
    """Calculate relevance score for a job offer dict (config por defecto: get_config())."""
    scoring = (cfg or get_config()).scoring
    title = (offer.get("title") or "").lower()
    description = (offer.get("description") or "").lower()
    location = (offer.get("location") or "").lower()
    tech_stack_raw = offer.get("tech_stack") or ""
    if isinstance(tech_stack_raw, list):
        tech_stack = " ".join(tech_stack_raw).lower()
    else:
        tech_stack = tech_stack_raw.lower()

    full_text = f"{title} {description} {tech_stack}"

    # \b requires word boundaries — evita falsos positivos como "cto" dentro de "proyecto"
    for neg in scoring.negative_keywords:
        if re.search(rf"\b{re.escape(neg.lower())}\b", full_text):
            return 0.0
    for neg in scoring.negative_title_keywords:
        if re.search(rf"\b{re.escape(neg.lower())}\b", title):
            return 0.0
    # Exige un idioma o requisito excluyente (permiso, residencia...) que no cumples: descartada.
    if eligibility_gate(offer)[0] == "reject":
        return 0.0

    score = 0.0
    for group in scoring.keyword_groups:
        hits = sum(1 for kw in group.keywords if _kw_hit(kw, full_text))
        score += group.weight * (min(hits, 5) / 5)

    score += (
        scoring.location.weight * _location_score(location, cfg)
        + scoring.experience.weight * _experience_score(title, description, cfg)
        + scoring.salary.weight * _salary_score(offer, cfg)
    )

    return round(min(score, 1.0), 3)


def classify_track(offer: dict, cfg: JobHunterConfig | None = None) -> tuple[str, float]:
    """Clasifica la oferta en un track estándar de la config, o 'manual_review'.

    Cada track puntúa hits/len(classify_keywords) (substring sobre título + descripción). Un único track
    con aciertos gana; con varios, gana el mejor si saca al menos `profile_confidence_threshold` de ventaja
    sobre el segundo. Devuelve (track_id, confianza); la confianza es el ratio o la ventaja sobre el segundo.
    """
    cfg = cfg or get_config()
    title = (offer.get("title") or "").lower()
    description = (offer.get("description") or "").lower()
    full_text = f"{title} {description}"

    ratios = []  # (track_id, ratio) solo de tracks con aciertos, en el orden de la config
    for track in cfg.standard_tracks():
        if not track.classify_keywords:
            continue
        hits = sum(1 for kw in track.classify_keywords if kw in full_text)
        if hits:
            ratios.append((track.id, hits / len(track.classify_keywords)))

    if not ratios:
        return ("manual_review", 0.0)
    if len(ratios) == 1:
        return ratios[0]

    ratios.sort(key=lambda r: r[1], reverse=True)  # estable: en empate gana el primero de la config
    diff = ratios[0][1] - ratios[1][1]
    if diff < cfg.scoring.profile_confidence_threshold:
        return ("manual_review", diff)
    return (ratios[0][0], diff)


def filter_offers(offers: list[dict]) -> list[dict]:
    """Add relevance_score, is_relevant, and cv_profile to each offer dict."""
    result = []
    for offer in offers:
        s = score_offer(offer)
        profile, _ = classify_track(offer)
        result.append({
            **offer,
            "relevance_score": s,
            "is_relevant": s >= get_config().scoring.min_relevance,
            "cv_profile": profile,
        })
    return sorted(result, key=lambda x: x["relevance_score"], reverse=True)
