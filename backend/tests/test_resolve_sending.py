"""Candidaturas atascadas en 'sending': la persona confirma si el email salió o no, y el sistema lo refleja."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import database  # noqa: E402
from automation import application_engine as engine  # noqa: E402
from tests.asgi_client import call  # noqa: E402

APPLICATION_ID = "app1"
CLIENT = ("x-jh-client", "dashboard")


@pytest.fixture
def conn(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "t.db")
    connection = database.get_conn()
    database.init_db(connection)
    connection.execute("INSERT INTO companies (id,name,source,created_at) VALUES ('c1','ACME','test','2026-01-01')")
    connection.execute(
        "INSERT INTO job_offers (id,company_id,title,description,is_relevant,relevance_score,cv_profile,scraped_at,url) "
        "VALUES ('o1','c1','Python Dev','x',1,0.8,'general','2026-01-01','http://a.com/1')"
    )
    connection.execute("INSERT INTO contacts (id,company_id,type,value,created_at) VALUES ('ct1','c1','email','jobs@acme.es','2026-01-01')")
    connection.execute(
        "INSERT INTO applications (id,company_id,job_offer_id,contact_id,status,method,cv_profile) "
        f"VALUES ('{APPLICATION_ID}','c1','o1','ct1','sending','email','general')"
    )
    connection.commit()
    monkeypatch.setattr(engine, "get_conn", database.get_conn)
    yield connection
    connection.close()


def _status(conn) -> str:
    return conn.execute("SELECT status FROM applications WHERE id=?", (APPLICATION_ID,)).fetchone()[0]


def test_confirmar_que_si_salio_la_marca_enviada_y_la_anota_en_el_historial(conn):
    assert engine.resolve_unconfirmed_send(APPLICATION_ID, was_sent=True) == "sent"

    assert _status(conn) == "sent"
    assert conn.execute("SELECT sent_at FROM applications WHERE id=?", (APPLICATION_ID,)).fetchone()[0]
    history = conn.execute("SELECT email_used FROM company_contact_history WHERE application_id=?", (APPLICATION_ID,)).fetchall()
    assert [r[0] for r in history] == ["jobs@acme.es"]  # cuenta para el enfriamiento de recontacto


def test_confirmar_que_no_salio_la_devuelve_a_pendiente_sin_historial(conn):
    assert engine.resolve_unconfirmed_send(APPLICATION_ID, was_sent=False) == "pending_approval"

    assert _status(conn) == "pending_approval"
    assert conn.execute("SELECT COUNT(*) FROM company_contact_history").fetchone()[0] == 0


@pytest.mark.parametrize("current", ["pending_approval", "sent", "rejected"])
def test_solo_se_resuelven_las_que_estan_en_sending(conn, current):
    conn.execute("UPDATE applications SET status=? WHERE id=?", (current, APPLICATION_ID))
    conn.commit()

    with pytest.raises(ValueError, match="sending"):
        engine.resolve_unconfirmed_send(APPLICATION_ID, was_sent=True)

    assert _status(conn) == current


def test_una_candidatura_inexistente_lanza_value_error(conn):
    with pytest.raises(ValueError):
        engine.resolve_unconfirmed_send("no-existe", was_sent=False)


def test_api_resuelve_y_devuelve_el_nuevo_estado(conn):
    status, _headers, body = call("POST", f"/api/applications/{APPLICATION_ID}/resolve-sending",
                                  headers=[CLIENT], query="sent=true")

    assert status == 200
    assert '"status":"sent"' in body.replace(" ", "")
    assert _status(conn) == "sent"


def test_api_rechaza_una_candidatura_que_no_esta_en_sending(conn):
    conn.execute("UPDATE applications SET status='pending_approval' WHERE id=?", (APPLICATION_ID,))
    conn.commit()

    status, _headers, _body = call("POST", f"/api/applications/{APPLICATION_ID}/resolve-sending",
                                   headers=[CLIENT], query="sent=true")

    assert status == 400
    assert _status(conn) == "pending_approval"


def test_api_lista_las_atascadas_por_estado(conn):
    status, _headers, body = call("GET", "/api/applications", headers=[CLIENT], query="status=sending")

    assert status == 200
    assert APPLICATION_ID in body
