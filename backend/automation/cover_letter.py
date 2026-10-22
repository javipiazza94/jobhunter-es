"""
automation/cover_letter.py — Generates personalised cover letters via Jinja2.
Supports variant_seed for deterministic cover letter variation per company.
"""
import hashlib
import re
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, TemplateNotFound
import config
from profile_store import load_profile


def available_template_languages() -> set[str]:
    """Conjunto de códigos de idioma para los que hay plantillas en backend/templates o JH_HOME/templates."""
    langs = {"es"}
    for base in (config.TEMPLATES_DIR, config.TEMPLATES_OVERRIDE_DIR):
        if base.is_dir():
            for child in base.iterdir():
                if child.is_dir() and not child.name.startswith((".", "_")):
                    if any(child.glob("*.j2")):
                        langs.add(child.name)
    return langs


def letter_language(offer: dict | None = None, profile: dict | None = None) -> str:
    """Idioma de los documentos de una oferta: offer.language si hay plantillas, si no el default del perfil, si no 'es'."""
    avail = available_template_languages()
    offer = offer or {}
    profile = profile or _load_profile()

    offer_lang = offer.get("language")
    if not offer_lang:
        from automation.language_detect import detect_language

        text = f"{offer.get('title') or ''}\n\n{offer.get('description') or ''}".strip()
        if text:
            offer_lang = detect_language(text)

    if offer_lang and offer_lang in avail:
        return offer_lang

    prefs = profile.get("preferences") or {}
    pref_lang = prefs.get("default_language") or prefs.get("ui_language")
    if pref_lang and pref_lang in avail:
        return pref_lang

    return "es"


def template_search_dirs(lang: str = "es") -> list[Path]:
    """Carpetas de búsqueda de plantillas Jinja para un idioma (override en JH_HOME primero)."""
    dirs: list[Path] = []
    override_lang = config.TEMPLATES_OVERRIDE_DIR / lang
    if override_lang.is_dir():
        dirs.append(override_lang)
    if lang == "es" and config.TEMPLATES_OVERRIDE_DIR.is_dir():
        dirs.append(config.TEMPLATES_OVERRIDE_DIR)
    builtin_lang = config.TEMPLATES_DIR / lang
    if builtin_lang.is_dir():
        dirs.append(builtin_lang)
    if config.TEMPLATES_DIR.is_dir():
        dirs.append(config.TEMPLATES_DIR)
    return dirs


def _load_profile() -> dict:
    """Perfil del usuario; `{}` si aún no existe (la plantilla usa valores por defecto)."""
    return load_profile()


_INTRO_TOKEN = re.compile(r"\{\{|\}\}|\{company_name\}")


def _fill_intro(text: str, company_name: str) -> str:
    """Sustituye `{company_name}` y convierte `{{`/`}}` en llaves literales, como el antiguo `str.format`, pero
    sin lanzar con otras llaves (`{x}`, `{0}` quedan tal cual)."""
    def repl(m: re.Match) -> str:
        return {"{{": "{", "}}": "}"}.get(m.group(0), company_name)
    return _INTRO_TOKEN.sub(repl, text)


def _pick_variant(variants: list[str], seed: str) -> str:
    """Return one variant deterministically based on seed (stable across restarts)."""
    idx = int(hashlib.md5(seed.encode()).hexdigest(), 16) % len(variants)
    return variants[idx]


def generate(
    company_name: str,
    job_title: str | None = None,
    tech_stack: str | None = None,
    template: str = "tech",
    variant_seed: str | None = None,
    lang: str = "es",
) -> str:
    """Return rendered cover letter as plain text."""
    profile = _load_profile()
    search_dirs = template_search_dirs(lang)
    env = Environment(loader=FileSystemLoader([str(p) for p in search_dirs]))
    tmpl_name = f"cover_letter_{template}.j2"
    try:
        tmpl = env.get_template(tmpl_name)
    except TemplateNotFound:
        tmpl = env.get_template("cover_letter_base.j2")

    personal = profile.get("personal", {})
    seed = variant_seed or (company_name + (job_title or ""))
    variant_index = int(_pick_variant(["0", "1", "2"], seed))

    # Solo experiencia IT relevante en la carta: los puestos previos no técnicos
    # (hostelería, teleoperador, comunicación, portero de cine) tienen stack=[]
    # en profile.json y no aportan a una candidatura tech.
    it_experience = [exp for exp in profile.get("experience", []) if exp.get("stack")]

    return tmpl.render(
        company_name=company_name,
        job_title=job_title,
        tech_stack=tech_stack,
        name=personal.get("name", ""),
        email=personal.get("email", ""),
        phone=personal.get("phone", ""),
        linkedin=personal.get("linkedin", ""),
        portfolio=personal.get("portfolio", ""),
        experience=it_experience,
        cover_letter_intro=_fill_intro(profile.get("cover_letter_intro", ""), company_name),
        cover_letter_stack=profile.get("cover_letter_stack", ""),
        cover_letter_closing=profile.get("cover_letter_closing", ""),
        variant_index=variant_index,
    )
