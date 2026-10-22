"""Finish line de SP3: flujo E2E completo de preparación de candidaturas.

De un JH_HOME limpio con perfil configurado por el asistente a:
- Preparación determinista (use_ai=false) generando CV (<= 2 páginas) y carta (1 página) que pasan verify_pdf.
- Preparación con IA (use_ai=true) con un proveedor simulado.
- Aprobación y envío con SMTP simulado, comprobando que ambos PDFs archivados se adjuntan.
- Comprobación del código 409 cuando no hay motor LaTeX disponible.
"""

from __future__ import annotations

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
from automation import application_archive, application_documents  # noqa: E402
from automation.latex_compiler import engine_available  # noqa: E402
from automation.verify_pdf import verify_pdf  # noqa: E402
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


class FakeScriptedAI(BaseProvider):
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
                    {
                        "company": "Tech Innovators SL",
                        "role": "Senior Data Engineer",
                        "date_range": "01/2022 - Actualidad",
                        "bullets": [
                            "Diseño y despliegue de pipelines de datos en tiempo real con Apache Spark y Python.",
                            "Optimización de modelos dimensionales y consultas SQL complejas sobre PostgreSQL.",
                        ],
                    }
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

    # Configuración de usuario desde el asistente
    setup_builder.apply_setup(setup_builder.SetupAnswers.model_validate(PROFILE_ANSWERS))

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
    1. Preparar sin IA -> genera CV (<= 2 páginas) y carta (1 página) conformes con verify_pdf.
    2. Preparar con IA simulada -> genera y archiva versiones adaptadas.
    3. Aprobar candidatura -> email SMTP simulado incluye ambos PDFs adjuntos del archivo.
    """
    app_id = clean_jh_home["app_id"]
    apps_dir = clean_jh_home["home"] / "applications" / app_id

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
    assert res["verification"]["pages"]["cv"] <= 2
    assert res["verification"]["pages"]["cover"] == 1

    cv_pdf = Path(res["cv_pdf"])
    cover_pdf = Path(res["cover_pdf"])
    assert cv_pdf.is_file() and cover_pdf.is_file()

    # Comprobar verify_pdf en ambos documentos
    verify_pdf(cv_pdf, expected_pages=res["verification"]["pages"]["cv"], required_text=("elena.torres@example.org", "+34 600 123 456"))
    verify_pdf(cover_pdf, expected_pages=1, required_text=("elena.torres@example.org", "+34 600 123 456"))

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
    assert res_ai["source"] == "ai"
    assert res_ai["verification"]["pages"]["cv"] <= 2
    assert res_ai["verification"]["pages"]["cover"] == 1

    # Verificar que el archivo conserva la versión más reciente
    assert (apps_dir / "cv.pdf").is_file()
    assert (apps_dir / "cover.pdf").is_file()
    assert (apps_dir / "job_posting.md").is_file()
    assert (apps_dir / "metadata.json").is_file()

    # 3. Aprobar y enviar con FakeSMTP
    FakeSMTP.sent_messages = []
    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
    monkeypatch.setenv("GMAIL_USER", "elena.torres@example.org")
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "fake-app-pwd-for-test")
    monkeypatch.setattr("secrets_store.keyring", None)

    status_app, _, body_app = call("POST", f"/api/applications/{app_id}/approve", headers=[CLIENT])
    assert status_app == 200, f"Error en /approve: {body_app}"
    assert json.loads(body_app)["success"] is True

    # Comprobar el mensaje enviado
    assert len(FakeSMTP.sent_messages) == 1
    sent_raw = FakeSMTP.sent_messages[0]
    assert "jobs@innovatech.example.com" in sent_raw
    assert "filename=cv.pdf" in sent_raw
    assert "filename=cover.pdf" in sent_raw

    # Comprobar estado en la base de datos
    conn = database.get_conn()
    row = conn.execute("SELECT status FROM applications WHERE id = ?", (app_id,)).fetchone()
    conn.close()
    assert row[0] == "sent"
