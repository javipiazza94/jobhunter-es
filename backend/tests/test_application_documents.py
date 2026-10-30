"""Preparar candidatura: CV y carta en PDF archivados en JH_HOME/applications/<id>/ y su API.

Casi todos los tests sustituyen `generate_deterministic_documents` por un generador falso (sin motor
LaTeX); el de integración compila de verdad y se salta si no hay motor instalado.
"""
import json
import smtplib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import config  # noqa: E402
import database  # noqa: E402
from automation import application_archive, application_documents  # noqa: E402
from automation.latex_compiler import engine_available  # noqa: E402
from automation.verify_pdf import VerificationError  # noqa: E402
from tests.asgi_client import call  # noqa: E402

CLIENT = ("x-jh-client", "dashboard")
requires_engine = pytest.mark.skipif(engine_available() is None, reason="no hay motor LaTeX instalado")

OFFER_DESCRIPTION = (
    "<p>Buscamos consultor/a <b>SAP SD</b> para proyectos de S/4HANA en Villanova.</p>"
    "<ul><li>Experiencia con billing plan e intercompany</li></ul>"
)


@pytest.fixture
def env(tmp_path, monkeypatch):
    """BD temporal con una candidatura pendiente y archivo de candidaturas en tmp."""
    apps_dir = tmp_path / "applications"
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "t.db")
    monkeypatch.setattr(config, "APPLICATIONS_DIR", apps_dir)
    monkeypatch.setattr(application_archive, "APPLICATIONS_DIR", apps_dir)
    monkeypatch.setattr(application_documents, "engine_available", lambda *a, **k: "tectonic")
    conn = database.get_conn()
    database.init_db(conn)
    conn.execute("INSERT INTO companies (id,name,source,created_at) VALUES ('c1','Acme Villanova','test','2026-01-01')")
    conn.execute(
        "INSERT INTO job_offers (id, company_id, title, description, location, tech_stack, url, scraped_at) "
        "VALUES ('o1','c1','Consultor SAP SD',?,'Villanova','SAP, ABAP','https://example.org/o1','2026-10-01')",
        (OFFER_DESCRIPTION,),
    )
    conn.execute(
        "INSERT INTO contacts (id, company_id, type, value, created_at) "
        "VALUES ('ct1','c1','email','rrhh@acme.example','2026-01-01')"
    )
    app_id = database.record_application(conn, {
        "company_id": "c1", "job_offer_id": "o1", "contact_id": "ct1", "method": "email",
        "status": "pending_approval", "cover_letter_used": "Hola, me interesa el puesto.",
    })
    conn.commit()
    conn.close()
    return {"app_id": app_id, "apps_dir": apps_dir}


@pytest.fixture
def fake_generator(monkeypatch):
    """Generador falso: escribe PDFs de mentira en output_dir y guarda los argumentos recibidos."""
    calls: list[dict] = []
    state = {"fail": None, "tag": "v1"}

    def fake(**kwargs):
        calls.append(kwargs)
        if state["fail"]:
            raise state["fail"]
        out = Path(kwargs["output_dir"])
        out.mkdir(parents=True, exist_ok=True)
        files = {}
        for name in ("cv.pdf", "cover.pdf", "cv.tex", "cover.tex"):
            (out / name).write_bytes(f"%PDF-1.5 {name} {state['tag']}".encode())
            files[name] = out / name
        return {
            "cv_pdf": files["cv.pdf"], "cover_pdf": files["cover.pdf"],
            "cv_tex": files["cv.tex"], "cover_tex": files["cover.tex"],
            "verification": {"pages": {"cv": 2, "cover": 1}, "trimmed": [], "present_keywords": ["sap sd"],
                             "missing_keywords": [], "layout": "skipped: poppler no instalado"},
        }

    monkeypatch.setattr(application_documents, "generate_deterministic_documents", fake)
    return calls, state


# ── Servicio ───────────────────────────────────────────────────────────────────

def test_prepara_y_archiva_cv_carta_oferta_y_metadatos(env, fake_generator):
    calls, _ = fake_generator
    docs = application_documents.prepare_application(env["app_id"])

    app_dir = env["apps_dir"] / env["app_id"]
    assert docs.application_id == env["app_id"]
    assert docs.source == "deterministic"
    assert docs.warnings == []
    assert docs.verification["pages"] == {"cv": 2, "cover": 1}
    assert Path(docs.cv_pdf) == app_dir / "cv.pdf" and Path(docs.cover_pdf) == app_dir / "cover.pdf"
    for name in ("cv.pdf", "cover.pdf", "cv.tex", "cover.tex", "job_posting.md", "metadata.json"):
        assert (app_dir / name).is_file(), name

    posting = (app_dir / "job_posting.md").read_text(encoding="utf-8")
    assert "Consultor SAP SD" in posting and "Acme Villanova" in posting
    assert "billing plan" in posting and "<p>" not in posting and "<b>" not in posting

    meta = json.loads((app_dir / "metadata.json").read_text(encoding="utf-8"))
    assert meta["source"] == "deterministic"
    assert meta["company"] == "Acme Villanova" and meta["role"] == "Consultor SAP SD"
    assert meta["verification"]["pages"]["cv"] == 2

    kwargs = calls[0]
    assert kwargs["company_name"] == "Acme Villanova" and kwargs["role_title"] == "Consultor SAP SD"
    assert {"sap sd", "billing plan", "intercompany", "abap"} <= set(kwargs["offer_keywords"])
    assert "successfactors" not in kwargs["offer_keywords"]  # del grupo de keywords pero no de la oferta
    # Se genera fuera de la carpeta final y no quedan restos temporales
    assert Path(kwargs["output_dir"]) != app_dir
    assert sorted(p.name for p in env["apps_dir"].iterdir()) == [env["app_id"]]


def test_volver_a_preparar_sustituye_el_archivo_y_conserva_el_pack_de_entrevista(env, fake_generator):
    _, state = fake_generator
    application_documents.prepare_application(env["app_id"])
    app_dir = env["apps_dir"] / env["app_id"]
    (app_dir / "interview.md").write_text("# Pack", encoding="utf-8")

    state["tag"] = "v2"
    application_documents.prepare_application(env["app_id"])

    assert (app_dir / "cv.pdf").read_bytes().endswith(b"v2")
    assert (app_dir / "interview.md").read_text(encoding="utf-8") == "# Pack"
    assert sorted(p.name for p in env["apps_dir"].iterdir()) == [env["app_id"]]


def test_un_fallo_deja_intacto_el_archivo_anterior(env, fake_generator):
    _, state = fake_generator
    application_documents.prepare_application(env["app_id"])
    app_dir = env["apps_dir"] / env["app_id"]
    before = {p.name: p.read_bytes() for p in app_dir.iterdir()}

    state["fail"] = VerificationError("El CV ocupa 3 páginas y no cabe en 2")
    state["tag"] = "v2"
    with pytest.raises(application_documents.VerificationFailed) as exc:
        application_documents.prepare_application(env["app_id"])

    assert exc.value.reasons == ["El CV ocupa 3 páginas y no cabe en 2"]
    assert {p.name: p.read_bytes() for p in app_dir.iterdir()} == before
    assert sorted(p.name for p in env["apps_dir"].iterdir()) == [env["app_id"]]


def test_sin_motor_latex_avisa_sin_generar_nada(env, fake_generator, monkeypatch):
    calls, _ = fake_generator
    monkeypatch.setattr(application_documents, "engine_available", lambda *a, **k: None)
    with pytest.raises(application_documents.NoTexEngine) as exc:
        application_documents.prepare_application(env["app_id"])
    assert str(exc.value).startswith("Instala Tectonic")
    assert calls == []
    assert not (env["apps_dir"] / env["app_id"]).exists()


def test_candidatura_desconocida(env, fake_generator):
    with pytest.raises(application_documents.ApplicationNotFound):
        application_documents.prepare_application("no-existe")


NO_AI_WARNING = "IA no disponible: La IA está desactivada (proveedor «none»)"


def test_use_ai_explicito_sin_proveedor_usa_la_via_determinista_con_aviso(env, fake_generator):
    docs = application_documents.prepare_application(env["app_id"], use_ai=True)
    assert docs.source == "deterministic"
    assert docs.warnings == [NO_AI_WARNING]
    docs = application_documents.prepare_application(env["app_id"], use_ai=None)
    assert docs.warnings == []


def test_la_lista_blanca_de_documentos_bloquea_rutas(env, fake_generator):
    application_documents.prepare_application(env["app_id"])
    assert application_documents.document_path(env["app_id"], "cv.pdf").name == "cv.pdf"
    for bad in ("../t.db", "metadata.json", "cv.tex", "/etc/passwd", "..", "cv.pdf/../x"):
        with pytest.raises(FileNotFoundError):
            application_documents.document_path(env["app_id"], bad)
    with pytest.raises(ValueError):
        application_archive.get_application_dir("../otro")


def test_el_pack_de_entrevista_se_guarda_en_interview_md(env):
    path = application_archive.save_interview_prep(env["app_id"], "# Pack técnico", stage="technical")
    assert path == env["apps_dir"] / env["app_id"] / "interview.md"
    assert path.read_text(encoding="utf-8") == "# Pack técnico"


# ── API ────────────────────────────────────────────────────────────────────────

def test_api_prepare_devuelve_los_documentos(env, fake_generator):
    status, _, body = call("POST", f"/api/applications/{env['app_id']}/prepare",
                           headers=[CLIENT, ("content-type", "application/json")],
                           body=json.dumps({"use_ai": True}).encode())
    assert status == 200, body
    data = json.loads(body)
    assert data["source"] == "deterministic" and data["application_id"] == env["app_id"]
    assert data["warnings"] == [NO_AI_WARNING]
    assert data["cv_pdf"].endswith("cv.pdf")


def test_api_prepare_sin_cuerpo(env, fake_generator):
    status, _, body = call("POST", f"/api/applications/{env['app_id']}/prepare", headers=[CLIENT])
    assert status == 200, body


def test_api_prepare_sin_motor_da_409_con_pista_de_instalacion(env, fake_generator, monkeypatch):
    monkeypatch.setattr(application_documents, "engine_available", lambda *a, **k: None)
    status, _, body = call("POST", f"/api/applications/{env['app_id']}/prepare", headers=[CLIENT])
    assert status == 409
    assert json.loads(body)["detail"].startswith("Instala Tectonic")


def test_api_prepare_verificacion_fallida_da_422_con_motivos(env, fake_generator):
    _, state = fake_generator
    state["fail"] = VerificationError("Falta el teléfono en el CV")
    status, _, body = call("POST", f"/api/applications/{env['app_id']}/prepare", headers=[CLIENT])
    assert status == 422
    detail = json.loads(body)["detail"]
    assert detail["reasons"] == ["Falta el teléfono en el CV"]


def test_api_prepare_candidatura_desconocida_da_404(env, fake_generator):
    status, _, _ = call("POST", "/api/applications/no-existe/prepare", headers=[CLIENT])
    assert status == 404


def test_api_lista_y_descarga_documentos(env, fake_generator):
    status, _, body = call("GET", f"/api/applications/{env['app_id']}/documents", headers=[CLIENT])
    assert status == 200 and json.loads(body) == []

    application_documents.prepare_application(env["app_id"])
    status, _, body = call("GET", f"/api/applications/{env['app_id']}/documents", headers=[CLIENT])
    names = [d["name"] for d in json.loads(body)]
    assert names == ["cv.pdf", "cover.pdf", "job_posting.md"]
    assert all(d["size"] > 0 for d in json.loads(body))

    status, headers, body = call("GET", f"/api/applications/{env['app_id']}/documents/cv.pdf", headers=[CLIENT])
    assert status == 200 and headers["content-type"] == "application/pdf"
    assert body.startswith("%PDF")


def test_api_descarga_bloquea_fuera_de_la_lista_blanca(env, fake_generator):
    application_documents.prepare_application(env["app_id"])
    base = f"/api/applications/{env['app_id']}/documents/"
    for name in ("metadata.json", "cv.tex", "..%2Ft.db", "%2E%2E"):
        status, _, _ = call("GET", base + name, headers=[CLIENT])
        assert status == 404, name


def test_api_documentos_de_candidatura_desconocida_da_404(env):
    status, _, _ = call("GET", "/api/applications/no-existe/documents", headers=[CLIENT])
    assert status == 404


# ── Aprobación: el email adjunta los PDFs preparados ──────────────────────────

class FakeSMTP:
    sent: list[str] = []

    def __init__(self, *a, **kw):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def ehlo(self):
        pass

    def starttls(self, *a, **kw):
        pass

    def login(self, *a):
        pass

    def sendmail(self, frm, to, msg):
        FakeSMTP.sent.append(msg)


def test_aprobar_adjunta_los_pdfs_preparados(env, fake_generator, monkeypatch):
    from automation import application_engine

    FakeSMTP.sent = []
    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
    monkeypatch.setenv("GMAIL_USER", "ana@example.com")
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "pw-test")
    monkeypatch.setattr("secrets_store.keyring", None)

    application_documents.prepare_application(env["app_id"])
    assert application_engine.send_approved(env["app_id"]) is True

    msg = FakeSMTP.sent[0]
    assert "filename=cv.pdf" in msg and "filename=cover.pdf" in msg
    conn = database.get_conn()
    try:
        assert conn.execute("SELECT status FROM applications WHERE id=?", (env["app_id"],)).fetchone()[0] == "sent"
    finally:
        conn.close()


# ── Integración: compila de verdad ────────────────────────────────────────────

@pytest.mark.integration
@requires_engine
def test_integracion_prepara_pdfs_reales(env, tmp_path, monkeypatch):
    profile = json.loads((Path(__file__).parent.parent / "profile.example.json").read_text(encoding="utf-8"))
    profile.setdefault("personal", {}).update({"email": "ana@example.com", "phone": "+34 600 000 000"})
    path = tmp_path / "profile.json"
    path.write_text(json.dumps(profile), encoding="utf-8")
    monkeypatch.setattr(config, "PROFILE_PATH", path)

    docs = application_documents.prepare_application(env["app_id"])
    assert docs.verification["pages"]["cover"] == 1
    assert docs.verification["pages"]["cv"] <= 2
    assert Path(docs.cv_pdf).read_bytes().startswith(b"%PDF")


# ── Recuperación tras un corte, cerrojo en el envío y descarga en línea ───────

def test_recupera_old_si_falta_la_carpeta_y_limpia_restos(env, fake_generator):
    application_documents.prepare_application(env["app_id"])
    app_dir = env["apps_dir"] / env["app_id"]
    old = app_dir.with_name(f"{app_dir.name}.old")
    app_dir.rename(old)  # corte entre los dos renombrados

    cv, cover = application_archive.get_application_attachments(env["app_id"])
    assert cv == app_dir / "cv.pdf" and cover == app_dir / "cover.pdf"
    assert not old.exists()

    for suffix in (".old", ".tmp", ".work"):
        leftover = app_dir.with_name(f"{app_dir.name}{suffix}")
        leftover.mkdir()
        (leftover / "cv.pdf").write_bytes(b"resto")
    assert application_archive.load_application_archive(env["app_id"])["application_id"] == env["app_id"]
    assert sorted(p.name for p in env["apps_dir"].iterdir()) == [env["app_id"]]
    assert (app_dir / "cv.pdf").read_bytes() != b"resto"


def test_preparar_recupera_old_antes_de_generar(env, fake_generator):
    application_documents.prepare_application(env["app_id"])
    app_dir = env["apps_dir"] / env["app_id"]
    (app_dir / "interview.md").write_text("# Pack", encoding="utf-8")
    app_dir.rename(app_dir.with_name(f"{app_dir.name}.old"))

    application_documents.prepare_application(env["app_id"])
    assert (app_dir / "interview.md").read_text(encoding="utf-8") == "# Pack"
    assert sorted(p.name for p in env["apps_dir"].iterdir()) == [env["app_id"]]


def test_archivar_exige_cv_y_carta(env, tmp_path):
    pdf = tmp_path / "x.pdf"
    pdf.write_bytes(b"%PDF")
    with pytest.raises(ValueError):
        application_archive.archive_application(env["app_id"], cv_pdf=pdf, cover_pdf=None)
    with pytest.raises(ValueError):
        application_archive.archive_application(env["app_id"], cv_pdf=tmp_path / "no.pdf", cover_pdf=pdf)
    assert not (env["apps_dir"] / env["app_id"]).exists()


def test_no_arrastra_ficheros_ocultos(env, fake_generator):
    application_documents.prepare_application(env["app_id"])
    app_dir = env["apps_dir"] / env["app_id"]
    (app_dir / ".interview.md.tmp").write_text("a medias", encoding="utf-8")
    application_documents.prepare_application(env["app_id"])
    assert not (app_dir / ".interview.md.tmp").exists()


def test_el_envio_espera_al_cerrojo_de_la_candidatura(env, fake_generator, monkeypatch):
    import threading

    from automation import application_engine

    application_documents.prepare_application(env["app_id"])
    sent: list = []
    monkeypatch.setattr(application_engine, "deliver_email",
                        lambda **kw: sent.append(kw) or "<id@test>")
    lock = application_archive.application_lock(env["app_id"])
    lock.acquire()
    try:
        worker = threading.Thread(target=application_engine.send_approved, args=(env["app_id"],))
        worker.start()
        worker.join(0.3)
        assert worker.is_alive() and sent == []  # no resuelve adjuntos mientras alguien archiva
    finally:
        lock.release()
    worker.join(5)
    assert not worker.is_alive()
    assert sent[0]["cv_path"] == env["apps_dir"] / env["app_id"] / "cv.pdf"


def test_api_descarga_en_linea_y_nosniff(env, fake_generator):
    application_documents.prepare_application(env["app_id"])
    base = f"/api/applications/{env['app_id']}/documents/"
    status, headers, _ = call("GET", base + "cv.pdf", headers=[CLIENT], query="inline=1")
    assert status == 200
    assert headers["content-disposition"].startswith("inline")
    assert headers["x-content-type-options"] == "nosniff"
    status, headers, _ = call("GET", base + "cv.pdf", headers=[CLIENT])
    assert headers["content-disposition"].startswith("attachment")
    assert headers["x-content-type-options"] == "nosniff"
    status, headers, _ = call("GET", base + "job_posting.md", headers=[CLIENT], query="inline=1")
    assert headers["content-disposition"].startswith("attachment")  # en línea solo PDFs


# ── Plantillas propias activas: motores, errores sin 500, reserva integrada y límites (revisión SP3 I2/I3) ──

@pytest.fixture
def custom_tpl(env, tmp_path, monkeypatch):
    """JH_HOME temporal; `install(kind, name, **meta)` deja una plantilla propia activa en disco."""
    import search_config
    from automation import templates_registry

    original = search_config.get_config()
    monkeypatch.setattr(config, "JH_HOME", tmp_path / "home")
    search_config.save_config(original, search_config.user_config_path())

    def install(kind: str, name: str, engine: str = "latex", **meta) -> None:
        target = templates_registry.template_dir(kind, name)
        target.mkdir(parents=True)
        main = "c.typ.j2" if engine == "typst" else "c.tex.j2"
        (target / main).write_text("x", encoding="utf-8")
        data = {"name": name, "kind": kind, "engine": engine, "main_file": main} | meta
        (target / "template.json").write_text(json.dumps(data), encoding="utf-8")
        cfg = search_config.get_config()
        field = "cv_template" if kind == "cv" else "letter_template"
        docs = cfg.documents.model_copy(update={field: name})
        search_config.save_config(cfg.model_copy(update={"documents": docs}), search_config.user_config_path())

    yield install
    search_config.set_config(original)


def test_plantilla_typst_sin_typst_da_409_con_pista(env, fake_generator, custom_tpl, monkeypatch):
    from automation import templates_registry

    custom_tpl("cv", "typ", engine="typst")
    monkeypatch.setattr(templates_registry, "_resolve_binary", lambda name: None)
    status, _, body = call("POST", f"/api/applications/{env['app_id']}/prepare", headers=[CLIENT])
    assert status == 409
    detail = json.loads(body)["detail"]
    assert "typst" in detail and "integradas" in detail
    calls, _ = fake_generator
    assert calls == []


def test_fallo_de_plantilla_propia_da_422_con_reserva_y_la_reserva_funciona(env, fake_generator, custom_tpl, monkeypatch):
    from automation import templates_registry

    custom_tpl("cv", "rota")
    monkeypatch.setattr(templates_registry, "_resolve_binary", lambda name: f"/usr/bin/{name}")
    calls, state = fake_generator
    state["fail"] = templates_registry.TemplateRenderError(
        "La plantilla no se puede renderizar: UndefinedError: 'dict object' has no attribute 'foto'"
    )
    status, _, body = call("POST", f"/api/applications/{env['app_id']}/prepare", headers=[CLIENT])
    assert status == 422, body
    detail = json.loads(body)["detail"]
    assert detail["builtin_fallback"] is True
    assert any("UndefinedError" in r for r in detail["reasons"])
    assert any("plantillas integradas" in r for r in detail["reasons"])

    seen = []
    state["fail"] = None
    original = application_documents.generate_deterministic_documents

    def spy(**kwargs):
        seen.append(templates_registry.active_template("cv"))
        return original(**kwargs)

    monkeypatch.setattr(application_documents, "generate_deterministic_documents", spy)
    payload = json.dumps({"builtin_templates": True}).encode()
    status, _, body = call("POST", f"/api/applications/{env['app_id']}/prepare", body=payload,
                           headers=[CLIENT, ("content-type", "application/json"), ("content-length", str(len(payload)))])
    assert status == 200, body
    assert seen == [None]  # dentro de la reserva manda la integrada
    assert templates_registry.active_template("cv").name == "rota"  # fuera, la propia sigue activa


def test_compilacion_de_plantilla_propia_fallida_ofrece_reserva(env, fake_generator, custom_tpl, monkeypatch):
    from automation import templates_registry
    from automation.latex_compiler import LaTeXCompilationError

    custom_tpl("letter", "mala")
    monkeypatch.setattr(templates_registry, "_resolve_binary", lambda name: f"/usr/bin/{name}")
    _, state = fake_generator
    state["fail"] = LaTeXCompilationError("Undefined control sequence")
    with pytest.raises(application_documents.VerificationFailed) as exc:
        application_documents.prepare_application(env["app_id"])
    assert exc.value.builtin_fallback is True


def test_limite_de_paginas_de_la_plantilla_activa_manda(env, fake_generator, custom_tpl, monkeypatch):
    from automation import templates_registry

    custom_tpl("cv", "corta", page_limit=1)
    monkeypatch.setattr(templates_registry, "_resolve_binary", lambda name: f"/usr/bin/{name}")
    calls, _ = fake_generator
    application_documents.prepare_application(env["app_id"], use_ai=False)
    assert calls[-1]["cv_pages"] == 1 and calls[-1]["letter_pages"] == 1
    application_documents.prepare_application(env["app_id"], use_ai=False, builtin_templates=True)
    assert calls[-1]["cv_pages"] == 2


def test_reglas_de_estilo_de_la_plantilla_llegan_a_la_ia(env, fake_generator, custom_tpl, monkeypatch):
    import ai
    from automation import templates_registry

    custom_tpl("cv", "estilo", page_limit=1, style_rules="Resumen de una sola frase")
    custom_tpl("letter", "carta", style_rules="Tono formal, sin viñetas")
    monkeypatch.setattr(templates_registry, "_resolve_binary", lambda name: f"/usr/bin/{name}")
    seen = {}

    def fake_flow(profile, offer, provider, **kwargs):
        seen.update(kwargs)
        raise ai.AIError("sin red en los tests")

    monkeypatch.setattr(application_documents, "get_provider", lambda: object())
    monkeypatch.setattr(application_documents, "run_ai_flow", fake_flow)
    docs = application_documents.prepare_application(env["app_id"], use_ai=True)
    assert docs.source == "deterministic"
    assert "Resumen de una sola frase" in seen["style"] and "Tono formal, sin viñetas" in seen["style"]
    assert "CV 1, carta 1" in seen["style"]


@pytest.mark.parametrize("available,warned", [({"tectonic"}, True), ({"tectonic", "xelatex"}, False)])
def test_plantilla_propia_con_tectonic_avisa_de_que_no_esta_confinada(env, fake_generator, custom_tpl, monkeypatch,
                                                                      available, warned):
    from automation import templates_registry

    custom_tpl("cv", "propia")
    monkeypatch.setattr(templates_registry, "_resolve_binary", lambda n: f"/usr/bin/{n}" if n in available else None)
    docs = application_documents.prepare_application(env["app_id"], use_ai=False)
    assert (templates_registry.UNCONFINED_WARNING in docs.warnings) is warned
    assert ("fuentes de confianza" in " ".join(docs.warnings)) is warned
    # con las integradas (Tectonic) no hay aviso
    docs = application_documents.prepare_application(env["app_id"], use_ai=False, builtin_templates=True)
    assert templates_registry.UNCONFINED_WARNING not in docs.warnings
