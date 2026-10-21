import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import database  # noqa: E402
from database import init_db  # noqa: E402
import load_inbox_applications as loader  # noqa: E402

FILE = """# comentario
# ===== ENVIADAS - SAP =====
2026-10-06|Globex Data|Consultant SAP SD||sent|t1
2026-10-06|(por confirmar)|Python Developer (InfoJobs)||sent|t2
2026-10-06|(por confirmar)|Dependiente/a (InfoJobs, 1)||sent|t3
2026-10-06|(por confirmar)|Dependiente/a (InfoJobs, 2)||sent|t4
# ===== ENVIADAS - TRABAJO PUENTE / OTROS (job_kind generic) =====
2026-10-06|Tienda Belmar|(puesto por confirmar; Teamtailor)||sent|t5
# ===== A REVISAR A MANO =====
# 2026-10-05 Tecnoempleo descartada sin oferta (thread x).
"""


def _run(tmp_path, monkeypatch, capsys, text, save=True):
    f = tmp_path / "in.txt"
    f.write_text(text, encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["x", str(f)] + (["--save"] if save else []))
    loader.main()
    return capsys.readouterr().out


def _db(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "t.db", raising=False)
    conn = sqlite3.connect(tmp_path / "t.db")
    conn.row_factory = sqlite3.Row
    init_db(conn)
    return conn


def test_pending_company_bridge_jobs_and_review_list(tmp_path, monkeypatch, capsys):
    conn = _db(tmp_path, monkeypatch)
    out = _run(tmp_path, monkeypatch, capsys, FILE)
    names = {r[0] for r in conn.execute("SELECT name FROM companies")}
    assert "Sin confirmar" in names and "(por confirmar)" not in names
    kinds = dict(conn.execute("SELECT title, job_kind FROM job_offers").fetchall())
    assert kinds["Dependiente/a (InfoJobs, 1)"] == "generic"
    assert kinds["Dependiente/a (InfoJobs, 2)"] == "generic"  # mismo título sin paréntesis, otro hilo: no se funde
    assert kinds["(puesto por confirmar; Teamtailor)"] == "generic"  # sección TRABAJO PUENTE
    assert kinds["Python Developer (InfoJobs)"] is None
    assert conn.execute("SELECT COUNT(*) FROM job_offers WHERE job_kind='generic' AND is_relevant=1").fetchone()[0] == 0
    assert "Por revisar" in out and "[comentario A REVISAR]" in out


def test_dry_run_writes_nothing_and_rerun_is_idempotent(tmp_path, monkeypatch, capsys):
    conn = _db(tmp_path, monkeypatch)
    _run(tmp_path, monkeypatch, capsys, FILE, save=False)
    assert conn.execute("SELECT COUNT(*) FROM applications").fetchone()[0] == 0
    _run(tmp_path, monkeypatch, capsys, FILE)
    n = conn.execute("SELECT COUNT(*) FROM applications").fetchone()[0]
    out = _run(tmp_path, monkeypatch, capsys, FILE)
    assert conn.execute("SELECT COUNT(*) FROM applications").fetchone()[0] == n
    assert "== nuevas: 0" in out


def test_rerunning_a_row_with_unknown_company_and_position_does_not_duplicate_it(tmp_path, monkeypatch, capsys):
    """«(por confirmar)» no tiene palabras útiles: el hilo de Gmail es lo único que identifica la fila. Antes se exigía
    parecido de puesto y cada recarga (el vigilante relee los ficheros conservados) creaba otra copia."""
    conn = _db(tmp_path, monkeypatch)
    text = "2026-10-07|(por confirmar)|(por confirmar)||sent|tX\n2026-10-07|(por confirmar)|(por confirmar)||rejected|tY\n"
    _run(tmp_path, monkeypatch, capsys, text)
    n = conn.execute("SELECT COUNT(*) FROM applications").fetchone()[0]
    assert n == 2
    for _ in range(3):
        out = _run(tmp_path, monkeypatch, capsys, text)
    assert conn.execute("SELECT COUNT(*) FROM applications").fetchone()[0] == n
    assert "== nuevas: 0" in out


def test_sent_never_downgrades_rejected_or_interview(tmp_path, monkeypatch, capsys):
    conn = _db(tmp_path, monkeypatch)
    _run(tmp_path, monkeypatch, capsys, "2026-10-01|ACME|Consultor SAP FI||rejected|a1\n2026-10-01|Beta|Consultor SAP MM||interview|b1\n")
    out = _run(tmp_path, monkeypatch, capsys, "2026-10-06|ACME|Consultor SAP FI||sent|a1\n2026-10-06|Beta|Consultor SAP MM||sent|b1\n")
    st = dict(conn.execute("SELECT c.name, a.status FROM applications a JOIN companies c ON c.id=a.company_id").fetchall())
    assert st == {"ACME": "rejected", "Beta": "interview"}
    assert "== actualizadas: 0" in out


def test_rejected_overrides_sent(tmp_path, monkeypatch, capsys):
    conn = _db(tmp_path, monkeypatch)
    _run(tmp_path, monkeypatch, capsys, "2026-10-01|ACME|Consultor SAP FI||sent|a1\n")
    _run(tmp_path, monkeypatch, capsys, "2026-10-06|ACME|Consultor SAP FI||rejected|a1\n")
    assert conn.execute("SELECT status FROM applications").fetchone()[0] == "rejected"


def test_loaded_file_is_deleted_only_when_nothing_pending(tmp_path, monkeypatch, capsys):
    _db(tmp_path, monkeypatch)
    clean = "2026-10-06|ACME|Consultor SAP FI||sent|a1\n"
    _run(tmp_path, monkeypatch, capsys, clean, save=False)
    assert (tmp_path / "in.txt").exists()  # simulacro: no borra
    out = _run(tmp_path, monkeypatch, capsys, clean)
    assert not (tmp_path / "in.txt").exists() and "borrado in.txt" in out
    out = _run(tmp_path, monkeypatch, capsys, FILE)  # trae un comentario «A REVISAR»
    assert (tmp_path / "in.txt").exists() and "conservado in.txt" in out
    out = _run(tmp_path, monkeypatch, capsys, "2026-10-06|ACME|x||nonsense|z9\n")  # estado inválido
    assert (tmp_path / "in.txt").exists()


def test_portal_rows_without_gmail_thread_are_created_once(tmp_path, monkeypatch, capsys):
    conn = _db(tmp_path, monkeypatch)
    text = "2026-10-06|Zelmar|Teleoperador/a Voltia||interview|portal-zelmar\n"
    _run(tmp_path, monkeypatch, capsys, text)
    row = conn.execute("SELECT a.status, jo.url, c.name FROM applications a JOIN job_offers jo ON jo.id=a.job_offer_id "
                       "JOIN companies c ON c.id=a.company_id").fetchone()
    assert tuple(row) == ("interview", "portal://job-hunter/portal-zelmar", "Zelmar")
    out = _run(tmp_path, monkeypatch, capsys, text)
    assert conn.execute("SELECT COUNT(*) FROM applications").fetchone()[0] == 1 and "== nuevas: 0" in out


def test_cv_profile_sale_de_classify_track_y_el_puente_usa_el_track_aislado(tmp_path, monkeypatch, capsys):
    conn = _db(tmp_path, monkeypatch)
    text = (
        "# ===== ENVIADAS =====\n"
        "2026-10-06|Acme|Consultor SAP FI||sent|c1\n"
        "2026-10-06|Beta|Python developer||sent|c2\n"
        "2026-10-06|Gamma|Camarero||sent|c3\n"
        "2026-10-06|Eps|Analista contable||sent|c5\n"
        "# ===== ENVIADAS - TRABAJO PUENTE =====\n"
        "2026-10-06|Delta|Teleoperador||sent|c4\n"
    )
    _run(tmp_path, monkeypatch, capsys, text)
    rows = dict(conn.execute(
        "SELECT jo.title, a.cv_profile FROM applications a JOIN job_offers jo ON jo.id=a.job_offer_id"
    ).fetchall())
    assert rows["Consultor SAP FI"] == "sap"
    assert rows["Python developer"] == "ia_dev"
    assert rows["Camarero"] == "generic"  # BRIDGE casa 'camarero': antes None, ahora el id del track aislado
    assert rows["Analista contable"] is None  # manual_review -> None
    assert rows["Teleoperador"] == "generic"  # id del track aislado de la config
