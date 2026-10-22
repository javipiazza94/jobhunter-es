"""
database.py — SQLite schema, connection, and UPSERT helpers for Job Hunter Spain.
"""
import sqlite3
import uuid
from collections.abc import Iterator
from datetime import datetime
from config import DB_PATH
from automation.job_key import make_key, slugify

CREATE_SCHEMA = """
CREATE TABLE IF NOT EXISTS companies (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    website         TEXT,
    careers_url     TEXT,
    sector          TEXT,
    city            TEXT,
    country         TEXT DEFAULT 'ES',
    remote_policy   TEXT,
    salary_transparent INTEGER DEFAULT 1,
    linkedin_url    TEXT,
    source          TEXT NOT NULL,
    created_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_companies_sector ON companies(sector);
CREATE INDEX IF NOT EXISTS idx_companies_country ON companies(country);

CREATE TABLE IF NOT EXISTS job_offers (
    id              TEXT PRIMARY KEY,
    company_id      TEXT REFERENCES companies(id),
    title           TEXT NOT NULL,
    description     TEXT,
    location        TEXT,
    salary_min      INTEGER,
    salary_max      INTEGER,
    tech_stack      TEXT,
    url             TEXT UNIQUE,
    source          TEXT,
    posted_at       TEXT,
    is_relevant     INTEGER DEFAULT 0,
    relevance_score REAL DEFAULT 0.0,
    cv_profile      TEXT DEFAULT NULL,  -- LEGADO: ya no se escribe; el perfil se calcula con classify_track
    scraped_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_offers_company ON job_offers(company_id);
CREATE INDEX IF NOT EXISTS idx_offers_relevant ON job_offers(is_relevant);

CREATE TABLE IF NOT EXISTS contacts (
    id              TEXT PRIMARY KEY,
    company_id      TEXT REFERENCES companies(id),
    type            TEXT NOT NULL,
    value           TEXT NOT NULL,
    method          TEXT,
    verified        INTEGER DEFAULT 0,
    created_at      TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_contacts_unique ON contacts(company_id, type, value);

CREATE TABLE IF NOT EXISTS applications (
    id                   TEXT PRIMARY KEY,
    company_id           TEXT,
    job_offer_id         TEXT,
    contact_id           TEXT,
    status               TEXT DEFAULT 'sent',
    method               TEXT,
    sent_at              TEXT,
    cover_letter_used    TEXT,
    cover_letter_edited  TEXT,
    approved_at          TEXT,
    cv_profile           TEXT,
    notes                TEXT
);
CREATE INDEX IF NOT EXISTS idx_apps_company ON applications(company_id);
CREATE INDEX IF NOT EXISTS idx_apps_status ON applications(status);

CREATE TABLE IF NOT EXISTS company_contact_history (
    id              TEXT PRIMARY KEY,
    company_name    TEXT NOT NULL,
    company_domain  TEXT,
    email_used      TEXT NOT NULL,
    profile_used    TEXT NOT NULL,
    sent_at         TEXT NOT NULL,
    outcome         TEXT DEFAULT 'sin_respuesta',
    notes           TEXT,
    application_id  TEXT
);
CREATE INDEX IF NOT EXISTS idx_history_company ON company_contact_history(company_name);
CREATE INDEX IF NOT EXISTS idx_history_email ON company_contact_history(email_used);
CREATE INDEX IF NOT EXISTS idx_history_sent ON company_contact_history(sent_at);
"""


def get_conn(check_same_thread: bool = True) -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=check_same_thread)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=10000")
    return conn


def get_db() -> Iterator[sqlite3.Connection]:
    """Dependencia de FastAPI: una conexión por petición, siempre cerrada (también si el
    endpoint lanza una excepción). check_same_thread=False porque FastAPI ejecuta la
    dependencia y el endpoint (ambos síncronos) en hilos distintos de su pool; la conexión
    solo la usa una petición a la vez."""
    conn = get_conn(check_same_thread=False)
    try:
        yield conn
    finally:
        conn.close()


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(CREATE_SCHEMA)
    _run_migrations(conn)
    conn.commit()


def _migration_001_baseline(conn: sqlite3.Connection) -> None:
    """Todo lo añadido antes de versionar el esquema. Idempotente: ADD COLUMN ignora lo que ya existe."""
    _add_column(conn, "job_offers", "cv_profile", "TEXT DEFAULT NULL")
    _add_column(conn, "applications", "cover_letter_edited", "TEXT")
    _add_column(conn, "applications", "approved_at", "TEXT")
    _add_column(conn, "applications", "cv_profile", "TEXT")
    # v2.0 migrations
    _add_column(conn, "job_offers", "experience_level", "TEXT")
    _add_column(conn, "job_offers", "contract_type", "TEXT")
    _add_column(conn, "job_offers", "posted_date", "TEXT")
    _add_column(conn, "job_offers", "salary_text", "TEXT")
    # SAP Public Cloud tier search (Tier 1/2/3 tracked companies)
    _add_column(conn, "job_offers", "sap_tier", "INTEGER")
    _add_column(conn, "job_offers", "sap_module", "TEXT")
    _add_column(conn, "job_offers", "open_to_junior", "INTEGER")
    # Data Science / IA tier search (Tier 1/2/3 tracked companies)
    _add_column(conn, "job_offers", "ds_tier", "INTEGER")
    _add_column(conn, "job_offers", "ds_category", "TEXT")
    # Descarte de ofertas: 'closed' (ya no acepta solicitudes), 'rejected' (candidatura
    # rechazada), 'expired' (candidatura caducada). Se usa para sacarlas del listado de
    # Ofertas sin borrar la fila y perder el historial de Candidaturas que la referencia.
    _add_column(conn, "job_offers", "discard_status", "TEXT DEFAULT NULL")
    # Trabajos "puente" genéricos (poca experiencia, afines a cv_general). job_kind='generic'
    # los separa del resto; su puntuación va en generic_score para que nunca se mezcle con
    # relevance_score/is_relevant (que alimentan borradores, envíos y notificaciones).
    _add_column(conn, "job_offers", "job_kind", "TEXT DEFAULT NULL")
    _add_column(conn, "job_offers", "generic_score", "REAL")


def _migration_002_application_indexes(conn: sqlite3.Connection) -> None:
    """Índices de candidaturas: «¿esta oferta ya tiene candidatura?» (marcar como enviada, is_applied en el
    listado de ofertas) y la lista de candidaturas ordenada por fecha recorrían la tabla entera."""
    conn.execute("CREATE INDEX IF NOT EXISTS idx_apps_offer ON applications(job_offer_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_apps_sent ON applications(sent_at)")


def _migration_003_review_flags_and_followups(conn: sqlite3.Connection) -> None:
    """Avisos de revisión de la oferta (posting_guard + filtro de idiomas, JSON) y seguimiento de
    candidaturas silenciosas: cuántos recordatorios se han enviado (máx. 2) y cuándo el último."""
    _add_column(conn, "job_offers", "review_flags", "TEXT DEFAULT NULL")
    _add_column(conn, "applications", "followup_count", "INTEGER DEFAULT 0")
    _add_column(conn, "applications", "last_followup_at", "TEXT")


def _migration_004_generic_track_columns(conn: sqlite3.Connection) -> None:
    """sap_tier/ds_tier -> followed_tier (el mejor = el número más bajo) y sap_module/ds_category -> track_tag."""
    _add_column(conn, "job_offers", "followed_tier", "INTEGER")
    _add_column(conn, "job_offers", "track_tag", "TEXT")
    cols = {r[1] for r in conn.execute("PRAGMA table_info(job_offers)")}
    old = [c for c in ("sap_tier", "ds_tier", "sap_module", "ds_category") if c in cols]
    tiers = [c for c in ("sap_tier", "ds_tier") if c in cols]
    tags = [c for c in ("sap_module", "ds_category") if c in cols]
    if tiers:
        # MIN(a, b) escalar devuelve NULL si alguno es NULL; con una sola columna no aplica.
        expr = (f"CASE WHEN {tiers[0]} IS NULL THEN {tiers[1]} WHEN {tiers[1]} IS NULL THEN {tiers[0]} "
                f"ELSE MIN({tiers[0]}, {tiers[1]}) END") if len(tiers) == 2 else tiers[0]
        conn.execute(f"UPDATE job_offers SET followed_tier = {expr}")
    if tags:
        conn.execute(f"UPDATE job_offers SET track_tag = COALESCE({', '.join(tags)})")
    for col in old:
        conn.execute(f"ALTER TABLE job_offers DROP COLUMN {col}")


def _migration_005_job_key(conn: sqlite3.Connection) -> None:
    """Clave canónica empresa+título (automation/job_key.py) para deduplicar la misma oferta llegada por
    fuentes distintas, además de por URL. Se rellena para las ofertas que ya hay."""
    _add_column(conn, "job_offers", "job_key", "TEXT")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_offers_job_key ON job_offers(job_key)")
    rows = conn.execute(
        "SELECT jo.id, jo.title, jo.url, c.name FROM job_offers jo "
        "LEFT JOIN companies c ON c.id = jo.company_id"
    ).fetchall()
    conn.executemany(
        "UPDATE job_offers SET job_key = ? WHERE id = ?",
        [(make_key(r[3] or "", r[1] or "", r[2] or ""), r[0]) for r in rows],
    )


def _migration_006_offer_evaluations(conn: sqlite3.Connection) -> None:
    """Evaluaciones detalladas con IA de las ofertas que marca el usuario (/rank en la app,
    automation/offer_evaluation.py). Tabla aparte: nunca cambian relevance_score ni is_relevant.
    Una fila por oferta (la última evaluación); se borra con la oferta."""
    conn.execute(
        """CREATE TABLE IF NOT EXISTS offer_evaluations (
               offer_id     TEXT PRIMARY KEY REFERENCES job_offers(id) ON DELETE CASCADE,
               verdict      TEXT NOT NULL,
               score_0_100  INTEGER NOT NULL,
               strengths    TEXT NOT NULL DEFAULT '[]',
               gaps         TEXT NOT NULL DEFAULT '[]',
               urgency      TEXT NOT NULL DEFAULT 'unknown',
               expired      INTEGER NOT NULL DEFAULT 0,
               evaluated_at TEXT NOT NULL,
               provider     TEXT NOT NULL
           )"""
    )


# Cada migración lleva la BD de la versión i a la i+1 (PRAGMA user_version) y se ejecuta una sola
# vez, dentro de una transacción: si falla se deshace entera y la versión no sube.
# Para cambiar el esquema: añade una función _migration_00N_… al final de esta lista y NO edites
# las anteriores. Las funciones no deben hacer commit.
MIGRATIONS = [_migration_001_baseline, _migration_002_application_indexes,
              _migration_003_review_flags_and_followups, _migration_004_generic_track_columns,
              _migration_005_job_key, _migration_006_offer_evaluations]


def schema_version(conn: sqlite3.Connection) -> int:
    return conn.execute("PRAGMA user_version").fetchone()[0]


def _run_migrations(conn: sqlite3.Connection) -> None:
    current = schema_version(conn)
    if current > len(MIGRATIONS):
        raise RuntimeError(
            f"La BD está en la versión {current} del esquema, pero este código solo conoce hasta la "
            f"{len(MIGRATIONS)}. Actualiza el código o restaura una copia de la BD."
        )
    for version in range(current, len(MIGRATIONS)):
        conn.execute("BEGIN IMMEDIATE")
        try:
            MIGRATIONS[version](conn)
            conn.execute(f"PRAGMA user_version = {version + 1}")
            conn.execute("COMMIT")
        except BaseException:
            conn.execute("ROLLBACK")
            raise


def discard_offer(conn: sqlite3.Connection, job_offer_id: str, reason: str) -> None:
    """Marca una oferta como descartada (closed/rejected/expired) sin borrarla."""
    conn.execute(
        "UPDATE job_offers SET discard_status=? WHERE id=?", (reason, job_offer_id)
    )
    conn.commit()


def discard_offer_for_application(conn: sqlite3.Connection, application_id: str, reason: str) -> None:
    """Igual que discard_offer, pero resuelve el job_offer_id a partir de la candidatura."""
    row = conn.execute(
        "SELECT job_offer_id FROM applications WHERE id=?", (application_id,)
    ).fetchone()
    if row and row["job_offer_id"]:
        discard_offer(conn, row["job_offer_id"], reason)


def _add_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    try:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
    except sqlite3.OperationalError:
        pass  # column already exists


def _new_id() -> str:
    return str(uuid.uuid4())


def upsert_company(conn: sqlite3.Connection, data: dict) -> str:
    """Insert or update a company. Returns the id used."""
    existing = conn.execute(
        "SELECT id FROM companies WHERE name = ?", (data["name"],)
    ).fetchone()

    if existing:
        cid = existing["id"]
        conn.execute(
            """UPDATE companies SET website=COALESCE(?,website),
               careers_url=COALESCE(?,careers_url),
               sector=COALESCE(?,sector), country=COALESCE(?,country),
               linkedin_url=COALESCE(?,linkedin_url)
               WHERE id=?""",
            (data.get("website"), data.get("careers_url"),
             data.get("sector"), data.get("country"),
             data.get("linkedin_url"), cid),
        )
    else:
        cid = data.get("id") or _new_id()
        conn.execute(
            """INSERT INTO companies
               (id, name, website, careers_url, sector, city, country,
                remote_policy, salary_transparent, linkedin_url, source, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (cid, data["name"], data.get("website"), data.get("careers_url"),
             data.get("sector"), data.get("city"), data.get("country", "ES"),
             data.get("remote_policy"), data.get("salary_transparent", 1),
             data.get("linkedin_url"), data["source"],
             datetime.now().isoformat()),
        )
    conn.commit()
    return cid


def _company_name(conn: sqlite3.Connection, company_id: str | None) -> str:
    row = conn.execute("SELECT name FROM companies WHERE id = ?", (company_id,)).fetchone() if company_id else None
    return (row[0] if row else "") or ""


def _same_posting_by_key(conn: sqlite3.Connection, job_key: str, location: str | None) -> sqlite3.Row | None:
    """Oferta normal ya guardada con la misma empresa+título. La ubicación debe ser compatible (igual, o
    vacía en alguna de las dos): el mismo puesto en dos ciudades son ofertas distintas y puntúan distinto."""
    new_loc = slugify(location or "")
    for row in conn.execute(
        "SELECT id, location FROM job_offers WHERE job_key = ? AND job_kind IS NULL ORDER BY scraped_at",
        (job_key,),
    ):
        old_loc = slugify(row["location"] or "")
        if not new_loc or not old_loc or new_loc == old_loc:
            return row
    return None


def upsert_job_offer(conn: sqlite3.Connection, data: dict) -> str:
    """Insert or update a job offer (unique by URL; también por empresa+título, ver job_key). Returns the id used."""
    existing = conn.execute(
        "SELECT id FROM job_offers WHERE url = ?", (data["url"],)
    ).fetchone()
    job_key = make_key(_company_name(conn, data.get("company_id")), data["title"], data["url"])
    if not existing:
        existing = _same_posting_by_key(conn, job_key, data.get("location"))

    if existing:
        oid = existing["id"]
        conn.execute(
            """UPDATE job_offers SET title=?, description=COALESCE(?,description),
               location=COALESCE(?,location), salary_min=COALESCE(?,salary_min),
               salary_max=COALESCE(?,salary_max), tech_stack=COALESCE(?,tech_stack),
               is_relevant=?, relevance_score=?, scraped_at=?, review_flags=?,
               followed_tier=COALESCE(?,followed_tier)
               WHERE id=?""",
            (data["title"], data.get("description"), data.get("location"),
             data.get("salary_min"), data.get("salary_max"), data.get("tech_stack"),
             int(data.get("is_relevant", 0)), data.get("relevance_score", 0.0),
             datetime.now().isoformat(), data.get("review_flags"),
             data.get("followed_tier"), oid),
        )
    else:
        oid = _new_id()
        conn.execute(
            """INSERT INTO job_offers
               (id, company_id, title, description, location, salary_min, salary_max,
                tech_stack, url, source, posted_at, is_relevant, relevance_score, scraped_at, review_flags,
                followed_tier, job_key)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (oid, data["company_id"], data["title"], data.get("description"),
             data.get("location"), data.get("salary_min"), data.get("salary_max"),
             data.get("tech_stack"), data["url"], data.get("source"),
             data.get("posted_at"), int(data.get("is_relevant", 0)),
             data.get("relevance_score", 0.0), datetime.now().isoformat(), data.get("review_flags"),
             data.get("followed_tier"), job_key),
        )
    conn.commit()
    return oid


def upsert_generic_offer(conn: sqlite3.Connection, data: dict, track_id: str) -> str | None:
    """Guarda una oferta de un track aislado (job_kind=<id del track>, puntuación en generic_score).

    A diferencia de upsert_job_offer NUNCA toca is_relevant/relevance_score y NO pisa filas
    de otra categoría: si la URL ya existe con job_kind NULL (SAP/IA/etc.) se omite y devuelve
    None. is_relevant se fuerza a 0 para que nada del pipeline de borradores/envíos/avisos la
    recoja.
    """
    existing = conn.execute(
        "SELECT id, job_kind FROM job_offers WHERE url = ?", (data["url"],)
    ).fetchone()
    if not existing:
        # El conector de Indeed da un enlace corto distinto en cada búsqueda: dedupe también por
        # empresa + título + ubicación contra filas genéricas ya guardadas.
        existing = conn.execute(
            """SELECT id, job_kind FROM job_offers
               WHERE job_kind=? AND company_id=? AND LOWER(title)=LOWER(?)
                 AND LOWER(COALESCE(location,''))=LOWER(?)""",
            (track_id, data["company_id"], data["title"], data.get("location") or ""),
        ).fetchone()
    now = datetime.now().isoformat()

    if existing:
        if existing["job_kind"] != track_id:
            return None
        conn.execute(
            """UPDATE job_offers SET title=?, description=COALESCE(?,description),
               location=COALESCE(?,location), salary_min=COALESCE(?,salary_min),
               generic_score=?, scraped_at=? WHERE id=?""",
            (data["title"], data.get("description"), data.get("location"),
             data.get("salary_min"), data.get("generic_score"), now, existing["id"]),
        )
        conn.commit()
        return existing["id"]

    oid = _new_id()
    conn.execute(
        """INSERT INTO job_offers
           (id, company_id, title, description, location, salary_min, salary_max,
            url, source, is_relevant, relevance_score, scraped_at, job_kind, generic_score)
           VALUES (?,?,?,?,?,?,?,?,?,0,0.0,?,?,?)""",
        (oid, data["company_id"], data["title"], data.get("description"),
         data.get("location"), data.get("salary_min"), data.get("salary_max"),
         data["url"], data.get("source"), now, track_id, data.get("generic_score")),
    )
    conn.commit()
    return oid


def upsert_contact(conn: sqlite3.Connection, data: dict) -> str:
    existing = conn.execute(
        "SELECT id FROM contacts WHERE company_id=? AND type=? AND value=?",
        (data["company_id"], data["type"], data["value"]),
    ).fetchone()

    if existing:
        return existing["id"]

    cid = _new_id()
    conn.execute(
        """INSERT INTO contacts (id, company_id, type, value, method, verified, created_at)
           VALUES (?,?,?,?,?,?,?)""",
        (cid, data["company_id"], data["type"], data["value"],
         data.get("method"), 0, datetime.now().isoformat()),
    )
    conn.commit()
    return cid


def record_application(conn: sqlite3.Connection, data: dict) -> str:
    aid = _new_id()
    status = data.get("status", "sent")
    sent_at = data.get("sent_at")
    if sent_at is None and status == "sent":
        sent_at = datetime.now().isoformat()
    conn.execute(
        """INSERT INTO applications
           (id, company_id, job_offer_id, contact_id, status, method, sent_at,
            cover_letter_used, cv_profile, notes)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (aid, data["company_id"], data.get("job_offer_id"), data.get("contact_id"),
         status, data["method"], sent_at,
         data.get("cover_letter_used"), data.get("cv_profile"), data.get("notes")),
    )
    conn.commit()
    return aid


def get_pending_offers(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        """SELECT jo.*, c.name as company_name, c.website, c.careers_url
           FROM job_offers jo
           JOIN companies c ON jo.company_id = c.id
           WHERE jo.is_relevant = 1
             AND jo.id NOT IN (SELECT job_offer_id FROM applications WHERE job_offer_id IS NOT NULL)
           ORDER BY jo.relevance_score DESC""",
    ).fetchall()


def get_all_companies(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        """SELECT c.*,
               COUNT(DISTINCT jo.id) as offer_count,
               COUNT(DISTINCT a.id) as application_count
           FROM companies c
           LEFT JOIN job_offers jo ON jo.company_id = c.id
           LEFT JOIN applications a ON a.company_id = c.id
           GROUP BY c.id
           ORDER BY c.name""",
    ).fetchall()


def get_pending_applications(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        """SELECT a.*, c.name as company_name, jo.title as job_title, jo.url as job_url, jo.track_tag as track_tag,
                  ct.value as contact_value, ct.type as contact_type
           FROM applications a
           LEFT JOIN companies c ON a.company_id = c.id
           LEFT JOIN job_offers jo ON a.job_offer_id = jo.id
           LEFT JOIN contacts ct ON a.contact_id = ct.id
           WHERE a.status = 'pending_approval'
           ORDER BY a.rowid DESC""",
    ).fetchall()


def record_history(conn: sqlite3.Connection, data: dict) -> str:
    hid = _new_id()
    conn.execute(
        """INSERT INTO company_contact_history
           (id, company_name, company_domain, email_used, profile_used, sent_at, outcome, notes, application_id)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (hid, data["company_name"], data.get("company_domain", ""),
         data["email_used"], data["profile_used"],
         data.get("sent_at") or datetime.now().isoformat(),
         data.get("outcome", "sin_respuesta"), data.get("notes"),
         data.get("application_id")),
    )
    conn.commit()
    return hid


def get_history(
    conn: sqlite3.Connection,
    company: str | None = None,
    profile: str | None = None,
    outcome: str | None = None,
) -> list[sqlite3.Row]:
    query = "SELECT * FROM company_contact_history"
    conditions: list[str] = []
    params: list = []
    if company:
        conditions.append("company_name LIKE ?")
        params.append(f"%{company}%")
    if profile:
        conditions.append("profile_used = ?")
        params.append(profile)
    if outcome:
        conditions.append("outcome = ?")
        params.append(outcome)
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " ORDER BY sent_at DESC"
    return conn.execute(query, params).fetchall()


def get_dashboard_stats(conn: sqlite3.Connection) -> dict:
    sent_this_week = conn.execute(
        "SELECT COUNT(*) FROM applications WHERE status='sent' AND sent_at > datetime('now', '-7 days')"
    ).fetchone()[0]
    pending = conn.execute(
        "SELECT COUNT(*) FROM applications WHERE status='pending_approval'"
    ).fetchone()[0]
    total_sent = conn.execute(
        "SELECT COUNT(*) FROM applications WHERE status='sent'"
    ).fetchone()[0]
    responded = conn.execute(
        "SELECT COUNT(*) FROM applications WHERE status IN ('replied','interview','offer')"
    ).fetchone()[0]
    sent_by_track = {
        row[0]: row[1]
        for row in conn.execute(
            "SELECT cv_profile, COUNT(*) FROM applications "
            "WHERE status='sent' AND cv_profile IS NOT NULL GROUP BY cv_profile ORDER BY MIN(rowid)"
        )
    }
    return {
        "sent_this_week": sent_this_week,
        "pending_approval": pending,
        "total_sent": total_sent,
        "response_rate": round(responded / total_sent, 2) if total_sent > 0 else 0.0,
        "sent_by_track": sent_by_track,
    }


def stats(conn: sqlite3.Connection) -> dict:
    return {
        "companies": conn.execute("SELECT COUNT(*) FROM companies WHERE source != 'generic'").fetchone()[0],
        "job_offers": conn.execute("SELECT COUNT(*) FROM job_offers WHERE job_kind IS NULL").fetchone()[0],
        "generic_offers": conn.execute("SELECT COUNT(*) FROM job_offers WHERE job_kind IS NOT NULL").fetchone()[0],
        "relevant_offers": conn.execute("SELECT COUNT(*) FROM job_offers WHERE is_relevant=1").fetchone()[0],
        "applications_sent": conn.execute("SELECT COUNT(*) FROM applications WHERE status='sent'").fetchone()[0],
        "contacts_found": conn.execute("SELECT COUNT(*) FROM contacts").fetchone()[0],
    }
