"""
test_document_generator.py — Pruebas para la generación determinista de CV y
carta de presentación en LaTeX desde profile.json sin IA.
"""

import copy
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "backend"))

import config  # noqa: E402
from automation.document_generator import (  # noqa: E402
    apply_trim,
    format_date_range,
    generate_deterministic_documents,
    latex_escape,
    latex_url,
    plan_trim_operations,
    prepare_cover_letter_context,
    prepare_cv_context,
    render_cover_letter_latex,
    render_cv_latex,
)
from automation.latex_compiler import engine_available  # noqa: E402
from automation.verify_pdf import (  # noqa: E402
    VerificationError,
    extract_text_layer,
    find_non_ascii_date_ranges,
    verify_pdf,
)

requires_engine = pytest.mark.skipif(engine_available() is None, reason="no hay motor LaTeX instalado")
requires_poppler = pytest.mark.skipif(shutil.which("pdftotext") is None, reason="Poppler no instalado")

SPECIAL = r"I+D & ventas 100% C# $5_000 {llaves} ~aprox ^sup \barra"


def _sample_profile() -> dict:
    """Perfil inventado mínimo y completo (email y teléfono)."""
    return {
        "personal": {
            "name": "Lucía Ferrán Ortega",
            "email": "lucia.ferran@example.com",
            "phone": "+34 600 123 456",
            "city": "Valencia",
            "country": "España",
        },
        "summary": {"general": "Ingeniera de datos con experiencia en Python y SQL."},
        "stack": {"programming": ["Python", "SQL"]},
        "experience": [
            {
                "company": "Datos Levante SL",
                "role": "Data Engineer",
                "start": "2021",
                "end": "2024",
                "bullets": ["Pipelines ETL en Python", "Informes en Excel"],
            }
        ],
        "education": [{"title": "Grado en Informática", "institution": "Universidad Inventada", "start": "2016", "end": "2020"}],
        "languages": [{"language": "Español", "level": "Nativo"}],
    }


def _long_profile() -> dict:
    """Perfil sintético largo: 6 empleos x 6 viñetas, ocupa más de 2 páginas."""
    profile = _sample_profile()
    topics = ["Python", "Kubernetes", "SQL", "Excel", "Spark", "Airflow"]
    profile["experience"] = [
        {
            "company": f"Empresa Ficticia {i}",
            "role": f"Ingeniero de datos {i}",
            "start": str(2024 - 2 * i),
            "end": str(2025 - 2 * i),
            "bullets": [
                f"Responsable de {topic} en el proyecto {i}-{j}: diseño, implantación, pruebas, "
                "documentación y soporte a usuarios internos de varios departamentos de la empresa."
                for j, topic in enumerate(topics)
            ],
        }
        for i in range(6)
    ]
    return profile


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

    def test_escapes_every_special_character_individually(self):
        cases = {
            "&": r"\&", "%": r"\%", "_": r"\_", "#": r"\#", "$": r"\$",
            "{": r"\{", "}": r"\}", "~": r"\textasciitilde{}", "^": r"\textasciicircum{}",
            "\\": r"\textbackslash{}",
        }
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(latex_escape(f"a{raw}b"), f"a{expected}b")

    def test_strips_emoji(self):
        escaped = latex_escape("Lanzamiento 🚀 completado ✅ con éxito 👍🏽 ❤️ 🇪🇸")
        for ch in "🚀✅👍🏽❤️🇪🇸":
            self.assertNotIn(ch, escaped)
        self.assertIn("Lanzamiento", escaped)
        self.assertIn("éxito", escaped)  # los acentos se conservan

    def test_latex_url_cannot_break_out(self):
        url = latex_url("https://example.com/in/a_b?x=1&y=2%20z#frag}\\input{x}")
        self.assertNotIn("}", url.replace(r"\}", ""))
        self.assertNotIn("\\input", url)
        self.assertIn(r"\%", url)
        self.assertIn(r"\#", url)

    def test_handles_none_and_empty(self):
        self.assertEqual(latex_escape(None), "")
        self.assertEqual(latex_escape(""), "")

    def test_format_date_range_ascii(self):
        self.assertEqual(format_date_range("2020", "2024"), "2020 - 2024")
        self.assertEqual(format_date_range("2023-01", "2024-03"), "01/2023 - 03/2024")
        self.assertEqual(format_date_range("2023-1-15", "03/2024"), "01/2023 - 03/2024")
        self.assertEqual(format_date_range("2022", "2022"), "2022")
        self.assertEqual(format_date_range(None, None), "")

    def test_open_end_follows_template_language(self):
        self.assertEqual(format_date_range("2023-01", None), "01/2023 - Actualidad")  # es por defecto
        self.assertEqual(format_date_range("2023-01", "Present"), "01/2023 - Actualidad")
        self.assertEqual(format_date_range("2023-01", "", lang="en"), "01/2023 - Present")
        self.assertEqual(format_date_range("2023-01", "actualidad", lang="en"), "01/2023 - Present")

    def test_date_ranges_are_ascii(self):
        for rng in (format_date_range("2023-01", None), format_date_range("2019-05", "2021-12", lang="en")):
            self.assertTrue(rng.isascii(), rng)
            self.assertEqual(find_non_ascii_date_ranges(rng), [])

    def test_strips_control_and_bidi_characters(self):
        self.assertEqual(latex_escape("a\x00b\x07c\u202ed\ufeffe\x7f\u2028f"), "abcdef")
        self.assertEqual(latex_escape("con\ttab"), "con\ttab")  # el tabulador se conserva

    def test_collapses_newlines(self):
        self.assertEqual(latex_escape("línea uno\n\n  línea dos\r\n tres"), "línea uno línea dos tres")


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
        self.assertEqual(ctx["experience"][0]["date_range"], "2021 - 2024")
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


class TestCoverLetterTemplate(unittest.TestCase):
    def test_linkedin_conditional_is_real_jinja(self):
        profile = _sample_profile()
        profile["personal"]["linkedin"] = "https://linkedin.com/in/lucia-inventada"
        rendered = render_cover_letter_latex(profile, company_name="Acme", role_title="Dev")
        self.assertNotIn("(* if", rendered)
        self.assertIn("LinkedIn", rendered)
        profile["personal"].pop("linkedin")
        self.assertNotIn("LinkedIn", render_cover_letter_latex(profile, company_name="Acme", role_title="Dev"))

    def test_date_in_spanish(self):
        ctx = prepare_cover_letter_context(_sample_profile(), company_name="Acme", role_title="Dev")
        months = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
                  "septiembre", "octubre", "noviembre", "diciembre"]
        self.assertTrue(any(f" de {m} de " in ctx["current_date"] for m in months), ctx["current_date"])


class TestCoverLetterPlaceholders(unittest.TestCase):
    def test_user_text_with_braces_is_literal(self):
        profile = _sample_profile()
        profile["cover_letter_intro"] = "Hola {x} en {company_name} como {role_title} {company_name.__class__}"
        profile["cover_letter_stack"] = "Stack {0} {}"
        profile["cover_letter_closing"] = "Gracias, {company_name}."
        ctx = prepare_cover_letter_context(profile, company_name="Acme", role_title="Dev")
        self.assertEqual(ctx["opening_paragraph"], "Hola {x} en Acme como Dev {company_name.__class__}")
        self.assertEqual(ctx["body_paragraph"], "Stack {0} {}")
        self.assertEqual(ctx["closing_paragraph"], "Gracias, Acme.")
        self.assertNotIn("class 'str'", ctx["opening_paragraph"])


class TestTrimKeepsRecentAndRelevant(unittest.TestCase):
    def test_most_recent_and_most_relevant_are_never_dropped(self):
        profile = _sample_profile()
        profile["experience"] = [
            {"company": "Reciente", "role": "Camarero", "start": "2024", "end": "", "bullets": ["Servir mesas"]},
            {"company": "Relevante", "role": "Data Engineer", "start": "2020", "end": "2023", "bullets": ["Python y Spark"]},
            {"company": "Vieja", "role": "Becario", "start": "2018", "end": "2019", "bullets": ["Fotocopias"]},
        ]
        ops = plan_trim_operations(profile, ["Python", "Spark"])
        self.assertEqual([op for op in ops if op[0] == "entry"], [("entry", 2)])
        trimmed = apply_trim(profile, ops)
        self.assertEqual([e["company"] for e in trimmed["experience"]], ["Reciente", "Relevante"])

    def test_latest_by_date_even_if_not_first(self):
        profile = _sample_profile()
        profile["experience"] = [
            {"company": "A", "role": "Dev", "start": "2015-01", "end": "2017-06", "bullets": ["Python"]},
            {"company": "B", "role": "Dev", "start": "2018-01", "end": "2019-01", "bullets": ["Java"]},
            {"company": "C", "role": "Dev", "start": "2021-03", "end": "Present", "bullets": ["Go"]},
        ]
        entry_ops = [op for op in plan_trim_operations(profile, ["Python"]) if op[0] == "entry"]
        self.assertNotIn(("entry", 2), entry_ops)  # C: la más reciente (fin abierto)
        self.assertNotIn(("entry", 0), entry_ops)  # A: la más relevante
        self.assertEqual(entry_ops, [("entry", 1)])

    def test_without_dates_first_entry_is_most_recent(self):
        profile = _sample_profile()
        profile["experience"] = [
            {"company": "A", "role": "x", "bullets": ["nada"]},
            {"company": "B", "role": "y", "bullets": ["Python"]},
            {"company": "C", "role": "z", "bullets": ["nada"]},
        ]
        entry_ops = [op for op in plan_trim_operations(profile, ["Python"]) if op[0] == "entry"]
        self.assertEqual(entry_ops, [("entry", 2)])


class TestTrimPlan(unittest.TestCase):
    """El recorte quita primero lo menos relevante para la oferta (solapamiento de palabras clave)."""

    def setUp(self):
        self.profile = _sample_profile()
        self.profile["experience"] = [
            {"company": "A", "role": "Data Engineer", "bullets": ["Python y Spark", "Excel", "Atención al cliente"]},
            {"company": "B", "role": "Camarero", "bullets": ["Servir mesas", "Python básico"]},
        ]

    def test_bullets_before_entries_least_relevant_first(self):
        ops = plan_trim_operations(self.profile, ["Python", "Spark"])
        bullet_ops = [op for op in ops if op[0] == "bullet"]
        entry_ops = [op for op in ops if op[0] == "entry"]
        self.assertEqual(ops[: len(bullet_ops)], bullet_ops)  # todas las viñetas antes que empleos
        # Nunca se quita la primera viñeta de un empleo en la fase de viñetas
        self.assertNotIn(("bullet", 0, 0), ops)
        self.assertNotIn(("bullet", 1, 0), ops)
        # Puntuación 0 primero; empate: el empleo más antiguo y la última viñeta antes
        self.assertEqual(bullet_ops[0], ("bullet", 0, 2))
        self.assertEqual(bullet_ops[-1], ("bullet", 1, 1))  # "Python básico" (relevante) va al final
        # Se conserva al menos un empleo: el más relevante (A)
        self.assertEqual(entry_ops, [("entry", 1)])

    def test_apply_trim_does_not_mutate_and_keeps_honesty(self):
        original = copy.deepcopy(self.profile)
        ops = plan_trim_operations(self.profile, ["Python"])
        trimmed = apply_trim(self.profile, ops)
        self.assertEqual(self.profile, original)
        self.assertEqual(len(trimmed["experience"]), 1)
        self.assertEqual(trimmed["experience"][0]["company"], "A")
        self.assertEqual(trimmed["experience"][0]["bullets"], ["Python y Spark"])
        # Nada inventado: todo lo que queda estaba en el perfil
        for exp in trimmed["experience"]:
            src = next(e for e in original["experience"] if e["company"] == exp["company"])
            self.assertTrue(set(exp["bullets"]) <= set(src["bullets"]))

    def test_description_only_entries_trim_as_bullets(self):
        self.profile["experience"].append({"company": "C", "role": "Becario", "description": "Tareas varias"})
        trimmed = apply_trim(self.profile, [("entry", 2)])
        self.assertEqual([e["company"] for e in trimmed["experience"]], ["A", "B"])


class TestGenerationContract(unittest.TestCase):
    """Contrato sin motor LaTeX: compilación y conteo de páginas simulados."""

    def _fake_compile(self, tex_path, output_dir=None, **kwargs):
        pdf = Path(output_dir) / (Path(tex_path).stem + ".pdf")
        pdf.write_bytes(b"%PDF-fake")
        return pdf

    def test_missing_phone_fails_verification(self):
        profile = _sample_profile()
        profile["personal"].pop("phone")
        with tempfile.TemporaryDirectory() as tmpdir, patch(
            "automation.document_generator.compile_latex", side_effect=self._fake_compile
        ):
            with self.assertRaisesRegex(VerificationError, "tel"):
                generate_deterministic_documents(profile_data=profile, output_dir=tmpdir)

    def test_default_output_dir_is_applications_preview(self):
        with tempfile.TemporaryDirectory() as tmpdir, patch.object(
            config, "APPLICATIONS_DIR", Path(tmpdir) / "applications"
        ), patch("automation.document_generator.compile_latex", side_effect=self._fake_compile), patch(
            "automation.document_generator._page_count", return_value=1
        ):
            docs = generate_deterministic_documents(profile_data=_sample_profile(), verify=False)
            self.assertEqual(docs["cv_pdf"].parent, (Path(tmpdir) / "applications" / "_preview").resolve())
            self.assertFalse(str(docs["cv_pdf"]).startswith(str(REPO_ROOT / "data")))

    def test_trimming_fits_with_few_compiles(self):
        profile = _long_profile()  # 36 viñetas + idiomas = 37 \\item {
        compiled = []

        def counting_compile(tex_path, output_dir=None, **kwargs):
            compiled.append(Path(tex_path).stem)
            return self._fake_compile(tex_path, output_dir=output_dir)

        def fake_pages(pdf):
            # Simula 1 página por cada 12 «\\item {» (viñetas + línea de idiomas)
            text = Path(pdf).with_suffix(".tex").read_text(encoding="utf-8")
            return -(-text.count("\\item {") // 12) if Path(pdf).stem == "cv" else 1

        with tempfile.TemporaryDirectory() as tmpdir, patch(
            "automation.document_generator.compile_latex", side_effect=counting_compile
        ), patch("automation.document_generator._page_count", side_effect=fake_pages):
            docs = generate_deterministic_documents(profile_data=profile, output_dir=tmpdir, verify=False)
            items = docs["cv_tex"].read_text(encoding="utf-8").count("\\item {")
            pdf_matches_tex = docs["cv_pdf"].read_bytes() == b"%PDF-fake"
        self.assertLessEqual(compiled.count("cv"), 5)
        self.assertEqual(compiled.count("cover"), 1)
        self.assertLessEqual(items, 24)  # cabe en 2 páginas
        self.assertGreaterEqual(items, 24 - 6)  # recorte grueso, pero sin pasarse mucho
        self.assertEqual(docs["verification"]["pages"]["cv"], 2)
        self.assertTrue(pdf_matches_tex)
        # El .tex que queda es el del mejor intento (no el último compilado)
        self.assertEqual(-(-items // 12), 2)

    def test_untrimmable_cv_raises(self):
        with tempfile.TemporaryDirectory() as tmpdir, patch(
            "automation.document_generator.compile_latex", side_effect=self._fake_compile
        ), patch("automation.document_generator._page_count", return_value=3):
            with self.assertRaisesRegex(VerificationError, "2"):
                generate_deterministic_documents(profile_data=_sample_profile(), output_dir=tmpdir, verify=False)


@requires_engine
@pytest.mark.integration
class TestDocumentGenerationIntegration(unittest.TestCase):
    def test_special_characters_compile_without_injection(self):
        profile = _sample_profile()
        profile["summary"]["general"] = SPECIAL + " 🚀 listo"
        profile["experience"][0]["bullets"] = [SPECIAL, "Ahorro del 30% en costes & plazos ✅"]
        profile["personal"]["linkedin"] = "https://linkedin.com/in/lucia_inventada?x=1&y=2%20#a"
        with tempfile.TemporaryDirectory() as tmpdir:
            docs = generate_deterministic_documents(
                profile_data=profile, company_name="Ñandú & Cía", role_title="Dev C#", output_dir=tmpdir
            )
            text, _, _ = extract_text_layer(docs["cv_pdf"])
            for literal in ("I+D & ventas 100% C#", "$5_000", "{llaves}", "30% en costes & plazos"):
                self.assertIn(literal, " ".join(text.split()))
            cover_text, _, _ = extract_text_layer(docs["cover_pdf"])
            self.assertIn("Ñandú & Cía", " ".join(cover_text.split()))

    def test_long_profile_trimmed_to_two_pages(self):
        import automation.document_generator as dg

        with tempfile.TemporaryDirectory() as tmpdir, patch.object(
            dg, "compile_latex", wraps=dg.compile_latex
        ) as spy:
            docs = generate_deterministic_documents(
                profile_data=_long_profile(),
                company_name="Acme",
                role_title="Data Engineer",
                output_dir=tmpdir,
                offer_keywords=["Python", "Spark"],
            )
            _, pages, _ = extract_text_layer(docs["cv_pdf"])
            self.assertLessEqual(spy.call_count, 6)  # <= 5 del CV + 1 de la carta
            self.assertLessEqual(pages, 2)
            self.assertEqual(docs["verification"]["pages"]["cv"], pages)
            self.assertTrue(docs["verification"]["trimmed"])
            # Lo relevante sobrevive antes que lo irrelevante
            cv_tex = docs["cv_tex"].read_text(encoding="utf-8")
            self.assertGreaterEqual(cv_tex.count("Responsable de Python"), cv_tex.count("Responsable de Excel"))

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
                offer_keywords=["Python", "Kubernetes"],
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

            verification = docs["verification"]
            self.assertLessEqual(verification["pages"]["cv"], 2)
            self.assertEqual(verification["pages"]["cover"], 1)
            self.assertIn("Kubernetes", verification["missing_keywords"])
            if shutil.which("pdftotext"):
                self.assertIsInstance(verification["layout"], dict)
            else:
                self.assertEqual(verification["layout"], "skipped: poppler no instalado")

    def test_layout_skipped_without_poppler(self):
        with tempfile.TemporaryDirectory() as tmpdir, patch(
            "automation.document_generator.find_pdftotext", return_value=None
        ):
            docs = generate_deterministic_documents(profile_data=_sample_profile(), output_dir=tmpdir)
            self.assertEqual(docs["verification"]["layout"], "skipped: poppler no instalado")


if __name__ == "__main__":
    unittest.main()
