"""
application_archive.py — Gestión del archivo de documentos por candidatura.

Conforme a §5.11 del spec:
- El CV, la carta, la oferta limpia y el pack de entrevista se guardan en JH_HOME/applications/<id>/.
- Es lo que ha leído el entrevistador; /interview y el seguimiento lo usan.
- Los adjuntos del email salen de ahí.

El archivo se escribe de forma atómica: todo se prepara en `<id>.tmp/` y se cambia por la carpeta
anterior con `os.replace`, así un email nunca adjunta un PDF a medio escribir y un fallo deja intacto
el archivo previo. El pack de entrevista (`interview.md`) sobrevive a cada nueva preparación.
"""

from __future__ import annotations

import json
import os
import shutil
import threading
from datetime import datetime
from pathlib import Path

import config

# Carpeta raíz del archivo. None = la de la configuración activa (config.APPLICATIONS_DIR, dentro de
# JH_HOME); los tests pueden fijarla.
APPLICATIONS_DIR: Path | None = None

INTERVIEW_FILE = "interview.md"
# Ficheros que se regeneran en cada preparación; el resto (pack de entrevista) se conserva.
GENERATED_FILES = ("cv.pdf", "cover.pdf", "cv.tex", "cover.tex", "job_posting.md", "metadata.json")

LEFTOVER_SUFFIXES = (".old", ".tmp", ".work")  # restos de una preparación cortada a medias

_locks: dict[str, threading.RLock] = {}
_locks_guard = threading.Lock()


def _root() -> Path:
    return Path(APPLICATIONS_DIR) if APPLICATIONS_DIR is not None else Path(config.APPLICATIONS_DIR)


def application_lock(application_id: str | int) -> threading.RLock:
    """Cerrojo (reentrante) por candidatura: serializa preparación, pack de entrevista y envío del
    email dentro del proceso, para que nadie vea la carpeta a medio sustituir."""
    key = str(application_id)
    with _locks_guard:
        return _locks.setdefault(key, threading.RLock())


def get_application_dir(application_id: str | int) -> Path:
    """Devuelve la ruta al directorio de archivo de una candidatura.

    Lanza ValueError si el id no es un nombre de carpeta simple (evita salir de JH_HOME/applications)."""
    name = str(application_id)
    if not name or name in (".", "..") or "/" in name or "\\" in name or "\x00" in name or name.startswith("."):
        raise ValueError(f"Id de candidatura no válido: {name!r}")
    return _root() / name


def recover_application_dir(application_id: str | int) -> Path:
    """Repara el archivo tras un corte: si falta `<id>/` pero queda `<id>.old/`, lo restaura; con
    `<id>/` presente, borra los restos `<id>.old/`, `<id>.tmp/` y `<id>.work/`. Devuelve `<id>/`."""
    app_dir = get_application_dir(application_id)
    with application_lock(application_id):
        old = app_dir.with_name(f"{app_dir.name}.old")
        if not app_dir.exists() and old.is_dir():
            os.replace(old, app_dir)
        if app_dir.exists():
            for suffix in LEFTOVER_SUFFIXES:
                leftover = app_dir.with_name(f"{app_dir.name}{suffix}")
                if leftover.exists():
                    shutil.rmtree(leftover, ignore_errors=True)
    return app_dir


def _swap_in(staging: Path, app_dir: Path) -> None:
    """Sustituye `app_dir` por `staging` con renombrados atómicos (mismo sistema de ficheros)."""
    if not app_dir.exists():
        os.replace(staging, app_dir)
        return
    old = app_dir.with_name(f"{app_dir.name}.old")
    if old.exists():
        shutil.rmtree(old)
    os.replace(app_dir, old)
    try:
        os.replace(staging, app_dir)
    except OSError:
        os.replace(old, app_dir)  # deja el archivo anterior tal cual
        raise
    shutil.rmtree(old, ignore_errors=True)


def _posting_markdown(job_posting: str | dict) -> str:
    if not isinstance(job_posting, dict):
        return str(job_posting)
    content = f"# {job_posting.get('title', 'Oferta')}\n\n"
    content += f"**Empresa:** {job_posting.get('company', '')}\n\n"
    content += f"**Ubicación:** {job_posting.get('location', '')}\n\n"
    content += f"**URL:** {job_posting.get('url', '')}\n\n"
    content += "## Descripción\n\n"
    content += job_posting.get("description", "") or job_posting.get("content", "")
    return content


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
      - cv.pdf y cover.pdf (obligatorios: ValueError si falta alguno)
      - cv.tex y cover.tex (opcional)
      - job_posting.md (la oferta limpia)
      - metadata.json (metadatos de la candidatura y ficheros archivados)

    Todo se escribe primero en `<id>.tmp/` y luego sustituye a la carpeta anterior de una vez; los
    ficheros que no se regeneran (el pack de entrevista) pasan a la carpeta nueva.
    Retorna la ruta al directorio de la candidatura.
    """
    app_dir = get_application_dir(application_id)
    for label, source in (("CV", cv_pdf), ("carta", cover_pdf)):
        if not source or not Path(source).is_file():
            raise ValueError(f"Falta el PDF de la {label} para archivar la candidatura {application_id}")
    app_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = app_dir.with_name(f"{app_dir.name}.tmp")

    # Sin recover_application_dir aquí: los PDFs de origen pueden estar en `<id>.work/` (los limpia el llamador).
    with application_lock(application_id):
        if staging.exists():
            shutil.rmtree(staging)
        staging.mkdir()
        try:
            files_recorded: dict[str, str] = {}

            def _copy_doc(source: Path | str | None, dest_name: str) -> None:
                if source:
                    src = Path(source).resolve()
                    if src.is_file():
                        shutil.copy2(src, staging / dest_name)
                        files_recorded[dest_name] = str(app_dir / dest_name)

            _copy_doc(cv_pdf, "cv.pdf")
            _copy_doc(cover_pdf, "cover.pdf")
            _copy_doc(cv_tex, "cv.tex")
            _copy_doc(cover_tex, "cover.tex")

            if job_posting:
                (staging / "job_posting.md").write_text(_posting_markdown(job_posting), encoding="utf-8")
                files_recorded["job_posting.md"] = str(app_dir / "job_posting.md")

            # Conservar lo que no se regenera (pack de entrevista y similares)
            previous_meta: dict = {}
            if app_dir.is_dir():
                for old_file in app_dir.iterdir():
                    if (old_file.is_file() and old_file.name not in GENERATED_FILES
                            and not old_file.name.startswith(".")):
                        shutil.copy2(old_file, staging / old_file.name)
                try:
                    previous_meta = json.loads((app_dir / "metadata.json").read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    previous_meta = {}

            meta = dict(metadata or {})
            if isinstance(previous_meta, dict) and "interview_preps" in previous_meta:
                meta.setdefault("interview_preps", previous_meta["interview_preps"])
            meta["application_id"] = str(application_id)
            meta["archived_at"] = datetime.now().isoformat()
            meta["files"] = files_recorded
            (staging / "metadata.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")

            _swap_in(staging, app_dir)
        except BaseException:
            shutil.rmtree(staging, ignore_errors=True)
            raise

    return app_dir


def get_application_attachments(
    application_id: str | int,
) -> tuple[Path | None, Path | None]:
    """
    Obtiene las rutas al CV y carta de presentación archivados para una candidatura.

    Retorna (cv_pdf_path, cover_pdf_path).
    Si alguno no existe en el archivo, su posición será None. Antes repara un corte a medias.
    """
    app_dir = recover_application_dir(application_id)
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

    Siempre en `interview.md` (un único pack por candidatura, el mismo que genera
    ai_writing.generate_interview_pack); la fase (`stage`) queda anotada en metadata.json.
    La escritura es atómica (tmp + os.replace).
    """
    app_dir = get_application_dir(application_id)
    with application_lock(application_id):
        app_dir.mkdir(parents=True, exist_ok=True)
        file_path = app_dir / INTERVIEW_FILE
        tmp = app_dir / f".{INTERVIEW_FILE}.tmp"
        tmp.write_text(content, encoding="utf-8")
        os.replace(tmp, file_path)

        # Actualizar metadata.json si existe
        meta_path = app_dir / "metadata.json"
        if meta_path.is_file():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                meta.setdefault("interview_preps", {})[stage or "initial"] = str(file_path)
                meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
            except (OSError, ValueError, AttributeError):
                pass  # los metadatos son informativos: el pack ya está guardado

    return file_path


def load_application_archive(application_id: str | int) -> dict:
    """Carga los metadatos y lista de ficheros existentes en el archivo de la candidatura."""
    app_dir = recover_application_dir(application_id)
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
