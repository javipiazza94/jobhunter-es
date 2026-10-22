"""
templates_registry.py — Plantillas propias de CV y carta (`add-template`).

Viven en `JH_HOME/templates/<kind>/<name>/` con un `template.json` (nombre, tipo cv|letter, motor
latex|typst, comando de compilación opcional, límite de páginas y reglas de estilo). Las integradas
(`moderncv-banking` para el CV y `cover-cls` para la carta) aparecen siempre y no se pueden borrar.

- Registrar una plantilla exige una compilación de prueba con `profile.example.json`: si no compila o
  no cabe en su límite de páginas, no se registra y el error vuelve al usuario.
- La plantilla activa se guarda en `jobhunter.yaml` (`documents:`); si la activa desaparece, se usa la
  integrada. Typst exige `typst` en el PATH (si no, `EngineMissing`, que la API traduce en 409).
- Seguridad: ningún nombre de archivo escapa de la carpeta de la plantilla (zip con `..`, rutas
  absolutas, enlaces simbólicos) y el comando de compilación solo puede ser un compilador conocido,
  sin shell.
"""

from __future__ import annotations

import io
import json
import logging
import os
import re
import shlex
import shutil
import stat
import subprocess
import tempfile
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any, Literal

from pydantic import BaseModel, Field

import config
from automation.latex_compiler import LaTeXCompilationError, compile_latex, engine_available

logger = logging.getLogger(__name__)

Kind = Literal["cv", "letter"]
Engine = Literal["latex", "typst"]

BUILTIN_TEMPLATES: dict[str, str] = {"cv": "moderncv-banking", "letter": "cover-cls"}
KINDS = tuple(BUILTIN_TEMPLATES)
META_FILE = "template.json"
TEMPLATE_SUFFIXES = {"latex": ".tex.j2", "typst": ".typ.j2"}
ALLOWED_COMPILERS = {"typst", "tectonic", "xelatex", "lualatex", "pdflatex", "latexmk"}
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,39}$")
MAX_ZIP_BYTES = 5 * 1024 * 1024
MAX_ZIP_FILES = 200
MAX_FILE_BYTES = 2 * 1024 * 1024
COMPILE_TIMEOUT = 180


class TemplateError(Exception):
    """Plantilla inválida (nombre, ficheros, compilación de prueba...)."""


class EngineMissing(TemplateError):
    """Falta el motor necesario (typst o un compilador LaTeX); el mensaje dice cómo instalarlo."""


class TemplateNotFound(TemplateError, LookupError):
    """La plantilla no existe."""


class TemplateInfo(BaseModel):
    name: str
    kind: Kind
    engine: Engine = "latex"
    builtin: bool = False
    active: bool = False
    main_file: str = ""
    compile_cmd: str | None = None
    page_limit: int | None = None
    style_rules: str = ""


class TemplateMeta(BaseModel):
    """Contenido de `template.json`."""

    name: str
    kind: Kind
    engine: Engine = "latex"
    main_file: str
    compile_cmd: str | None = None
    page_limit: int | None = Field(None, ge=1, le=6)
    style_rules: str = Field("", max_length=2000)


# ── Rutas ──────────────────────────────────────────────────────────────────────

def templates_root() -> Path:
    return Path(config.JH_HOME) / "templates"


def template_dir(kind: str, name: str) -> Path:
    return templates_root() / kind / name


def _check_name(name: str) -> str:
    name = (name or "").strip()
    if not NAME_RE.fullmatch(name):
        raise TemplateError("El nombre debe ser minúsculas, dígitos, - o _ (máx. 40) y empezar por letra o dígito")
    return name


def _check_kind(kind: str) -> str:
    if kind not in KINDS:
        raise TemplateError("El tipo de plantilla debe ser 'cv' o 'letter'")
    return kind


# ── Lectura ────────────────────────────────────────────────────────────────────

def _read_meta(path: Path) -> TemplateMeta | None:
    try:
        return TemplateMeta.model_validate(json.loads((path / META_FILE).read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return None


def _builtin_info(kind: str) -> TemplateInfo:
    main = "cv/cv.tex.j2" if kind == "cv" else "cover_letters/cover.tex.j2"
    return TemplateInfo(name=BUILTIN_TEMPLATES[kind], kind=kind, engine="latex", builtin=True, main_file=main)


def _active_names() -> dict[str, str]:
    from search_config import get_config

    docs = get_config().documents
    return {"cv": docs.cv_template, "letter": docs.letter_template}


def list_templates() -> list[TemplateInfo]:
    """Integradas + propias, con la activa marcada (si la activa ya no existe, lo está la integrada)."""
    active = _active_names()
    found: dict[str, list[TemplateInfo]] = {kind: [_builtin_info(kind)] for kind in KINDS}
    for kind in KINDS:
        root = templates_root() / kind
        if not root.is_dir():
            continue
        for entry in sorted(root.iterdir()):
            meta = _read_meta(entry) if entry.is_dir() and not entry.name.endswith(".tmp") else None
            if meta is None or meta.name != entry.name or meta.kind != kind or entry.name == BUILTIN_TEMPLATES[kind]:
                continue
            found[kind].append(TemplateInfo(
                name=meta.name, kind=kind, engine=meta.engine, main_file=meta.main_file,
                compile_cmd=meta.compile_cmd, page_limit=meta.page_limit, style_rules=meta.style_rules,
            ))
    out: list[TemplateInfo] = []
    for kind in KINDS:
        names = {t.name for t in found[kind]}
        current = active[kind] if active[kind] in names else BUILTIN_TEMPLATES[kind]
        for info in found[kind]:
            info.active = info.name == current
            out.append(info)
    return out


def active_template(kind: str) -> TemplateInfo | None:
    """Plantilla propia activa de ese tipo; None si manda la integrada."""
    for info in list_templates():
        if info.kind == kind and info.active and not info.builtin:
            return info
    return None


def active_suffix(kind: str) -> str:
    """Extensión del fuente que se compila: `.typ` con Typst; `.tex` en cualquier otro caso."""
    info = active_template(kind)
    return ".typ" if info is not None and info.engine == "typst" else ".tex"


# ── Renderizado y compilación ──────────────────────────────────────────────────

_TYPST_SPECIAL = re.compile(r"[\\#$*_`<>@\[\]~]")


def typst_escape(value: Any) -> str:
    """Texto del usuario → Typst seguro (no puede abrir código ni marcado)."""
    from automation.document_generator import _CONTROL_REGEX, _EMOJI_REGEX

    text = _EMOJI_REGEX.sub("", _CONTROL_REGEX.sub("", str(value if value is not None else "")))
    return _TYPST_SPECIAL.sub(lambda m: "\\" + m.group(0), text)


def _jinja_env(directory: Path):
    from automation.document_generator import _get_jinja_env

    env = _get_jinja_env(directory)
    env.filters["typst_escape"] = typst_escape
    return env


def _render_file(info: TemplateInfo, context: dict) -> str:
    directory = template_dir(info.kind, info.name)
    return _jinja_env(directory).get_template(info.main_file).render(**context)


def render_active(kind: str, context: dict) -> str | None:
    """Fuente de la plantilla propia activa renderizada con `context`; None si manda la integrada."""
    info = active_template(kind)
    return None if info is None else _render_file(info, context)


def copy_assets(kind: str, out_dir: Path) -> bool:
    """Copia los ficheros de apoyo de la plantilla propia activa (clases, fuentes, imágenes) junto al
    fuente. Devuelve False si manda la integrada."""
    info = active_template(kind)
    if info is None:
        return False
    src = template_dir(kind, info.name)
    for path in src.rglob("*"):
        rel = path.relative_to(src)
        if not path.is_file() or path.is_symlink() or rel.name == META_FILE or path.name.endswith(".j2"):
            continue
        dest = Path(out_dir) / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        if not dest.exists():
            shutil.copy2(path, dest)
    return True


def _split_cmd(cmd: str, source: Path, out_dir: Path, pdf: Path) -> list[str]:
    try:
        parts = shlex.split(cmd)
    except ValueError as exc:
        raise TemplateError(f"Comando de compilación inválido: {exc}") from None
    if not parts or Path(parts[0]).name not in ALLOWED_COMPILERS or parts[0] != Path(parts[0]).name:
        raise TemplateError(
            f"El comando de compilación debe empezar por un compilador conocido ({', '.join(sorted(ALLOWED_COMPILERS))})"
        )
    subs = {"{input}": str(source), "{output}": str(pdf), "{outdir}": str(out_dir)}
    return [subs.get(p, p) for p in parts]


def _run(cmd: list[str], cwd: Path) -> None:
    if shutil.which(cmd[0]) is None:
        raise EngineMissing(f"No se encuentra '{cmd[0]}' en el PATH")
    try:
        proc = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, timeout=COMPILE_TIMEOUT)
    except subprocess.TimeoutExpired:
        raise LaTeXCompilationError(f"La compilación agotó el tiempo límite ({COMPILE_TIMEOUT}s)") from None
    except OSError as exc:
        raise LaTeXCompilationError(f"No se pudo ejecutar '{cmd[0]}': {exc}") from None
    if proc.returncode != 0:
        tail = "\n".join((proc.stderr.strip() or proc.stdout.strip()).splitlines()[-25:])
        raise LaTeXCompilationError(f"Compilación con {cmd[0]} falló (código {proc.returncode}):\n{tail}")


def compile_source(source: Path | str, out_dir: Path | str, passes: int = 2, kind: str | None = None) -> Path:
    """Compila un fuente a PDF: `.typ` con Typst, el resto como LaTeX. Si la plantilla propia activa
    define `compile_cmd` (solo compiladores conocidos), se usa en su lugar."""
    src, out = Path(source).resolve(), Path(out_dir).resolve()
    info = active_template(kind) if kind else None
    custom_cmd = info.compile_cmd if info is not None else None
    return _compile(src, out, passes, custom_cmd)


def _compile(src: Path, out: Path, passes: int, custom_cmd: str | None) -> Path:
    out.mkdir(parents=True, exist_ok=True)
    pdf = out / f"{src.stem}.pdf"
    if custom_cmd:
        _run(_split_cmd(custom_cmd, src, out, pdf), src.parent)
    elif src.suffix == ".typ":
        _run(["typst", "compile", str(src), str(pdf)], src.parent)
    else:
        return compile_latex(src, output_dir=out, passes=passes)
    if not pdf.is_file():
        raise LaTeXCompilationError(f"El compilador terminó con éxito pero no se generó '{pdf}'")
    return pdf


# ── Registro ───────────────────────────────────────────────────────────────────

def _clean_member(name: str) -> PurePosixPath:
    posix = PurePosixPath(name.replace("\\", "/"))
    if (not name or posix.is_absolute() or ".." in posix.parts or posix.parts[:1] == ("",)
            or any(re.match(r"^[A-Za-z]:", p) for p in posix.parts[:1])):
        raise TemplateError(f"Ruta no permitida en la plantilla: {name!r}")
    return posix


def files_from_zip(data: bytes) -> dict[str, bytes]:
    """Extrae un zip en memoria con límites de tamaño y sin rutas que escapen (path traversal)."""
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise TemplateError("El archivo no es un zip válido") from None
    infos = [i for i in archive.infolist() if not i.is_dir()]
    if len(infos) > MAX_ZIP_FILES:
        raise TemplateError(f"El zip tiene demasiados ficheros (máx. {MAX_ZIP_FILES})")
    if sum(i.file_size for i in infos) > MAX_ZIP_BYTES:
        raise TemplateError("El zip descomprimido es demasiado grande (máx. 5 MB)")
    files: dict[str, bytes] = {}
    for info in infos:
        rel = _clean_member(info.filename)
        mode = info.external_attr >> 16
        if stat.S_ISLNK(mode):
            raise TemplateError(f"Enlaces simbólicos no permitidos en la plantilla: {info.filename!r}")
        if info.file_size > MAX_FILE_BYTES:
            raise TemplateError(f"El fichero {info.filename!r} es demasiado grande")
        files[str(rel)] = archive.read(info)
    return files


def _find_main(files: dict[str, bytes], engine: str, main_file: str | None) -> str:
    suffix = TEMPLATE_SUFFIXES[engine]
    if main_file:
        main = str(_clean_member(main_file))
        if main not in files:
            raise TemplateError(f"El fichero principal {main_file!r} no está en la plantilla")
        return main
    candidates = sorted(n for n in files if n.endswith(suffix))
    if not candidates:
        raise TemplateError(f"Falta el fichero principal de la plantilla (*{suffix})")
    return candidates[0]


def _test_context(kind: str) -> dict:
    from automation.document_generator import prepare_cover_letter_context, prepare_cv_context

    profile = json.loads((config.REPO_ROOT / "backend" / "profile.example.json").read_text(encoding="utf-8"))
    if kind == "cv":
        return prepare_cv_context(profile)
    return prepare_cover_letter_context(profile, company_name="Empresa Demo", role_title="Puesto Demo")


def _test_compile(directory: Path, meta: TemplateMeta) -> None:
    """Compilación de prueba obligatoria: renderiza con `profile.example.json`, compila y cuenta páginas."""
    from automation.document_generator import _page_count

    if meta.engine == "typst" and shutil.which("typst") is None and not meta.compile_cmd:
        raise EngineMissing("Esta plantilla usa Typst: instala `typst` (https://typst.app) y vuelve a intentarlo")
    if meta.engine == "latex" and not meta.compile_cmd and engine_available() is None:
        raise EngineMissing("Instala Tectonic o TeX Live (xelatex) para registrar plantillas LaTeX")
    try:
        source = _jinja_env(directory).get_template(meta.main_file).render(**_test_context(meta.kind))
    except Exception as exc:  # noqa: BLE001 — sintaxis Jinja o variables que no existen
        raise TemplateError(f"La plantilla no se puede renderizar: {type(exc).__name__}: {exc}") from None
    with tempfile.TemporaryDirectory(prefix="jh-template-test-") as tmp:
        work = Path(tmp)
        for path in directory.rglob("*"):
            rel = path.relative_to(directory)
            if path.is_file() and not path.is_symlink() and rel.name != META_FILE and not path.name.endswith(".j2"):
                (work / rel).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, work / rel)
        stem = "cv" if meta.kind == "cv" else "cover"
        src = work / (stem + (".typ" if meta.engine == "typst" else ".tex"))
        src.write_text(source, encoding="utf-8")
        try:
            pdf = _compile(src, work, 1, meta.compile_cmd)
        except (LaTeXCompilationError, TemplateError) as exc:
            if isinstance(exc, EngineMissing):
                raise
            raise TemplateError(f"La compilación de prueba falló: {exc}") from None
        pages = _page_count(pdf)
    from search_config import get_config

    docs = get_config().documents
    limit = meta.page_limit or (docs.cv_pages if meta.kind == "cv" else docs.letter_pages)
    if pages > limit:
        raise TemplateError(f"La compilación de prueba ocupa {pages} páginas y el límite es {limit}")


def register_template(
    name: str,
    kind: str,
    files: dict[str, bytes],
    engine: str = "latex",
    main_file: str | None = None,
    compile_cmd: str | None = None,
    page_limit: int | None = None,
    style_rules: str = "",
) -> TemplateInfo:
    """Valida, compila de prueba y registra una plantilla. Si ya existía una propia con ese nombre
    se sustituye de una vez (`os.replace` de la carpeta). Lanza TemplateError / EngineMissing."""
    name, kind = _check_name(name), _check_kind(kind)
    if engine not in TEMPLATE_SUFFIXES:
        raise TemplateError("El motor debe ser 'latex' o 'typst'")
    if name == BUILTIN_TEMPLATES[kind]:
        raise TemplateError(f"'{name}' es el nombre de la plantilla integrada")
    if not files:
        raise TemplateError("La plantilla no tiene ficheros")
    if sum(len(v) for v in files.values()) > MAX_ZIP_BYTES:
        raise TemplateError("La plantilla es demasiado grande (máx. 5 MB)")
    clean = {str(_clean_member(n)): data for n, data in files.items() if PurePosixPath(n).name != META_FILE}
    cmd = (compile_cmd or "").strip() or None
    if cmd:
        _split_cmd(cmd, Path("in"), Path("out"), Path("out.pdf"))  # valida el compilador permitido
    meta = TemplateMeta(
        name=name, kind=kind, engine=engine, main_file=_find_main(clean, engine, main_file),
        compile_cmd=cmd, page_limit=page_limit, style_rules=(style_rules or "").strip(),
    )
    target = template_dir(kind, name)
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = target.with_name(f"{name}.tmp")
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir()
    try:
        for rel, data in clean.items():
            dest = staging / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
        (staging / META_FILE).write_text(meta.model_dump_json(indent=2), encoding="utf-8")
        _test_compile(staging, meta)
        old = target.with_name(f"{name}.old")
        shutil.rmtree(old, ignore_errors=True)
        if target.exists():
            os.replace(target, old)
        os.replace(staging, target)
        shutil.rmtree(old, ignore_errors=True)
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    logger.info("Plantilla %s/%s registrada", kind, name)
    return next(t for t in list_templates() if t.kind == kind and t.name == name)


def _find(kind: str, name: str) -> TemplateInfo:
    try:
        return next(t for t in list_templates() if t.kind == _check_kind(kind) and t.name == name)
    except StopIteration:
        raise TemplateNotFound(f"Plantilla desconocida: {kind}/{name}") from None


def activate_template(kind: str, name: str) -> TemplateInfo:
    """Marca una plantilla como la activa de su tipo (se guarda en `documents:` de jobhunter.yaml)."""
    from search_config import get_config, save_config, user_config_path

    info = _find(kind, name)
    if info.engine == "typst" and shutil.which("typst") is None and not info.compile_cmd:
        raise EngineMissing("Esta plantilla usa Typst: instala `typst` para poder activarla")
    current = get_config()
    field = "cv_template" if kind == "cv" else "letter_template"
    docs = current.documents.model_copy(update={field: name})
    save_config(current.model_copy(update={"documents": docs}), user_config_path())
    return _find(kind, name)


def delete_template(kind: str, name: str) -> None:
    """Borra una plantilla propia. Las integradas no se pueden borrar; si era la activa, vuelve la integrada."""
    info = _find(kind, name)
    if info.builtin:
        raise TemplateError("Las plantillas integradas no se pueden borrar")
    was_active = info.active
    shutil.rmtree(template_dir(kind, name), ignore_errors=True)
    if was_active:
        activate_template(kind, BUILTIN_TEMPLATES[kind])


# ── CLI: python -m automation.templates_registry list|add|activate|delete ─────

def _cli(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(prog="python -m automation.templates_registry", description=__doc__.splitlines()[1])
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list", help="Lista las plantillas")
    add = sub.add_parser("add", help="Registra una plantilla desde un .zip o un único fichero .tex.j2/.typ.j2")
    add.add_argument("path")
    add.add_argument("--name", required=True)
    add.add_argument("--kind", choices=KINDS, required=True)
    add.add_argument("--engine", choices=list(TEMPLATE_SUFFIXES), default=None)
    add.add_argument("--compile-cmd", default=None)
    add.add_argument("--page-limit", type=int, default=None)
    add.add_argument("--style-rules", default="")
    act = sub.add_parser("activate")
    act.add_argument("kind", choices=KINDS)
    act.add_argument("name")
    rm = sub.add_parser("delete")
    rm.add_argument("kind", choices=KINDS)
    rm.add_argument("name")
    args = parser.parse_args(argv)
    try:
        if args.cmd == "list":
            for t in list_templates():
                print(f"{'*' if t.active else ' '} {t.kind:6} {t.name:24} {t.engine}{' (integrada)' if t.builtin else ''}")
        elif args.cmd == "add":
            path = Path(args.path)
            engine = args.engine or ("typst" if path.name.endswith(".typ.j2") else "latex")
            files = files_from_zip(path.read_bytes()) if path.suffix == ".zip" else {path.name: path.read_bytes()}
            info = register_template(args.name, args.kind, files, engine=engine, compile_cmd=args.compile_cmd,
                                     page_limit=args.page_limit, style_rules=args.style_rules)
            print(f"Registrada {info.kind}/{info.name} ({info.engine}); actívala con: activate {info.kind} {info.name}")
        elif args.cmd == "activate":
            print(f"Activa: {activate_template(args.kind, args.name).name}")
        else:
            delete_template(args.kind, args.name)
            print("Borrada")
    except (TemplateError, OSError) as exc:
        print(f"Error: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
