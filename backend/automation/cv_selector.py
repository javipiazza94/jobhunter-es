"""automation/cv_selector.py — qué CV adjuntar a cada candidatura, según la config del track.

`TrackCV.default` / `by_tag` son claves de profile.json (`cv_sap_path`, `cv_sap_modules.FI_CO`) o
rutas relativas a JH_HOME (si contienen `/` o acaban en .pdf/.docx).
"""
import json
import re
from pathlib import Path

from config import PROFILE_PATH, resolve_data_path
from search_config import Track, get_config


def load_profile() -> dict:
    """profile.json como dict; `{}` si falta o está corrupto (un clon recién hecho aún no lo tiene)."""
    try:
        data = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _is_path(ref: str) -> bool:
    return "/" in ref or ref.lower().endswith((".pdf", ".docx"))


def _resolve_ref(ref: str | None, profile: dict) -> str | None:
    """Clave de profile.json (con '.' para anidar) o ruta relativa → ruta como texto."""
    if not ref:
        return None
    if _is_path(ref):
        return ref
    value: object = profile
    for part in ref.split("."):
        value = value.get(part) if isinstance(value, dict) else None
    return value if isinstance(value, str) and value else None


def cv_tag_key(track: Track, tag: str | None, title: str | None) -> str | None:
    """Etiqueta de CV de la oferta, o None si no se puede determinar (→ CV por defecto del track)."""
    cv = track.cv
    if tag in cv.tag_aliases:
        return cv.tag_aliases[tag]
    if tag:  # etiqueta conocida sin alias: CV por defecto
        return None
    found = {p.tag for p in cv.tag_patterns if re.search(p.regex, title or "", re.IGNORECASE)}
    return found.pop() if len(found) == 1 else None  # ambiguo → por defecto


def select_cv(track_id: str | None, profile: dict, tag: str | None = None,
              title: str | None = None, cfg=None) -> Path | None:
    """Ruta del CV a adjuntar (None si el track no existe o el fichero no existe)."""
    track = (cfg or get_config()).track(track_id) if track_id else None
    if track is None:
        return None
    key = cv_tag_key(track, tag, title)
    rel = _resolve_ref(track.cv.by_tag.get(key), profile) if key else None
    rel = rel or _resolve_ref(track.cv.default, profile)
    if not rel:
        return None
    cv = resolve_data_path(rel)
    return cv if cv.exists() else None


def cover_template_for(track_id: str | None, cfg=None) -> str:
    """Plantilla de carta del track; 'tech' si el track no existe."""
    track = (cfg or get_config()).track(track_id) if track_id else None
    return track.cover_template if track else "tech"


def default_track_id(cfg=None) -> str | None:
    """Primer track estándar de la config (para candidaturas sin cv_profile guardado)."""
    standard = (cfg or get_config()).standard_tracks()
    return standard[0].id if standard else None


def cover_letter_docx_for(track_id: str | None, profile: dict, cfg=None) -> Path | None:
    """Carta pre-escrita (.docx) del track; cae a la clave 'generica' si falta. None si no existe."""
    track = (cfg or get_config()).track(track_id) if track_id else None
    docs = profile.get("cover_letter_docx", {})
    rel = (docs.get(track.cover_letter_docx_key) if track and track.cover_letter_docx_key else None) or docs.get("generica", "")
    if not rel:
        return None
    path = resolve_data_path(rel)
    return path if path.exists() else None
