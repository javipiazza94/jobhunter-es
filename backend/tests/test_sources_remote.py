"""Tests para las fuentes remotas JSON: Remotive, RemoteOK, Arbeitnow y Freehire."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from database import get_conn, init_db
from scraper import persist
from scraper.sources import RunContext, SourceError, get, registry, reset_cache

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "sources"


class FakeResponse:
    def __init__(self, data=None, status_code=200, text=""):
        self._data = data
        self.status_code = status_code
        self.text = text or (json.dumps(data) if data is not None else "")

    def json(self):
        if self._data is not None:
            return self._data
        raise ValueError("JSON inválido")


@pytest.fixture(autouse=True)
def _reset_registry():
    reset_cache()
    yield
    reset_cache()


def _load_fixture(name: str):
    path = FIXTURES_DIR / f"{name}.json"
    with open(path, encoding="utf-8") as f:
        return json.load(f)


class TestRemoteSourcesSpecs:
    def test_specs_registered(self):
        reg = registry()
        for source_id in ("remotive", "remoteok", "arbeitnow", "freehire"):
            assert source_id in reg
            spec = reg[source_id]
            assert "remote" in spec.markets
            assert spec.kind == "json"
            assert spec.default_on is False

    def test_attribution_requirements(self):
        remotive = get("remotive")
        assert remotive.attribution.required is True
        assert remotive.attribution.name == "Remotive"
        assert remotive.attribution.url == "https://remotive.com"

        remoteok = get("remoteok")
        assert remoteok.attribution.required is True
        assert remoteok.attribution.name == "RemoteOK"
        assert remoteok.attribution.url == "https://remoteok.com"

        arbeitnow = get("arbeitnow")
        assert arbeitnow.attribution.required is False
        assert arbeitnow.attribution.name == "Arbeitnow"

        freehire = get("freehire")
        assert freehire.attribution.required is False
        assert freehire.attribution.name == "Freehire"


class TestRemotiveSource:
    def test_parsing_and_keyword_filter(self):
        data = _load_fixture("remotive")
        with patch("requests.get", return_value=FakeResponse(data=data)):
            spec = get("remotive")

            # Sin keywords: devuelve todas las ofertas con URL
            offers = spec.run(RunContext(settings={}, keywords=[]))
            assert len(offers) == 2
            assert offers[0]["source"] == "remotive"
            assert offers[0]["title"] == "Senior Python Engineer"
            assert offers[0]["company_name"] == "Novatech Global"
            assert offers[0]["url"] == "https://remotive.com/remote-jobs/software-dev/senior-python-engineer-1001"
            assert "python" in offers[0]["tech_stack"]

            # Con keyword que coincide
            filtered = spec.run(RunContext(settings={}, keywords=["python"]))
            assert len(filtered) == 1
            assert filtered[0]["title"] == "Senior Python Engineer"

            # Con keyword que no coincide
            empty = spec.run(RunContext(settings={}, keywords=["ruby"]))
            assert len(empty) == 0

    def test_http_errors_raise_source_error(self):
        with patch("requests.get", return_value=FakeResponse(status_code=429, text="Too Many Requests")):
            spec = get("remotive")
            with pytest.raises(SourceError, match="HTTP 429"):
                spec.run(RunContext(settings={}, keywords=[]))

    def test_invalid_json_raises_source_error(self):
        with patch("requests.get", return_value=FakeResponse(status_code=200, text="<html>Error</html>")):
            spec = get("remotive")
            with pytest.raises(SourceError, match="JSON inválido"):
                spec.run(RunContext(settings={}, keywords=[]))

    def test_missing_keys_raises_source_error(self):
        with patch("requests.get", return_value=FakeResponse(data={"status": "ok"})):
            spec = get("remotive")
            with pytest.raises(SourceError, match="falta 'jobs'"):
                spec.run(RunContext(settings={}, keywords=[]))


class TestRemoteOKSource:
    def test_parsing_and_keyword_filter(self):
        data = _load_fixture("remoteok")
        with patch("requests.get", return_value=FakeResponse(data=data)):
            spec = get("remoteok")

            offers = spec.run(RunContext(settings={}, keywords=[]))
            assert len(offers) == 2  # omite el primer elemento legal
            assert offers[0]["source"] == "remoteok"
            assert offers[0]["title"] == "Data Engineer"
            assert offers[0]["company_name"] == "DataCraft Studio"
            assert offers[0]["salary_text"] == "$85000 - $110000"

            # Filtro de keyword
            filtered = spec.run(RunContext(settings={}, keywords=["frontend"]))
            assert len(filtered) == 1
            assert filtered[0]["title"] == "Senior Frontend Developer"

    def test_errors_raise_source_error(self):
        with patch("requests.get", return_value=FakeResponse(status_code=500, text="Server Error")):
            spec = get("remoteok")
            with pytest.raises(SourceError, match="HTTP 500"):
                spec.run(RunContext(settings={}, keywords=[]))

    def test_unexpected_shape_raises_source_error(self):
        with patch("requests.get", return_value=FakeResponse(data={"error": "not a list"})):
            spec = get("remoteok")
            with pytest.raises(SourceError, match="debe ser una lista"):
                spec.run(RunContext(settings={}, keywords=[]))


class TestArbeitnowSource:
    def test_parsing_and_keyword_filter(self):
        data = _load_fixture("arbeitnow")
        with patch("requests.get", return_value=FakeResponse(data=data)):
            spec = get("arbeitnow")

            offers = spec.run(RunContext(settings={}, keywords=[]))
            assert len(offers) == 2
            assert offers[0]["source"] == "arbeitnow"
            assert offers[0]["title"] == "Senior Backend Engineer (Python)"
            assert offers[0]["company_name"] == "Apex Software"
            assert "fastapi" in offers[0]["tech_stack"]

            # Filtro
            filtered = spec.run(RunContext(settings={}, keywords=["devops"]))
            assert len(filtered) == 1
            assert filtered[0]["title"] == "DevOps Cloud Architect"

    def test_errors_raise_source_error(self):
        with patch("requests.get", return_value=FakeResponse(status_code=403, text="Forbidden")):
            spec = get("arbeitnow")
            with pytest.raises(SourceError, match="HTTP 403"):
                spec.run(RunContext(settings={}, keywords=[]))


class TestFreehireSource:
    def test_parsing_and_keyword_filter(self):
        data = _load_fixture("freehire")
        with patch("requests.get", return_value=FakeResponse(data=data)):
            spec = get("freehire")

            offers = spec.run(RunContext(settings={}, keywords=[]))
            assert len(offers) == 2
            assert offers[0]["source"] == "freehire"
            assert offers[0]["title"] == "Lead Python Developer"
            assert offers[0]["company_name"] == "NextGen Analytics"
            assert "django" in offers[0]["tech_stack"]

            # Filtro
            filtered = spec.run(RunContext(settings={}, keywords=["kubernetes"]))
            assert len(filtered) == 1
            assert filtered[0]["title"] == "Site Reliability Engineer"

    def test_errors_raise_source_error(self):
        with patch("requests.get", return_value=FakeResponse(status_code=502, text="Bad Gateway")):
            spec = get("freehire")
            with pytest.raises(SourceError, match="HTTP 502"):
                spec.run(RunContext(settings={}, keywords=[]))


class TestRemoteOfferPersistence:
    def test_persistence_preserves_source_and_url(self, tmp_path, monkeypatch):
        import database
        db_file = tmp_path / "test_remote.db"
        monkeypatch.setattr(database, "DB_PATH", db_file)
        conn = get_conn()
        init_db(conn)

        data = _load_fixture("remotive")
        with patch("requests.get", return_value=FakeResponse(data=data)):
            spec = get("remotive")
            offers = spec.run(RunContext(settings={}, keywords=[]))
            assert len(offers) > 0

            first = offers[0]
            offer_id = persist.save_scored_offer(conn, first, first["source"])
            row = conn.execute("SELECT source, url, title, company_id FROM job_offers WHERE id = ?", (offer_id,)).fetchone()
            assert row is not None
            assert row["source"] == "remotive"
            assert row["url"] == first["url"]
            assert row["title"] == first["title"]
            conn.close()
