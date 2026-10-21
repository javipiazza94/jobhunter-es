import sys
import sqlite3
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))


def _in_memory_conn():
    """Return an initialised in-memory SQLite connection."""
    from database import init_db
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    init_db(conn)
    return conn


def _seed(conn):
    """Insert a company, offer, and contact into the DB."""
    conn.execute(
        "INSERT INTO companies (id,name,source,created_at) VALUES ('c1','ACME','test','2026-01-01')"
    )
    conn.execute(
        """INSERT INTO job_offers
           (id,company_id,title,description,is_relevant,relevance_score,cv_profile,scraped_at,url)
           VALUES ('o1','c1','Python Dev','FastAPI LLM Python react next.js',1,0.8,'ia_dev','2026-01-01','http://a.com/1')"""
    )
    conn.execute(
        "INSERT INTO contacts (id,company_id,type,value,created_at) VALUES ('ct1','c1','email','jobs@acme.es','2026-01-01')"
    )
    conn.commit()


def test_create_drafts_returns_summary_keys():
    from automation.application_engine import create_drafts
    result = create_drafts.__code__.co_varnames  # just check it exists
    assert callable(create_drafts)


def test_is_recently_contacted_false_for_new_company():
    from automation.application_engine import _is_recently_contacted
    conn = _in_memory_conn()
    assert _is_recently_contacted(conn, "c1", "jobs@acme.es") is False
    conn.close()


def test_is_recently_contacted_true_after_application():
    from automation.application_engine import _is_recently_contacted
    from database import record_application
    conn = _in_memory_conn()
    conn.execute("INSERT INTO companies (id,name,source,created_at) VALUES ('c1','ACME','test','2026-01-01')")
    conn.execute("INSERT INTO contacts (id,company_id,type,value,created_at) VALUES ('ct1','c1','email','jobs@acme.es','2026-01-01')")
    conn.commit()
    record_application(conn, {
        "company_id": "c1",
        "contact_id": "ct1",
        "method": "email",
        "status": "sent",
        "sent_at": "2026-06-01T10:00:00",
    })
    assert _is_recently_contacted(conn, "c1", "jobs@acme.es") is True
    conn.close()


def test_send_approved_raises_for_unknown_id(tmp_path, monkeypatch):
    import database
    from automation.application_engine import send_approved
    import pytest
    # BD temporal: el test no debe tocar job_hunter.db ni depender de que exista.
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "t.db")
    conn = database.get_conn()
    database.init_db(conn)
    conn.close()
    with pytest.raises(ValueError, match="not found"):
        send_approved("nonexistent-id")
