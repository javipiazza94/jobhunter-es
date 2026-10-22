"""GET /api/applications/pending: un clon recién hecho (sin profile.json) no debe dar 500."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import config  # noqa: E402
import database  # noqa: E402
import main  # noqa: E402
import search_config  # noqa: E402
from automation import cv_selector  # noqa: E402


def _use_profile(monkeypatch, path):
    # cv_selector es el lector público de este endpoint.
    monkeypatch.setattr(cv_selector, "PROFILE_PATH", path)


@pytest.fixture
def conn(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "t.db")
    monkeypatch.setattr(config, "JH_HOME", tmp_path)
    c = database.get_conn()
    database.init_db(c)
    c.execute("INSERT INTO companies (id,name,source,created_at) VALUES ('c1','ACME','test','2026-01-01')")
    c.commit()
    database.record_application(c, {
        "company_id": "c1", "method": "email", "status": "pending_approval",
        "cover_letter_used": "carta", "cv_profile": search_config.get_config().standard_tracks()[0].id,
    })
    yield c
    c.close()


def test_sin_profile_json_devuelve_la_lista_con_cv_file_nulo(conn, tmp_path, monkeypatch):
    _use_profile(monkeypatch, tmp_path / "no-existe.json")
    out = main.get_pending_applications_endpoint(conn=conn)
    assert len(out) == 1
    assert out[0]["cv_file"] is None


def test_profile_json_corrupto_tambien_es_tolerado(conn, tmp_path, monkeypatch):
    bad = tmp_path / "profile.json"
    bad.write_text("{no es json", encoding="utf-8")
    _use_profile(monkeypatch, bad)
    assert main.get_pending_applications_endpoint(conn=conn)[0]["cv_file"] is None


def test_con_cv_presente_cv_file_es_el_nombre_del_fichero(conn, tmp_path, monkeypatch):
    track = search_config.get_config().standard_tracks()[0]
    (tmp_path / "mi_cv.pdf").write_bytes(b"%PDF-1.4")
    profile = tmp_path / "profile.json"
    profile.write_text(json.dumps({"cv_x": "mi_cv.pdf"}), encoding="utf-8")
    _use_profile(monkeypatch, profile)
    monkeypatch.setattr(cv_selector, "resolve_data_path", lambda rel: tmp_path / rel)
    track = track.model_copy(update={"cv": search_config.TrackCV(default="cv_x")})
    cfg = search_config.get_config()
    patched = cfg.model_copy(update={"tracks": [track if t.id == track.id else t for t in cfg.tracks]})
    search_config.set_config(patched)
    try:
        assert main.get_pending_applications_endpoint(conn=conn)[0]["cv_file"] == "mi_cv.pdf"
    finally:
        search_config.set_config(cfg)
