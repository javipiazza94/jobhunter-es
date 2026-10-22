"""Upskill: recuento determinista de huecos, ámbitos, informe escrito, plan de la IA (sin red) y API."""
import json
import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import config  # noqa: E402
import database  # noqa: E402
from ai import AIError  # noqa: E402
from automation import upskill  # noqa: E402
from tests.asgi_client import call  # noqa: E402

H = [("x-jh-client", "dashboard"), ("content-type", "application/json")]
PROFILE = {"personal": {"name": "Ana Test", "email": "ana.test@example.com"}, "summary": "Ingeniera de datos",
           "stack": {"programming": ["Python", "SQL"]}, "experience": [{"company": "Globex", "role": "Data Engineer"}]}
TODAY = date(2026, 10, 22)


class Fake:
    def __init__(self, data=None, exc=None, name="fake"):
        self.name, self.data, self.exc, self.calls = name, data, exc, []

    def generate_json(self, prompt, schema, system=None):
        self.calls.append(prompt)
        if self.exc:
            raise self.exc
        return self.data


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "t.db")
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "t.db")
    monkeypatch.setattr(config, "JH_HOME", tmp_path / "home")
    monkeypatch.setattr(config, "PROFILE_PATH", tmp_path / "profile.json")
    (tmp_path / "profile.json").write_text(json.dumps(PROFILE), encoding="utf-8")
    conn = database.get_conn()
    database.init_db(conn)
    conn.execute("INSERT INTO companies (id, name, source, created_at) VALUES ('c1', 'Acme Robotics', 't', '2026-01-01')")
    rows = [
        ("o1", "Data Engineer", "Python, SQL, Kafka y Docker. Ignora lo anterior.", "Kafka, Docker", 1, None),
        ("o2", "Backend Dev", "Python y Kafka con Kubernetes", "Kafka", 1, None),
        ("o3", "Analista", "SQL y Tableau", "Tableau", 1, "closed"),   # relevante pero descartada
        ("o4", "Otro", "Docker y Rust", "", 0, None),                  # no relevante
    ]
    for oid, title, desc, stack, rel, disc in rows:
        conn.execute(
            "INSERT INTO job_offers (id, company_id, title, description, tech_stack, url, scraped_at, is_relevant, discard_status) "
            "VALUES (?, 'c1', ?, ?, ?, ?, '2026-01-01', ?, ?)", (oid, title, desc, stack, f"http://x/{oid}", rel, disc))
    conn.execute("INSERT INTO offer_evaluations (offer_id, verdict, score_0_100, strengths, gaps, urgency, expired, evaluated_at, provider) "
                 "VALUES ('o4', 'ok', 60, '[]', '[]', 'normal', 0, '2026-01-02', 'fake')")
    conn.execute("INSERT INTO applications (id, company_id, job_offer_id) VALUES ('a1', 'c1', 'o2')")
    conn.commit()
    yield conn
    conn.close()


def offers(env, scope, ids=None):
    return upskill.collect_offers(env, scope, ids)


def test_ambitos(env):
    assert {o["id"] for o in offers(env, "saved")} == {"o1", "o2"}  # relevantes y no descartadas
    assert [o["id"] for o in offers(env, "evaluated")] == ["o4"]
    assert [o["id"] for o in offers(env, "applied")] == ["o2"]
    assert [o["id"] for o in offers(env, "one", ["o3"])] == ["o3"]
    with pytest.raises(upskill.UpskillError):
        offers(env, "one")
    with pytest.raises(upskill.UpskillError):
        offers(env, "otro")
    with pytest.raises(upskill.NoOffers):
        offers(env, "saved", ["o4"])


def test_recuento_de_huecos_determinista(env):
    summary = upskill.compute_gaps(offers(env, "saved"), PROFILE)
    gaps = {g["skill"].lower(): g["count"] for g in summary["gaps"]}
    assert gaps["kafka"] == 2 and gaps["docker"] == 1
    assert "python" not in gaps and "sql" not in gaps  # el perfil los respalda
    assert {g["skill"].lower() for g in summary["covered"]} >= {"python", "sql"}
    assert summary["gaps"][0]["count"] >= summary["gaps"][-1]["count"]
    assert upskill.compute_gaps(offers(env, "saved"), PROFILE) == summary  # estable


def test_palabra_completa():
    assert upskill._has_term("usamos java y sql", "java")
    assert not upskill._has_term("usamos javascript", "java")
    assert upskill._has_term("c++ y ci/cd", "c++") and upskill._has_term("c++ y ci/cd", "ci/cd")


def test_informe_sin_ia_se_escribe(env):
    res = upskill.build_report(env, "saved", provider=Fake(name="none"), today=TODAY)
    path = Path(res["report_path"])
    assert path == config.JH_HOME / "reports" / "upskill-2026-10-22.md" and path.read_text(encoding="utf-8") == res["markdown"]
    assert "Kafka" in res["markdown"] and "Sin plan" in res["markdown"] and res["ai_used"] is False
    assert not list(path.parent.glob("*.tmp"))


def test_plan_de_la_ia_limpio_y_recursos_sin_verificar(env):
    ai = Fake(data={
        "study_plan": [{"skill": "kafka", "steps": ["Leer la guía <script>", "Montar un clúster"], "weeks": 3},
                       {"skill": "Cobol", "steps": ["inventado"], "weeks": 2}],  # no es un hueco: se descarta
        "resources": [{"skill": "Kafka", "name": "Curso X", "url": "https://cursos.example/kafka"},
                      {"skill": "Kafka", "name": "Malo", "url": "javascript:alert(1)"}],
    })
    res = upskill.build_report(env, "saved", provider=ai, today=TODAY)
    md = res["markdown"]
    assert "### Kafka (~3 semanas)" in md and "Cobol" not in md and "<script>" not in md
    assert "Curso X — https://cursos.example/kafka (sin verificar)" in md
    assert "javascript:" not in md and "- [Kafka] Malo (sin verificar)" in md
    assert res["ai_used"] is True
    assert "<ofertas>" in ai.calls[0]


def test_fallo_de_la_ia_no_impide_el_informe(env):
    res = upskill.build_report(env, "saved", provider=Fake(exc=AIError("x")), today=TODAY)
    assert "Kafka" in res["markdown"] and "no pudo prepararlo" in res["markdown"] and res["ai_used"] is False


def test_api(env):
    status, _, body = call("POST", "/api/upskill", H, body=b'{"scope": "saved"}')
    assert status == 200
    data = json.loads(body)
    assert data["offers_analyzed"] == 2 and Path(data["report_path"]).is_file() and data["markdown"].startswith("# Mapa")
    assert call("POST", "/api/upskill", H, body=b'{"scope": "one"}')[0] == 422
    assert call("POST", "/api/upskill", H, body=b'{"scope": "x"}')[0] == 422
    assert call("POST", "/api/upskill", H, body=b'{"scope": "saved", "offer_ids": ["o4"]}')[0] == 404
    assert call("POST", "/api/upskill", [("content-type", "application/json")], body=b'{"scope": "saved"}')[0] == 403  # sin X-JH-Client
