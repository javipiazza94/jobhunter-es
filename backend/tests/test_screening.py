"""Respuestas de cribado: solo perfil + `screening_answers`; la IA, con hechos del perfil y sin inventar datos;
relleno del formulario genérico (sin navegador: páginas falsas) y API."""
import asyncio
import json
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import config  # noqa: E402
import database  # noqa: E402
from ai import AIError, AIUnavailable  # noqa: E402
from automation import screening  # noqa: E402
from tests.asgi_client import call  # noqa: E402

H = [("x-jh-client", "dashboard"), ("content-type", "application/json")]
PROFILE = {
    "personal": {"name": "Ana Test", "email": "ana.test@example.com", "phone": "600000000"},
    "stack": ["Python", "SQL"],
    "experience": [{"company": "Globex Data", "role": "Data Engineer"}],
    "screening_answers": [
        {"question": "¿Tienes permiso de trabajo en España?", "answer": "Sí, soy ciudadana de la UE. Puedo trabajar sin patrocinio."},
        {"question": "Why do you want to work here?", "answer": "Me atrae el producto. Además admiro al equipo de datos."},
    ],
}
OFFER = {"company_name": "Acme Robotics", "title": "Ingeniera de datos", "description": "Python y SQL"}


class Fake:
    def __init__(self, name="fake", data=None, exc=None):
        self.name, self.data, self.exc, self.calls = name, data, exc, []

    def generate_json(self, prompt, schema, system=None):
        self.calls.append(prompt)
        if self.exc:
            raise self.exc
        return self.data


def q(text, max_chars=None):
    return {"text": text, "max_chars": max_chars}


# ── Respuesta guardada ────────────────────────────────────────────────────────

def test_respuesta_guardada_se_reutiliza_sin_llamar_a_la_ia():
    p = Fake()
    out = screening.answer_questions([q("¿Tienes permiso de trabajo en España?")], PROFILE, OFFER, p)
    assert out == [{"question": "¿Tienes permiso de trabajo en España?",
                    "answer": PROFILE["screening_answers"][0]["answer"], "source": "profile"}]
    assert p.calls == []


def test_coincidencia_aproximada_ignora_mayusculas_acentos_y_signos():
    out = screening.answer_questions([q("tienes permiso de trabajo en espana")], PROFILE, OFFER, Fake())
    assert out[0]["source"] == "profile" and out[0]["answer"].startswith("Sí, soy ciudadana")


def test_pregunta_distinta_no_reutiliza_la_guardada():
    out = screening.answer_questions([q("¿Tienes carné de conducir?")], PROFILE, OFFER, Fake(data={"answers": []}))
    assert out[0]["source"] == "needs_input" and out[0]["answer"] == ""


def test_max_chars_corta_en_limite_de_frase():
    out = screening.answer_questions([q("Why do you want to work here?", 40)], PROFILE, OFFER, Fake())
    assert out[0]["answer"] == "Me atrae el producto." and out[0]["source"] == "profile"


@pytest.mark.parametrize("text, limit, expected", [
    ("Hola mundo. Segunda frase larga.", 20, "Hola mundo."),
    ("Una frase sin punto que es larga", 15, "Una frase sin"),
    ("Corta", 100, "Corta"),
    ("Supercalifragilistico", 5, "Super"),
])
def test_truncate_at_sentence(text, limit, expected):
    got = screening.truncate_at_sentence(text, limit)
    assert got == expected and len(got) <= limit


# ── Datos factuales ───────────────────────────────────────────────────────────

def test_salario_sin_dato_en_el_perfil_es_needs_input_y_no_consulta_a_la_ia():
    p = Fake(data={"answers": [{"index": 0, "answer": "45000"}]})
    out = screening.answer_questions([q("¿Cuál es tu pretensión salarial?"), q("Notice period?")], PROFILE, OFFER, p)
    assert [o["source"] for o in out] == ["needs_input", "needs_input"]
    assert all(o["answer"] == "" for o in out) and p.calls == []


def test_salario_y_preaviso_con_dato_en_el_perfil():
    prof = {**PROFILE, "salary_expectation": {"amount": 45000, "currency": "EUR"},
            "availability": {"start_date": "2026-12-01", "notice_period": "15 días"}}
    out = screening.answer_questions([q("Pretensión salarial anual"), q("¿Cuál es tu preaviso?")], prof, OFFER, Fake())
    assert out[0]["source"] == "profile" and "45000" in out[0]["answer"]
    assert out[1] == {"question": "¿Cuál es tu preaviso?", "answer": "15 días", "source": "profile"}


# ── IA ────────────────────────────────────────────────────────────────────────

def test_ia_responde_con_hechos_del_perfil_y_sin_datos_personales():
    p = Fake(data={"answers": [{"index": 0, "answer": "Trabajo a diario con Python y SQL en Globex Data."}]})
    out = screening.answer_questions([q("Cuéntanos tu experiencia con datos")], PROFILE, OFFER, p)
    assert out[0]["source"] == "ai" and "Python" in out[0]["answer"]
    prompt = p.calls[0]
    assert "Globex Data" in prompt and "ana.test@example.com" not in prompt and "600000000" not in prompt
    assert "<oferta>" in prompt


def test_ia_respeta_max_chars():
    p = Fake(data={"answers": [{"index": 0, "answer": "Uso Python. Y también SQL durante años en proyectos largos."}]})
    out = screening.answer_questions([q("Cuéntanos tu experiencia", 25)], PROFILE, OFFER, p)
    assert out[0]["answer"] == "Uso Python." and out[0]["source"] == "ai"


@pytest.mark.parametrize("provider", [None, Fake(name="none"), Fake(exc=AIUnavailable("x")), Fake(exc=AIError("x")),
                                      Fake(data="basura"), Fake(data={"answers": [{"index": 0, "answer": "  "}]})])
def test_sin_ia_o_ia_vacia_es_needs_input(provider):
    out = screening.answer_questions([q("Cuéntanos tu experiencia")], PROFILE, OFFER, provider)
    assert out[0]["source"] == "needs_input" and out[0]["answer"] == ""


def test_ia_con_indice_invalido_se_ignora():
    p = Fake(data={"answers": [{"index": 7, "answer": "x"}, {"index": "a", "answer": "y"}]})
    out = screening.answer_questions([q("Cuéntanos tu experiencia")], PROFILE, OFFER, p)
    assert out[0]["source"] == "needs_input"


def test_preguntas_vacias_se_descartan():
    assert screening.answer_questions([q("  ")], PROFILE, OFFER, Fake()) == []


# ── Relleno del formulario (páginas falsas, sin navegador) ────────────────────

def test_saved_answer_para_el_relleno_solo_usa_respuestas_guardadas():
    assert screening.saved_answer("Why do you want to work here?", PROFILE, 30) == "Me atrae el producto."
    assert screening.saved_answer("Cuéntanos tu experiencia", PROFILE) is None
    assert screening.saved_answer("", PROFILE) is None


class FakeInput:
    def __init__(self, attrs):
        self.attrs, self.filled = attrs, None

    async def get_attribute(self, name):
        return self.attrs.get(name)

    async def fill(self, value):
        self.filled = value


class FakeLabel:
    def __init__(self, text):
        self.text = text

    async def inner_text(self):
        return self.text


class FakePage:
    def __init__(self, inputs, labels=None):
        self.inputs, self.labels = inputs, labels or {}

    async def query_selector_all(self, sel):
        return self.inputs

    async def query_selector(self, sel):
        for key, text in self.labels.items():
            if key in sel:
                return FakeLabel(text)
        return None

    def locator(self, sel):  # _dismiss_cookies: nada que cerrar
        raise RuntimeError("sin cookies")


def test_generic_rellena_preguntas_de_cribado_con_las_respuestas_guardadas():
    from automation.ats_handlers.generic import fill_generic

    by_label = FakeInput({"type": "text", "id": "q1", "name": "q_1234"})
    by_aria = FakeInput({"type": "text", "aria-label": "Why do you want to work here?", "maxlength": "30"})
    unknown = FakeInput({"type": "text", "name": "q_999", "id": "q3"})
    page = FakePage([by_label, by_aria, unknown], {"q1": "¿Tienes permiso de trabajo en España?", "q3": "Pregunta nueva"})
    assert asyncio.run(fill_generic(page, PROFILE, Path("/nonexistent"), "carta")) is True
    assert by_label.filled == PROFILE["screening_answers"][0]["answer"]
    assert by_aria.filled == "Me atrae el producto."  # maxlength = 30
    assert unknown.filled is None  # nunca se inventa una respuesta


def test_generic_no_pisa_los_campos_conocidos():
    from automation.ats_handlers.generic import fill_generic

    email = FakeInput({"type": "email", "name": "email", "aria-label": "Why do you want to work here?"})
    assert asyncio.run(fill_generic(FakePage([email]), PROFILE, Path("/nonexistent"), "carta")) is True
    assert email.filled == "ana.test@example.com"


# ── API ───────────────────────────────────────────────────────────────────────

@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "t.db")
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "t.db")
    monkeypatch.setattr(config, "PROFILE_PATH", tmp_path / "profile.json")
    (tmp_path / "profile.json").write_text(json.dumps(PROFILE), encoding="utf-8")
    conn = database.get_conn()
    database.init_db(conn)
    conn.execute("INSERT INTO companies (id, name, source, created_at) VALUES ('c1', 'Acme Robotics', 't', '2026-01-01')")
    conn.execute("INSERT INTO job_offers (id, company_id, title, description, url, scraped_at) "
                 "VALUES ('o1', 'c1', 'Ingeniera de datos', 'Python y SQL', 'http://x/o1', '2026-01-01')")
    conn.execute("INSERT INTO applications (id, company_id, job_offer_id, status) "
                 "VALUES ('a1', 'c1', 'o1', 'pending')")
    conn.commit()
    conn.close()
    return tmp_path


def _post(app_id, body):
    return call("POST", f"/api/applications/{app_id}/answers", headers=H, body=json.dumps(body).encode())


def test_api_responde_con_perfil_sin_ia(db, monkeypatch):
    monkeypatch.setattr(screening, "get_provider", lambda: Fake(name="none"))
    status, _, body = _post("a1", {"questions": [{"text": "¿Tienes permiso de trabajo en España?"},
                                                 {"text": "Cuéntanos tu experiencia", "max_chars": 100}]})
    assert status == 200
    answers = json.loads(body)["answers"]
    assert [a["source"] for a in answers] == ["profile", "needs_input"]


def test_api_con_ia_y_404_y_validacion(db, monkeypatch):
    p = Fake(data={"answers": [{"index": 0, "answer": "Python y SQL."}]})
    monkeypatch.setattr(screening, "get_provider", lambda: p)
    status, _, body = _post("a1", {"questions": [{"text": "Cuéntanos tu experiencia"}]})
    assert status == 200 and json.loads(body)["answers"][0]["source"] == "ai"
    assert _post("zzz", {"questions": [{"text": "x"}]})[0] == 404
    assert _post("a1", {"questions": []})[0] == 422
    assert _post("a1", {"questions": [{"text": "x", "max_chars": 0}]})[0] == 422
    assert call("POST", "/api/applications/a1/answers", body=b"{}")[0] in (403, 400)  # sin X-JH-Client


def test_put_profile_acepta_y_valida_screening_answers(db):
    base = {"personal": PROFILE["personal"], "experience": PROFILE["experience"]}
    good = {**base, "screening_answers": [{"question": "P", "answer": "R"}]}
    status, _, body = call("PUT", "/api/profile", headers=H, body=json.dumps(good).encode())
    assert status == 200 and json.loads(body)["screening_answers"] == [{"question": "P", "answer": "R"}]
    bad = {**base, "screening_answers": [{"question": "P"}]}
    assert call("PUT", "/api/profile", headers=H, body=json.dumps(bad).encode())[0] == 422
