"""
application_archive.py — Gestión del archivo de documentos por candidatura.

Conforme a §5.11 del spec:
- El CV, la carta, la oferta limpia y el pack de entrevista se guardan en JH_HOME/applications/<id>/.
- Es lo que ha leído el entrevistador; /interview y el seguimiento lo usan.
- Los adjuntos del email salen de ahí.
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path

from config import APPLICATIONS_DIR


def get_application_dir(application_id: str | int) -> Path:
    """Devuelve la ruta al directorio de archivo de una candidatura."""
    return APPLICATIONS_DIR / str(application_id)


def archive_application(
    application_id: str | int,
    cv_pdf: Path | str | None = None,
    cover_pdf: Path | str | None = None,
    cv_tex: Path | str | None = None,
    cover_tex: Path | str | None = None,
    job_posting: str | dict | None = None,
    metadata: dict | None = None,
) -> Path:
    """
    Guarda los documentos de una candidatura en su carpeta de archivo JH_HOME/applications/<id>/.

    Copia o escribe:
      - cv.pdf y cover.pdf
      - cv.tex y cover.tex (opcional)
      - job_posting.md (la oferta limpia)
      - metadata.json (metadatos de la candidatura y ficheros archivados)

    Retorna la ruta al directorio de la candidatura.
    """
    app_dir = get_application_dir(application_id)
    app_dir.mkdir(parents=True, exist_ok=True)

    files_recorded: dict[str, str] = {}

    def _copy_doc(source: Path | str | None, dest_name: str) -> None:
        if source:
            src = Path(source).resolve()
            if src.is_file():
                dst = app_dir / dest_name
                shutil.copy2(src, dst)
                files_recorded[dest_name] = str(dst)

    _copy_doc(cv_pdf, "cv.pdf")
    _copy_doc(cover_pdf, "cover.pdf")
    _copy_doc(cv_tex, "cv.tex")
    _copy_doc(cover_tex, "cover.tex")

    # Guardar oferta de trabajo limpia
    if job_posting:
        posting_path = app_dir / "job_posting.md"
        if isinstance(job_posting, dict):
            content = f"# {job_posting.get('title', 'Oferta')}\n\n"
            content += f"**Empresa:** {job_posting.get('company', '')}\n\n"
            content += f"**Ubicación:** {job_posting.get('location', '')}\n\n"
            content += f"**URL:** {job_posting.get('url', '')}\n\n"
            content += "## Descripción\n\n"
            content += job_posting.get("description", "") or job_posting.get("content", "")
            posting_path.write_text(content, encoding="utf-8")
        else:
            posting_path.write_text(str(job_posting), encoding="utf-8")
        files_recorded["job_posting.md"] = str(posting_path)

    # Metadatos del archivo
    meta = dict(metadata or {})
    meta["application_id"] = str(application_id)
    meta["archived_at"] = datetime.now().isoformat()
    meta["files"] = files_recorded

    meta_path = app_dir / "metadata.json"
    meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")

    return app_dir


def get_application_attachments(
    application_id: str | int,
) -> tuple[Path | None, Path | None]:
    """
    Obtiene las rutas al CV y carta de presentación archivados para una candidatura.

    Retorna (cv_pdf_path, cover_pdf_path).
    Si alguno no existe en el archivo, su posición será None.
    """
    app_dir = get_application_dir(application_id)
    cv_pdf = app_dir / "cv.pdf"
    cover_pdf = app_dir / "cover.pdf"

    return (
        cv_pdf if cv_pdf.is_file() else None,
        cover_pdf if cover_pdf.is_file() else None,
    )


def save_interview_prep(
    application_id: str | int,
    content: str,
    stage: str = "initial",
) -> Path:
    """
    Guarda el pack de preparación de entrevista en el archivo de la candidatura.
    Nombre: interview_prep_<stage>.md (ej: interview_prep_initial.md o interview_prep_technical.md).
    """
    app_dir = get_application_dir(application_id)
    app_dir.mkdir(parents=True, exist_ok=True)

    file_name = f"interview_prep_{stage}.md" if stage else "interview_prep.md"
    file_path = app_dir / file_name
    file_path.write_text(content, encoding="utf-8")

    # Actualizar metadata.json si existe
    meta_path = app_dir / "metadata.json"
    if meta_path.is_file():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            meta.setdefault("interview_preps", {})[stage] = str(file_path)
            meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass

    return file_path


def load_application_archive(application_id: str | int) -> dict:
    """Carga los metadatos y lista de ficheros existentes en el archivo de la candidatura."""
    app_dir = get_application_dir(application_id)
    if not app_dir.is_dir():
        return {}

    meta_path = app_dir / "metadata.json"
    if meta_path.is_file():
        try:
            return json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    # Si no hay metadata.json, inferir de los ficheros presentes
    files = {f.name: str(f) for f in app_dir.iterdir() if f.is_file()}
    return {
        "application_id": str(application_id),
        "files": files,
    }
