"""
profile_proposal.py — Propone un borrador de perfil a partir del texto de un CV usando la capa de IA.

Sin IA (proveedor `none`, error, salida inválida) devuelve un borrador vacío con source "empty":
el asistente deja entonces que el usuario lo rellene a mano. Nunca lanza excepciones.
"""
import logging
import re
from typing import Literal

from pydantic import BaseModel, Field, ValidationError

from ai import AIError, get_provider

log = logging.getLogger(__name__)

MAX_CV_CHARS = 20_000
LEVELS = ("A1", "A2", "B1", "B2", "C1", "C2", "native")
MODALITIES = ("remote", "hybrid", "onsite")

SYSTEM_PROMPT = (
    "You extract a job-seeker profile from a CV. Extract ONLY facts that are present in the CV text; "
    "never invent or guess missing data (use empty strings, empty lists or null instead). "
    "Return a single JSON object that matches the given schema, with no extra commentary. "
    "Language levels must be CEFR (A1, A2, B1, B2, C1, C2) or 'native'. "
    "Work modality values must be 'remote', 'hybrid' or 'onsite'. "
    "Each target is a job title the person is a good fit for, with a few search keywords."
)


class TargetDraft(BaseModel):
    title: str = ""
    keywords: list[str] = Field(default_factory=list)


class ExperienceDraft(BaseModel):
    company: str = ""
    role: str = ""
    start: str = ""
    end: str = ""
    description: str = ""
    stack: list[str] = Field(default_factory=list)


class LanguageDraft(BaseModel):
    language: str
    level: Literal["A1", "A2", "B1", "B2", "C1", "C2", "native"]


class EligibilityDraft(BaseModel):
    work_permit_countries: list[str] = Field(default_factory=list)
    needs_sponsorship: bool | None = None
    driving_license: bool | None = None


class ProfileDraft(BaseModel):
    full_name: str = ""
    email: str = ""
    phone: str = ""
    city: str = ""
    country: str = ""
    targets: list[TargetDraft] = Field(default_factory=list)
    years_experience: int | None = None
    experience: list[ExperienceDraft] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)
    languages: list[LanguageDraft] = Field(default_factory=list)
    modality: list[Literal["remote", "hybrid", "onsite"]] = Field(default_factory=list)
    eligibility: EligibilityDraft = Field(default_factory=EligibilityDraft)


def _schema() -> dict:
    """Esquema del borrador. Solo `targets` es obligatorio: si el modelo omite otras claves (p. ej. no hay
    teléfono en el CV), `_sanitize` las rellena con sus valores por defecto en vez de descartar la respuesta."""
    schema = ProfileDraft.model_json_schema()
    schema["required"] = ["targets"]
    return schema


def _str(value) -> str:
    return value.strip() if isinstance(value, str) else ""


def _str_list(value) -> list[str]:
    return [s.strip() for s in value if isinstance(s, str) and s.strip()] if isinstance(value, list) else []


def _dicts(value) -> list[dict]:
    return [v for v in value if isinstance(v, dict)] if isinstance(value, list) else []


def _years(value) -> int | None:
    """Entero inicial de «5», 5.0, «5 años» o «5 years»; None si no hay."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value) if value >= 0 else None
    match = re.match(r"\s*(\d+)", value) if isinstance(value, str) else None
    return int(match.group(1)) if match else None


def _bool_or_none(value) -> bool | None:
    return value if isinstance(value, bool) else None


def _sanitize(data: dict) -> ProfileDraft:
    """Construye un borrador tolerante: descarta lo que no encaja (niveles, modalidades, tipos)."""
    languages = []
    for item in _dicts(data.get("languages")):
        level = _str(item.get("level"))
        level = "native" if level.lower() in ("native", "nativo", "nativa") else level.upper()
        if _str(item.get("language")) and level in LEVELS:
            languages.append({"language": _str(item["language"]), "level": level})
    elig = data.get("eligibility") if isinstance(data.get("eligibility"), dict) else {}
    return ProfileDraft(
        full_name=_str(data.get("full_name")),
        email=_str(data.get("email")),
        phone=_str(data.get("phone")),
        city=_str(data.get("city")),
        country=_str(data.get("country")),
        targets=[
            {"title": _str(t.get("title")), "keywords": _str_list(t.get("keywords"))}
            for t in _dicts(data.get("targets"))
            if _str(t.get("title"))
        ],
        years_experience=_years(data.get("years_experience")),
        experience=[
            {
                **{k: _str(e.get(k)) for k in ("company", "role", "start", "end", "description")},
                "stack": _str_list(e.get("stack")),
            }
            for e in _dicts(data.get("experience"))
        ],
        tools=_str_list(data.get("tools")),
        languages=languages,
        modality=[m for m in _str_list(data.get("modality")) if m in MODALITIES],
        eligibility={
            "work_permit_countries": _str_list(elig.get("work_permit_countries")),
            "needs_sponsorship": _bool_or_none(elig.get("needs_sponsorship")),
            "driving_license": _bool_or_none(elig.get("driving_license")),
        },
    )


def draft_from_dict(data: dict) -> ProfileDraft:
    """Borrador tolerante a partir de un dict con los campos de `ProfileDraft` (descarta lo que no encaja)."""
    return _sanitize(data if isinstance(data, dict) else {})


def propose_profile(cv_text: str, provider=None) -> tuple[ProfileDraft, str]:
    """(borrador, origen): origen "ai" si la IA lo propuso, "empty" si no hay IA o falló."""
    if not (cv_text or "").strip():
        return ProfileDraft(), "empty"
    try:
        provider = provider or get_provider()
        data = provider.generate_json(
            "CV text:\n\n" + cv_text[:MAX_CV_CHARS], _schema(), system=SYSTEM_PROMPT
        )
        return _sanitize(data), "ai"
    except (AIError, ValidationError) as exc:
        log.info("Propuesta de perfil sin IA: %s", type(exc).__name__)
    except Exception as exc:  # un proveedor defectuoso nunca debe romper el asistente
        log.error("Error inesperado proponiendo el perfil: %s", type(exc).__name__)
    return ProfileDraft(), "empty"
