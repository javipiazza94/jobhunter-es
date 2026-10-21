"""
automation/generic_filter.py — Scoring del track aislado (trabajo "puente": poca experiencia, baja cualificación).

Independiente de filter_engine.score_offer: aquel pondera el stack técnico y un suelo salarial alto,
así que las ofertas puente (atención al cliente, handling, administrativo, hostelería/retail) puntuarían ~0.
Aquí se puntúa con las reglas `isolated` del track (jobhunter.yaml); no lee `scoring.location`.

score_isolated() devuelve None si la oferta debe descartarse (hard exclude) o un float 0-1.
"""
import re
from datetime import date
from functools import lru_cache

from automation.experience_classifier import classify_experience
from search_config import IsolatedRules, Track, get_config


@lru_cache(maxsize=None)
def _compiled(pattern: str) -> re.Pattern | None:
    """Regex compilada (IGNORECASE) y cacheada por patrón; un patrón vacío no casa nunca."""
    return re.compile(pattern, re.IGNORECASE) if pattern else None


def _search(pattern: str, text: str) -> bool:
    rx = _compiled(pattern)
    return bool(rx and rx.search(text))


def primary_isolated_track() -> Track | None:
    """Track aislado que usan los flujos de trabajo puente (el primero de la config); None si no hay."""
    tracks = get_config().isolated_tracks()
    return tracks[0] if tracks else None


def isolated_min_score(track: Track) -> float:
    """Score mínimo para guardar una oferta del track aislado."""
    return track.isolated.min_score


def _hits(text: str, words: list[str]) -> bool:
    return any(w in text for w in words)


def _role_score(rules: IsolatedRules, title: str, description: str) -> float:
    t, d = title.lower(), description.lower()
    best = 0.0
    for words in rules.role_families.values():
        if _hits(t, words):
            return 1.0
        if _hits(d, words):
            best = 0.5
    return best


def _is_capital(rules: IsolatedRules, location: str) -> bool:
    """'Capital', 'Capital, Provincia'... sí; 'Pueblo, Provincia' o un
    'Provincia' suelto (sin ciudad) son provincia, no capital."""
    first = location.split(",")[0].strip().lower()
    return first in rules.capital_names


def _is_province(rules: IsolatedRules, location: str) -> bool:
    """Resto de la provincia: la regex de provincia o un municipio conocido."""
    loc = location.lower()
    return _search(rules.province_regex, loc) or any(t in loc for t in rules.province_towns)


def _location_score(rules: IsolatedRules, location: str | None, title: str, description: str) -> float | None:
    """capital/remoto = máximo, 'Toda España' (teletrabajo en InfoJobs), resto de la provincia,
    sin ubicación = neutro (no descarta, rankea bajo); None = excluir (otra provincia o ciudad)."""
    scores = rules.location_scores
    loc = location or ""
    blob = f"{loc} {title} {description}"
    if _is_capital(rules, loc) or _search(rules.remote_regex, blob):
        return scores["capital"]
    if _search(rules.nationwide_regex, loc):
        return scores["nationwide"]
    if not loc.strip():
        return scores["unknown"]
    if _is_province(rules, loc):
        return scores["province"]
    return None


def _recency_score(rules: IsolatedRules, posted_at: str | None) -> float:
    """Más reciente = más probable que siga abierta. Sin fecha: neutro."""
    if not posted_at:
        return 0.5
    try:
        age = (date.today() - date.fromisoformat(posted_at[:10])).days
    except ValueError:
        return 0.5
    for max_days, score in rules.recency:
        if age <= max_days:
            return score
    return 0.0


def score_isolated(offer: dict, track: Track) -> float | None:
    rules = track.isolated
    title = offer.get("title") or ""
    description = offer.get("description") or ""

    if _search(rules.exclude_title_regex, title) or _search(rules.exclude_text_regex, f"{title} {description}"):
        return None
    if _search(rules.exclude_lang_regex, title):
        return None

    role = _role_score(rules, title, description)
    if role == 0.0:
        return None

    loc = _location_score(rules, offer.get("location"), title, description)
    if loc is None:
        return None

    level = classify_experience(title, description)
    if level in rules.reject_levels:
        return None
    exp = 1.0 if level == "junior" else rules.unknown_level_score  # desconocida pasa, pero rankea menos

    sal = offer.get("salary_min")
    if sal is None:
        sal_score = rules.salary_scores["unknown"]
    else:
        sal_score = rules.salary_scores["above" if sal >= rules.salary_floor else "below"]  # no es un gate, solo desempata

    w = rules.weights
    score = (w.get("role", 0.0) * role + w.get("location", 0.0) * loc + w.get("experience", 0.0) * exp
             + w.get("salary", 0.0) * sal_score + w.get("recency", 0.0) * _recency_score(rules, offer.get("posted_at")))
    return round(score, 3)
