"""
test_latex_compiler.py — Pruebas para descubrimiento de motor LaTeX, resolución
de plantillas (con override en JH_HOME) y compilación con Tectonic / LaTeX.
"""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from automation.latex_compiler import (  # noqa: E402
    LaTeXCompilationError,
    compile_latex,
    find_latex_compiler,
    resolve_template_path,
)


class TestCompilerDiscovery(unittest.TestCase):
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

    def test_compile_latex_invalid_syntax_raises(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            broken_tex = Path(tmpdir) / "broken.tex"
            broken_tex.write_text(r"\documentclass{article}\begin{document}\invalidcommand{foo}")
            with self.assertRaises(LaTeXCompilationError):
                compile_latex(broken_tex)

    def test_compile_cover_letter_integration(self):
        cover_tex = resolve_template_path("cover_letters/cover_example.tex")
        with tempfile.TemporaryDirectory() as tmpdir:
            out_pdf = compile_latex(cover_tex, output_dir=tmpdir)
            self.assertTrue(out_pdf.is_file())
            self.assertEqual(out_pdf.name, "cover_example.pdf")
            self.assertGreater(out_pdf.stat().st_size, 1000)

    def test_compile_cv_integration(self):
        cv_tex = resolve_template_path("cv/main_example.tex")
        with tempfile.TemporaryDirectory() as tmpdir:
            out_pdf = compile_latex(cv_tex, output_dir=tmpdir)
            self.assertTrue(out_pdf.is_file())
            self.assertEqual(out_pdf.name, "main_example.pdf")
            self.assertGreater(out_pdf.stat().st_size, 1000)


if __name__ == "__main__":
    unittest.main()
