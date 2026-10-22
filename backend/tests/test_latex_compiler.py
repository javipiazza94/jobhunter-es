"""
test_latex_compiler.py — Pruebas para descubrimiento de motor LaTeX, resolución
de plantillas (con override en JH_HOME) y compilación con Tectonic / LaTeX.
"""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from automation.latex_compiler import (  # noqa: E402
    LaTeXCompilationError,
    compile_latex,
    engine_available,
    find_latex_compiler,
    resolve_template_path,
)


NO_ENGINE = engine_available() is None
requires_engine = pytest.mark.skipif(NO_ENGINE, reason="no hay motor LaTeX (tectonic/xelatex) instalado")


class TestCompilerDiscovery(unittest.TestCase):
    @requires_engine
    def test_find_latex_compiler_finds_available_engine(self):
        engine, path = find_latex_compiler()
        self.assertIn(engine, ("tectonic", "xelatex", "lualatex", "pdflatex"))
        self.assertTrue(path.is_file())

    def test_find_latex_compiler_raises_when_none_found(self):
        with patch("shutil.which", return_value=None):
            with patch("os.access", return_value=False):
                with self.assertRaises(LaTeXCompilationError):
                    find_latex_compiler()

    def test_find_latex_compiler_respects_preferred_engine(self):
        with patch("shutil.which", side_effect=lambda cmd: f"/usr/bin/{cmd}" if cmd == "xelatex" else None):
            engine, path = find_latex_compiler(preferred_engine="xelatex")
            self.assertEqual(engine, "xelatex")
            self.assertEqual(path, Path("/usr/bin/xelatex"))


class TestEngineAvailable(unittest.TestCase):
    def test_returns_none_without_engine(self):
        with patch("shutil.which", return_value=None), patch("os.access", return_value=False):
            self.assertIsNone(engine_available())

    def test_returns_engine_name(self):
        with patch(
            "shutil.which", side_effect=lambda cmd: "/usr/bin/xelatex" if cmd == "xelatex" else None
        ), patch("os.access", return_value=False):
            self.assertEqual(engine_available(), "xelatex")


class TestCompilePasses(unittest.TestCase):
    """compile_latex repite la pasada en motores clásicos; Tectonic gestiona sus propias repeticiones."""

    def _run(self, engine: str, passes: int) -> int:
        with tempfile.TemporaryDirectory() as tmpdir:
            tex = Path(tmpdir) / "doc.tex"
            tex.write_text("x")
            calls = []

            def fake_run(cmd, **kwargs):
                calls.append(cmd)
                (Path(tmpdir) / "doc.pdf").write_bytes(b"%PDF")
                return subprocess.CompletedProcess(cmd, 0, "", "")

            with patch(
                "automation.latex_compiler.find_latex_compiler",
                return_value=(engine, Path(f"/usr/bin/{engine}")),
            ), patch("automation.latex_compiler.subprocess.run", side_effect=fake_run):
                compile_latex(tex, passes=passes)
            return len(calls)

    def test_xelatex_runs_two_passes_by_default(self):
        self.assertEqual(self._run("xelatex", 2), 2)

    def test_tectonic_runs_once(self):
        self.assertEqual(self._run("tectonic", 2), 1)

    def test_single_pass_requested(self):
        self.assertEqual(self._run("lualatex", 1), 1)


class TestTemplateResolution(unittest.TestCase):
    def test_resolves_default_templates(self):
        cv_template = resolve_template_path("cv/main_example.tex")
        self.assertTrue(cv_template.is_file())
        self.assertTrue(cv_template.name == "main_example.tex")

        cover_template = resolve_template_path("cover_letters/cover_example.tex")
        self.assertTrue(cover_template.is_file())

        cover_cls = resolve_template_path("cover_letters/cover.cls")
        self.assertTrue(cover_cls.is_file())

    def test_raises_when_template_missing(self):
        with self.assertRaises(FileNotFoundError):
            resolve_template_path("non_existent/template.tex")

    def test_override_takes_precedence(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            fake_override = Path(tmpdir)
            custom_cv = fake_override / "cv" / "main_example.tex"
            custom_cv.parent.mkdir(parents=True)
            custom_cv.write_text("% Custom user CV override")

            with patch("automation.latex_compiler.LATEX_TEMPLATES_OVERRIDE_DIR", fake_override):
                resolved = resolve_template_path("cv/main_example.tex")
                self.assertEqual(resolved, custom_cv)
                self.assertEqual(resolved.read_text(), "% Custom user CV override")


class TestCompilation(unittest.TestCase):
    def test_compile_latex_missing_file_raises(self):
        with self.assertRaises(FileNotFoundError):
            compile_latex("/tmp/definitely_missing_file_xyz.tex")

    @requires_engine
    def test_compile_latex_invalid_syntax_raises(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            broken_tex = Path(tmpdir) / "broken.tex"
            broken_tex.write_text(r"\documentclass{article}\begin{document}\invalidcommand{foo}")
            with self.assertRaises(LaTeXCompilationError):
                compile_latex(broken_tex)

    @requires_engine
    @pytest.mark.integration
    def test_compile_cover_letter_integration(self):
        cover_tex = resolve_template_path("cover_letters/cover_example.tex")
        with tempfile.TemporaryDirectory() as tmpdir:
            out_pdf = compile_latex(cover_tex, output_dir=tmpdir)
            self.assertTrue(out_pdf.is_file())
            self.assertEqual(out_pdf.name, "cover_example.pdf")
            self.assertGreater(out_pdf.stat().st_size, 1000)

    @requires_engine
    @pytest.mark.integration
    def test_compile_cv_integration(self):
        cv_tex = resolve_template_path("cv/main_example.tex")
        with tempfile.TemporaryDirectory() as tmpdir:
            out_pdf = compile_latex(cv_tex, output_dir=tmpdir)
            self.assertTrue(out_pdf.is_file())
            self.assertEqual(out_pdf.name, "main_example.pdf")
            self.assertGreater(out_pdf.stat().st_size, 1000)


if __name__ == "__main__":
    unittest.main()
