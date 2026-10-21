import sys
import sqlite3
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))


def _make_conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def test_init_db_creates_all_tables():
    from database import init_db
    conn = _make_conn()
    init_db(conn)
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    assert "companies" in tables
    assert "job_offers" in tables
    assert "contacts" in tables
    assert "applications" in tables
    assert "company_contact_history" in tables
    conn.close()


def test_init_db_is_idempotent():
    from database import init_db
    conn = _make_conn()
    init_db(conn)
    init_db(conn)  # second call must not raise
    conn.close()


def test_applications_has_new_columns():
    from database import init_db
    conn = _make_conn()
    init_db(conn)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(applications)").fetchall()}
    assert "cv_profile" in cols
    assert "cover_letter_edited" in cols
    assert "approved_at" in cols
    conn.close()


def test_job_offers_has_cv_profile_column():
    from database import init_db
    conn = _make_conn()
    init_db(conn)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(job_offers)").fetchall()}
    assert "cv_profile" in cols
    conn.close()


def test_record_application_draft_has_null_sent_at():
    from database import init_db, record_application
    conn = _make_conn()
    init_db(conn)
    conn.execute("INSERT INTO companies (id,name,source,created_at) VALUES ('c1','ACME','test','2026-01-01')")
    conn.commit()
    aid = record_application(conn, {
        "company_id": "c1",
        "method": "email",
        "status": "pending_approval",
        "cover_letter_used": "test letter",
        "cv_profile": "ia_dev",
    })
    row = conn.execute("SELECT * FROM applications WHERE id=?", (aid,)).fetchone()
    assert row["status"] == "pending_approval"
    assert row["sent_at"] is None
    assert row["cv_profile"] == "ia_dev"
    conn.close()


def test_record_application_sent_has_sent_at():
    from database import init_db, record_application
    conn = _make_conn()
    init_db(conn)
    conn.execute("INSERT INTO companies (id,name,source,created_at) VALUES ('c1','ACME','test','2026-01-01')")
    conn.commit()
    aid = record_application(conn, {
        "company_id": "c1",
        "method": "email",
        "status": "sent",
        "cover_letter_used": "test letter",
    })
    row = conn.execute("SELECT * FROM applications WHERE id=?", (aid,)).fetchone()
    assert row["status"] == "sent"
    assert row["sent_at"] is not None
    conn.close()


def test_record_history_inserts_row():
    from database import init_db, record_history
    conn = _make_conn()
    init_db(conn)
    hid = record_history(conn, {
        "company_name": "ACME",
        "company_domain": "acme.es",
        "email_used": "jobs@acme.es",
        "profile_used": "ia_dev",
        "application_id": "app-1",
    })
    row = conn.execute("SELECT * FROM company_contact_history WHERE id=?", (hid,)).fetchone()
    assert row["company_name"] == "ACME"
    assert row["profile_used"] == "ia_dev"
    assert row["outcome"] == "sin_respuesta"
    conn.close()


def test_get_dashboard_stats_returns_all_keys():
    from database import init_db, get_dashboard_stats
    conn = _make_conn()
    init_db(conn)
    result = get_dashboard_stats(conn)
    for key in ("sent_this_week", "pending_approval", "total_sent", "response_rate", "sent_by_track"):
        assert key in result
    conn.close()
