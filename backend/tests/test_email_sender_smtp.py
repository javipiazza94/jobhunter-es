"""SMTP genérico: preset Gmail (comportamiento histórico), servidor propio, contraseña del llavero."""
import smtplib

import pytest

import search_config
from automation import email_sender
from search_config import EmailSettings


class FakeSMTP:
    instances: list["FakeSMTP"] = []

    def __init__(self, host, port, *a, **kw):
        self.host, self.port = host, port
        self.calls: list[tuple] = []
        FakeSMTP.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def ehlo(self):
        self.calls.append(("ehlo",))

    def starttls(self, *a, **kw):
        self.calls.append(("starttls",))

    def login(self, user, password):
        self.calls.append(("login", user, password))

    def sendmail(self, frm, to, msg):
        self.calls.append(("sendmail", frm, to, msg))

    def quit(self):
        self.calls.append(("quit",))


@pytest.fixture(autouse=True)
def _fake(monkeypatch):
    FakeSMTP.instances = []
    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
    for var in ("GMAIL_USER", "GMAIL_APP_PASSWORD"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr("secrets_store.keyring", None)
    # restaura el estado exacto de la config (fijada o no) para no afectar a otros tests
    saved = (search_config._cache, search_config._pinned, search_config._loaded_from)
    yield
    search_config._cache, search_config._pinned, search_config._loaded_from = saved


def _cfg(email: EmailSettings | None):
    base = search_config.get_config()
    search_config.set_config(base.model_copy(update={"email": email or EmailSettings()}))


def _call(name):
    return [c for c in FakeSMTP.instances[0].calls if c[0] == name]


def test_sin_seccion_email_se_comporta_como_siempre(monkeypatch):
    monkeypatch.setenv("GMAIL_USER", "ana@example.com")
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "pw-env")
    _cfg(None)
    ok, mid = email_sender.send_email("hr@acme.example", "Hola", "cuerpo")
    assert ok and mid
    s = FakeSMTP.instances[0]
    assert (s.host, s.port) == ("smtp.gmail.com", 587)
    assert [c[0] for c in s.calls][:3] == ["ehlo", "starttls", "login"]
    assert _call("login") == [("login", "ana@example.com", "pw-env")]
    sent = _call("sendmail")[0]
    assert sent[1] == "ana@example.com" and sent[2] == "hr@acme.example"
    assert "From: ana@example.com\n" in sent[3]


def test_servidor_propio_usa_su_host_puerto_y_usuario(monkeypatch):
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "pw-env")
    _cfg(EmailSettings(preset="custom", smtp_host="mail.example.org", smtp_port=2525,
                       username="bea@example.org"))
    ok, _ = email_sender.send_email("hr@acme.example", "Hola", "cuerpo")
    assert ok
    s = FakeSMTP.instances[0]
    assert (s.host, s.port) == ("mail.example.org", 2525)
    assert _call("login") == [("login", "bea@example.org", "pw-env")]


def test_sin_starttls_no_lo_negocia(monkeypatch):
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "pw")
    _cfg(EmailSettings(preset="custom", smtp_host="m.example.org", smtp_port=25,
                       use_starttls=False, username="c@example.org"))
    assert email_sender.send_email("hr@acme.example", "s", "b")[0]
    assert _call("starttls") == []


def test_sin_contrasena_no_conecta(monkeypatch):
    monkeypatch.setenv("GMAIL_USER", "ana@example.com")
    _cfg(None)
    assert email_sender.send_email("hr@acme.example", "s", "b") == (False, None)
    assert FakeSMTP.instances == []


def test_sin_usuario_no_conecta(monkeypatch):
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "pw")
    _cfg(None)
    assert email_sender.send_email("hr@acme.example", "s", "b") == (False, None)
    assert FakeSMTP.instances == []


def test_from_name_en_la_cabecera(monkeypatch):
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "pw")
    _cfg(EmailSettings(username="ana@example.com", from_name="Ana Ejemplo"))
    assert email_sender.send_email("hr@acme.example", "s", "b")[0]
    sent = _call("sendmail")[0]
    assert sent[1] == "ana@example.com"
    assert "From: Ana Ejemplo <ana@example.com>" in sent[3]


def test_dry_run_no_conecta(monkeypatch):
    monkeypatch.setenv("GMAIL_USER", "a@example.com")
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "pw")
    _cfg(None)
    ok, mid = email_sender.send_email("x@y.example", "s", "b", dry_run=True)
    assert ok and mid.startswith("<dry-run-") and FakeSMTP.instances == []


def test_smtp_settings_resuelve_todo(monkeypatch):
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "pw")
    _cfg(EmailSettings(username="ana@example.com", from_name="Ana"))
    assert email_sender.smtp_settings() == (
        "smtp.gmail.com", 587, True, "ana@example.com", "pw", "Ana <ana@example.com>")


def test_connection_ok_hace_login_sin_enviar(monkeypatch):
    monkeypatch.setenv("GMAIL_USER", "ana@example.com")
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "pw")
    _cfg(None)
    ok, msg = email_sender.check_smtp_connection()
    assert ok and _call("login") and not _call("sendmail")
    assert "pw" not in msg


def test_connection_sin_credenciales(monkeypatch):
    _cfg(None)
    ok, msg = email_sender.check_smtp_connection()
    assert not ok and msg and FakeSMTP.instances == []


def test_connection_error_no_filtra_la_contrasena(monkeypatch):
    monkeypatch.setenv("GMAIL_USER", "ana@example.com")
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "secreto123")

    def boom(self, user, password):
        raise smtplib.SMTPAuthenticationError(535, b"bad credentials secreto123")

    monkeypatch.setattr(FakeSMTP, "login", boom)
    _cfg(None)
    ok, msg = email_sender.check_smtp_connection()
    assert not ok and "secreto123" not in msg


def test_port_465_uses_implicit_tls(monkeypatch):
    """Puerto 465: SMTP_SSL, sin STARTTLS."""
    FakeSMTP.instances.clear()
    monkeypatch.setattr(smtplib, "SMTP_SSL", FakeSMTP)
    monkeypatch.setattr(email_sender, "smtp_settings",
                        lambda: ("smtp.acme.test", 465, True, "u@acme.test", "pw", "u@acme.test"))
    ok, _ = email_sender.check_smtp_connection()
    assert ok
    calls = [c[0] for c in FakeSMTP.instances[-1].calls]
    assert "starttls" not in calls and "login" in calls
