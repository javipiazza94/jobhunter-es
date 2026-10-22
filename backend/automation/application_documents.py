"""
application_documents.py — «Preparar candidatura»: CV y carta en PDF para una candidatura concreta.

Flujo de `prepare_application(id)`:
  1. Carga la candidatura con su oferta y empresa de la BD.
  2. Comprueba que hay motor LaTeX (si no, `NoTexEngine` → la API responde 409 con la pista de instalación).
  3. Genera CV y carta en una carpeta de trabajo propia (`<id>.work/`), nunca en la del archivo.
  4. Archiva de forma atómica en JH_HOME/applications/<id>/ (cv.pdf, cover.pdf, .tex, job_posting.md
     con la oferta limpia y metadata.json). Si algo falla, el archivo anterior queda intacto.

El email de aprobación adjunta esos PDFs (application_engine → get_application_attachments).
Con IA (`_generate` → `_generate_with_ai`): redactor + revisor (ai_documents.run_ai_flow) con validador
de honestidad, mismas plantillas y verificación; si se sale de páginas se pide a la IA que acorte y luego
se recorta. Cualquier fallo de la IA o de verificación de su versión → vía determinista con aviso.
"""

from __future__ import annotations

import logging
import re
import shutil
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel

from ai import AIError, get_provider
from automation import application_archive
from automation.ai_documents import AI_DEADLINE_SECONDS, cap_warnings, run_ai_flow, shorten_documents
from automation.document_generator import (
    PageOverflow,
    generate_deterministic_documents,
    generate_documents_from_context,
)
from automation.latex_compiler import LaTeXCompilationError, engine_available
from automation.posting_guard import clean_html
from automation.verify_pdf import VerificationError
from profile_store import load_profile

logger = logging.getLogger(__name__)

NO_ENGINE_MESSAGE = (
    "Instala Tectonic (https://tectonic-typesetting.github.io) o TeX Live con xelatex para generar el CV "
    "y la carta en PDF. Mientras tanto, aprobar la candidatura sigue adjuntando tus documentos de siempre."
)
AI_UNAVAILABLE_PREFIX = "IA no disponible: "
# Documentos que la API puede servir (lista blanca exacta; nada de rutas).
DOWNLOADABLE = ("cv.pdf", "cover.pdf", "job_posting.md", "interview.md")
MAX_OFFER_KEYWORDS = 40

_HTML_TAG = re.compile(r"<\s*/?\s*[a-zA-Z!][^>]*>")
_BLANK_LINES = re.compile(r"\n{3,}")


class DocumentsError(Exception):
    """Error al preparar los documentos de una candidatura."""


class ApplicationNotFound(DocumentsError, LookupError):
    """La candidatura no existe."""


class NoTexEngine(DocumentsError):
    """No hay motor LaTeX instalado (tectonic, xelatex o lualatex)."""

    def __init__(self, message: str = NO_ENGINE_MESSAGE):
        super().__init__(message)


class VerificationFailed(DocumentsError):
    """Los PDFs no superan la verificación (o no compilan); `reasons` explica por qué."""

    def __init__(self, reasons: list[str]):
        self.reasons = [r for r in reasons if r] or ["La verificación de los PDFs falló"]
        super().__init__("; ".join(self.reasons))


class PreparedDocs(BaseModel):
    """Resultado de preparar una candidatura: PDFs archivados, origen, verificación y avisos."""

    application_id: str
    cv_pdf: str
    cover_pdf: str
    source: Literal["ai", "deterministic"]
    verification: dict[str, Any]
    warnings: list[str]


# ── Datos de la candidatura ────────────────────────────────────────────────────

def load_application(application_id: str) -> dict:
    """Candidatura con su oferta y empresa. Lanza ApplicationNotFound si no existe."""
    from database import get_conn

    conn = get_conn()
    try:
        row = conn.execute(
            """SELECT a.id, a.status, a.cv_profile, a.job_offer_id,
                      c.name AS company_name, jo.title AS job_title, jo.description, jo.location,
                      jo.tech_stack, jo.url, jo.track_tag
               FROM applications a
               LEFT JOIN companies c ON a.company_id = c.id
               LEFT JOIN job_offers jo ON a.job_offer_id = jo.id
               WHERE a.id = ?""",
            (str(application_id),),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        raise ApplicationNotFound(f"Candidatura desconocida: {application_id}")
    return dict(row)


def clean_offer_text(text: str | None) -> str:
    """Texto visible de la oferta: sin HTML (ni contenido oculto) y sin líneas en blanco de sobra."""
    text = text or ""
    if _HTML_TAG.search(text):
        # Saltos de línea en los bloques para no pegar párrafos y elementos de lista
        text = re.sub(r"(?i)<\s*(br|/p|/li|/h[1-6]|/div|/tr)\b[^>]*>", "\n", text)
        text = re.sub(r"(?i)<\s*li\b[^>]*>", "\n- ", text)
        text, _ = clean_html(text)
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines()]
    return _BLANK_LINES.sub("\n\n", "\n".join(lines)).strip()


def job_posting_markdown(app: dict) -> str:
    """job_posting.md: la oferta limpia tal como la leyó la candidatura (datos, nunca instrucciones)."""
    return application_archive._posting_markdown({
        "title": app.get("job_title") or "Oferta",
        "company": app.get("company_name") or "",
        "location": app.get("location") or "",
        "url": app.get("url") or "",
        "description": clean_offer_text(app.get("description")) + "\n",
    })


def _fold(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower())


def offer_keywords(app: dict, cfg=None) -> list[str]:
    """Keywords de la configuración (grupos de scoring y classify_keywords de los tracks) que aparecen
    en la oferta, más su tech_stack. Sirven para medir cobertura y decidir qué recortar del CV."""
    from search_config import get_config

    cfg = cfg or get_config()
    offer_text = _fold(" ".join(
        (str(app.get("job_title") or ""), clean_offer_text(app.get("description")), str(app.get("tech_stack") or ""))
    ))
    candidates: list[str] = []
    for group in cfg.scoring.keyword_groups:
        candidates.extend(group.keywords)
    for track in cfg.tracks:
        candidates.extend(track.classify_keywords)
    candidates.extend(part.strip() for part in str(app.get("tech_stack") or "").split(","))

    found: list[str] = []
    for kw in candidates:
        kw_norm = _fold(str(kw)).strip()
        if not kw_norm or kw_norm in found:
            continue
        if re.search(rf"(?<!\w){re.escape(kw_norm)}(?!\w)", offer_text):
            found.append(kw_norm)
        if len(found) >= MAX_OFFER_KEYWORDS:
            break
    return found


def _resolve_track(app: dict, cfg=None) -> tuple[str, str]:
    """(id del track, clave del resumen en profile.json) de la candidatura."""
    from automation.cv_selector import default_track_id
    from search_config import get_config

    cfg = cfg or get_config()
    track_id = app.get("cv_profile") or app.get("track_tag") or default_track_id(cfg) or "general"
    track = cfg.track(track_id)
    summary_key = (track.summary_key if track and track.summary_key else track_id) or "general"
    return track_id, summary_key


# ── Generación ─────────────────────────────────────────────────────────────────

def _resolve_use_ai(use_ai: bool | None) -> bool:
    """None → IA si hay proveedor configurado (distinto de «none»)."""
    if use_ai is not None:
        return use_ai
    try:
        from search_config import get_config

        return get_config().ai.provider != "none"
    except Exception:  # noqa: BLE001 — configuración ilegible: sin IA
        return False


def _generate(
    profile: dict,
    app: dict,
    summary_key: str,
    keywords: list[str],
    output_dir: Path,
    use_ai: bool,
    ai_requested: bool,
) -> tuple[dict, Literal["ai", "deterministic"], list[str]]:
    """Punto de despacho entre la vía con IA y la determinista. Devuelve (resultado, origen, avisos).

    Con `use_ai` se intenta la vía con IA; si la IA falla (AIError) el aviso es «IA no disponible: …»
    y si su versión no compila o no verifica se explica el motivo; en ambos casos se sigue con la
    determinista. `ai_requested` (IA pedida explícitamente) se conserva por compatibilidad."""
    warnings: list[str] = []
    if use_ai:
        try:
            result, ai_warnings = _generate_with_ai(profile, app, summary_key, keywords, output_dir)
            return result, "ai", ai_warnings
        except AIError as exc:
            warnings.append(f"{AI_UNAVAILABLE_PREFIX}{exc}")
        except (VerificationError, LaTeXCompilationError) as exc:
            warnings.append(f"La versión con IA no superó la verificación ({exc}); se usa la determinista")
        except Exception:  # noqa: BLE001 — un fallo inesperado de la vía con IA nunca debe dar un 500
            logger.exception("Fallo inesperado en la vía con IA de la candidatura %s", app.get("id"))
            warnings.append("La vía con IA falló por un error inesperado; se usa la versión determinista")
        warnings = cap_warnings(warnings)
        shutil.rmtree(output_dir, ignore_errors=True)
    result = generate_deterministic_documents(
        profile_data=profile,
        company_name=app.get("company_name") or "Empresa",
        role_title=app.get("job_title") or "Puesto",
        track=summary_key,
        output_dir=output_dir,
        verify=True,
        offer_keywords=keywords,
    )
    return result, "deterministic", warnings


def _generate_with_ai(
    profile: dict, app: dict, summary_key: str, keywords: list[str], output_dir: Path
) -> tuple[dict, list[str]]:
    """Redactor + revisor con IA; compila sin recortar y, si algo no cabe, pide a la IA que acorte
    (una sola petición para CV y carta) y vuelve a compilar con el recorte determinista como red.
    Si acortar falla o se agotó el plazo de IA (AI_DEADLINE_SECONDS), se recorta sin IA con aviso.
    Lanza AIError (redactor/revisor) o VerificationError."""
    deadline = time.monotonic() + AI_DEADLINE_SECONDS
    try:
        provider = get_provider()
    except AIError:
        raise
    except Exception as exc:  # noqa: BLE001 — configuración de IA inválida
        raise AIError(f"configuración de IA no válida ({type(exc).__name__})") from None
    offer = {
        "company_name": app.get("company_name") or "Empresa",
        "job_title": app.get("job_title") or "Puesto",
        "description": clean_offer_text(app.get("description")),
        "tech_stack": app.get("tech_stack") or "",
        "keywords": keywords,
    }
    cv_ctx, letter_ctx, warnings = run_ai_flow(profile, offer, provider, track=summary_key, deadline=deadline)
    try:
        result = generate_documents_from_context(
            cv_ctx, letter_ctx, output_dir=output_dir, verify=True, offer_keywords=keywords, trim=False
        )
    except PageOverflow as overflow:
        if time.monotonic() >= deadline:
            warnings.append(f"{overflow}: tiempo de IA agotado, se recorta sin IA")
        else:
            try:
                cv_ctx, letter_ctx, more = shorten_documents(
                    cv_ctx, letter_ctx, profile, offer, provider, overflow, track=summary_key
                )
                warnings += [*more, f"{overflow}: se pidió a la IA una versión más corta"]
            except AIError as exc:
                warnings.append(f"{overflow}: la IA no pudo acortarlo ({exc}), se recorta sin IA")
        result = generate_documents_from_context(
            cv_ctx, letter_ctx, output_dir=output_dir, verify=True, offer_keywords=keywords, trim=True
        )
    return result, cap_warnings(warnings)


def prepare_application(application_id: str, use_ai: bool | None = None) -> PreparedDocs:
    """Genera CV y carta en PDF para la candidatura y los archiva en JH_HOME/applications/<id>/.

    Lanza ApplicationNotFound, NoTexEngine (sin motor LaTeX) o VerificationFailed (los PDFs no
    compilan o no pasan la verificación); en esos casos el archivo anterior no se toca."""
    from search_config import get_config

    app = load_application(application_id)
    if engine_available() is None:
        raise NoTexEngine()

    cfg = get_config()
    track_id, summary_key = _resolve_track(app, cfg)
    keywords = offer_keywords(app, cfg)
    profile = load_profile()

    app_dir = application_archive.get_application_dir(application_id)
    app_dir.parent.mkdir(parents=True, exist_ok=True)
    work_dir = app_dir.with_name(f"{app_dir.name}.work")
    # Mismo cerrojo que el archivo y el envío: mientras se prepara, nadie adjunta ni limpia `<id>.work/`
    with application_archive.application_lock(application_id):
        application_archive.recover_application_dir(application_id)
        if work_dir.exists():
            shutil.rmtree(work_dir)
        try:
            try:
                result, source, warnings = _generate(
                    profile, app, summary_key, keywords, work_dir,
                    use_ai=_resolve_use_ai(use_ai), ai_requested=use_ai is True,
                )
            except VerificationError as exc:
                raise VerificationFailed([str(exc)]) from exc
            except LaTeXCompilationError as exc:
                raise VerificationFailed([f"La compilación LaTeX falló: {exc}"]) from exc

            verification = result.get("verification") or {}
            final_dir = application_archive.archive_application(
                application_id,
                cv_pdf=result["cv_pdf"],
                cover_pdf=result["cover_pdf"],
                cv_tex=result.get("cv_tex"),
                cover_tex=result.get("cover_tex"),
                job_posting=job_posting_markdown(app),
                metadata={
                    "source": source,
                    "track": track_id,
                    "company": app.get("company_name") or "",
                    "role": app.get("job_title") or "",
                    "offer_id": app.get("job_offer_id"),
                    "offer_url": app.get("url") or "",
                    "offer_keywords": keywords,
                    "verification": verification,
                    "warnings": warnings,
                },
            )
        finally:
            shutil.rmtree(work_dir, ignore_errors=True)

    logger.info("Candidatura %s preparada (%s)", application_id, source)
    return PreparedDocs(
        application_id=str(application_id),
        cv_pdf=str(final_dir / "cv.pdf"),
        cover_pdf=str(final_dir / "cover.pdf"),
        source=source,
        verification=verification,
        warnings=warnings,
    )


# ── Consulta del archivo ───────────────────────────────────────────────────────

def list_documents(application_id: str) -> list[dict]:
    """Documentos descargables del archivo de la candidatura (en el orden de DOWNLOADABLE)."""
    app_dir = application_archive.get_application_dir(application_id)
    out = []
    for name in DOWNLOADABLE:
        path = app_dir / name
        if path.is_file():
            stat = path.stat()
            modified = datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds")
            out.append({"name": name, "size": stat.st_size, "modified_at": modified})
    return out


def document_path(application_id: str, name: str) -> Path:
    """Ruta de un documento archivado. Solo nombres de la lista blanca; si no, FileNotFoundError."""
    if name not in DOWNLOADABLE:
        raise FileNotFoundError(name)
    path = application_archive.get_application_dir(application_id) / name
    if not path.is_file():
        raise FileNotFoundError(name)
    return path
