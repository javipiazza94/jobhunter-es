"""
automation/cover_letter.py — Generates personalised cover letters via Jinja2.
Supports variant_seed for deterministic cover letter variation per company.
"""
import hashlib
import re

from jinja2 import Environment, FileSystemLoader, TemplateNotFound
from config import TEMPLATES_DIR
from profile_store import load_profile


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
) -> str:
    """Return rendered cover letter as plain text."""
    profile = _load_profile()
    env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)))
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
