"""Envío de candidaturas: nunca duplicar un email, nunca enviarlo incompleto y nunca perder el motivo de un fallo."""
import smtplib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import database  # noqa: E402
from automation import application_engine as engine  # noqa: E402
from automation import email_sender  # noqa: E402
from automation.email_sender import EmailSendError  # noqa: E402

APPLICATION_ID = "app1"


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
        "INSERT INTO applications (id,company_id,job_offer_id,contact_id,status,method,cover_letter_used,cv_profile) "
        f"VALUES ('{APPLICATION_ID}','c1','o1','ct1','pending_approval','email','Carta','general')"
    )
    connection.commit()
    monkeypatch.setattr(engine, "get_conn", database.get_conn)
    monkeypatch.setattr(engine, "_load_profile", lambda: {"personal": {"name": "Test"}})
    monkeypatch.setattr(engine, "select_cv", lambda *a, **k: None)
    monkeypatch.setattr(engine, "cover_letter_docx_for", lambda *a, **k: None)
    monkeypatch.setattr(engine, "get_application_attachments", lambda _id: (None, None))
    yield connection
    connection.close()


def _status(conn) -> str:
    return conn.execute("SELECT status FROM applications WHERE id=?", (APPLICATION_ID,)).fetchone()[0]


def _event_kinds(conn) -> list[str]:
    rows = conn.execute("SELECT kind FROM application_events WHERE application_id=? ORDER BY id", (APPLICATION_ID,)).fetchall()
    return [r[0] for r in rows]


class _Deliveries:
    """Sustituto de deliver_email que cuenta las llamadas."""

    def __init__(self, error: EmailSendError | None = None):
        self.calls = 0
        self.error = error

    def __call__(self, **kwargs):
        self.calls += 1
        if self.error:
            raise self.error
        return "<msg-1@jobhunter>"


def test_envio_correcto_marca_sent_y_deja_traza(conn, monkeypatch):
    deliveries = _Deliveries()
    monkeypatch.setattr(engine, "deliver_email", deliveries)

    assert engine._send_approved(conn, APPLICATION_ID) is True

    assert _status(conn) == "sent"
    assert deliveries.calls == 1
    history = conn.execute("SELECT email_used FROM company_contact_history WHERE application_id=?", (APPLICATION_ID,)).fetchall()
    assert [r[0] for r in history] == ["jobs@acme.es"]


def test_fallo_smtp_devuelve_la_candidatura_a_pendiente_con_el_motivo(conn, monkeypatch):
    monkeypatch.setattr(engine, "deliver_email", _Deliveries(EmailSendError("SMTPAuthenticationError")))

    assert engine._send_approved(conn, APPLICATION_ID) is False

    assert _status(conn) == "pending_approval"
    notes = conn.execute("SELECT notes FROM applications WHERE id=?", (APPLICATION_ID,)).fetchone()[0]
    assert "SMTPAuthenticationError" in notes


def test_si_falla_el_registro_tras_enviar_no_se_reenvia(conn, monkeypatch, caplog):
    deliveries = _Deliveries()
    monkeypatch.setattr(engine, "deliver_email", deliveries)

    def history_down(*_args, **_kwargs):
        raise RuntimeError("database is locked")

    monkeypatch.setattr(engine, "record_history", history_down)

    with pytest.raises(RuntimeError):
        engine._send_approved(conn, APPLICATION_ID)

    assert _status(conn) == "sending"  # el email salió: jamás vuelve a pending_approval
    assert "<msg-1@jobhunter>" in caplog.text  # el message_id queda en el log para reconciliar a mano
    with pytest.raises(ValueError):
        engine._send_approved(conn, APPLICATION_ID)
    assert deliveries.calls == 1


def test_una_candidatura_ya_en_envio_no_se_vuelve_a_enviar(conn, monkeypatch):
    deliveries = _Deliveries()
    monkeypatch.setattr(engine, "deliver_email", deliveries)
    conn.execute("UPDATE applications SET status='sending' WHERE id=?", (APPLICATION_ID,))
    conn.commit()

    with pytest.raises(ValueError):
        engine._send_approved(conn, APPLICATION_ID)

    assert deliveries.calls == 0


@pytest.fixture
def smtp_configured(monkeypatch):
    monkeypatch.setattr(email_sender, "smtp_settings", lambda: ("smtp.test", 587, True, "me@test", "s3cret-pass", "me@test"))


def test_adjunto_inexistente_aborta_antes_de_conectar(smtp_configured, monkeypatch, tmp_path):
    def must_not_connect(*_args):
        raise AssertionError("no debe abrirse conexión SMTP")

    monkeypatch.setattr(email_sender, "_connect", must_not_connect)

    with pytest.raises(EmailSendError, match="cv.pdf"):
        email_sender.deliver_email("hr@acme.es", "Asunto", "Cuerpo", cv_path=tmp_path / "cv.pdf")


def test_el_motivo_del_fallo_smtp_no_filtra_credenciales(smtp_configured, monkeypatch):
    def refuse(*_args):
        raise smtplib.SMTPAuthenticationError(535, b"s3cret-pass rechazada")

    monkeypatch.setattr(email_sender, "_connect", refuse)

    with pytest.raises(EmailSendError) as caught:
        email_sender.deliver_email("hr@acme.es", "Asunto", "Cuerpo")

    assert caught.value.reason == "SMTPAuthenticationError"
    assert "s3cret" not in str(caught.value)


def test_send_email_mantiene_su_contrato_de_tupla(smtp_configured, monkeypatch):
    def refuse(*_args):
        raise TimeoutError()

    monkeypatch.setattr(email_sender, "_connect", refuse)

    assert email_sender.send_email("hr@acme.es", "Asunto", "Cuerpo") == (False, None)
