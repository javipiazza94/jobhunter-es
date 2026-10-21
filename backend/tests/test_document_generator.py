"""
test_document_generator.py — Pruebas para la generación determinista de CV y
carta de presentación en LaTeX desde profile.json sin IA.
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from automation.document_generator import (  # noqa: E402
    format_date_range,
    generate_deterministic_documents,
    latex_escape,
    prepare_cover_letter_context,
    prepare_cv_context,
    render_cover_letter_latex,
    render_cv_latex,
)
from automation.verify_pdf import verify_pdf  # noqa: E402


class TestLatexEscape(unittest.TestCase):
    def test_escapes_special_characters(self):
        raw = r"100% & C# $5_000 {foo} ^bar ~baz \path"
        escaped = latex_escape(raw)
        self.assertIn(r"\%", escaped)
        self.assertIn(r"\&", escaped)
        self.assertIn(r"\#", escaped)
        self.assertIn(r"\$", escaped)
        self.assertIn(r"\_", escaped)
        self.assertIn(r"\{", escaped)
        self.assertIn(r"\}", escaped)
        self.assertIn(r"\textasciicircum{}", escaped)
        self.assertIn(r"\textasciitilde{}", escaped)
        self.assertIn(r"\textbackslash{}", escaped)

    def test_handles_none_and_empty(self):
        self.assertEqual(latex_escape(None), "")
        self.assertEqual(latex_escape(""), "")

    def test_format_date_range_ascii(self):
        self.assertEqual(format_date_range("2020", "2024"), "2020-2024")
        self.assertEqual(format_date_range("2023", None), "2023-Present")
        self.assertEqual(format_date_range("2022", "2022"), "2022")
        self.assertEqual(format_date_range(None, None), "")


class TestContextAndHonesty(unittest.TestCase):
    def setUp(self):
        self.sample_profile = {
            "personal": {
                "name": "Jane Doe",
                "email": "jane.doe@example.com",
                "phone": "+34 600 111 222",
                "city": "Madrid",
                "country": "España",
                "linkedin": "https://linkedin.com/in/janedoe",
            },
            "summary": {
                "general": "Experienced Software Engineer with a passion for robust systems.",
            },
            "stack": {
                "programming": ["Python", "Rust"],
                "frameworks": ["FastAPI", "Next.js"],
            },
            "experience": [
                {
                    "company": "Tech Corp",
                    "role": "Backend Engineer",
                    "start": "2021",
                    "end": "2024",
                    "bullets": ["Scaled microservices to 10k req/s"],
                }
            ],
            "education": [
                {
                    "title": "BSc Computer Science",
                    "institution": "Universidad Politécnica",
                    "start": "2017",
                    "end": "2021",
                }
            ],
            "languages": [
                {"language": "Español", "level": "Nativo"},
                {"language": "Inglés", "level": "C1"},
            ],
        }

    def test_prepare_cv_context_adheres_to_honesty_rule(self):
        ctx = prepare_cv_context(self.sample_profile)
        self.assertEqual(ctx["personal"]["first_name"], "Jane")
        self.assertEqual(ctx["personal"]["last_name"], "Doe")
        self.assertEqual(len(ctx["competencies"]), 2)
        self.assertEqual(ctx["competencies"][0][0], "Programming Languages")
        self.assertEqual(ctx["competencies"][0][1], "Python, Rust")
        self.assertEqual(ctx["experience"][0]["date_range"], "2021-2024")
        self.assertEqual(ctx["languages_line"], "Español (Nativo), Inglés (C1)")

    def test_render_cv_latex_contains_required_sections(self):
        rendered = render_cv_latex(self.sample_profile)
        self.assertIn(r"\name{Jane}{Doe}", rendered)
        self.assertIn("Programming Languages", rendered)
        self.assertIn("Tech Corp", rendered)
        self.assertIn("Scaled microservices", rendered)

    def test_render_cover_letter_latex(self):
        rendered = render_cover_letter_latex(
            self.sample_profile,
            company_name="Acme Inc",
            role_title="Senior Python Developer",
        )
        self.assertIn("Jane Doe", rendered)
        self.assertIn("Acme Inc", rendered)
        self.assertIn("Senior Python Developer", rendered)


class TestDocumentGenerationIntegration(unittest.TestCase):
    def test_generate_documents_integration(self):
        with open(REPO_ROOT / "backend" / "profile.example.json", encoding="utf-8") as f:
            profile = json.load(f)

        with tempfile.TemporaryDirectory() as tmpdir:
            docs = generate_deterministic_documents(
                profile_data=profile,
                company_name="Test Enterprise",
                role_title="Software Engineer",
                output_dir=tmpdir,
                verify=True,
            )

            cv_pdf = docs["cv_pdf"]
            cover_pdf = docs["cover_pdf"]

            self.assertTrue(cv_pdf.is_file())
            self.assertTrue(cover_pdf.is_file())
            self.assertGreater(cv_pdf.stat().st_size, 1000)
            self.assertGreater(cover_pdf.stat().st_size, 1000)

            # verify_pdf directo con fechas ASCII
            verify_pdf(cv_pdf, ascii_dates=True)
            verify_pdf(cover_pdf, expected_pages=1, ascii_dates=True)


if __name__ == "__main__":
    unittest.main()
