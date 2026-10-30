"""Una IA mal configurada degrada a «sin IA» avisando; elegir «none» a propósito no avisa."""
import logging
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from ai import warn_ai_unavailable  # noqa: E402
from ai.base import NoneProvider  # noqa: E402
from automation import ai_writing, application_documents, application_engine, expand_profile, screening, upskill  # noqa: E402


def _broken_provider(*_args, **_kwargs):
    raise ValueError("clave-secreta-123 no válida")


def test_el_aviso_nombra_el_motivo_sin_filtrar_el_detalle(caplog):
    with caplog.at_level(logging.WARNING):
        warn_ai_unavailable("cartas", ValueError("clave-secreta-123"))

    assert "cartas" in caplog.text and "ValueError" in caplog.text
    assert "clave-secreta" not in caplog.text


@pytest.mark.parametrize("call", [
    lambda: application_engine._letter_provider(),
    lambda: upskill._resolve_provider(None),
    lambda: ai_writing.adapt_cover_letter("Carta base", {}, {}),
    lambda: expand_profile.propose([], None, {}),
], ids=["cartas-motor", "upskill", "adapt_cover_letter", "expand_profile"])
def test_configuracion_invalida_avisa_y_sigue_sin_ia(monkeypatch, caplog, call):
    for module in (application_engine, upskill, ai_writing, expand_profile):
        monkeypatch.setattr(module, "get_provider", _broken_provider, raising=False)

    with caplog.at_level(logging.WARNING):
        call()

    assert "IA no disponible" in caplog.text
    assert "clave-secreta" not in caplog.text


def test_documentos_con_configuracion_ilegible_avisan(monkeypatch, caplog):
    def unreadable_config():
        raise OSError("jobhunter.yaml ilegible")

    monkeypatch.setattr("search_config.get_config", unreadable_config)

    with caplog.at_level(logging.WARNING):
        assert application_documents._resolve_use_ai(None) is False

    assert "IA no disponible" in caplog.text


def test_screening_con_configuracion_invalida_avisa(tmp_path, monkeypatch, caplog):
    import database

    monkeypatch.setattr(database, "DB_PATH", tmp_path / "t.db")
    conn = database.get_conn()
    database.init_db(conn)
    conn.execute("INSERT INTO companies (id,name,source,created_at) VALUES ('c1','ACME','test','2026-01-01')")
    conn.execute(
        "INSERT INTO job_offers (id,company_id,title,description,is_relevant,relevance_score,cv_profile,scraped_at,url) "
        "VALUES ('o1','c1','Python Dev','x',1,0.8,'general','2026-01-01','http://a.com/1')"
    )
    conn.execute("INSERT INTO applications (id,company_id,job_offer_id,status) VALUES ('app1','c1','o1','pending_approval')")
    conn.commit()
    conn.close()
    monkeypatch.setattr(screening, "get_provider", _broken_provider, raising=False)

    with caplog.at_level(logging.WARNING):
        screening.answer_for_application("app1", [])

    assert "IA no disponible" in caplog.text


@pytest.mark.parametrize("call", [
    lambda: application_engine._letter_provider(),
    lambda: upskill._resolve_provider(None),
    lambda: ai_writing.adapt_cover_letter("Carta base", {}, {}),
], ids=["cartas-motor", "upskill", "adapt_cover_letter"])
def test_elegir_none_a_proposito_no_avisa(monkeypatch, caplog, call):
    for module in (application_engine, upskill, ai_writing):
        monkeypatch.setattr(module, "get_provider", lambda *_a, **_k: NoneProvider(), raising=False)

    with caplog.at_level(logging.WARNING):
        call()

    assert "IA no disponible" not in caplog.text
