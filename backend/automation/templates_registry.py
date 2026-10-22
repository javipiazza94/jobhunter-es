"""
templates_registry.py — Plantillas propias de CV y carta (`add-template`).

Viven en `JH_HOME/templates/<kind>/<name>/` con un `template.json` (nombre, tipo cv|letter, motor
latex|typst, compilador de una lista cerrada, límite de páginas y reglas de estilo). Las integradas
(`moderncv-banking` para el CV y `cover-cls` para la carta) aparecen siempre y no se pueden borrar.

- Registrar una plantilla exige una compilación de prueba con `profile.example.json`: si no compila o
  no cabe en su límite de páginas, no se registra y el error vuelve al usuario.
- La plantilla activa se guarda en `jobhunter.yaml` (`documents:`); si la activa desaparece, se usa la
  integrada. Typst exige `typst` en el PATH (si no, `EngineMissing`, que la API traduce en 409).
- Seguridad (una plantilla es código: instala solo las de confianza):
  · Ningún nombre de archivo escapa de la carpeta de la plantilla (zip con `..`, rutas absolutas, enlaces
    simbólicos); `latexmkrc`, `.latexmkrc` y `texmf.cnf` se descartan.
  · Las plantillas propias se renderizan en un entorno Jinja aislado (`ImmutableSandboxedEnvironment`):
    nada de atributos internos de Python (`__globals__`...) → `SecurityError`.
  · Toda salida `((( x )))` se escapa por defecto (`latex_escape` o `typst_escape` según el motor);
    `|safe_raw` la deja tal cual a propósito.
  · No hay comando de compilación libre: el compilador sale de una lista cerrada (tectonic, xelatex,
    lualatex, typst) y la línea de órdenes se construye en el código con opciones seguras (sin
    shell-escape; Typst con `--root` en la carpeta de trabajo). Nunca se ejecuta latexmk.
  · LaTeX propio: se prefieren xelatex/lualatex con kpathsea paranoico (openin_any=p/openout_any=p);
    Tectonic no confina las lecturas y solo se usa si no hay ninguno (preparar lo avisa).
  · Registrar exige `trusted=True`: una plantilla puede leer ficheros del equipo y meterlos en el PDF.
  · Se rechaza al registrar cualquier `\\input`, `\\include`, `\\openin`... con ruta absoluta o con `..`.
"""

from __future__ import annotations

import contextlib
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
from contextvars import ContextVar
from pathlib import Path, PurePosixPath
from typing import Any, Literal

import jinja2
import jinja2.sandbox
from pydantic import BaseModel, Field, ValidationError

import config
from automation.latex_compiler import (
    DEFAULT_ENGINES,
    LaTeXCompilationError,
    find_latex_compiler,
)

logger = logging.getLogger(__name__)

Kind = Literal["cv", "letter"]
Engine = Literal["latex", "typst"]
Compiler = Literal["tectonic", "xelatex", "lualatex", "typst"]

BUILTIN_TEMPLATES: dict[str, str] = {"cv": "moderncv-banking", "letter": "cover-cls"}
KINDS = tuple(BUILTIN_TEMPLATES)
META_FILE = "template.json"
TEMPLATE_SUFFIXES = {"latex": ".tex.j2", "typst": ".typ.j2"}
COMPILERS: tuple[str, ...] = ("tectonic", "xelatex", "lualatex", "typst")
LATEX_COMPILERS = DEFAULT_ENGINES  # tectonic, xelatex, lualatex
# Motores que kpathsea confina con openin_any=p/openout_any=p (sin rutas absolutas ni '..'). Tectonic no
# usa kpathsea: un \input{/ruta/absoluta} se lee aunque vaya con --untrusted, así que para plantillas propias
# solo se usa si no hay xelatex ni lualatex (y entonces se avisa).
CONFINED_LATEX = ("xelatex", "lualatex")
TRUST_WARNING = (
    "Una plantilla puede leer ficheros de tu equipo y meterlos en el PDF que envías. "
    "Instala solo plantillas de fuentes de confianza."
)
UNCONFINED_WARNING = (
    "La plantilla propia se compiló con Tectonic, que no impide leer ficheros fuera de su carpeta: "
    "instala xelatex o lualatex (TeX Live) para aislarla. " + TRUST_WARNING
)
# Ficheros de configuración que un compilador o latexmk leerían de la carpeta de trabajo: se descartan.
IGNORED_MEMBERS = {"latexmkrc", ".latexmkrc", "texmf.cnf"}
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


class TemplateRenderError(TemplateError):
    """La plantilla propia activa no se pudo renderizar (sintaxis, variable inexistente, acceso bloqueado
    por el entorno aislado...)."""


class TemplateInfo(BaseModel):
    name: str
    kind: Kind
    engine: Engine = "latex"
    builtin: bool = False
    active: bool = False
    main_file: str = ""
    compiler: Compiler | None = None
    page_limit: int | None = None
    style_rules: str = ""
    invalid_reason: str | None = None
    trusted: bool = False


class TemplateMeta(BaseModel):
    """Contenido de `template.json`. `compiler` None = el primero disponible (LaTeX) o typst (Typst)."""

    name: str
    kind: Kind
    engine: Engine = "latex"
    main_file: str
    compiler: Compiler | None = None
    page_limit: int | None = Field(None, ge=1, le=6)
    style_rules: str = Field("", max_length=2000)
    invalid_reason: str | None = None
    trusted: bool = False  # la persona confirmó al registrarla que viene de una fuente de confianza


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

def _legacy_compiler(cmd: Any) -> tuple[str | None, str | None]:
    """`compile_cmd` libre de versiones anteriores → (compilador, motivo de invalidez). Si nombra un
    compilador conocido se usa ese compilador con las opciones seguras (las del comando se ignoran); si no
    (latexmk, pdflatex, un shell...), la plantilla queda inválida."""
    try:
        first = shlex.split(str(cmd or ""))[:1]
    except ValueError:
        first = []
    name = first[0] if first else ""
    if name in COMPILERS:
        return name, None
    return None, (
        f"Su comando de compilación ({name or 'vacío'}) ya no se admite: vuelve a registrarla eligiendo "
        f"compilador ({', '.join(COMPILERS)})"
    )


def _read_meta(path: Path) -> TemplateMeta | None:
    try:
        data = json.loads((path / META_FILE).read_text(encoding="utf-8"))
        if isinstance(data, dict) and "compile_cmd" in data:
            legacy = data.pop("compile_cmd")
            if legacy and not data.get("compiler"):
                data["compiler"], data["invalid_reason"] = _legacy_compiler(legacy)
        return TemplateMeta.model_validate(data)
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
                compiler=meta.compiler, page_limit=meta.page_limit, style_rules=meta.style_rules,
                invalid_reason=meta.invalid_reason, trusted=meta.trusted,
            ))
    out: list[TemplateInfo] = []
    for kind in KINDS:
        names = {t.name for t in found[kind] if not t.invalid_reason}
        current = active[kind] if active[kind] in names else BUILTIN_TEMPLATES[kind]
        for info in found[kind]:
            info.active = info.name == current
            out.append(info)
    return out


_BUILTIN_ONLY: ContextVar[bool] = ContextVar("jh_builtin_templates_only", default=False)


@contextlib.contextmanager
def builtin_only():
    """Dentro del bloque se usan las plantillas integradas aunque haya propias activas (reserva cuando una
    plantilla propia falla: «Preparar con las plantillas integradas»)."""
    token = _BUILTIN_ONLY.set(True)
    try:
        yield
    finally:
        _BUILTIN_ONLY.reset(token)


def active_template(kind: str) -> TemplateInfo | None:
    """Plantilla propia activa de ese tipo; None si manda la integrada (o dentro de `builtin_only()`)."""
    if _BUILTIN_ONLY.get():
        return None
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


class _Escaped(str):
    """Texto ya escapado (o crudo a propósito con `safe_raw`): `finalize` no lo vuelve a escapar."""


def _custom_jinja_env(directory: Path, engine: str) -> jinja2.sandbox.ImmutableSandboxedEnvironment:
    """Entorno de las plantillas PROPIAS: aislado (sin acceso a atributos internos de Python ni a métodos
    que muten datos), mismos delimitadores que las integradas y escape por defecto de toda salida según el
    motor. Los filtros de escape devuelven texto marcado para no escaparlo dos veces."""
    from automation.document_generator import latex_escape, latex_url

    escape = typst_escape if engine == "typst" else latex_escape

    def finalize(value: Any) -> str:
        if isinstance(value, _Escaped):
            return value
        if value is None or isinstance(value, jinja2.Undefined):
            return ""
        return escape(value)

    env = jinja2.sandbox.ImmutableSandboxedEnvironment(
        block_start_string="((*",
        block_end_string="*))",
        variable_start_string="(((",
        variable_end_string=")))",
        comment_start_string="((=",
        comment_end_string="=))",
        loader=jinja2.FileSystemLoader(str(directory)),
        trim_blocks=True,
        lstrip_blocks=True,
        autoescape=False,
        finalize=finalize,
    )
    env.filters["latex_escape"] = lambda v: _Escaped(latex_escape(v))
    env.filters["latex_url"] = lambda v: _Escaped(latex_url(v))
    env.filters["typst_escape"] = lambda v: _Escaped(typst_escape(v))
    env.filters["safe_raw"] = lambda v: _Escaped("" if v is None else str(v))
    return env


def _render(directory: Path, engine: str, main_file: str, context: dict) -> str:
    """Renderiza una plantilla propia en el entorno aislado. Cualquier fallo (sintaxis, variable que no
    existe, acceso bloqueado → SecurityError) se convierte en TemplateRenderError con el motivo."""
    try:
        source = _custom_jinja_env(directory, engine).get_template(main_file).render(**context)
    except Exception as exc:  # noqa: BLE001 — jinja2.TemplateError, SecurityError, TypeError de la plantilla...
        raise TemplateRenderError(f"La plantilla no se puede renderizar: {type(exc).__name__}: {exc}") from None
    if engine == "latex":
        lint_latex(source, main_file)
    return source


def _render_file(info: TemplateInfo, context: dict) -> str:
    return _render(template_dir(info.kind, info.name), info.engine, info.main_file, context)


def render_active(kind: str, context: dict) -> str | None:
    """Fuente de la plantilla propia activa renderizada con `context`; None si manda la integrada.
    Lanza TemplateRenderError si la plantilla falla."""
    info = active_template(kind)
    return None if info is None else _render_file(info, context)


def copy_assets(kind: str, out_dir: Path) -> bool:
    """Copia los ficheros de apoyo de la plantilla propia activa (clases, fuentes, imágenes) junto al
    fuente, sobrescribiendo los de una preparación anterior. Devuelve False si manda la integrada."""
    info = active_template(kind)
    if info is None:
        return False
    _copy_support_files(template_dir(kind, info.name), Path(out_dir))
    return True


def _copy_support_files(src: Path, dest_root: Path) -> None:
    for path in src.rglob("*"):
        rel = path.relative_to(src)
        if (not path.is_file() or path.is_symlink() or rel.name == META_FILE or path.name.endswith(".j2")
                or path.name.lower() in IGNORED_MEMBERS):
            continue
        dest = dest_root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, dest)


def _check_compiler(compiler: Any) -> str:
    if compiler not in COMPILERS:
        raise TemplateError(f"El compilador debe ser uno de: {', '.join(COMPILERS)}")
    return compiler


def compile_argv(compiler: str, source: Path, out_dir: Path, passes: int = 1) -> list[str]:
    """Línea de órdenes fija y segura de cada compilador (sin shell ni opciones de la plantilla):
    - tectonic: `--untrusted` (desactiva shell-escape y demás funciones inseguras).
    - xelatex / lualatex: `-no-shell-escape -interaction=nonstopmode -halt-on-error -output-directory=<out>`.
    - typst: `compile --root <carpeta del fuente>` (no puede leer fuera de la carpeta de trabajo).
    Nunca latexmk (ejecutaría el Perl de un latexmkrc)."""
    compiler = _check_compiler(compiler)
    src, out = str(source), str(out_dir)
    if compiler == "tectonic":
        return ["tectonic", "--untrusted", "-o", out, *(["--reruns", "0"] if passes <= 1 else []), src]
    if compiler == "typst":
        return ["typst", "compile", "--root", str(Path(source).parent), src, str(Path(out_dir) / f"{Path(source).stem}.pdf")]
    return [compiler, "-no-shell-escape", "-interaction=nonstopmode", "-halt-on-error", f"-output-directory={out}", src]


def _resolve_binary(name: str) -> str | None:
    try:
        return str(find_latex_compiler(preferred_engine=name)[1])
    except LaTeXCompilationError:
        return None


def _missing_hint(compiler: str) -> str:
    if compiler == "typst":
        return "Esta plantilla usa Typst: instala `typst` (https://typst.app) y vuelve a intentarlo"
    return f"Esta plantilla necesita `{compiler}`: instálalo (o elige otro compilador) y vuelve a intentarlo"


def is_unconfined(compiler: str) -> bool:
    """True si el compilador no confina la lectura de ficheros a la carpeta de trabajo (Tectonic)."""
    return compiler == "tectonic"


def resolve_compiler(engine: str, compiler: str | None) -> str:
    """Compilador que se usará para una plantilla PROPIA:
    - Typst: typst (confinado con --root).
    - LaTeX: xelatex o lualatex si hay alguno (kpathsea en modo paranoico); el elegido entre ellos si está.
      Tectonic, aunque se haya elegido, solo si no hay ninguno de los dos (no confina las lecturas).
    Lanza EngineMissing si no está instalado."""
    if compiler:
        _check_compiler(compiler)
    if engine == "typst" or compiler == "typst":
        chosen = compiler or "typst"
    elif compiler in CONFINED_LATEX:
        chosen = compiler
    else:
        chosen = next((c for c in CONFINED_LATEX if _resolve_binary(c) is not None), "")
        if not chosen:
            chosen = "tectonic" if _resolve_binary("tectonic") is not None else ""
        if not chosen:
            raise EngineMissing("Instala TeX Live (xelatex o lualatex) o Tectonic para usar plantillas LaTeX")
    if (engine == "typst") != (chosen == "typst"):
        raise TemplateError(f"El compilador {chosen} no sirve para plantillas {engine}")
    if _resolve_binary(chosen) is None:
        raise EngineMissing(_missing_hint(chosen))
    return chosen


def _run(cmd: list[str], cwd: Path, env: dict[str, str] | None = None) -> None:
    binary = _resolve_binary(cmd[0])
    if binary is None:
        raise EngineMissing(_missing_hint(cmd[0]))
    try:
        proc = subprocess.run([binary, *cmd[1:]], cwd=str(cwd), env=env, capture_output=True, text=True,
                              timeout=COMPILE_TIMEOUT)
    except subprocess.TimeoutExpired:
        raise LaTeXCompilationError(f"La compilación agotó el tiempo límite ({COMPILE_TIMEOUT}s)") from None
    except OSError as exc:
        raise LaTeXCompilationError(f"No se pudo ejecutar '{cmd[0]}': {exc}") from None
    if proc.returncode != 0:
        tail = "\n".join((proc.stderr.strip() or proc.stdout.strip()).splitlines()[-25:])
        raise LaTeXCompilationError(f"Compilación con {cmd[0]} falló (código {proc.returncode}):\n{tail}")


def _paranoid_env() -> dict[str, str]:
    """kpathsea en modo paranoico: sin leer/escribir rutas absolutas ni con `..`, y sin shell-escape."""
    return {**os.environ, "openin_any": "p", "openout_any": "p", "shell_escape": "f"}


def compile_source(source: Path | str, out_dir: Path | str, passes: int = 2, kind: str | None = None) -> Path:
    """Compila el fuente de la plantilla propia activa de `kind` con su compilador y opciones seguras."""
    src, out = Path(source).resolve(), Path(out_dir).resolve()
    info = active_template(kind) if kind else None
    engine = info.engine if info is not None else ("typst" if src.suffix == ".typ" else "latex")
    return _compile(src, out, passes, engine, info.compiler if info is not None else None)


def _compile(src: Path, out: Path, passes: int, engine: str, compiler: str | None) -> Path:
    out.mkdir(parents=True, exist_ok=True)
    chosen = resolve_compiler(engine, compiler)
    argv = compile_argv(chosen, src, out, passes)
    runs = 1 if chosen in ("tectonic", "typst") else max(1, passes)
    env = None if chosen == "typst" else _paranoid_env()
    for _ in range(runs):
        _run(argv, src.parent, env)
    pdf = out / f"{src.stem}.pdf"
    if not pdf.is_file():
        raise LaTeXCompilationError(f"El compilador terminó con éxito pero no se generó '{pdf}'")
    return pdf


# ── Lint: lecturas de ficheros fuera de la carpeta de la plantilla ─────────────

_FILE_COMMANDS = (
    "input", "include", "openin", "InputIfFileExists", "IfFileExists", "includegraphics", "includepdf",
    "lstinputlisting", "verbatiminput", "VerbatimInput", "import", "subimport", "subfile", "includeonly",
    "usepackage", "RequirePackage", "documentclass", "LoadClass", "addbibresource", "bibliography",
    "setmainfont", "setsansfont", "setmonofont", "fontspec", "newfontfamily", "read",
)
_FILE_ARG = re.compile(
    r"\\(" + "|".join(_FILE_COMMANDS) + r")(?![A-Za-z@])\d*\s*(?:=\s*)?(?:\[[^\]]*\]\s*)*(?:\{([^}]*)\}|([^\s{}\\%]+))"
)
_TEXT_SUFFIXES = (".j2", ".tex", ".sty", ".cls", ".def", ".cfg", ".clo", ".ltx", ".bib", ".typ")


def _bad_path(path: str) -> bool:
    p = path.strip().replace("\\", "/")
    return bool(p) and (p.startswith(("/", "~")) or re.match(r"^[A-Za-z]:", p) is not None
                        or ".." in PurePosixPath(p).parts or "../" in p)


_CATCODE = re.compile(r"\\catcode(?![A-Za-z@])")
_CSNAME_FILE = re.compile(
    r"\\csname\s*@*(?:input|include|openin|read|InputIfFileExists|IfFileExists|includegraphics|"
    r"lstinputlisting|verbatiminput|import|subimport|subfile)\b"
)


def lint_latex(text: str, filename: str) -> None:
    """Lint de mejor esfuerzo (no es una barrera completa: una plantilla es código). Rechaza cambios de
    \\catcode, órdenes de lectura construidas con \\csname y lecturas fuera de la carpeta:
    `\\input{/…}`, `\\include{../…}`, `\\openin5=/…` y similares: una plantilla solo puede leer
    ficheros de su propia carpeta (y paquetes de la distribución TeX por nombre)."""
    if _CATCODE.search(text):
        raise TemplateError(f"La plantilla cambia \\catcode ({filename}): no se permite (podría ocultar lecturas de ficheros)")
    m = _CSNAME_FILE.search(text)
    if m:
        raise TemplateError(f"La plantilla construye una orden de lectura con \\csname ({m.group(0)} en {filename}): no se permite")
    for m in _FILE_ARG.finditer(text):
        for arg in (m.group(2) or m.group(3) or "").split(","):
            if _bad_path(arg):
                raise TemplateError(
                    f"La plantilla lee un fichero fuera de su carpeta (\\{m.group(1)} {arg.strip()} en {filename}): "
                    "no se permiten rutas absolutas, con ~ ni con '..'"
                )


def _lint_files(files: dict[str, bytes]) -> None:
    for name, data in files.items():
        if name.lower().endswith(_TEXT_SUFFIXES):
            lint_latex(data.decode("utf-8", errors="replace"), name)


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

    resolve_compiler(meta.engine, meta.compiler)  # EngineMissing antes de nada si falta el motor
    # Mismo entorno aislado y con escape por defecto que en cada «Preparar candidatura»
    source = _render(directory, meta.engine, meta.main_file, _test_context(meta.kind))
    with tempfile.TemporaryDirectory(prefix="jh-template-test-") as tmp:
        work = Path(tmp)
        _copy_support_files(directory, work)
        stem = "cv" if meta.kind == "cv" else "cover"
        src = work / (stem + (".typ" if meta.engine == "typst" else ".tex"))
        src.write_text(source, encoding="utf-8")
        try:
            pdf = _compile(src, work, 1, meta.engine, meta.compiler)
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
    compiler: str | None = None,
    page_limit: int | None = None,
    style_rules: str = "",
    trusted: bool = False,
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
    clean = {
        str(_clean_member(n)): data for n, data in files.items()
        if PurePosixPath(n.replace("\\", "/")).name != META_FILE
        and PurePosixPath(n.replace("\\", "/")).name.lower() not in IGNORED_MEMBERS
    }
    if page_limit is not None and not 1 <= page_limit <= 6:
        raise TemplateError("page_limit debe estar entre 1 y 6")
    compiler = (compiler or "").strip() or None
    if compiler is not None:
        _check_compiler(compiler)
    if engine == "latex":
        _lint_files(clean)
    if trusted is not True:
        raise TemplateError(f"Confirma que la plantilla es de confianza (trusted): {TRUST_WARNING}")
    try:
        meta = TemplateMeta(
            name=name, kind=kind, engine=engine, main_file=_find_main(clean, engine, main_file),
            compiler=compiler, page_limit=page_limit, style_rules=(style_rules or "").strip(), trusted=True,
        )
    except ValidationError as exc:
        raise TemplateError(f"Datos de la plantilla no válidos: {exc.errors()[0].get('msg', exc)}") from None
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
    if info.invalid_reason:
        raise TemplateError(f"La plantilla {kind}/{name} no es válida: {info.invalid_reason}")
    if not info.builtin:
        resolve_compiler(info.engine, info.compiler)  # EngineMissing si falta su motor
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
    add.add_argument("--compiler", choices=COMPILERS, default=None,
                     help="Compilador (por defecto: typst en Typst; en LaTeX el primero instalado)")
    add.add_argument("--page-limit", type=int, default=None)
    add.add_argument("--style-rules", default="")
    add.add_argument("--trusted", action="store_true", required=True,
                     help="Confirma que la plantilla viene de una fuente de confianza (puede leer ficheros de tu equipo)")
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
                flag = " (integrada)" if t.builtin else (f" (NO VÁLIDA: {t.invalid_reason})" if t.invalid_reason else "")
                print(f"{'*' if t.active else ' '} {t.kind:6} {t.name:24} {t.engine}{flag}")
        elif args.cmd == "add":
            path = Path(args.path)
            engine = args.engine or ("typst" if path.name.endswith(".typ.j2") else "latex")
            files = files_from_zip(path.read_bytes()) if path.suffix == ".zip" else {path.name: path.read_bytes()}
            info = register_template(args.name, args.kind, files, engine=engine, compiler=args.compiler,
                                     page_limit=args.page_limit, style_rules=args.style_rules, trusted=args.trusted)
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
