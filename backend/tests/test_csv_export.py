"""La exportación CSV del historial neutraliza las fórmulas (CSV injection): un texto externo que
empiece por = + - @ no debe ejecutarse al abrir el CSV en Excel o LibreOffice."""
import asyncio
import csv
import io
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import database  # noqa: E402
import main  # noqa: E402


@pytest.mark.parametrize("value, expected", [
    ('=HYPERLINK("http://evil.example","clic")', '\'=HYPERLINK("http://evil.example","clic")'),
    ("@SUM(1+1)", "'@SUM(1+1)"),
    ("+cmd|' /C calc'!A0", "'+cmd|' /C calc'!A0"),
    ("-2+3", "'-2+3"),
    ("\t=1+1", "'\t=1+1"),
    ("\r=1+1", "'\r=1+1"),
    # Lo que no es una fórmula se deja como está:
    ("+34 600 123 456", "+34 600 123 456"),   # teléfono
    ("-5", "-5"),
    ("Acme SL", "Acme SL"),
    ("reclutadora@acme.com", "reclutadora@acme.com"),
    ("2026-10-07T10:00:00", "2026-10-07T10:00:00"),
    ("", ""),
    (None, None),
    (7, 7),
])
def test_csv_safe(value, expected):
    assert main._csv_safe(value) == expected


def _csv_de_la_respuesta(resp) -> str:
    async def leer():
        return "".join([c if isinstance(c, str) else c.decode() async for c in resp.body_iterator])
    return asyncio.run(leer())


def test_la_exportacion_csv_neutraliza_las_formulas(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "t.db")
    conn = database.get_conn()
    database.init_db(conn)
    database.record_history(conn, {
        "company_name": '=HYPERLINK("http://evil.example","x")', "email_used": "+34 600 123 456",
        "profile_used": "sap", "notes": "@SUM(A1:A9)",
    })
    resp = main.export_history(format="csv", conn=conn)
    conn.close()
    fila = next(csv.DictReader(io.StringIO(_csv_de_la_respuesta(resp))))
    assert fila["company_name"].startswith("'=HYPERLINK")
    assert fila["notes"] == "'@SUM(A1:A9)"
    assert fila["email_used"] == "+34 600 123 456"  # un teléfono no se altera


def test_la_exportacion_json_no_se_modifica(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "t.db")
    conn = database.get_conn()
    database.init_db(conn)
    database.record_history(conn, {"company_name": "=X", "email_used": "a@b.c", "profile_used": "sap"})
    rows = main.export_history(format="json", conn=conn)
    conn.close()
    assert rows[0]["company_name"] == "=X"  # el JSON no ejecuta nada: se devuelve tal cual
