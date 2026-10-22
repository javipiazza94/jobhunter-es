"""Finish line de SP3: flujo E2E completo de preparación de candidaturas.

De un JH_HOME limpio con perfil configurado por el asistente a:
- Preparación determinista (use_ai=false): CV recortado a 2 páginas y carta de 1 que pasan verify_pdf (páginas contadas en los PDFs).
- Preparación con IA (use_ai=true) con un proveedor simulado: verify_pdf sobre los PDFs archivados de la IA.
- Aprobación y envío con SMTP simulado: los adjuntos son byte a byte los PDFs archivados.
- Comprobación del código 409 cuando no hay motor LaTeX disponible.
"""

from __future__ import annotations

import email
import json
import smtplib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import config  # noqa: E402
import database  # noqa: E402
import profile_store  # noqa: E402
import search_config  # noqa: E402
import setup_builder  # noqa: E402
from ai.base import BaseProvider  # noqa: E402
from automation import application_archive, application_documents, document_generator  # noqa: E402
from automation.latex_compiler import engine_available  # noqa: E402
from automation.verify_pdf import extract_text_layer, verify_pdf  # noqa: E402
from tests.asgi_client import call  # noqa: E402

requires_engine = pytest.mark.skipif(engine_available() is None, reason="no hay motor LaTeX instalado")
CLIENT = ("x-jh-client", "dashboard")

PROFILE_ANSWERS = {
    "draft": {
        "targets": [{"title": "Data Engineer", "keywords": ["python", "spark", "sql"]}],
        "experience": [
            {
                "role": "Senior Data Engineer",
                "company": "Tech Innovators SL",
                "start": "2022-01",
                "end": "Actualidad",
                "bullets": [
                    "Diseño y despliegue de pipelines de datos en tiempo real con Apache Spark y Python.",
                    "Optimización de modelos dimensionales y consultas SQL complejas sobre PostgreSQL.",
                ],
                "skills": ["Python", "Spark", "SQL", "PostgreSQL"],
            },
            {
                "role": "Data Analyst",
                "company": "Analytics Lab",
                "start": "2020-01",
                "end": "2021-12",
                "bullets": [
                    "Creación de paneles y cuadros de mando interactivos.",
                    "Extracción de métricas clave mediante SQL y modelado estadístico.",
                ],
                "skills": ["SQL", "Tableau", "Python"],
            },
        ],
        "tools": ["Python", "Spark", "SQL", "PostgreSQL", "Docker", "Git"],
        "languages": [{"language": "Spanish", "level": "native"}, {"language": "English", "level": "B2"}],
        "education": [
            {
                "title": "Grado en Ingeniería Informática",
                "institution": "Universidad de Villanova",
                "start": "2015",
                "end": "2019",
            }
        ],
        "full_name": "Elena Torres Vega",
        "email": "elena.torres@example.org",
        "phone": "+34 600 123 456",
        "city": "Villanova",
        "province": "Villanova",
        "country": "España",
        "years_experience": 5,
        "modality": ["remote", "hybrid"],
        "eligibility": {"work_permit_countries": ["ES"], "needs_sponsorship": False, "driving_license": True},
    },
    "markets": ["spain"],
    "sources": ["tecnoempleo"],
    "acknowledged_sources": [],
    "followed_companies": [],
}


# Empleos inventados de más para que el CV sin recortar no quepa en 2 páginas: así el e2e comprueba que el
# recorte (y la petición de acortar a la IA) deja el CV en exactamente 2 páginas.
EXTRA_JOBS = [
    {
        "role": f"Data Engineer {n}",
        "company": f"Empresa Ficticia {n} SL",
        "start": f"{2019 - 2 * n}-01",
        "end": f"{2020 - 2 * n}-12",
        "bullets": [
            f"Proyecto {n}.{b}: migración de procesos ETL heredados a pipelines de Python con pruebas automáticas, "
            "documentación técnica y revisión de código entre pares para todo el equipo de datos."
            for b in range(1, 7)
        ],
    }
    for n in range(1, 10)
]


def _enrich_profile() -> None:
    profile = profile_store.load_profile()
    profile["experience"] = list(profile.get("experience") or []) + EXTRA_JOBS
    profile_store.save_profile(profile)


def _pdf_pages(path: Path) -> int:
    return extract_text_layer(path)[1]


def _attachments(raw: str) -> dict[str, bytes]:
    """Adjuntos del mensaje enviado: {nombre: bytes decodificados}."""
    msg = email.message_from_string(raw)
    return {part.get_filename(): part.get_payload(decode=True) for part in msg.walk() if part.get_filename()}


class FakeScriptedAI(BaseProvider):
    """IA guionizada: el redactor devuelve TODOS los empleos del perfil (con sus viñetas literales), así que
    el CV de la IA tampoco cabe sin acortar/recortar; el revisor da el visto bueno."""

    name = "fake_scripted"

    def _complete(self, prompt: str, system: str | None = None, json_mode: bool = False) -> str:
        if "responsable de selección" in prompt or "verdict" in prompt:
            return json.dumps({"verdict": "ok", "issues": [], "missing_keywords": [], "unsupported_claims": []})
        if "analista que resume empresas" in (system or "") or (
            "resumen" in prompt.lower() and "cv" not in prompt.lower() and "redacta" not in prompt.lower()
        ):
            return json.dumps({
                "summary": "InnovaTech es una empresa tecnológica líder en ingeniería de datos y software.",
                "products": ["Data Platform"],
                "culture_signals": ["Innovación"],
                "tech_stack": ["Python", "Spark", "PostgreSQL"],
                "size_hint": "50-100 empleados",
            })
        return json.dumps({
            "cv": {
                "summary_text": "Data Engineer especializada en streaming y procesamiento masivo con Spark y Python.",
                "competencies": [
                    ["Herramientas", "Python, Spark, SQL, PostgreSQL"],
                ],
                "experience": [
                    {"company": e["company"], "role": e["role"], "date_range": e["date_range"], "bullets": e["bullets"]}
                    for e in document_generator.prepare_cv_context(profile_store.load_profile())["experience"]
                ],
                "education": [
                    {
                        "title": "Grado en Ingeniería Informática",
                        "institution": "Universidad de Villanova",
                    }
                ],
                "certifications": [],
            },
            "letter": {
                "opening_paragraph": "Me complace presentar mi candidatura como Data Engineer en InnovaTech.",
                "body_paragraph": "Cuento con experiencia directa en pipelines con Spark y modelado en SQL.",
                "bullets": [
                    "Diseño y despliegue de pipelines de datos en tiempo real con Apache Spark y Python.",
                    "Optimización de modelos dimensionales y consultas SQL complejas sobre PostgreSQL.",
                ],
                "connection_paragraph": "Valoro enormemente el enfoque de ingeniería de datos y calidad de InnovaTech.",
                "closing_paragraph": "Quedo a su disposición para comentar mi perfil en una entrevista.",
            },
        })

    def check(self) -> tuple[bool, str]:
        return True, "Fake AI disponible"


class FakeSMTP:
    sent_messages: list[str] = []

    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def ehlo(self):
        pass

    def starttls(self, *a, **kw):
        pass

    def login(self, user, password):
        pass

    def sendmail(self, from_addr, to_addrs, msg):
        FakeSMTP.sent_messages.append(msg)


@pytest.fixture
def clean_jh_home(tmp_path, monkeypatch):
    """Inicializa un entorno limpio de JH_HOME con perfil y BD listos."""
    home_dir = tmp_path / "jh_home"
    home_dir.mkdir(parents=True)
    monkeypatch.setattr(config, "JH_HOME", home_dir)
    monkeypatch.setattr(config, "DB_PATH", home_dir / "job_hunter.db")
    monkeypatch.setattr(config, "PROFILE_PATH", home_dir / "profile.json")
    monkeypatch.setattr(config, "APPLICATIONS_DIR", home_dir / "applications")
    monkeypatch.setattr(database, "DB_PATH", home_dir / "job_hunter.db")
    monkeypatch.setattr(application_archive, "APPLICATIONS_DIR", home_dir / "applications")

    saved_cfg = (search_config._cache, search_config._pinned, search_config._loaded_from)

    # Inicializar base de datos
    conn = database.get_conn()
    database.init_db(conn)

    # Configuración de usuario desde el asistente (+ empleos de más para forzar el recorte a 2 páginas)
    setup_builder.apply_setup(setup_builder.SetupAnswers.model_validate(PROFILE_ANSWERS))
    _enrich_profile()

    # Crear oferta y candidatura
    conn.execute("INSERT INTO companies (id, name, source, created_at) VALUES ('comp_1', 'InnovaTech', 'test', '2026-10-01')")
    conn.execute(
        """INSERT INTO job_offers (id, company_id, title, description, location, tech_stack, url, scraped_at)
           VALUES ('offer_1', 'comp_1', 'Senior Data Engineer',
                   'Buscamos Senior Data Engineer con sólida experiencia en Python, Apache Spark y SQL.',
                   'Villanova', 'Python, Spark, SQL', 'https://innovatech.example.com/jobs/1', '2026-10-01')"""
    )
    conn.execute(
        """INSERT INTO contacts (id, company_id, type, value, created_at)
           VALUES ('contact_1', 'comp_1', 'email', 'jobs@innovatech.example.com', '2026-10-01')"""
    )
    app_id = database.record_application(conn, {
        "company_id": "comp_1",
        "job_offer_id": "offer_1",
        "contact_id": "contact_1",
        "method": "email",
        "status": "pending_approval",
        "cover_letter_used": "Carta inicial de borrador.",
    })
    conn.commit()
    conn.close()

    try:
        yield {"home": home_dir, "app_id": app_id}
    finally:
        search_config._cache, search_config._pinned, search_config._loaded_from = saved_cfg


def test_prepare_sin_motor_devuelve_409_siempre(clean_jh_home, monkeypatch):
    """Sin motor LaTeX disponible, /prepare siempre responde con 409 y mensaje claro."""
    monkeypatch.setattr(application_documents, "engine_available", lambda *a, **k: None)
    app_id = clean_jh_home["app_id"]

    status, _, body = call("POST", f"/api/applications/{app_id}/prepare", headers=[CLIENT])
    assert status == 409
    assert "Instala Tectonic" in json.loads(body)["detail"]


@requires_engine
def test_e2e_preparar_candidatura_determinista_y_con_ia_y_aprobar(clean_jh_home, monkeypatch):
    """Flujo completo con compilación real de PDFs (Tectonic / LaTeX):
    1. Preparar sin IA -> CV de exactamente 2 páginas (recortado) y carta de 1 que pasan verify_pdf.
    2. Preparar con IA simulada -> mismas páginas y verify_pdf sobre los PDFs archivados de la IA.
    3. Aprobar -> el email SMTP simulado adjunta byte a byte los PDFs del archivo.
    Las páginas se cuentan en los propios PDFs, no en lo que dice la respuesta.
    """
    app_id = clean_jh_home["app_id"]
    apps_dir = clean_jh_home["home"] / "applications" / app_id
    required = ("elena.torres@example.org", "+34 600 123 456")
    limits = search_config.get_config().documents
    assert (limits.cv_pages, limits.letter_pages) == (2, 1)

    # 1. Preparar determinista (use_ai=false)
    status, _, body = call(
        "POST",
        f"/api/applications/{app_id}/prepare",
        headers=[CLIENT, ("content-type", "application/json")],
        body=json.dumps({"use_ai": False}).encode(),
    )
    assert status == 200, f"Error en /prepare determinista: {body}"
    res = json.loads(body)
    assert res["source"] == "deterministic"
    cv_pdf, cover_pdf = Path(res["cv_pdf"]), Path(res["cover_pdf"])
    assert cv_pdf == apps_dir / "cv.pdf" and cover_pdf == apps_dir / "cover.pdf"
    assert _pdf_pages(cv_pdf) == 2 and _pdf_pages(cover_pdf) == 1
    assert res["verification"]["pages"] == {"cv": 2, "cover": 1}
    assert res["verification"]["trimmed"], "el perfil largo debe obligar a recortar"
    verify_pdf(cv_pdf, expected_pages=2, min_chars=50, required_text=required, ascii_dates=True)
    verify_pdf(cover_pdf, expected_pages=1, min_chars=50, required_text=required, ascii_dates=True)

    # 2. Preparar con IA
    fake_ai = FakeScriptedAI()
    monkeypatch.setattr("ai.get_provider", lambda: fake_ai)
    monkeypatch.setattr("automation.application_documents.get_provider", lambda: fake_ai)

    status_ai, _, body_ai = call(
        "POST",
        f"/api/applications/{app_id}/prepare",
        headers=[CLIENT, ("content-type", "application/json")],
        body=json.dumps({"use_ai": True}).encode(),
    )
    assert status_ai == 200, f"Error en /prepare con IA: {body_ai}"
    res_ai = json.loads(body_ai)
    assert res_ai["source"] == "ai", res_ai["warnings"]
    ai_cv, ai_cover = apps_dir / "cv.pdf", apps_dir / "cover.pdf"
    assert _pdf_pages(ai_cv) == 2 and _pdf_pages(ai_cover) == 1
    assert res_ai["verification"]["pages"] == {"cv": 2, "cover": 1}
    _, ai_cv_text, _ = verify_pdf(ai_cv, expected_pages=2, min_chars=50, required_text=required, ascii_dates=True)
    _, ai_cover_text, _ = verify_pdf(ai_cover, expected_pages=1, min_chars=50, required_text=required, ascii_dates=True)
    # Es la versión de la IA (su resumen y su carta), no la determinista; sin espacios por el kerning del PDF
    assert "especializadaenstreaming" in "".join(ai_cv_text.split())
    assert "Valoroenormementeelenfoque" in "".join(ai_cover_text.split())
    assert json.loads((apps_dir / "metadata.json").read_text(encoding="utf-8"))["source"] == "ai"
    assert (apps_dir / "job_posting.md").is_file()

    # 3. Aprobar y enviar con FakeSMTP
    FakeSMTP.sent_messages = []
    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
    monkeypatch.setenv("GMAIL_USER", "elena.torres@example.org")
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "fake-app-pwd-for-test")
    monkeypatch.setattr("secrets_store.keyring", None)

    status_app, _, body_app = call("POST", f"/api/applications/{app_id}/approve", headers=[CLIENT])
    assert status_app == 200, f"Error en /approve: {body_app}"
    assert json.loads(body_app)["success"] is True

    # El mensaje enviado adjunta exactamente los PDFs archivados de la IA
    assert len(FakeSMTP.sent_messages) == 1
    sent_raw = FakeSMTP.sent_messages[0]
    assert "jobs@innovatech.example.com" in sent_raw
    attached = _attachments(sent_raw)
    assert set(attached) == {"cv.pdf", "cover.pdf"}
    assert attached["cv.pdf"] == ai_cv.read_bytes()
    assert attached["cover.pdf"] == ai_cover.read_bytes()

    # Comprobar estado en la base de datos
    conn = database.get_conn()
    row = conn.execute("SELECT status FROM applications WHERE id = ?", (app_id,)).fetchone()
    conn.close()
    assert row[0] == "sent"
