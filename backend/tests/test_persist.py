import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from database import init_db  # noqa: E402
from scraper.persist import save_scored_offers  # noqa: E402


def _conn(tmp_path, monkeypatch):
    import database
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "t.db", raising=False)
    conn = sqlite3.connect(tmp_path / "t.db")
    conn.row_factory = sqlite3.Row
    init_db(conn)
    return conn


def test_save_scored_offers_reuses_company_and_skips_offers_without_url(tmp_path, monkeypatch):
    conn = _conn(tmp_path, monkeypatch)
    offers = [
        {"title": "SAP S/4HANA Public Cloud Consultant", "company_name": "ACME", "url": "https://x/1", "location": "Villanova"},
        {"title": "Otro puesto", "company_name": "ACME", "url": "https://x/2", "location": "Villanova"},
        {"title": "Sin url", "company_name": "ACME", "url": None},
    ]
    assert save_scored_offers(conn, offers, "test") == 2
    assert conn.execute("SELECT COUNT(*) FROM companies").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM job_offers").fetchone()[0] == 2
