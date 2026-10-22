"""
document_generator.py — Generación determinista de CV y carta de presentación en LaTeX.

Conforme a §5.11 del spec:
- Generación determinista desde profile.json con plantillas Jinja → LaTeX (sin IA).
- Reglas de honestidad: no inventa habilidades ni datos ausentes en profile.json.
- Escape riguroso de caracteres especiales LaTeX y rangos de fecha ASCII (sin en-dashes Unicode).
- Compilación vía latex_compiler (Tectonic) y verificación mediante verify_pdf.
- Límite de páginas: el CV se recorta (lo menos relevante para la oferta primero) hasta caber en
  `cv_pages`; la carta debe ocupar exactamente `letter_pages`.
"""

from __future__ import annotations

import contextlib
import copy
import io
import json
import os
import re
import shutil
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import quote

import jinja2

import config
from automation.latex_compiler import compile_latex, resolve_template_path
from automation.verify_layout import find_pdftotext, parse_pdf, report
from automation.verify_pdf import VerificationError, extract_text_layer, keyword_coverage, verify_pdf
from config import REPO_ROOT

LAYOUT_SKIPPED = "skipped: poppler no instalado"
TRIM_BISECT_STEPS = 3  # compilaciones de bisección como mucho al recortar el CV

_SPANISH_MONTHS = (
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
)

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
# Emoji y pictogramas: las fuentes de las plantillas no tienen esos glifos (saldrían como huecos o
# romperían la compilación), así que se eliminan junto con sus modificadores (tono de piel,
# selectores de variación, unión de anchura cero y banderas).
_EMOJI_REGEX = re.compile(
    "["
    "\U0001F000-\U0001FAFF"  # pictogramas, emoticonos, transporte, banderas, tonos de piel...
    "\U0001FB00-\U0001FBFF"
    "\u2600-\u27BF"  # símbolos varios y dingbats (✅ ❤ ✈...)
    "\u2B00-\u2BFF"  # flechas y estrellas (⭐ ⬆)
    "\uFE00-\uFE0F"  # selectores de variación
    "\u200D"  # zero width joiner
    "\u20E3"  # keycap
    "]"
)


# Caracteres de control, separadores de línea/párrafo Unicode, marcas de dirección (bidi) y BOM:
# invisibles en el PDF pero capaces de romper la compilación o desordenar el texto que lee un ATS.
_CONTROL_REGEX = re.compile("[\x00-\x08\x0b-\x1f\x7f\u2028\u2029\u202a-\u202e\u2066-\u2069\ufeff]")
_NEWLINE_REGEX = re.compile(r"\s*\n\s*")


def latex_escape(value: Any) -> str:
    """Convierte texto del usuario en texto LaTeX seguro (sin inyección ni errores de sintaxis).

    - Escapa los especiales de LaTeX: \\ & % $ # _ { } ~ ^.
    - Elimina emoji y pictogramas (rangos U+1F000-U+1FBFF, símbolos varios y dingbats
      U+2600-U+27BF, flechas/estrellas U+2B00-U+2BFF) junto con sus modificadores: selectores de
      variación U+FE00-U+FE0F, unión de anchura cero U+200D y keycap U+20E3. Las fuentes de las
      plantillas no tienen esos glifos: saldrían como huecos o romperían la compilación.
    - Elimina caracteres de control (salvo tabulador), separadores U+2028/U+2029, marcas bidi
      U+202A-U+202E y U+2066-U+2069 y el BOM U+FEFF.
    - Une los saltos de línea (con los espacios que los rodeen) en un solo espacio: un salto
      doble en LaTeX abriría un párrafo nuevo dentro de un argumento y rompería \\cventry.
    """
    if value is None:
        return ""
    text = _CONTROL_REGEX.sub("", _EMOJI_REGEX.sub("", str(value)))
    text = _NEWLINE_REGEX.sub(" ", text)
    return _LATEX_REGEX.sub(lambda m: _LATEX_ESCAPES[m.group(0)], text)


def latex_url(value: Any) -> str:
    """Prepara una URL para \\href: codifica en %XX lo que podría cerrar el argumento o ejecutar
    macros (llaves, barra invertida, ~, ^, espacios...) y escapa %, # y & para LaTeX."""
    if value is None:
        return ""
    encoded = quote(_EMOJI_REGEX.sub("", str(value)).strip(), safe=":/?=&#%@+,;.-_!'()*").replace("~", "%7E")
    return encoded.replace("%", r"\%").replace("#", r"\#").replace("&", r"\&")


def _safe_link(value: Any) -> str:
    """Solo enlaces http(s): añade https:// si falta esquema y descarta otros esquemas (javascript:...)."""
    url = str(value or "").strip()
    if not url:
        return ""
    lowered = url.lower()
    if lowered.startswith(("http://", "https://")):
        return url
    if re.match(r"^[a-z][a-z0-9+.-]*:", lowered) and not re.match(r"^[^:/]+:\d", lowered):
        return ""
    return "https://" + url


def _spanish_date(day: date) -> str:
    """Fecha en castellano sin depender del locale del sistema: «22 de octubre de 2026»."""
    return f"{day.day} de {_SPANISH_MONTHS[day.month - 1]} de {day.year}"


PRESENT_LABELS = {"es": "Actualidad", "en": "Present"}
_OPEN_END_WORDS = {"present", "presente", "actualidad", "actual", "current", "now", "hoy", "today"}
_YEAR_MONTH_RE = re.compile(r"^(\d{4})-(\d{1,2})(?:-\d{1,2})?$")
_MONTH_YEAR_RE = re.compile(r"^(\d{1,2})/(\d{4})$")
_YEAR_RE = re.compile(r"^(\d{4})$")


def _is_open_end(value: str) -> bool:
    return value.strip().casefold() in _OPEN_END_WORDS


def _format_date(value: str) -> str:
    """«2023-01» o «2023-01-15» -> «01/2023»; «2023» y «01/2023» tal cual; el resto sin tocar."""
    m = _YEAR_MONTH_RE.match(value)
    if m:
        return f"{int(m.group(2)):02d}/{m.group(1)}"
    m = _MONTH_YEAR_RE.match(value)
    if m:
        return f"{int(m.group(1)):02d}/{m.group(2)}"
    return value


def _date_key(value: Any) -> tuple[int, int] | None:
    """Clave ordenable (año, mes) de una fecha del perfil; None si no se entiende."""
    v = str(value or "").strip()
    for regex, year_group, month_group in ((_YEAR_MONTH_RE, 1, 2), (_MONTH_YEAR_RE, 2, 1), (_YEAR_RE, 1, None)):
        m = regex.match(v)
        if m:
            return int(m.group(year_group)), int(m.group(month_group)) if month_group else 0
    return None


def format_date_range(start: str | None, end: str | None, lang: str = "es") -> str:
    """
    Formatea un rango de fechas como «MM/YYYY - MM/YYYY» con guion ASCII (verify_pdf --ascii-dates).

    Un final vacío o «Present/Actualidad» se escribe en el idioma de la plantilla
    (`lang`: "es" -> «Actualidad», "en" -> «Present»).
    """
    present = PRESENT_LABELS.get(lang, PRESENT_LABELS["es"])
    s = str(start or "").strip()
    e = str(end or "").strip()
    if not s and not e:
        return ""
    s_fmt = _format_date(s)
    e_fmt = present if (not e or _is_open_end(e)) else _format_date(e)
    if not s:
        return e_fmt
    if s_fmt == e_fmt:
        return s_fmt
    return f"{s_fmt} - {e_fmt}"


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
    env.filters["latex_url"] = latex_url
    return env


def prepare_cv_context(profile: dict, track: str = "general", lang: str = "es") -> dict:
    """
    Prepara el diccionario de contexto para la plantilla de CV a partir de profile.json.
    Aplica las reglas de honestidad: solo incluye información presente en el perfil.
    `lang` es el idioma de la plantilla (afecta a «Actualidad»/«Present» en las fechas).
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
    for link in ("linkedin", "github"):
        if personal.get(link):
            personal[link] = _safe_link(personal[link])

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
        date_range = format_date_range(start, end, lang=lang)
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
        date_range = format_date_range(start, end, lang=lang)
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


def _fill_placeholders(text: str, company_name: str, role_title: str) -> str:
    """Sustituye {company_name} y {role_title} literalmente. No usa str.format: con texto del
    usuario, «{x}» lanzaría KeyError y «{company_name.__class__}» accedería a atributos."""
    return str(text).replace("{company_name}", company_name).replace("{role_title}", role_title)


def prepare_cover_letter_context(
    profile: dict,
    company_name: str,
    role_title: str,
    track: str = "general",
) -> dict:
    """Prepara el contexto determinista para la carta de presentación."""
    personal = dict(profile.get("personal", {}))
    if personal.get("linkedin"):
        personal["linkedin"] = _safe_link(personal["linkedin"])

    # Párrafo de apertura
    intro_template = profile.get("cover_letter_intro") or (
        "Me dirijo a ustedes para presentar mi candidatura al puesto de {role_title} en {company_name}."
    )
    opening = _fill_placeholders(intro_template, company_name, role_title)

    # Párrafo de cuerpo / stack
    body_template = profile.get("cover_letter_stack") or (
        "Cuento con sólida experiencia en desarrollo de software y análisis de datos, "
        "aplicando buenas prácticas de ingeniería y orientación a resultados."
    )
    body = _fill_placeholders(body_template, company_name, role_title)

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
    closing = _fill_placeholders(closing_template, company_name, role_title)

    return {
        "personal": personal,
        "company_name": company_name,
        "role_title": role_title,
        "current_date": _spanish_date(date.today()),
        "opening_paragraph": opening,
        "body_paragraph": body,
        "bullets": bullets,
        "connection_paragraph": connection,
        "closing_paragraph": closing,
    }


def render_cv_from_context(context: dict) -> str:
    """Renderiza el LaTeX del CV a partir de un contexto ya preparado (determinista o de la IA)."""
    tpl_path = resolve_template_path("cv/cv.tex.j2")
    env = _get_jinja_env(tpl_path.parent)
    return env.get_template(tpl_path.name).render(**context)


def render_cover_letter_from_context(context: dict) -> str:
    """Renderiza el LaTeX de la carta a partir de un contexto ya preparado (determinista o de la IA)."""
    tpl_path = resolve_template_path("cover_letters/cover.tex.j2")
    env = _get_jinja_env(tpl_path.parent)
    return env.get_template(tpl_path.name).render(**context)


def render_cv_latex(profile: dict, track: str = "general", lang: str = "es") -> str:
    """Renderiza el código fuente LaTeX del CV determinista."""
    return render_cv_from_context(prepare_cv_context(profile, track=track, lang=lang))


def render_cover_letter_latex(
    profile: dict,
    company_name: str,
    role_title: str,
    track: str = "general",
) -> str:
    """Renderiza el código fuente LaTeX de la carta de presentación determinista."""
    context = prepare_cover_letter_context(
        profile,
        company_name=company_name,
        role_title=role_title,
        track=track,
    )
    return render_cover_letter_from_context(context)


def _experience_bullets(exp: dict) -> list[str]:
    """Viñetas de un empleo; si no tiene, su descripción hace de única viñeta."""
    bullets = list(exp.get("bullets") or [])
    if not bullets and exp.get("description"):
        bullets = [exp["description"]]
    return [str(b) for b in bullets]


def _relevance(text: str, keywords: list[str]) -> int:
    """Relevancia para la oferta: nº de palabras clave de la oferta presentes en el texto."""
    if not keywords:
        return 0
    present, _ = keyword_coverage(text, keywords)
    return len(present)


def plan_trim_operations(profile: dict, keywords: list[str] | None = None) -> list[tuple]:
    """
    Orden de recorte del CV, de lo menos a lo más relevante para la oferta.

    Fase 1: viñetas de experiencia, salvo la primera de cada empleo, por relevancia ascendente
    (empate: empleo más antiguo y última viñeta primero) -> ("bullet", i_empleo, j_viñeta).
    Fase 2: empleos completos, igual criterio -> ("entry", i_empleo). Nunca se quitan ni el
    empleo más reciente (fin abierto o fecha más tardía; si no hay fechas, experience[0]) ni el
    más relevante para la oferta.
    Nunca se reescribe ni se inventa nada: solo se quita contenido del perfil.
    """
    kws = [k for k in (keywords or []) if k and str(k).strip()]
    experience = profile.get("experience") or []
    bullet_ops = []
    entry_scores = []
    for i, exp in enumerate(experience):
        bullets = _experience_bullets(exp)
        for j, bullet in enumerate(bullets[1:], start=1):
            bullet_ops.append(((_relevance(bullet, kws), -i, -j), ("bullet", i, j)))
        entry_text = " ".join([str(exp.get("role", "")), str(exp.get("company", "")), *bullets])
        entry_scores.append((_relevance(entry_text, kws), -i, i))
    ops = [op for _, op in sorted(bullet_ops)]
    if len(entry_scores) > 1:
        keep = {max(entry_scores, key=lambda e: (e[0], e[1]))[2], _most_recent_index(experience)}
        ops += [("entry", i) for _, _, i in sorted(entry_scores) if i not in keep]
    return ops


def _most_recent_index(experience: list[dict]) -> int:
    """Índice del empleo más reciente: fin abierto > fecha de fin > fecha de inicio; empate o sin
    fechas -> el que aparece antes (experience[0] es el más reciente por convención)."""
    best_i, best_key = 0, None
    for i, exp in enumerate(experience):
        end = str(exp.get("end") or "").strip()
        start_key = _date_key(exp.get("start"))
        if start_key is None and not end:
            continue  # sin fechas: no compite
        end_key = (9999, 99) if (not end or _is_open_end(end)) else _date_key(end)
        key = (end_key or (0, 0), start_key or (0, 0))
        if best_key is None or key > best_key:
            best_i, best_key = i, key
    return best_i


def apply_trim(profile: dict, ops: list[tuple]) -> dict:
    """Devuelve una copia del perfil sin las viñetas/empleos indicados (no modifica el original)."""
    trimmed = copy.deepcopy(profile)
    removed_entries = {op[1] for op in ops if op[0] == "entry"}
    removed_bullets = {(op[1], op[2]) for op in ops if op[0] == "bullet"}
    new_experience = []
    for i, exp in enumerate(trimmed.get("experience") or []):
        if i in removed_entries:
            continue
        bullets = _experience_bullets(exp)
        exp["bullets"] = [b for j, b in enumerate(bullets) if (i, j) not in removed_bullets]
        exp["description"] = ""  # ya está en bullets; evita que vuelva a aparecer tras recortar
        new_experience.append(exp)
    if "experience" in trimmed:
        trimmed["experience"] = new_experience
    return trimmed


def _describe_op(profile: dict, op: tuple) -> str:
    """Descripción legible de un recorte, para el informe de verificación."""
    exp = (profile.get("experience") or [])[op[1]]
    where = f"{exp.get('role', '')} @ {exp.get('company', '')}"
    if op[0] == "entry":
        return f"empleo: {where}"
    return f"viñeta de {where}: {_experience_bullets(exp)[op[2]][:80]}"


def _page_count(pdf_path: Path) -> int:
    """Número de páginas del PDF (pypdf, con Poppler de reserva)."""
    return extract_text_layer(pdf_path)[1]


def _layout_warnings(pdf_path: Path) -> list[str] | str:
    """Avisos de maquetación de verify_layout (huecos, huérfanas, pie...) sin imprimir nada."""
    try:
        pages = parse_pdf(pdf_path)
        with contextlib.redirect_stdout(io.StringIO()):
            return report(pdf_path, pages)
    except RuntimeError as exc:
        return f"skipped: {exc}"


def _ensure_cover_dependencies(out: Path) -> None:
    """Copia cover.cls y enlaza OpenFonts junto a cover.tex (la clase usa rutas relativas)."""
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


def generate_deterministic_documents(
    profile_data: dict | None = None,
    profile_path: Path | str | None = None,
    company_name: str = "Empresa",
    role_title: str = "Puesto",
    track: str = "general",
    output_dir: Path | str | None = None,
    verify: bool = True,
    cv_pages: int = 2,
    letter_pages: int = 1,
    offer_keywords: list[str] | None = None,
    lang: str = "es",
) -> dict[str, Any]:
    """
    Genera y compila deterministamente el CV y la carta de presentación en PDF.

    - output_dir: por defecto `config.APPLICATIONS_DIR / "_preview"` (dentro de JH_HOME, nunca en el repo).
    - cv_pages: máximo de páginas del CV; si se pasa, se recorta lo menos relevante para la oferta
      (solapamiento con `offer_keywords`) hasta que quepa. Si ni recortando todo cabe -> VerificationError.
    - letter_pages: páginas exactas de la carta (se comprueba si verify=True).
    - lang: idioma de la plantilla para las fechas («Actualidad»/«Present»).
    - El recorte es grueso (rejilla de 2**TRIM_BISECT_STEPS cortes): puede quitar algo más de lo
      estrictamente necesario a cambio de compilar como mucho 2 + TRIM_BISECT_STEPS veces.
    - verify: exige email y teléfono literales en ambos PDFs, texto ATS legible y fechas ASCII.

    Retorna un diccionario con cv_tex, cv_pdf, cover_tex, cover_pdf y `verification`:
    pages {cv, cover}, trimmed (lista de recortes), present_keywords, missing_keywords y layout
    (avisos por documento, o "skipped: poppler no instalado").
    """
    if profile_data is None:
        p_path = Path(profile_path) if profile_path else config.PROFILE_PATH
        if not p_path.is_file():
            # Fallback a profile.example.json si profile.json no existe
            p_path = REPO_ROOT / "backend" / "profile.example.json"
        with open(p_path, encoding="utf-8") as f:
            profile_data = json.load(f)

    return _build_documents(
        trim_base=profile_data,
        render_cv=lambda data: render_cv_latex(data, track=track, lang=lang),
        cover_source=render_cover_letter_latex(
            profile_data,
            company_name=company_name,
            role_title=role_title,
            track=track,
        ),
        personal=profile_data.get("personal", {}) or {},
        output_dir=output_dir,
        verify=verify,
        cv_pages=cv_pages,
        letter_pages=letter_pages,
        offer_keywords=offer_keywords,
        trim=True,
    )


class PageOverflow(VerificationError):
    """CV y/o carta no caben en su límite de páginas y no se pidió recortar.

    `overflows`: lista de (doc, páginas, límite) con doc "cv" o "cover" (ambos se compilan antes de
    lanzarla, así el llamador puede pedir una sola versión más corta que cubra los dos)."""

    def __init__(self, overflows: list[tuple[str, int, int]]):
        self.overflows = list(overflows)
        super().__init__("; ".join(
            f"{'El CV' if doc == 'cv' else 'La carta'} ocupa {pages} páginas y el límite es {limit}"
            for doc, pages, limit in self.overflows
        ))


def generate_documents_from_context(
    cv_context: dict,
    letter_context: dict,
    output_dir: Path | str | None = None,
    verify: bool = True,
    cv_pages: int = 2,
    letter_pages: int = 1,
    offer_keywords: list[str] | None = None,
    trim: bool = True,
) -> dict[str, Any]:
    """
    Igual que `generate_deterministic_documents`, pero a partir de contextos ya preparados (los de la
    IA, ya validados): mismas plantillas, mismo recorte, misma verificación y mismo resultado.

    - El recorte opera sobre `cv_context["experience"]` (cada empleo con `bullets`, `role`, `company` y
      opcionalmente `start`/`end` para saber cuál es el más reciente).
    - trim=False: se compilan CV y carta sin recortar y, si alguno pasa de su límite, se lanza
      `PageOverflow` con todos los desbordes (el llamador puede pedir a la IA una versión más corta y
      reintentar con trim=True).
    """
    return _build_documents(
        trim_base=cv_context,
        render_cv=render_cv_from_context,
        cover_source=render_cover_letter_from_context(letter_context),
        personal=cv_context.get("personal", {}) or {},
        output_dir=output_dir,
        verify=verify,
        cv_pages=cv_pages,
        letter_pages=letter_pages,
        offer_keywords=offer_keywords,
        trim=trim,
    )


def _build_documents(
    trim_base: dict,
    render_cv,
    cover_source: str,
    personal: dict,
    output_dir: Path | str | None,
    verify: bool,
    cv_pages: int,
    letter_pages: int,
    offer_keywords: list[str] | None,
    trim: bool,
) -> dict[str, Any]:
    """Núcleo común: compila CV (con recorte si hace falta y `trim`) y carta, y los verifica.

    `trim_base` es lo que se recorta (perfil o contexto del CV) y `render_cv(trim_base_recortado)`
    devuelve el LaTeX del CV; `cover_source` es el LaTeX de la carta ya renderizado."""
    email = str(personal.get("email") or "").strip()
    phone = str(personal.get("phone") or "").strip()
    if verify:
        missing = [label for label, value in (("email", email), ("teléfono", phone)) if not value]
        if missing:
            raise VerificationError(
                f"El perfil no tiene {' ni '.join(missing)}: el CV y la carta deben incluirlos "
                "literalmente para que un ATS los lea. Complétalo en la pestaña Perfil."
            )

    out = Path(output_dir).resolve() if output_dir else (config.APPLICATIONS_DIR / "_preview").resolve()
    out.mkdir(parents=True, exist_ok=True)
    _ensure_cover_dependencies(out)

    # 1. CV: compilar sin recortes; si no cabe, probar con todos los recortes (demuestra que cabe)
    #    y bisecar con pasos gruesos (TRIM_BISECT_STEPS compilaciones como mucho). Cada intento se
    #    guarda en memoria para restaurar el mejor sin recompilar: <= 2 + TRIM_BISECT_STEPS en total.
    keywords = [k for k in (offer_keywords or []) if k and str(k).strip()]
    ops = plan_trim_operations(trim_base, keywords)
    cv_tex_path = out / "cv.tex"
    cv_pdf_path = out / "cv.pdf"
    attempts: dict[int, tuple[str, bytes, int]] = {}

    def build_cv(k: int) -> int:
        source = render_cv(apply_trim(trim_base, ops[:k]))
        cv_tex_path.write_text(source, encoding="utf-8")
        # Una sola pasada: la segunda solo añade los marcadores (outline) de hyperref, que un CV
        # no necesita (pdfpagemode=UseNone); texto, enlaces y maquetación salen idénticos.
        pdf = compile_latex(cv_tex_path, output_dir=out, passes=1)
        pages = _page_count(pdf)
        attempts[k] = (source, pdf.read_bytes(), pages)
        return pages

    first_pages = build_cv(0)
    best = 0
    overflows: list[tuple[str, int, int]] = []
    if first_pages > cv_pages and not trim:
        overflows.append(("cv", first_pages, cv_pages))
    elif first_pages > cv_pages:
        if not ops or build_cv(len(ops)) > cv_pages:
            raise VerificationError(
                f"El CV ocupa {first_pages} páginas y no cabe en {cv_pages} ni quitando todo lo "
                "recortable; acorta el resumen, las competencias o la formación del perfil."
            )
        # Rejilla gruesa de cortes: 2**TRIM_BISECT_STEPS intervalos -> TRIM_BISECT_STEPS compilaciones
        intervals = 2**TRIM_BISECT_STEPS
        grid = sorted({round(len(ops) * n / intervals) for n in range(intervals + 1)})
        lo, hi = 0, len(grid) - 1  # grid[lo] no cabe, grid[hi] cabe
        while hi - lo > 1:
            mid = (lo + hi) // 2
            if build_cv(grid[mid]) <= cv_pages:
                hi = mid
            else:
                lo = mid
        best = grid[hi]
    source, pdf_bytes, best_pages = attempts[best]
    cv_tex_path.write_text(source, encoding="utf-8")
    cv_pdf_path.write_bytes(pdf_bytes)

    # 2. Carta
    cover_tex_path = out / "cover.tex"
    cover_tex_path.write_text(cover_source, encoding="utf-8")
    cover_pdf_path = compile_latex(cover_tex_path, output_dir=out)
    cover_pages = _page_count(cover_pdf_path)
    if cover_pages > letter_pages and not trim:
        overflows.append(("cover", cover_pages, letter_pages))
    if overflows:
        raise PageOverflow(overflows)

    verification: dict[str, Any] = {
        "pages": {"cv": best_pages, "cover": cover_pages},
        "trimmed": [_describe_op(trim_base, op) for op in ops[:best]],
        "present_keywords": [],
        "missing_keywords": [],
        "layout": "skipped: verificación desactivada",
    }

    # 3. Verificación completa
    if verify:
        required = (email, phone)
        _, cv_text, _ = verify_pdf(cv_pdf_path, min_chars=50, required_text=required, ascii_dates=True)
        verify_pdf(
            cover_pdf_path,
            expected_pages=letter_pages,
            min_chars=50,
            required_text=required,
            ascii_dates=True,
        )
        present, missing_kw = keyword_coverage(cv_text, keywords)
        verification["present_keywords"] = present
        verification["missing_keywords"] = missing_kw
        if find_pdftotext() is None:
            verification["layout"] = LAYOUT_SKIPPED
        else:
            verification["layout"] = {
                "cv": _layout_warnings(cv_pdf_path),
                "cover": _layout_warnings(cover_pdf_path),
            }

    return {
        "cv_tex": cv_tex_path,
        "cv_pdf": cv_pdf_path,
        "cover_tex": cover_tex_path,
        "cover_pdf": cover_pdf_path,
        "verification": verification,
    }
