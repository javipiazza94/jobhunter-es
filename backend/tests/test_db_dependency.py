"""get_db: una conexión por petición, cerrada siempre; main.py no abre conexiones a mano."""
import ast
import sqlite3
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import database  # noqa: E402


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "t.db")
    conn = database.get_conn()
    database.init_db(conn)
    conn.close()


def _is_closed(conn: sqlite3.Connection) -> bool:
    try:
        conn.execute("SELECT 1")
    except sqlite3.ProgrammingError:
        return True
    return False


def test_get_db_cierra_la_conexion_al_terminar(tmp_db):
    gen = database.get_db()
    conn = next(gen)
    assert not _is_closed(conn)
    with pytest.raises(StopIteration):
        next(gen)
    assert _is_closed(conn)


def test_get_db_cierra_la_conexion_si_el_endpoint_falla(tmp_db):
    gen = database.get_db()
    conn = next(gen)
    with pytest.raises(RuntimeError):
        gen.throw(RuntimeError("boom"))
    assert _is_closed(conn)


def test_get_db_se_puede_usar_desde_otro_hilo(tmp_db):
    # FastAPI resuelve la dependencia y ejecuta el endpoint en hilos distintos del pool.
    gen = database.get_db()
    conn = next(gen)
    with ThreadPoolExecutor(max_workers=1) as ex:
        assert ex.submit(lambda: conn.execute("SELECT 1").fetchone()[0]).result() == 1
    gen.close()


def test_endpoint_que_lanza_httpexception_no_deja_la_conexion_abierta(tmp_db):
    import main
    from fastapi import HTTPException

    gen = database.get_db()
    conn = next(gen)
    with pytest.raises(HTTPException) as exc:
        try:
            main.discard_offer_endpoint("no-existe", "expired", conn)
        except HTTPException as e:
            gen.throw(e)  # lo que hace FastAPI al propagar la excepción del endpoint
    assert exc.value.status_code == 404
    assert _is_closed(conn)


def test_mark_offer_sent_funciona_con_la_conexion_inyectada(tmp_db):
    import main

    conn = database.get_conn()
    cid = database.upsert_company(conn, {"name": "ACME", "source": "test"})
    conn.execute(
        "INSERT INTO job_offers (id, company_id, title, scraped_at) VALUES ('o1', ?, 'Dev', datetime('now'))",
        (cid,),
    )
    conn.commit()
    created = main.mark_offer_sent("o1", conn)
    assert created["created"] is True
    again = main.mark_offer_sent("o1", conn)
    assert again["already_sent"] is True
    assert main.unmark_offer_sent("o1", conn) == {"removed": True}
    conn.close()


def test_los_endpoints_no_abren_conexiones_a_mano():
    """Solo lifespan y las tareas en segundo plano pueden llamar a get_conn()."""
    tree = ast.parse((Path(__file__).parent.parent / "main.py").read_text(encoding="utf-8"))
    ofensores = []
    for fn in ast.walk(tree):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        es_endpoint = any(
            isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute)
            and isinstance(d.func.value, ast.Name) and d.func.value.id == "app"
            for d in fn.decorator_list
        )
        if es_endpoint and any(
            isinstance(c, ast.Call) and isinstance(c.func, ast.Name) and c.func.id == "get_conn"
            for c in ast.walk(fn)
        ):
            ofensores.append(fn.name)
    assert ofensores == []
