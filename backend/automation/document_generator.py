"""
document_generator.py — Generación determinista de CV y carta de presentación en LaTeX.

Conforme a §5.11 del spec:
- Generación determinista desde profile.json con plantillas Jinja → LaTeX (sin IA).
- Reglas de honestidad: no inventa habilidades ni datos ausentes en profile.json.
- Escape riguroso de caracteres especiales LaTeX y rangos de fecha ASCII (sin en-dashes Unicode).
- Compilación vía latex_compiler (Tectonic) y verificación mediante verify_pdf.
"""

from __future__ import annotations

import json
import os
import re
import shutil
from datetime import date
from pathlib import Path
from typing import Any

import jinja2

from automation.latex_compiler import compile_latex, resolve_template_path
from automation.verify_pdf import verify_pdf
from config import PROFILE_PATH, REPO_ROOT

_LATEX_ESCAPES = {
    "\\": r"\textbackslash{}",
    "&": r"\&",
    "%": r"\%",
    "$": r"\$",
    "#": r"\#",
    "_": r"\_",
    "{": r"\{",
    "}": r"\}",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
}
_LATEX_REGEX = re.compile(r"[\\&%$#_{}~^]")


def latex_escape(value: Any) -> str:
    """Escapa caracteres especiales de LaTeX para evitar inyección o errores de sintaxis."""
    if value is None:
        return ""
    return _LATEX_REGEX.sub(lambda m: _LATEX_ESCAPES[m.group(0)], str(value))


def format_date_range(start: str | None, end: str | None) -> str:
    """
    Formatea un rango de fechas con guion ASCII simple (-)
    para satisfacer la verificación de verify_pdf (--ascii-dates).
    """
    s = (start or "").strip()
    e = (end or "").strip()
    if not s and not e:
        return ""
    if s and not e:
        return f"{s}-Present"
    if s == e:
        return s
    return f"{s}-{e}"


def _get_jinja_env(template_dir: Path) -> jinja2.Environment:
    """Crea un entorno Jinja configurado para plantillas LaTeX con delimitadores seguros."""
    env = jinja2.Environment(
        block_start_string="((*",
        block_end_string="*))",
        variable_start_string="(((",
        variable_end_string=")))",
        comment_start_string="((=",
        comment_end_string="=))",
        loader=jinja2.FileSystemLoader(str(template_dir)),
        trim_blocks=True,
        lstrip_blocks=True,
        autoescape=False,
    )
    env.filters["latex_escape"] = latex_escape
    return env


def prepare_cv_context(profile: dict, track: str = "general") -> dict:
    """
    Prepara el diccionario de contexto para la plantilla de CV a partir de profile.json.
    Aplica las reglas de honestidad: solo incluye información presente en el perfil.
    """
    personal = dict(profile.get("personal", {}))
    full_name = personal.get("name", "")
    first_name = personal.get("first_name", "")
    last_name = personal.get("last_name", "")

    if not first_name and full_name:
        parts = full_name.split()
        first_name = parts[0] if parts else ""
        last_name = " ".join(parts[1:]) if len(parts) > 1 else ""

    personal["first_name"] = first_name
    personal["last_name"] = last_name

    # Summary según track
    summary_dict = profile.get("summary", {})
    summary_text = summary_dict.get(track) or summary_dict.get("general") or ""

    # Competencias agrupadas desde stack
    stack = profile.get("stack", {})
    category_labels = [
        ("programming", "Programming Languages"),
        ("frameworks", "Frameworks & Libraries"),
        ("ai_ml", "AI & Machine Learning"),
        ("data", "Data & Databases"),
        ("devops_cloud", "Cloud & DevOps"),
        ("sap_modules", "SAP Modules"),
        ("sap_tools", "SAP Tools"),
        ("other_tools", "Tools & Platforms"),
    ]
    competencies = []
    for key, label in category_labels:
        items = stack.get(key, [])
        if items and isinstance(items, list):
            competencies.append((label, ", ".join(str(x) for x in items)))

    # Experiencia
    exp_list = []
    for item in profile.get("experience", []):
        start = item.get("start", "")
        end = item.get("end", "")
        date_range = format_date_range(start, end)
        bullets = item.get("bullets", [])
        desc = item.get("description", "")
        if not bullets and desc:
            bullets = [desc]
        exp_list.append({
            "company": item.get("company", ""),
            "role": item.get("role", ""),
            "location": item.get("location") or personal.get("city", ""),
            "date_range": date_range,
            "bullets": bullets,
            "description": desc,
        })

    # Educación
    edu_list = []
    for item in profile.get("education", []):
        start = str(item.get("start", ""))
        end = str(item.get("end", ""))
        date_range = format_date_range(start, end)
        edu_list.append({
            "title": item.get("title", ""),
            "institution": item.get("institution", ""),
            "location": item.get("location") or personal.get("city", ""),
            "date_range": date_range,
            "details": item.get("description") or item.get("details", ""),
        })

    # Idiomas
    languages = profile.get("languages", [])
    lang_parts = []
    for lang in languages:
        if isinstance(lang, dict):
            name = lang.get("language", "")
            level = lang.get("level", "")
            lang_parts.append(f"{name} ({level})" if level else name)
        elif isinstance(lang, str):
            lang_parts.append(lang)
    languages_line = ", ".join(lang_parts)

    # Certificaciones
    certifications = profile.get("certifications", [])

    return {
        "personal": personal,
        "summary_text": summary_text,
        "competencies": competencies,
        "experience": exp_list,
        "education": edu_list,
        "languages": languages,
        "languages_line": languages_line,
        "certifications": certifications,
    }


def prepare_cover_letter_context(
    profile: dict,
    company_name: str,
    role_title: str,
    track: str = "general",
) -> dict:
    """Prepara el contexto determinista para la carta de presentación."""
    personal = profile.get("personal", {})

    # Párrafo de apertura
    intro_template = profile.get("cover_letter_intro") or (
        "Me dirijo a ustedes para presentar mi candidatura al puesto de {role_title} en {company_name}."
    )
    opening = intro_template.format(company_name=company_name, role_title=role_title)

    # Párrafo de cuerpo / stack
    body_template = profile.get("cover_letter_stack") or (
        "Cuento con sólida experiencia en desarrollo de software y análisis de datos, "
        "aplicando buenas prácticas de ingeniería y orientación a resultados."
    )
    body = body_template.format(company_name=company_name, role_title=role_title)

    # Bullets de logros más relevantes desde experience
    bullets = []
    for exp in profile.get("experience", []):
        for b in exp.get("bullets", []):
            if len(bullets) < 3:
                bullets.append(b)
        if not exp.get("bullets") and exp.get("description"):
            if len(bullets) < 3:
                bullets.append(exp.get("description"))

    # Conexión con la empresa
    connection = (
        f"Me entusiasma la visión y el crecimiento de {company_name}, donde considero que mis "
        "conocimientos pueden aportar valor directo al equipo desde el primer día."
    )

    # Cierre
    closing_template = profile.get("cover_letter_closing") or (
        "Agradezco de antemano su tiempo y consideración, y quedo a su entera disposición "
        "para profundizar en mi trayectoria en una entrevista."
    )
    closing = closing_template.format(company_name=company_name, role_title=role_title)

    return {
        "personal": personal,
        "company_name": company_name,
        "role_title": role_title,
        "current_date": date.today().strftime("%d de %B de %Y"),
        "opening_paragraph": opening,
        "body_paragraph": body,
        "bullets": bullets,
        "connection_paragraph": connection,
        "closing_paragraph": closing,
    }


def render_cv_latex(profile: dict, track: str = "general") -> str:
    """Renderiza el código fuente LaTeX del CV determinista."""
    tpl_path = resolve_template_path("cv/cv.tex.j2")
    env = _get_jinja_env(tpl_path.parent)
    template = env.get_template(tpl_path.name)
    context = prepare_cv_context(profile, track=track)
    return template.render(**context)


def render_cover_letter_latex(
    profile: dict,
    company_name: str,
    role_title: str,
    track: str = "general",
) -> str:
    """Renderiza el código fuente LaTeX de la carta de presentación determinista."""
    tpl_path = resolve_template_path("cover_letters/cover.tex.j2")
    env = _get_jinja_env(tpl_path.parent)
    template = env.get_template(tpl_path.name)
    context = prepare_cover_letter_context(
        profile,
        company_name=company_name,
        role_title=role_title,
        track=track,
    )
    return template.render(**context)


def generate_deterministic_documents(
    profile_data: dict | None = None,
    profile_path: Path | str | None = None,
    company_name: str = "Empresa",
    role_title: str = "Puesto",
    track: str = "general",
    output_dir: Path | str | None = None,
    verify: bool = True,
) -> dict[str, Path]:
    """
    Genera y compila deterministamente el CV y la carta de presentación en PDF.

    Retorna un diccionario con las rutas:
      - cv_tex, cv_pdf, cover_tex, cover_pdf
    """
    if profile_data is None:
        p_path = Path(profile_path) if profile_path else PROFILE_PATH
        if not p_path.is_file():
            # Fallback a profile.example.json si profile.json no existe
            p_path = REPO_ROOT / "backend" / "profile.example.json"
        with open(p_path, encoding="utf-8") as f:
            profile_data = json.load(f)

    out = Path(output_dir).resolve() if output_dir else REPO_ROOT / "data" / "generated_docs"
    out.mkdir(parents=True, exist_ok=True)

    # 1. Asegurar dependencias de la carta (cover.cls y OpenFonts) en out
    cover_cls_src = resolve_template_path("cover_letters/cover.cls")
    cover_cls_dst = out / "cover.cls"
    if not cover_cls_dst.exists():
        shutil.copy2(cover_cls_src, cover_cls_dst)

    openfonts_src = resolve_template_path("cover_letters/OpenFonts")
    openfonts_dst = out / "OpenFonts"
    if not openfonts_dst.exists():
        if hasattr(os, "symlink"):
            try:
                os.symlink(openfonts_src, openfonts_dst, target_is_directory=True)
            except OSError:
                shutil.copytree(openfonts_src, openfonts_dst)
        else:
            shutil.copytree(openfonts_src, openfonts_dst)

    # 2. Generar y escribir cv.tex
    cv_source = render_cv_latex(profile_data, track=track)
    cv_tex_path = out / "cv.tex"
    cv_tex_path.write_text(cv_source, encoding="utf-8")

    # 3. Generar y escribir cover.tex
    cover_source = render_cover_letter_latex(
        profile_data,
        company_name=company_name,
        role_title=role_title,
        track=track,
    )
    cover_tex_path = out / "cover.tex"
    cover_tex_path.write_text(cover_source, encoding="utf-8")

    # 4. Compilar CV y Carta con compile_latex (Tectonic)
    cv_pdf_path = compile_latex(cv_tex_path, output_dir=out)
    cover_pdf_path = compile_latex(cover_tex_path, output_dir=out)

    # 5. Verificación mediante verify_pdf
    if verify:
        email = profile_data.get("personal", {}).get("email")
        required_cv = (email,) if email else ()
        verify_pdf(
            cv_pdf_path,
            min_chars=50,
            required_text=required_cv,
            ascii_dates=True,
        )
        verify_pdf(
            cover_pdf_path,
            expected_pages=1,
            min_chars=50,
            required_text=required_cv,
            ascii_dates=True,
        )

    return {
        "cv_tex": cv_tex_path,
        "cv_pdf": cv_pdf_path,
        "cover_tex": cover_tex_path,
        "cover_pdf": cover_pdf_path,
    }
