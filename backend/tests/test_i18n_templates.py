"""
test_i18n_templates.py — Pruebas de selección de idioma para plantillas, cartas y etiquetas LaTeX.

Conforme a SP4 Task 7:
- Oferta en alemán + plantillas es/en → idioma por defecto (es / profile preference).
- Oferta en inglés → carta en inglés y etiquetas de LaTeX en inglés.
- Añadir un directorio de idioma ficticio (p. ej. 'xx') sin tocar código es descubierto y utilizado.
"""
from datetime import date
from pathlib import Path

import pytest

from automation.cover_letter import available_template_languages, generate, letter_language, template_search_dirs
from automation.document_generator import (
    _format_cover_date,
    load_latex_labels,
    prepare_cover_letter_context,
    prepare_cv_context,
    render_cover_letter_latex,
    render_cv_latex,
)
from automation.followup import draft_followup


def test_letter_language_selection():
    # 1. Oferta en alemán sin plantillas en alemán -> default (es)
    german_offer = {
        "title": "Softwareentwickler Python",
        "description": "Wir suchen einen erfahrenen Entwickler für unser Team in Berlin. Deutschkenntnisse erforderlich.",
        "language": "de",
    }
    assert letter_language(german_offer, {}) == "es"

    # Con preferencia en perfil a inglés:
    profile_en = {"preferences": {"default_language": "en"}}
    assert letter_language(german_offer, profile_en) == "en"

    # 2. Oferta en inglés -> detecta o usa 'en'
    english_offer = {
        "title": "Senior Python Backend Engineer",
        "description": "We are looking for a skilled engineer to join our platform team. You will build APIs.",
        "language": "en",
    }
    assert letter_language(english_offer, {}) == "en"

    # 3. Oferta sin idioma explícito pero en inglés (mínimo 20 palabras para el detector)
    detected_offer = {
        "title": "Senior Cloud Architect",
        "description": (
            "We are seeking an experienced architect with expertise in distributed systems, microservices, "
            "and Kubernetes. You will design and deploy scalable cloud infrastructure for our global platform team."
        ),
    }
    assert letter_language(detected_offer, {}) == "en"


def test_latex_labels_loading():
    labels_es = load_latex_labels("es")
    assert labels_es["sections"]["competencies"] == "Competencias principales"
    assert "Estimado/a" in labels_es["salutation"]
    assert labels_es["closing"] == "Atentamente,"

    labels_en = load_latex_labels("en")
    assert labels_en["sections"]["competencies"] == "Core Competencies"
    assert "Dear Hiring Team" in labels_en["salutation"]
    assert labels_en["closing"] == "Sincerely,"

    # Idioma inexistente -> fallback a 'es'
    labels_fallback = load_latex_labels("unsupported_lang")
    assert labels_fallback["sections"]["competencies"] == "Competencias principales"


def test_cover_letter_english_context_and_latex():
    profile = {
        "personal": {
            "name": "Jane Doe",
            "email": "jane@example.com",
            "phone": "+34 600 000 000",
            "city": "Madrid",
        },
        "experience": [
            {
                "company": "Tech Corp",
                "role": "Software Engineer",
                "bullets": ["Engineered high-throughput event processing pipelines."],
            }
        ],
    }

    ctx_en = prepare_cover_letter_context(
        profile=profile,
        company_name="Acme Global",
        role_title="Backend Lead",
        lang="en",
    )

    assert "Acme Global" in ctx_en["salutation"]
    assert "Dear Hiring Team" in ctx_en["salutation"]
    assert ctx_en["closing"] == "Sincerely,"
    assert "Backend Lead" in ctx_en["opening_paragraph"]
    assert "interest" in ctx_en["opening_paragraph"]
    assert ctx_en["lang"] == "en"

    # Fecha formateada en inglés
    day = date(2026, 10, 23)
    formatted_date = _format_cover_date(day, lang="en", labels=ctx_en["labels"])
    assert formatted_date == "October 23, 2026"

    # Render LaTeX
    tex = render_cover_letter_latex(profile, "Acme Global", "Backend Lead", lang="en")
    assert "Acme Global" in tex
    assert "Dear Hiring Team" in tex
    assert "Sincerely," in tex


def test_cv_english_context_and_latex():
    profile = {
        "personal": {
            "name": "Jane Doe",
            "email": "jane@example.com",
            "phone": "+34 600 000 000",
        },
        "experience": [
            {
                "company": "Tech Corp",
                "role": "Software Engineer",
                "start": "2022-01",
                "end": "present",
                "bullets": ["Led the core platform migration."],
            }
        ],
    }

    ctx_en = prepare_cv_context(profile, lang="en")
    assert ctx_en["labels"]["sections"]["experience"] == "Professional Experience"
    assert ctx_en["experience"][0]["date_range"] == "01/2022 - Present"

    tex = render_cv_latex(profile, lang="en")
    assert "Professional Experience" in tex


def test_draft_followup_english():
    app = {
        "company_name": "Acme Global",
        "job_title": "Senior Engineer",
        "method": "email",
        "sent_at": "2026-10-01",
    }
    profile = {
        "personal": {"name": "Jane Doe", "email": "jane@example.com"},
        "summary": {"general": "Experienced engineer with a focus on scalable systems."},
    }

    draft = draft_followup(app, profile, lang="en")
    assert "Acme Global" in draft
    assert "Senior Engineer" in draft
    assert "follow up" in draft.lower() or "following up" in draft.lower() or "regarding" in draft.lower()
    assert "Jane Doe" in draft


def test_extensibility_custom_language_directory(tmp_path, monkeypatch):
    """Prueba de cierre: añadir un directorio con una plantilla 'xx' sin tocar código es descubierto y utilizado."""
    import config

    custom_templates_dir = tmp_path / "custom_templates"
    xx_dir = custom_templates_dir / "xx"
    xx_dir.mkdir(parents=True)

    # Crear una plantilla en el nuevo idioma 'xx'
    (xx_dir / "cover_letter_base.j2").write_text(
        "Konnichiwa {{ company_name }}. Candidate: {{ candidate_name }}.\n", encoding="utf-8"
    )

    monkeypatch.setattr(config, "TEMPLATES_OVERRIDE_DIR", custom_templates_dir)

    # available_template_languages debe incluir 'xx'
    avail = available_template_languages()
    assert "xx" in avail

    offer_xx = {
        "title": "Developer",
        "company_name": "Tokyo Tech",
        "language": "xx",
    }
    assert letter_language(offer_xx, {}) == "xx"

    dirs = template_search_dirs("xx")
    assert any("xx" in str(d) for d in dirs)
