"""get_offers: limit se aplica DESPUÉS de los filtros calculados (modalidad, perfil, ubicación)."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import database  # noqa: E402
import main  # noqa: E402

# (id, título, ubicación, relevance_score): las mejor puntuadas NO son remotas.
OFFERS = [
    ("o1", "Dev A", "Madrid", 0.9),
    ("o2", "Dev B", "Barcelona", 0.8),
    ("o3", "Dev C", "Remoto", 0.7),
    ("o4", "Dev D", "Remoto", 0.6),
    ("o5", "Dev E", "Villanova", 0.5),
]


@pytest.fixture
def conn(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "t.db")
    c = database.get_conn()
    database.init_db(c)
    cid = database.upsert_company(c, {"name": "ACME", "source": "test"})
    for oid, title, loc, score in OFFERS:
        c.execute(
            "INSERT INTO job_offers (id, company_id, title, location, relevance_score, is_relevant, scraped_at) "
            "VALUES (?, ?, ?, ?, ?, 1, datetime('now'))",
            (oid, cid, title, loc, score),
        )
    c.commit()
    yield c
    c.close()


def _ids(rows):
    return [r["id"] for r in rows]


def test_limit_sin_filtros_calculados(conn):
    assert _ids(main.get_offers(limit=2, conn=conn)) == ["o1", "o2"]


def test_limit_se_aplica_despues_del_filtro_de_modalidad(conn):
    # Antes: LIMIT 2 en SQL devolvía o1,o2 y el filtro de modalidad los descartaba → [].
    assert _ids(main.get_offers(modality="remoto", limit=2, conn=conn)) == ["o3", "o4"]


def test_limit_se_aplica_despues_del_filtro_de_ubicacion(conn):
    assert _ids(main.get_offers(location="villanova", limit=1, conn=conn)) == ["o5"]


def test_limit_menor_que_los_resultados_filtrados(conn):
    assert _ids(main.get_offers(modality="remoto", limit=1, conn=conn)) == ["o3"]


def test_sin_limit_devuelve_todo_lo_filtrado(conn):
    assert _ids(main.get_offers(modality="remoto", conn=conn)) == ["o3", "o4"]


# ── Filtro por track ───────────────────────────────────────────────────────────

@pytest.fixture
def conn_tracks(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "tracks.db")
    c = database.get_conn()
    database.init_db(c)
    cid = database.upsert_company(c, {"name": "ACME", "source": "test"})
    # (id, título, relevance, followed_tier, job_kind, generic_score)
    filas = [
        ("s1", "Consultor SAP SD", 0.5, None, None, None),
        ("s2", "Consultor SAP MM", 0.9, 2, None, None),
        ("s3", "Consultor SAP PS", 0.6, 1, None, None),
        ("s4", "Consultor SAP FI", 0.7, 1, None, None),
        ("d1", "Desarrollador Python FastAPI", 0.8, None, None, None),
        ("g1", "Dependiente tienda", 0.0, None, "generic", 0.4),
        ("g2", "Atención al cliente", 0.0, None, "generic", 0.9),
    ]
    for oid, title, score, tier, kind, gscore in filas:
        c.execute(
            "INSERT INTO job_offers (id, company_id, title, relevance_score, is_relevant, scraped_at, "
            "followed_tier, job_kind, generic_score) VALUES (?, ?, ?, ?, 1, datetime('now'), ?, ?, ?)",
            (oid, cid, title, score, tier, kind, gscore),
        )
    c.commit()
    yield c
    c.close()


def test_offers_por_track_estandar_clasifica(conn_tracks):
    assert set(_ids(main.get_offers(track="sap", conn=conn_tracks))) == {"s1", "s2", "s3", "s4"}
    assert _ids(main.get_offers(track="ia_dev", conn=conn_tracks)) == ["d1"]
    # sin track: todo lo que no es aislado
    assert set(_ids(main.get_offers(conn=conn_tracks))) == {"s1", "s2", "s3", "s4", "d1"}


def test_offers_por_track_aislado_usa_job_kind(conn_tracks):
    # orden por afinidad descendente, aunque el cliente pida otro
    assert _ids(main.get_offers(track="generic", conn=conn_tracks)) == ["g2", "g1"]


def test_orden_por_tier_y_score(conn_tracks):
    # tier ascendente (nulos al final) y después relevance_score descendente
    assert _ids(main.get_offers(track="sap", conn=conn_tracks)) == ["s4", "s3", "s2", "s1"]


def test_track_desconocido_es_404(conn_tracks):
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as e:
        main.get_offers(track="no_existe", conn=conn_tracks)
    assert e.value.status_code == 404


def test_api_tracks_en_orden_de_config():
    import json

    from tests.asgi_client import call

    status, _, body = call("GET", "/api/tracks")
    assert status == 200
    tracks = json.loads(body)
    assert [t["id"] for t in tracks] == ["ia_dev", "sap", "generic"]
    assert [t["kind"] for t in tracks] == ["standard", "standard", "isolated"]
    assert set(tracks[0]) == {"id", "label", "kind"}
    assert isinstance(tracks[1]["label"], dict)
