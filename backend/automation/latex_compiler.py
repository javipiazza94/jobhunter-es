"""
latex_compiler.py — Descubrimiento de compilador LaTeX y compilación de documentos.

Portado / adaptado para Job Hunter Spain conforme a §5.11 del spec.
Soporta Tectonic (por defecto, motor standalone) con fallback a xelatex, lualatex o pdflatex.
Permite sustitución de plantillas en $JH_HOME/templates/latex/.
"""

import os
import shutil
import subprocess
from pathlib import Path

from config import DEFAULT_LATEX_TEMPLATES_DIR, LATEX_TEMPLATES_OVERRIDE_DIR


class LaTeXCompilationError(Exception):
    """Fallo en la compilación de un documento LaTeX."""
    pass


def find_latex_compiler(preferred_engine: str | None = None) -> tuple[str, Path]:
    """
    Localiza un ejecutable de compilación LaTeX disponible.

    Orden de prioridad por defecto:
      1. tectonic (motor XeTeX standalone, descarga paquetes bajo demanda)
      2. xelatex (soporte nativo de fuentes del sistema y fontspec)
      3. lualatex
      4. pdflatex

    Busca en PATH y en ubicaciones de usuario comunes (~/.cargo/bin, ~/.local/bin).
    Retorna una tupla (nombre_motor, ruta_al_binario).
    Lanza LaTeXCompilationError si no se encuentra ningún compilador utilizable.
    """
    candidates = [preferred_engine] if preferred_engine else ["tectonic", "xelatex", "lualatex", "pdflatex"]
    extra_dirs = [
        Path.home() / ".cargo" / "bin",
        Path.home() / ".local" / "bin",
        Path("/usr/local/bin"),
        Path("/usr/bin"),
    ]

    for candidate in candidates:
        if not candidate:
            continue
        # 1. Comprobar en PATH
        found = shutil.which(candidate)
        if found:
            return candidate, Path(found)

        # 2. Comprobar en directorios extra de usuario
        for d in extra_dirs:
            bin_path = d / candidate
            if bin_path.is_file() and os.access(bin_path, os.X_OK):
                return candidate, bin_path

    raise LaTeXCompilationError(
        f"No se encontró ningún compilador LaTeX válido (probados: {candidates}). "
        "Instala Tectonic ('cargo install tectonic' o binario standalone) o TeX Live."
    )


def resolve_template_path(template_rel: str | Path) -> Path:
    """
    Resuelve la ruta a una plantilla o archivo LaTeX.
    Comprueba primero si existe un override en $JH_HOME/templates/latex/<template_rel>.
    Si no, usa la plantilla de serie en REPO_ROOT/templates/latex/<template_rel>.
    Lanza FileNotFoundError si no existe en ninguna de las dos ubicaciones.
    """
    rel = Path(template_rel)

    # 1. Override de usuario
    override_path = LATEX_TEMPLATES_OVERRIDE_DIR / rel
    if override_path.exists():
        return override_path

    # 2. Plantilla por defecto del repositorio
    default_path = DEFAULT_LATEX_TEMPLATES_DIR / rel
    if default_path.exists():
        return default_path

    raise FileNotFoundError(
        f"Plantilla LaTeX '{template_rel}' no encontrada. "
        f"Buscado en '{override_path}' y '{default_path}'."
    )


def compile_latex(
    tex_path: str | Path,
    output_dir: str | Path | None = None,
    engine: str | None = None,
    timeout: int = 120,
) -> Path:
    """
    Compila un archivo .tex a .pdf utilizando el compilador detectado o especificado.

    - tex_path: Ruta al archivo .tex fuente.
    - output_dir: Directorio donde dejar el .pdf generado. Por defecto, el mismo que tex_path.
    - engine: Motor específico ('tectonic', 'xelatex', 'lualatex', 'pdflatex').
    - timeout: Límite de tiempo en segundos (por defecto 120s para permitir descarga de paquetes).

    Retorna la ruta (Path) al archivo .pdf generado.
    Lanza LaTeXCompilationError en caso de fallo de compilación o si el PDF no se genera.
    """
    src = Path(tex_path).resolve()
    if not src.is_file():
        raise FileNotFoundError(f"Archivo fuente LaTeX no encontrado: {src}")

    out_dir = Path(output_dir).resolve() if output_dir else src.parent
    out_dir.mkdir(parents=True, exist_ok=True)

    expected_pdf = out_dir / f"{src.stem}.pdf"

    engine_name, compiler_bin = find_latex_compiler(preferred_engine=engine)
    cwd = src.parent

    if engine_name == "tectonic":
        cmd = [
            str(compiler_bin),
            "-o",
            str(out_dir),
            str(src),
        ]
    elif engine_name in ("xelatex", "lualatex", "pdflatex"):
        cmd = [
            str(compiler_bin),
            "-interaction=nonstopmode",
            f"-output-directory={out_dir}",
            str(src),
        ]
    else:
        cmd = [str(compiler_bin), str(src)]

    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise LaTeXCompilationError(
            f"Compilación LaTeX agotó el tiempo límite ({timeout}s): {exc}"
        ) from exc
    except Exception as exc:
        raise LaTeXCompilationError(f"Error ejecutando compilador LaTeX '{compiler_bin}': {exc}") from exc

    if proc.returncode != 0:
        err_msg = proc.stderr.strip() or proc.stdout.strip()
        # Mostrar las últimas 25 líneas para diagnóstico
        tail = "\n".join(err_msg.splitlines()[-25:])
        raise LaTeXCompilationError(
            f"Compilación con {engine_name} falló (código {proc.returncode}):\n{tail}"
        )

    if not expected_pdf.is_file():
        raise LaTeXCompilationError(
            f"El compilador {engine_name} terminó con éxito pero no se generó '{expected_pdf}'."
        )

    return expected_pdf
