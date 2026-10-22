"""
eligibility_gate.py — Filtro de elegibilidad de una oferta frente a los datos del perfil.

Conforme a §5.11 del spec:
- Amplía language_gate: evalúa permiso de trabajo / visado, residencia exigida,
  título obligatorio y carné de conducir.
- Incumplir un requisito duro deja la oferta en 'reject' (filtro devuelve score 0).
- Un requisito dudoso o no especificado en el perfil deja 'flag' (aviso informativo,
  no toca la puntuación, decide el usuario).
- Requisitos marcados como valorables / nice to have no penalizan.
"""

from __future__ import annotations

import json
import re

from automation.language_gate import language_gate
from config import PROFILE_PATH

# ── Expresiones regulares de detección de requisitos ──────────────────────────

_REQUIRED = re.compile(
    r"\b(imprescindible|obligatori[oa]|requisito|requerid[oa]|necesari[oa]|indispensable|"
    r"required|mandatory|essential|exigid[oa]|se requiere)\b",
    re.I,
)

_NICE_TO_HAVE = re.compile(
    r"(valorable|se valorar[aá]|valoraremos|valorar[aá]|deseable|preferible|\bplus\b|nice to have|"
    r"\bbonus\b|advantage|ventaja|\bideally\b|idealmente|would be (a )?(plus|great)|is a plus|desirable|"
    r"te har[aá] destacar|destacar[aá]s|puntos extra|nice-to-have|o experiencia equivalente|or equivalent experience)",
    re.I,
)

# 1. Autorización / Visado / Ciudadanía
_US_CITIZENSHIP_RX = re.compile(
    r"\b(us citizenship required|must be a us citizen|only us citizens|citizenship: us|"
    r"us citizen only|requiere ciudadan[íi]a estadounidense)\b",
    re.I,
)

_SECURITY_CLEARANCE_RX = re.compile(
    r"\b(security clearance required|active security clearance|top secret clearance|secret clearance|"
    r"habilitaci[oó]n de seguridad requerida)\b",
    re.I,
)

_NO_SPONSORSHIP_RX = re.compile(
    r"\b(must be authorized to work in the us without sponsorship|"
    r"no (visa )?sponsorship (is )?available|no sponsorship provided|"
    r"no ofrecemos (visado|patrocinio de visado))\b",
    re.I,
)

_SPAIN_WORK_PERMIT_RX = re.compile(
    r"\b(permiso de trabajo|autorizaci[oó]n para trabajar en espa[ñn]a|permiso de residencia y trabajo)\b",
    re.I,
)

# Sin patrocinio de visado (genérico, de cualquier país): solo importa si el candidato lo necesita
_SPONSORSHIP_UNAVAILABLE_RX = re.compile(
    r"\b(no (visa )?sponsorship(?!\s+(?:is\s+)?(?:needed|required|necessary|necesario))|sponsorship (is )?(not|un)available|unable to (offer |provide )?(visa )?sponsor\w*|"
    r"(do|does) not (offer|provide) (visa )?sponsorship|sin patrocinio de visado|no (ofrecemos|damos) patrocinio)\b",
    re.I,
)

# 2. Residencia geográfica excluyente
_NON_EU_RESIDENCE_RX = re.compile(
    r"\b(must be (based|located) in (the )?(us|usa|united states|uk|united kingdom|canada|australia|germany|france)|"
    r"residencia obligatoria en (eeuu|estados unidos|reino unido|francia|alemania))\b",
    re.I,
)

# 3. Título universitario obligatorio
_DEGREE_TERMS_RX = re.compile(
    r"\b(t[íi]tulo universitario|grado universitario|licenciatura|ingenier[íi]a|"
    r"bachelor('?s)? degree|master('?s)? degree)\b",
    re.I,
)

# 4. Carné de conducir
_DRIVING_LICENSE_RX = re.compile(
    r"\b(carn[eé] de conducir|permiso de conducir|licencia de conducir|driver('?s)? licen[sc]e|carnet b)\b",
    re.I,
)


def _load_profile() -> dict:
    try:
        return json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


_RESIDENCE_CODES = {
    "us": "US", "usa": "US", "united states": "US", "eeuu": "US", "estados unidos": "US",
    "uk": "GB", "united kingdom": "GB", "reino unido": "GB", "canada": "CA", "australia": "AU",
    "germany": "DE", "alemania": "DE", "france": "FR", "francia": "FR",
}
_RESIDENCE_NAME_RX = re.compile(
    r"(?:based|located) in (?:the )?(\w+(?: \w+)?)|residencia obligatoria en (\w+(?: \w+)?)", re.I)


_COUNTRY_ALIASES = {"UK": "GB"}  # el perfil puede traer UK; la tabla de residencias usa ISO (GB)
_ALTERNATIVES_RX = re.compile(r"\s*(?:/|,|\b(?:or|and|o|y)\b)", re.I)


def _has_residence_alternatives(line: str) -> bool:
    """True si tras el país exigido hay alternativas ('UK or Ireland', 'US / Europe'): dudoso, no excluyente."""
    m = _NON_EU_RESIDENCE_RX.search(line)
    return bool(m and _ALTERNATIVES_RX.match(line, m.end()))


def _required_residence_code(line: str) -> str:
    """Código de país de la residencia exigida en la línea ('' si no se reconoce)."""
    m = _RESIDENCE_NAME_RX.search(line)
    if not m:
        return ""
    name = (m.group(1) or m.group(2)).lower()
    return _RESIDENCE_CODES.get(name) or _RESIDENCE_CODES.get(name.split()[0], "")


def _needs_sponsorship(personal: dict, profile: dict) -> bool:
    """True si el perfil declara que necesita patrocinio de visado (`personal` o bloque `eligibility`)."""
    eligibility = profile.get("eligibility") if isinstance(profile.get("eligibility"), dict) else {}
    return (personal.get("needs_sponsorship") or eligibility.get("needs_sponsorship")) is True


def _has_spanish_work_authorization(personal: dict) -> bool:
    """Comprueba si el perfil cuenta con autorización de trabajo en España/UE."""
    dni_nie = personal.get("dni_nie") or ""
    country_code = (personal.get("country_code") or "").upper()
    country = (personal.get("country") or "").lower()
    nationality = (personal.get("nationality") or "").lower()

    if country_code == "ES" or "españ" in country or "españ" in nationality:
        return True
    # DNI español (8 números + letra) o NIE comunitario
    if re.match(r"^\d{8}[A-Z]$", dni_nie.strip().upper()):
        return True
    return personal.get("work_permit") is True


def _has_university_degree(education: list[dict]) -> bool:
    """Comprueba si el candidato declara algún título de grado, licenciatura, ingeniería o máster."""
    degree_keywords = re.compile(
        r"\b(grado|licenciatura|ingenier[íi]a|m[aá]ster|master|bachelor|phd|doctorado)\b",
        re.I,
    )
    for edu in education:
        title = edu.get("title") or ""
        if degree_keywords.search(title):
            return True
    return False


def check_eligibility(offer: dict, profile_data: dict | None = None, extended: bool = False) -> tuple[str, list[str]]:
    """
    Evalúa la elegibilidad del candidato para una oferta concreta.

    `extended` activa las reglas de requisitos duros añadidas después (patrocinio de visado necesario,
    residencia exigida en otro país): solo las usa `offer_review.apply_hard_requirements` con
    `scoring.eligibility_hard_reject`; `score_offer` no las pasa, así que sus puntuaciones no cambian.

    Retorna una tupla:
      (veredicto, motivos)
      - veredicto: 'ok' | 'flag' | 'reject'
      - motivos: lista de explicaciones detalladas
    """
    text = f"{offer.get('title') or ''}\n{offer.get('description') or ''}"
    if not text.strip():
        return "ok", []

    profile = profile_data if profile_data is not None else _load_profile()
    personal = profile.get("personal", {})
    education = profile.get("education", [])

    rejects: list[str] = []
    flags: list[str] = []

    # 1. Filtro de idiomas existente
    lang_verdict, lang_reasons = language_gate(offer)
    if lang_verdict == "reject":
        rejects.extend(lang_reasons)
    elif lang_verdict == "flag":
        flags.extend(lang_reasons)

    # Evaluación línea a línea para evitar cruce de contextos
    for line in text.splitlines():
        line_clean = line.strip()
        if not line_clean or _NICE_TO_HAVE.search(line_clean):
            continue

        # ── 2. Autorización / Visado / Ciudadanía ─────────────────────────────
        if _US_CITIZENSHIP_RX.search(line_clean):
            nat = (personal.get("nationality") or "").lower()
            if "estados unidos" not in nat and "us" not in nat and "american" not in nat:
                rejects.append("elegibilidad: exige ciudadanía estadounidense")

        if _SECURITY_CLEARANCE_RX.search(line_clean):
            rejects.append("elegibilidad: exige habilitación de seguridad (security clearance)")

        if _NO_SPONSORSHIP_RX.search(line_clean):
            # Si exige trabajo en US sin patrocinio y el candidato reside en España
            if (personal.get("country_code") or "").upper() == "ES":
                rejects.append("elegibilidad: requiere autorización de trabajo en EE.UU. sin patrocinio")

        if extended and _SPONSORSHIP_UNAVAILABLE_RX.search(line_clean) and _needs_sponsorship(personal, profile):
            rejects.append("elegibilidad: la oferta no patrocina visado y lo necesitas")

        if _SPAIN_WORK_PERMIT_RX.search(line_clean) and bool(_REQUIRED.search(line_clean)):
            if personal.get("work_permit") is False:
                rejects.append("elegibilidad: exige permiso de trabajo en España y no dispones de él")
            elif not _has_spanish_work_authorization(personal) and personal.get("work_permit") is None:
                flags.append("elegibilidad: exige permiso de trabajo en España (revisa tu perfil)")

        # ── 3. Residencia geográfica excluyente ───────────────────────────────
        if _NON_EU_RESIDENCE_RX.search(line_clean):
            country_code = (personal.get("country_code") or "").upper()
            required = _required_residence_code(line_clean)
            if country_code == "ES":
                rejects.append("elegibilidad: exige residencia fuera de España/UE")
            elif extended and country_code and required:
                country_code = _COUNTRY_ALIASES.get(country_code, country_code)
                if country_code != required:
                    if _has_residence_alternatives(line_clean):
                        flags.append("elegibilidad: exige residir en un país con alternativas; revisa si cumples")
                    else:
                        rejects.append(f"elegibilidad: exige residir en {required} y resides en {country_code}")

        # ── 4. Título universitario obligatorio ──────────────────────────────
        if _DEGREE_TERMS_RX.search(line_clean) and bool(_REQUIRED.search(line_clean)):
            if not _has_university_degree(education):
                rejects.append("elegibilidad: exige titulación universitaria")

        # ── 5. Carné de conducir ──────────────────────────────────────────────
        if _DRIVING_LICENSE_RX.search(line_clean) and bool(_REQUIRED.search(line_clean)):
            driving_val = personal.get("driving_license")
            if driving_val is False:
                rejects.append("elegibilidad: exige carné de conducir y declaras no tenerlo")
            elif driving_val is None or (isinstance(driving_val, list) and not driving_val):
                flags.append("elegibilidad: la oferta exige carné de conducir y no consta en tu perfil")

    # Eliminar duplicados preservando orden
    def _dedupe(seq: list[str]) -> list[str]:
        seen = set()
        return [x for x in seq if not (x in seen or seen.add(x))]

    rejects = _dedupe(rejects)
    flags = _dedupe(flags)

    if rejects:
        return "reject", rejects + flags
    if flags:
        return "flag", flags
    return "ok", []


def eligibility_gate(offer: dict, profile_data: dict | None = None, extended: bool = False) -> tuple[str, list[str]]:
    """Función de entrada principal para el filtro de elegibilidad."""
    return check_eligibility(offer, profile_data=profile_data, extended=extended)
