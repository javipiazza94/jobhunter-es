import sqlite3

from database import init_db, upsert_company, upsert_generic_offer, upsert_job_offer


def _conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_db(conn)
    return conn


def _offer(cid, url, title="Camarero", location="Villanova"):
    return {"company_id": cid, "title": title, "location": location, "url": url,
            "source": "indeed", "generic_score": 0.9}


def test_same_posting_with_different_url_does_not_duplicate():
    conn = _conn()
    cid = upsert_company(conn, {"name": "Domestiko", "source": "generic"})
    first = upsert_generic_offer(conn, _offer(cid, "https://to.indeed.com/aaa"), "generic")
    second = upsert_generic_offer(conn, _offer(cid, "https://to.indeed.com/bbb"), "generic")
    assert first == second
    assert conn.execute("SELECT COUNT(*) FROM job_offers").fetchone()[0] == 1


def test_generic_never_overwrites_other_category_or_relevance():
    conn = _conn()
    cid = upsert_company(conn, {"name": "Acme Robotics", "source": "sap"})
    upsert_job_offer(conn, {"company_id": cid, "title": "SAP FI", "url": "https://x/1",
                            "is_relevant": 1, "relevance_score": 0.8})
    assert upsert_generic_offer(conn, _offer(cid, "https://x/1", title="SAP FI"), "generic") is None
    row = conn.execute("SELECT is_relevant, relevance_score, job_kind FROM job_offers").fetchone()
    assert (row["is_relevant"], row["relevance_score"], row["job_kind"]) == (1, 0.8, None)


def test_generic_rows_are_never_relevant():
    conn = _conn()
    cid = upsert_company(conn, {"name": "Vexcorp", "source": "generic"})
    upsert_generic_offer(conn, _offer(cid, "https://x/2"), "generic")
    row = conn.execute("SELECT is_relevant, relevance_score, job_kind, generic_score FROM job_offers").fetchone()
    assert (row["is_relevant"], row["relevance_score"], row["job_kind"], row["generic_score"]) == (0, 0.0, "generic", 0.9)
