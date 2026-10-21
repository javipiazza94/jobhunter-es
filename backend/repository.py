"""
repository.py — consultas SQL de los endpoints de la API.

main.py solo valida entrada, llama a estas funciones y da forma a la respuesta. Cada función recibe la
conexión de la petición (`Depends(get_db)`) y no abre ni cierra conexiones. Las lecturas devuelven filas
`sqlite3.Row`; las escrituras hacen su propio commit, como hacían los endpoints.
La capa de persistencia de los scrapers y del motor de candidaturas sigue en database.py.
"""
import sqlite3
import uuid

# Columnas por las que la API deja ordenar las ofertas (se interpolan en el SQL: lista cerrada).
OFFER_SORT_COLUMNS = {"relevance_score", "generic_score", "salary_min", "salary_max", "scraped_at", "title"}


# ── Ofertas ────────────────────────────────────────────────────────────────────

def list_offers(
    conn: sqlite3.Connection,
    *,
    relevant_only: bool = False,
    source: str | None = None,
    salary_min: int | None = None,
    salary_max: int | None = None,
    posted_after: str | None = None,
    min_score: float | None = None,
    experience_level: str | None = None,
    contract_type: str | None = None,
    stack: str | None = None,
    job_kind: str | None = None,
    tier_first: bool = False,
    include_discarded: bool = False,
    sort_by: str = "relevance_score",
    sort_dir: str = "desc",
    limit: int | None = None,
) -> list[sqlite3.Row]:
    """Ofertas con empresa y marca `is_applied`. `limit` es el tope en SQL (None = sin tope).

    `job_kind`: id de un track aislado (None = ofertas de los tracks estándar). `tier_first` ordena por tier.
    """
    query = (
        "SELECT jo.*, c.name as company_name, "
        "CASE WHEN a.job_offer_id IS NOT NULL THEN 1 ELSE 0 END as is_applied "
        "FROM job_offers jo "
        "JOIN companies c ON jo.company_id = c.id "
        "LEFT JOIN (SELECT DISTINCT job_offer_id FROM applications) a ON a.job_offer_id = jo.id"
    )
    conditions: list[str] = []
    params: list = []
    if not include_discarded:
        conditions.append("jo.discard_status IS NULL")
    if relevant_only:
        conditions.append("jo.is_relevant = 1")
    if source:
        conditions.append("jo.source = ?")
        params.append(source)
    if salary_min is not None:
        conditions.append("jo.salary_min >= ?")
        params.append(salary_min)
    if salary_max is not None:
        conditions.append("(jo.salary_max <= ? OR (jo.salary_max IS NULL AND jo.salary_min <= ?))")
        params.extend([salary_max, salary_max])
    if posted_after:
        conditions.append("jo.scraped_at >= ?")
        params.append(posted_after)
    if min_score is not None:
        conditions.append("jo.relevance_score >= ?")
        params.append(min_score)
    if experience_level:
        conditions.append("jo.experience_level = ?")
        params.append(experience_level)
    if contract_type:
        conditions.append("jo.contract_type = ?")
        params.append(contract_type)
    # Las ofertas de un track aislado (job_kind = id del track) tienen su pestaña; fuera de cualquier otro listado.
    if job_kind:
        conditions.append("jo.job_kind = ?")
        params.append(job_kind)
    else:
        conditions.append("jo.job_kind IS NULL")
    if stack:
        for term in (s.strip() for s in stack.split(",") if s.strip()):
            conditions.append("(LOWER(jo.title || ' ' || COALESCE(jo.description,'') || ' ' || COALESCE(jo.tech_stack,'')) LIKE ?)")
            params.append(f"%{term.lower()}%")
    if conditions:
        query += " WHERE " + " AND ".join(conditions)

    sort_col = sort_by if sort_by in OFFER_SORT_COLUMNS else "relevance_score"
    direction = "ASC" if sort_dir.lower() == "asc" else "DESC"
    if tier_first:
        # Empresas seguidas primero (tier 1, 2…; sin tier al final) y dentro de cada tier por score.
        query += " ORDER BY jo.followed_tier IS NULL, jo.followed_tier ASC, jo.relevance_score DESC"
    else:
        query += f" ORDER BY jo.{sort_col} {direction}"
    if limit is not None:
        query += f" LIMIT {int(limit)}"
    return conn.execute(query, params).fetchall()


def get_offer(conn: sqlite3.Connection, offer_id: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM job_offers WHERE id = ?", (offer_id,)).fetchone()


def offer_exists(conn: sqlite3.Connection, offer_id: str) -> bool:
    return conn.execute("SELECT id FROM job_offers WHERE id = ?", (offer_id,)).fetchone() is not None


def restore_offer(conn: sqlite3.Connection, offer_id: str) -> None:
    conn.execute("UPDATE job_offers SET discard_status=NULL WHERE id=?", (offer_id,))
    conn.commit()


# ── Candidaturas ───────────────────────────────────────────────────────────────

def find_application_id_for_offer(conn: sqlite3.Connection, offer_id: str) -> str | None:
    row = conn.execute("SELECT id FROM applications WHERE job_offer_id = ?", (offer_id,)).fetchone()
    return row["id"] if row else None


def create_manual_application(conn: sqlite3.Connection, offer: sqlite3.Row, cv_profile: str | None) -> str:
    """Registra una candidatura marcada a mano como enviada y devuelve su id."""
    app_id = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO applications (id, company_id, job_offer_id, status, method, sent_at, cv_profile) "
        "VALUES (?, ?, ?, 'sent', 'manual', datetime('now'), ?)",
        (app_id, offer["company_id"], offer["id"], cv_profile),
    )
    conn.commit()
    return app_id


def delete_manual_application(conn: sqlite3.Connection, offer_id: str) -> None:
    conn.execute("DELETE FROM applications WHERE job_offer_id = ? AND method = 'manual'", (offer_id,))
    conn.commit()


def list_applications(conn: sqlite3.Connection, status: str | None = None) -> list[sqlite3.Row]:
    query = """SELECT a.*, c.name as company_name,
                      jo.title as job_title, jo.url as offer_url,
                      jo.source as offer_source, jo.location as offer_location,
                      jo.relevance_score
               FROM applications a
               LEFT JOIN companies c ON a.company_id = c.id
               LEFT JOIN job_offers jo ON a.job_offer_id = jo.id"""
    order_by = " ORDER BY (a.sent_at IS NULL) ASC, a.sent_at DESC"
    if status:
        return conn.execute(query + " WHERE a.status = ?" + order_by, [status]).fetchall()
    return conn.execute(query + order_by).fetchall()


def set_application_status(conn: sqlite3.Connection, app_id: str, status: str) -> None:
    conn.execute("UPDATE applications SET status=? WHERE id=?", (status, app_id))
    conn.commit()


def set_cover_letter(conn: sqlite3.Connection, app_id: str, text: str) -> None:
    conn.execute("UPDATE applications SET cover_letter_edited=? WHERE id=?", (text, app_id))
    conn.commit()


# ── Contactos ──────────────────────────────────────────────────────────────────

def list_contacts(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute("""
        SELECT ct.*, c.name as company_name, c.website as company_website
        FROM contacts ct
        LEFT JOIN companies c ON c.id = ct.company_id
        ORDER BY ct.created_at DESC
    """).fetchall()


def list_relevant_offers_for_contacts(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute("""
        SELECT id, company_id, title, url, relevance_score, location
        FROM job_offers WHERE is_relevant = 1
        ORDER BY relevance_score DESC
    """).fetchall()


# ── Historial ──────────────────────────────────────────────────────────────────

def set_history_outcome(conn: sqlite3.Connection, history_id: str, outcome: str) -> None:
    conn.execute("UPDATE company_contact_history SET outcome=? WHERE id=?", (outcome, history_id))
    conn.commit()


def list_history_for_export(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM company_contact_history ORDER BY sent_at DESC").fetchall()
