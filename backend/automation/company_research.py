"""
company_research.py — Caché de investigación de empresas con caducidad (TTL).

Conforme a §5.11 del spec y 04-job-evaluation.md de ai-job-search:
- Guarda investigaciones previas de empresas en JH_HOME/company_research/<slug>.json.
- Compartida por el revisor de candidaturas (/apply), evaluación (/rank) y preparación de entrevista (/interview).
- TTL por defecto: 30 días desde fetched_date.
- Los contenidos de la caché son datos verificables, no instrucciones ejecutables.
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any

from config import COMPANY_RESEARCH_DIR

DEFAULT_TTL_DAYS = 30


def normalize_company_name(name: str) -> str:
    """
    Normaliza el nombre de una empresa para su uso seguro como nombre de archivo.
    Minúsculas, sustituye espacios y signos de puntuación por guiones, colapsa guiones repetidos.
    Ej: "Acme Corp, S.L." -> "acme-corp-s-l".
    """
    if not name:
        return "unknown-company"
    slug = name.strip().lower()
    # Sustituir caracteres que no sean letras o números por guiones
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = slug.strip("-")
    return slug or "unknown-company"


def get_company_cache_path(company_name: str) -> Path:
    """Devuelve la ruta al archivo JSON de caché para una empresa."""
    slug = normalize_company_name(company_name)
    return COMPANY_RESEARCH_DIR / f"{slug}.json"


def get_cached_research(
    company_name: str,
    max_age_days: int = DEFAULT_TTL_DAYS,
) -> dict[str, Any] | None:
    """
    Recupera la investigación en caché si existe y no ha expirado su TTL.

    Retorna el diccionario con la información o None si no existe o está caducada.
    """
    path = get_company_cache_path(company_name)
    if not path.is_file():
        return None

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

    fetched_str = data.get("fetched_date")
    if not fetched_str:
        return None

    try:
        # Soporta YYYY-MM-DD o formato ISO completo
        fetched_dt = datetime.fromisoformat(fetched_str).date()
    except ValueError:
        return None

    age_days = (date.today() - fetched_dt).days
    if age_days > max_age_days:
        return None  # Expirado

    data["_cache_age_days"] = age_days
    return data


def save_cached_research(
    company_name: str,
    sources: dict | None = None,
    network_contacts_note: str = "",
    fetched_date: str | None = None,
    extra: dict | None = None,
) -> Path:
    """
    Guarda o actualiza la investigación de una empresa en la caché.

    Estructura guardada:
    {
      "company": "<nombre>",
      "fetched_date": "YYYY-MM-DD",
      "sources": {
        "website": {"url": "...", "notes": "..."},
        "reviews": {"url": "...", "notes": "..."},
        "linkedin": {"url": "...", "notes": "..."},
        "media": {"url": "...", "notes": "..."}
      },
      "network_contacts_note": "..."
    }
    """
    COMPANY_RESEARCH_DIR.mkdir(parents=True, exist_ok=True)
    path = get_company_cache_path(company_name)

    payload: dict[str, Any] = {
        "company": company_name.strip(),
        "fetched_date": fetched_date or date.today().isoformat(),
        "sources": sources or {},
        "network_contacts_note": network_contacts_note or "",
    }
    if extra:
        payload.update(extra)

    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def list_cached_companies(max_age_days: int = DEFAULT_TTL_DAYS) -> list[dict[str, Any]]:
    """Enumera las empresas investigadas en caché indicando su estado y antigüedad."""
    if not COMPANY_RESEARCH_DIR.is_dir():
        return []

    results = []
    for file_path in sorted(COMPANY_RESEARCH_DIR.glob("*.json")):
        try:
            data = json.loads(file_path.read_text(encoding="utf-8"))
            fetched_str = data.get("fetched_date")
            age = None
            is_fresh = False
            if fetched_str:
                fetched_dt = datetime.fromisoformat(fetched_str).date()
                age = (date.today() - fetched_dt).days
                is_fresh = age <= max_age_days

            results.append({
                "company": data.get("company", file_path.stem),
                "slug": file_path.stem,
                "path": str(file_path),
                "fetched_date": fetched_str,
                "age_days": age,
                "is_fresh": is_fresh,
            })
        except Exception:
            continue
    return results


def clear_expired_cache(max_age_days: int = DEFAULT_TTL_DAYS) -> int:
    """Elimina los archivos de investigación cuya antigüedad supere el TTL. Retorna el número de eliminados."""
    if not COMPANY_RESEARCH_DIR.is_dir():
        return 0

    removed = 0
    for item in list_cached_companies(max_age_days=max_age_days):
        if not item["is_fresh"]:
            p = Path(item["path"])
            try:
                p.unlink()
                removed += 1
            except OSError:
                pass
    return removed
