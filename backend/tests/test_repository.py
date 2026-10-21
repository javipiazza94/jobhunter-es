"""repository.py: las consultas que antes vivían dentro de los endpoints. BD temporal, nunca la real."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import database  # noqa: E402
import repository  # noqa: E402


@pytest.fixture
def conn(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "t.db")
    c = database.get_conn()
    database.init_db(c)
    cid = database.upsert_company(c, {"name": "ACME", "source": "test"})
    rows = [
        # id, título, score, fuente, tipo, relevante, descartada, sueldo mínimo
        ("o1", "Consultor SAP PS", 0.9, "tecnoempleo", None, 1, None, 30000),
        ("o2", "Dev Python", 0.5, "infojobs", None, 0, None, 20000),
        ("o3", "Dev Java", 0.7, "tecnoempleo", None, 1, "expired", 25000),
        ("o4", "Dependiente", 0.1, "infojobs", "generic", 0, None, None),
    ]
    for id_, title, score, source, kind, relevant, discarded, smin in rows:
        c.execute(
            "INSERT INTO job_offers (id, company_id, title, description, source, job_kind, is_relevant, "
            "discard_status, salary_min, relevance_score, scraped_at) VALUES (?,?,?,?,?,?,?,?,?,?,datetime('now'))",
            (id_, cid, title, f"stack de {title}", source, kind, relevant, discarded, smin, score),
        )
    c.commit()
    yield c
    c.close()


def _ids(rows):
    return [r["id"] for r in rows]


# ── list_offers ────────────────────────────────────────────────────────────────

def test_por_defecto_excluye_descartadas_y_trabajos_puente(conn):
    assert _ids(repository.list_offers(conn)) == ["o1", "o2"]  # orden: score desc


def test_los_trabajos_puente_solo_salen_con_su_filtro(conn):
    assert _ids(repository.list_offers(conn, job_kind="generic")) == ["o4"]


def test_incluir_descartadas(conn):
    assert set(_ids(repository.list_offers(conn, include_discarded=True))) == {"o1", "o2", "o3"}


def test_filtros_de_fuente_score_sueldo_y_relevancia(conn):
    assert _ids(repository.list_offers(conn, source="infojobs")) == ["o2"]
    assert _ids(repository.list_offers(conn, min_score=0.8)) == ["o1"]
    assert _ids(repository.list_offers(conn, salary_min=25000)) == ["o1"]
    assert _ids(repository.list_offers(conn, relevant_only=True)) == ["o1"]


def test_filtro_de_stack_y_orden_por_columna_valida(conn):
    assert _ids(repository.list_offers(conn, stack="python")) == ["o2"]
    assert _ids(repository.list_offers(conn, sort_by="title", sort_dir="asc")) == ["o1", "o2"]
    assert _ids(repository.list_offers(conn, sort_by="title", sort_dir="desc")) == ["o2", "o1"]


def test_una_columna_de_orden_no_permitida_cae_al_score_sin_inyectar_sql(conn):
    rows = repository.list_offers(conn, sort_by="title; DROP TABLE job_offers", sort_dir="desc")
    assert _ids(rows) == ["o1", "o2"]
    assert conn.execute("SELECT COUNT(*) FROM job_offers").fetchone()[0] == 4


def test_limite_en_sql(conn):
    assert _ids(repository.list_offers(conn, limit=1)) == ["o1"]


def test_is_applied_marca_las_ofertas_con_candidatura(conn):
    repository.create_manual_application(conn, repository.get_offer(conn, "o2"), "ia_dev")
    por_id = {r["id"]: r["is_applied"] for r in repository.list_offers(conn)}
    assert por_id == {"o1": 0, "o2": 1}


# ── candidaturas ───────────────────────────────────────────────────────────────

def test_ciclo_de_candidatura_manual(conn):
    oferta = repository.get_offer(conn, "o1")
    assert repository.find_application_id_for_offer(conn, "o1") is None
    app_id = repository.create_manual_application(conn, oferta, "sap")
    assert repository.find_application_id_for_offer(conn, "o1") == app_id
    fila = conn.execute("SELECT status, method, cv_profile FROM applications WHERE id=?", (app_id,)).fetchone()
    assert (fila["status"], fila["method"], fila["cv_profile"]) == ("sent", "manual", "sap")
    repository.delete_manual_application(conn, "o1")
    assert repository.find_application_id_for_offer(conn, "o1") is None


def test_borrar_la_marca_no_toca_candidaturas_que_no_son_manuales(conn):
    conn.execute("INSERT INTO applications (id, company_id, job_offer_id, status, method, sent_at) "
                 "SELECT 'a-auto', company_id, id, 'sent', 'email', datetime('now') FROM job_offers WHERE id='o1'")
    conn.commit()
    repository.delete_manual_application(conn, "o1")
    assert repository.find_application_id_for_offer(conn, "o1") == "a-auto"


def test_listar_candidaturas_con_filtro_de_estado_y_datos_de_la_oferta(conn):
    repository.create_manual_application(conn, repository.get_offer(conn, "o1"), "sap")
    todas = repository.list_applications(conn)
    assert len(todas) == 1 and todas[0]["company_name"] == "ACME" and todas[0]["job_title"] == "Consultor SAP PS"
    repository.set_application_status(conn, todas[0]["id"], "interview")
    assert repository.list_applications(conn, "sent") == []
    assert len(repository.list_applications(conn, "interview")) == 1


def test_carta_editada(conn):
    app_id = repository.create_manual_application(conn, repository.get_offer(conn, "o1"), "sap")
    repository.set_cover_letter(conn, app_id, "Hola")
    assert conn.execute("SELECT cover_letter_edited FROM applications WHERE id=?", (app_id,)).fetchone()[0] == "Hola"


def test_restaurar_una_oferta_descartada(conn):
    assert repository.offer_exists(conn, "o3") and not repository.offer_exists(conn, "nope")
    repository.restore_offer(conn, "o3")
    assert "o3" in _ids(repository.list_offers(conn))


# ── contactos e historial ──────────────────────────────────────────────────────

def test_contactos_con_empresa_y_ofertas_relevantes(conn):
    cid = conn.execute("SELECT id FROM companies").fetchone()["id"]
    database.upsert_contact(conn, {"company_id": cid, "type": "email", "value": "rrhh@acme.test"})
    contactos = repository.list_contacts(conn)
    assert contactos[0]["company_name"] == "ACME"
    assert [o["id"] for o in repository.list_relevant_offers_for_contacts(conn)] == ["o1", "o3"]


def test_resultado_del_historial_y_exportacion(conn):
    cid = conn.execute("SELECT id FROM companies").fetchone()["id"]
    hid = database.record_history(conn, {"company_name": "ACME", "email_used": "x@acme.test", "profile_used": "sap"})
    repository.set_history_outcome(conn, hid, "entrevista")
    filas = repository.list_history_for_export(conn)
    assert [f["outcome"] for f in filas] == ["entrevista"]
