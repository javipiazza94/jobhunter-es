"""
automation/experience_classifier.py — Detects experience level from job offer text.
Maps raw text ("2-3 años de experiencia", "Senior", "Junior") to normalised levels.
"""
import re

# Patterns ordered by specificity
_YEAR_PATTERN = re.compile(
    r"(\d+)\s*[-–a]\s*(\d+)\s*(?:años?|years?)",
    re.IGNORECASE,
)
_SINGLE_YEAR = re.compile(
    r"(?:mínimo|al menos|minimum|min\.?|más de|mas de|more than|>)\s*(\d+)\s*(?:años?|years?)",
    re.IGNORECASE,
)

_LEVEL_KEYWORDS: dict[str, list[str]] = {
    "junior": [
        "junior", "jr.", "jr ", "entry level", "entry-level",
        "sin experiencia", "no experience", "recién titulad",
        "recien titulad", "prácticas", "internship", "becario",
        "trainee", "graduate", "formación",
    ],
    "mid": [
        "mid-level", "mid level", "midlevel", "semi-senior",
        "semi senior", "semisenior", "intermediate",
        "2-4 años", "3-5 años", "2+ años", "3+ años",
    ],
    "senior": [
        "senior", "sr.", "sr ", "experienced",
        "5+ años", "5-8 años", "6+ años", "7+ años",
        "especialista", "specialist", "expert",
    ],
    "lead": [
        "lead", "principal", "staff", "architect",
        "tech lead", "team lead", "head of", "director",
        "manager", "cto", "vp ", "responsable",
        "8+ años", "10+ años",
    ],
}


def classify_experience(title: str, description: str | None = None) -> str | None:
    """
    Classify a job offer into experience level.
    Returns: 'junior' | 'mid' | 'senior' | 'lead' | None
    """
    text = f"{title} {description or ''}".lower()

    # 1. Check explicit year ranges first
    m = _YEAR_PATTERN.search(text)
    if m:
        lo, hi = int(m.group(1)), int(m.group(2))
        avg = (lo + hi) / 2
        if avg <= 1.5:
            return "junior"
        if avg <= 4:
            return "mid"
        if avg <= 7:
            return "senior"
        return "lead"

    m2 = _SINGLE_YEAR.search(text)
    if m2:
        years = int(m2.group(1))
        if years <= 1:
            return "junior"
        if years <= 3:
            return "mid"
        if years <= 6:
            return "senior"
        return "lead"

    # 2. Keyword-based detection (title gets priority)
    title_lower = title.lower()

    # Check title first — most reliable signal
    for level in ("lead", "senior", "junior", "mid"):
        for kw in _LEVEL_KEYWORDS[level]:
            if kw in title_lower:
                return level

    # Check full text (title + description)
    for level in ("lead", "senior", "junior", "mid"):
        for kw in _LEVEL_KEYWORDS[level]:
            if kw in text:
                return level

    return None


def classify_contract(title: str, description: str | None = None) -> str | None:
    """
    Detect contract type from offer text.
    Returns: 'indefinido' | 'temporal' | 'freelance' | 'practicas' | None
    """
    text = f"{title} {description or ''}".lower()

    if any(kw in text for kw in ("freelance", "autónomo", "autonomo", "contractor", "por proyecto")):
        return "freelance"
    if any(kw in text for kw in ("prácticas", "practicas", "internship", "beca", "becario", "trainee")):
        return "practicas"
    if any(kw in text for kw in ("temporal", "temporary", "contract", "duración determinada")):
        return "temporal"
    if any(kw in text for kw in ("indefinido", "permanent", "fijo", "estable", "plantilla")):
        return "indefinido"

    return None
