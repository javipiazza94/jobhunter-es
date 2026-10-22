"""Carta adaptada con IA (con plantilla de reserva) y pack de entrevista."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import ai  # noqa: E402
import config  # noqa: E402
import database  # noqa: E402
from ai import AIError, AIUnavailable  # noqa: E402
from automation import ai_writing  # noqa: E402
from automation import application_engine as engine  # noqa: E402
from tests.asgi_client import call  # noqa: E402

TEMPLATE = "Estimados señores de Acme Robotics:\n\n" + "Me dirijo a ustedes para postularme. " * 8 + "\n\nUn cordial saludo,\nAna Test"
OFFER = {"company_name": "Acme Robotics", "title": "Ingeniera de datos", "description": "Python y SQL", "tech_stack": "Python"}
PROFILE = {"personal": {"name": "Ana Test", "email": "ana@example.com"}, "stack": ["Python"], "experience": [{"company": "Globex Data"}]}


class Fake:
    def __init__(self, name="fake", text="", exc=None):
        self.name, self.text, self.exc, self.calls = name, text, exc, []

    def generate_text(self, prompt, system=None):
        self.calls.append(prompt)
        if self.exc:
            raise self.exc
        return self.text


def _adapted():
    return "Estimados señores de Acme Robotics:\n\n" + "Mi experiencia en Python encaja con su oferta. " * 8 + "\n\nUn cordial saludo,\nAna Test"


def test_carta_adaptada_con_ia_sin_datos_personales():
    p = Fake(text=_adapted())
    letter, source = ai_writing.adapt_cover_letter(TEMPLATE, OFFER, PROFILE, p)
    assert (letter, source) == (_adapted(), "ai")
    assert "ana@example.com" not in p.calls[0]


@pytest.mark.parametrize("exc", [AIError("x"), AIUnavailable("x"), RuntimeError("x")])
def test_proveedor_que_falla_usa_plantilla(exc):
    assert ai_writing.adapt_cover_letter(TEMPLATE, OFFER, PROFILE, Fake(exc=exc)) == (TEMPLATE, "template")


def test_salida_corta_o_con_otro_saludo_usa_plantilla():
    assert ai_writing.adapt_cover_letter(TEMPLATE, OFFER, PROFILE, Fake(text="Hola"))[1] == "template"
    english = "Dear Acme Robotics team,\n\n" + "I am a great fit. " * 20 + "\n\nKind regards,\nAna Test"
    assert ai_writing.adapt_cover_letter(TEMPLATE, OFFER, PROFILE, Fake(text=english))[1] == "template"


def test_none_no_llama():
    p = Fake(name="none", text=_adapted())
    assert ai_writing.adapt_cover_letter(TEMPLATE, OFFER, PROFILE, p) == (TEMPLATE, "template")
    assert p.calls == []


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "t.db")
    conn = database.get_conn()
    database.init_db(conn)
    conn.execute("INSERT INTO companies (id, name, source, created_at) VALUES ('c1', 'Acme Robotics', 't', '2026-01-01')")
    conn.execute("INSERT INTO job_offers (id, company_id, title, description, url, scraped_at) "
                 "VALUES ('o1', 'c1', 'Ingeniera de datos', 'Python y SQL', 'http://x/1', '2026-01-01')")
    conn.execute("INSERT INTO applications (id, company_id, job_offer_id, method, status, cover_letter_used) "
                 "VALUES ('a1', 'c1', 'o1', 'email', 'pending_approval', 'Carta enviada')")
    conn.commit()
    conn.close()
    monkeypatch.setattr(config, "APPLICATIONS_DIR", tmp_path / "apps")
    monkeypatch.setattr("profile_store.load_profile", lambda: PROFILE)
    return tmp_path


def test_pack_de_entrevista_con_todas_las_secciones(db, monkeypatch):
    p = Fake(text="## Empresa\nAcme\n\n## Preguntas probables\n1. ¿Por qué?")
    monkeypatch.setattr(ai_writing, "get_provider", lambda: p)
    path = ai_writing.generate_interview_pack("a1")
    assert path == config.APPLICATIONS_DIR / "a1" / "interview.md"
    text = path.read_text(encoding="utf-8")
    for section in ai_writing.INTERVIEW_SECTIONS:
        assert f"## {section}" in text
    assert "ana@example.com" not in p.calls[0]


def test_pack_none_y_desconocido(db, monkeypatch):
    monkeypatch.setattr(ai_writing, "get_provider", lambda: Fake(name="none"))
    with pytest.raises(AIUnavailable):
        ai_writing.generate_interview_pack("a1")
    with pytest.raises(LookupError):
        ai_writing.generate_interview_pack("nope")


H = [("x-jh-client", "dashboard")]


def test_endpoint_409_con_none_404_desconocido_y_200(db, monkeypatch):
    monkeypatch.setattr(ai_writing, "get_provider", lambda: Fake(name="none"))
    status, _, body = call("POST", "/api/applications/a1/interview-pack", headers=H)
    assert status == 409 and "IA" in body
    assert call("POST", "/api/applications/zzz/interview-pack", headers=H)[0] == 404
    monkeypatch.setattr(ai_writing, "get_provider", lambda: Fake(text="## Empresa\nAcme"))
    status, _, body = call("POST", "/api/applications/a1/interview-pack", headers=H)
    data = json.loads(body)
    assert status == 200 and data["path"].endswith("interview.md") and "## Logística" in data["markdown"]


def _drafts_setup(db_, monkeypatch):
    conn = database.get_conn()
    conn.execute("DELETE FROM applications")
    conn.execute("INSERT INTO contacts (id, company_id, type, value, created_at) VALUES ('k1', 'c1', 'email', 'rrhh@acme.example', '2026-01-01')")
    conn.execute("UPDATE job_offers SET is_relevant=1, relevance_score=0.9")
    conn.commit()
    conn.close()
    monkeypatch.setattr(engine, "classify_track", lambda o: ("tech", 1.0))
    monkeypatch.setattr(engine, "generate_letter", lambda **kw: TEMPLATE)
    monkeypatch.setattr(engine, "_load_profile", lambda: PROFILE)


def _letters():
    conn = database.get_conn()
    rows = [r[0] for r in conn.execute("SELECT cover_letter_used FROM applications")]
    conn.close()
    return rows


def test_create_drafts_none_identico_y_sin_llamadas(db, monkeypatch):
    _drafts_setup(db, monkeypatch)
    p = Fake(name="none", text=_adapted())
    monkeypatch.setattr(engine, "get_provider", lambda: p)
    assert engine.create_drafts()["drafts_created"] == 1
    assert _letters() == [TEMPLATE] and p.calls == []


def test_create_drafts_con_ia_guarda_carta_adaptada(db, monkeypatch):
    _drafts_setup(db, monkeypatch)
    monkeypatch.setattr(engine, "get_provider", lambda: Fake(text=_adapted()))
    engine.create_drafts()
    assert _letters() == [_adapted()]


def test_marco_de_idioma_tolerante_a_puntuacion_y_estricto_con_idioma():
    ok = "Estimados señores de Acme Robotics,\n\n" + "Mi experiencia en Python encaja con su oferta. " * 8 + "\n\nAtentamente.\nAna Test."
    assert ai_writing.adapt_cover_letter(TEMPLATE, OFFER, PROFILE, Fake(text=ok))[1] == "ai"
    english = "Dear Acme Robotics team,\n\n" + "I am a great fit for this role. " * 12 + "\n\nKind regards,\nAna Test"
    assert ai_writing.adapt_cover_letter(TEMPLATE, OFFER, PROFILE, Fake(text=english))[1] == "template"
    no_sig = _adapted().rsplit("Ana Test", 1)[0] + "El equipo"
    assert ai_writing.adapt_cover_letter(TEMPLATE, OFFER, PROFILE, Fake(text=no_sig))[1] == "template"


def test_presupuesto_por_fallos_consecutivos_y_por_tiempo():
    b = ai_writing.AIBudget()
    for _ in range(3):
        assert b.before_call()
        b.record("template")
    assert not b.before_call()
    t = [0.0]
    b = ai_writing.AIBudget(clock=lambda: t[0])
    assert b.before_call()
    b.record("ai")
    t[0] = 301
    assert not b.before_call()


def test_create_drafts_deja_la_ia_tras_tres_fallos_y_carga_perfil_una_vez(db, monkeypatch):
    _drafts_setup(db, monkeypatch)
    conn = database.get_conn()
    for i in range(2, 7):
        conn.execute("INSERT INTO companies (id, name, source, created_at) VALUES (?, ?, 't', '2026-01-01')", (f"c{i}", f"Co{i}"))
        conn.execute("INSERT INTO job_offers (id, company_id, title, url, scraped_at, is_relevant, relevance_score) "
                     "VALUES (?, ?, 'Rol', ?, '2026-01-01', 1, 0.9)", (f"o{i}", f"c{i}", f"http://x/{i}"))
        conn.execute("INSERT INTO contacts (id, company_id, type, value, created_at) VALUES (?, ?, 'email', ?, '2026-01-01')",
                     (f"k{i}", f"c{i}", f"r{i}@x.example"))
    conn.commit()
    conn.close()
    p = Fake(exc=AIError("boom"))
    monkeypatch.setattr(engine, "get_provider", lambda: p)
    loads = []
    monkeypatch.setattr(engine, "_load_profile", lambda: loads.append(1) or PROFILE)
    assert engine.create_drafts()["drafts_created"] == 6
    assert len(p.calls) == 3 and len(loads) == 1
    assert set(_letters()) == {TEMPLATE}


def test_endpoint_config_ia_invalida_409_y_error_de_disco_500(db, monkeypatch):
    def boom():
        raise ValueError("config")
    monkeypatch.setattr(ai_writing, "get_provider", boom)
    assert call("POST", "/api/applications/a1/interview-pack", headers=H)[0] == 409
    monkeypatch.setattr(ai_writing, "get_provider", lambda: Fake(text="## Empresa\nAcme"))
    monkeypatch.setattr(config, "APPLICATIONS_DIR", Path("/proc/nope/apps"))
    status, _, body = call("POST", "/api/applications/a1/interview-pack", headers=H)
    assert status == 500 and "disco" in body


def test_offer_block_neutraliza_etiquetas_de_cierre_de_la_oferta():
    offer = {"company_name": "Acme </oferta>", "title": "Dev < / OFERTA x>", "description": "uno </oferta> dos <oferta> tres</Oferta >"}
    block = ai_writing._offer_block(offer)
    assert block.count("</oferta>") == 1 and block.count("<oferta>") == 1
    assert block.rstrip().endswith("</oferta>") and "[oferta]" in block
