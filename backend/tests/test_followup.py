"""Seguimiento de candidaturas silenciosas (idea de /outcome followup y stale de ai-job-search)."""
import json
import sqlite3
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent))

from asgi_client import call  # noqa: E402
import main  # noqa: E402
from automation import followup  # noqa: E402
from database import get_db, init_db  # noqa: E402

CLIENT = [("x-jh-client", "dashboard")]
PROFILE = {
    "personal": {"name": "Ana Ejemplo Prueba", "first_name": "Ana", "email": "j@example.com", "phone": ""},
    "summary": {"sap": "Consultor SAP FI con máster en S/4HANA. Segunda frase que no debe salir.",
                "ia": "Perfil de Data Science e IA aplicada."},
}


def _ago(days):
    return (date.today() - timedelta(days=days)).isoformat()


@pytest.fixture
def conn(tmp_path, monkeypatch):
    p = tmp_path / "profile.json"
    p.write_text(json.dumps(PROFILE), encoding="utf-8")
    monkeypatch.setattr(followup, "PROFILE_PATH", p)
    c = sqlite3.connect(tmp_path / "t.db", check_same_thread=False)
    c.row_factory = sqlite3.Row
    init_db(c)
    c.execute("INSERT INTO companies (id, name, source, created_at) VALUES ('c1', 'ACME', 't', 'hoy')")
    c.execute("INSERT INTO job_offers (id, company_id, title, url, scraped_at) VALUES ('o1', 'c1', 'SAP FI Consultant', 'u1', 'hoy')")
    rows = [
        ("a_old", "sent", "email", _ago(40) + "T10:00:00", "sap", "o1"),
        ("a_li", "sent", "linkedin_easy_apply", _ago(12), "ia_dev", None),
        ("a_new", "sent", "portal", _ago(3), "sap", None),
        ("a_reply", "replied", "email", _ago(50), "sap", None),
        ("a_bad", "sent", "portal", _ago(70)[:10] + "T00:00:00T12:00:00", None, None),  # formato roto real
    ]
    for i, st, m, sent, prof, offer in rows:
        c.execute("INSERT INTO applications (id, company_id, job_offer_id, status, method, sent_at, cv_profile) "
                  "VALUES (?, 'c1', ?, ?, ?, ?, ?)", (i, offer, st, m, sent, prof))
    c.commit()
    yield c
    c.close()


def test_lista_solo_sent_silenciosas_mas_antiguas_primero(conn):
    ids = [a["id"] for a in followup.list_followups(conn, 10)]
    assert ids == ["a_bad", "a_old", "a_li"]


def test_borrador_por_canal_sin_meritos_nuevos(conn):
    apps = {a["id"]: a for a in followup.list_followups(conn, 10)}
    email = apps["a_old"]["draft"]
    assert email.startswith("Asunto: Seguimiento de mi candidatura – SAP FI Consultant")
    assert "Consultor SAP FI con máster en S/4HANA." in email
    assert "Segunda frase" not in email
    li = apps["a_li"]
    assert li["channel"] == "linkedin" and "Asunto" not in li["draft"]
    assert "Data Science" in li["draft"] and li["draft"].rstrip().endswith("Ana")


def test_titulo_de_relleno_no_aparece():
    draft = followup.draft_followup({"method": "email", "company_name": "X", "job_title": "(ver Gmail)",
                                     "sent_at": "2026-09-10"}, PROFILE)
    assert "(ver Gmail)" not in draft and "candidatura espontánea" in draft


def test_maximo_dos_recordatorios_y_cuenta_desde_el_ultimo(conn):
    assert followup.mark_followup_sent(conn, "a_old", when=date.today())
    assert "a_old" not in [a["id"] for a in followup.list_followups(conn, 10)]  # recién recordada
    assert followup.mark_followup_sent(conn, "a_old")
    assert not followup.mark_followup_sent(conn, "a_old")  # tercero: no
    assert not followup.mark_followup_sent(conn, "a_reply")  # no está en 'sent'
    row = conn.execute("SELECT followup_count, notes FROM applications WHERE id='a_old'").fetchone()
    assert row["followup_count"] == 2 and "Seguimiento enviado" in row["notes"]


def test_barrido_de_estancadas(conn):
    assert [a["id"] for a in followup.list_stale(conn, 60)] == ["a_bad"]
    assert followup.resolve_stale(conn, ["a_bad", "a_reply"]) == 1  # a_reply no está en 'sent'
    assert conn.execute("SELECT status FROM applications WHERE id='a_bad'").fetchone()[0] == "no_response"
    assert conn.execute("SELECT status FROM applications WHERE id='a_reply'").fetchone()[0] == "replied"
    assert followup.resolve_stale(conn, []) == 0


@pytest.fixture
def api(conn):
    main.app.dependency_overrides[get_db] = lambda: conn
    yield
    main.app.dependency_overrides.pop(get_db, None)


def test_api_followups_y_marcar(api):
    status, _, body = call("GET", "/api/followups", query="days=10")
    assert status == 200
    data = json.loads(body)
    assert [a["id"] for a in data] == ["a_bad", "a_old", "a_li"] and data[1]["draft"]
    assert call("POST", "/api/applications/a_li/followup", headers=CLIENT)[0] == 200
    assert call("POST", "/api/applications/a_reply/followup", headers=CLIENT)[0] == 400


def test_api_barrido(api):
    status, _, body = call("GET", "/api/followups/stale")
    assert status == 200 and [a["id"] for a in json.loads(body)] == ["a_bad"]
    status, _, body = call("POST", "/api/followups/stale/resolve", headers=CLIENT + [("content-type", "application/json")],
                           body=json.dumps({"ids": ["a_bad"]}).encode())
    assert status == 200 and json.loads(body) == {"resolved": 1}


def test_api_acepta_no_response(api):
    status, _, _ = call("PATCH", "/api/applications/a_li/status", headers=CLIENT, query="status=no_response")
    assert status == 200
