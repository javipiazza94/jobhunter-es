import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import database  # noqa: E402
from database import init_db  # noqa: E402
import load_inbox_offers as loader  # noqa: E402


def _run(tmp_path, monkeypatch, text, *flags):
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "t.db", raising=False)
    init_db(sqlite3.connect(tmp_path / "t.db"))
    f = tmp_path / "ofertas.txt"
    f.write_text(text, encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["x", str(f), *flags])
    loader.main()
    return f


GOOD = "ia|AI Engineer remoto|ACME|Remoto|https://x.test/1|2026-10-01|indefinido|nota\n"


def test_offers_file_is_deleted_after_save_but_not_in_dry_run(tmp_path, monkeypatch):
    assert _run(tmp_path, monkeypatch, GOOD).exists()
    assert not _run(tmp_path, monkeypatch, GOOD, "--save").exists()


def test_offers_file_with_malformed_lines_is_kept(tmp_path, monkeypatch):
    assert _run(tmp_path, monkeypatch, GOOD + "linea rota\n", "--save").exists()


# --- tipo: ids de tracks de la config (+ alias antiguos) ------------------------------------------

LINE = "{}|AI Engineer remoto|ACME|Remoto|https://x.test/1|2026-10-01|indefinido|nota"


def test_tipo_accepts_standard_track_ids_from_config():
    o = loader.parse_line(LINE.format("ia_dev"))
    assert o is not None and o["tipo"] == "ia_dev"
    assert loader.resolve_tipo("ia_dev") == ("standard", None)
    assert loader.resolve_tipo("sap") == ("standard", None)


def test_tipo_accepts_isolated_track_ids_from_config():
    kind, track = loader.resolve_tipo("generic")
    assert kind == "isolated" and track.id == "generic"
    assert loader.parse_line(LINE.format("generic")) is not None


def test_tipo_legacy_aliases_still_work():
    assert loader.resolve_tipo("ia") == ("standard", None)
    kind, track = loader.resolve_tipo("puente")
    assert kind == "isolated" and track.id == "generic"  # primer track aislado de la config


def test_unknown_tipo_is_malformed():
    assert loader.parse_line(LINE.format("inventado")) is None
    assert loader.resolve_tipo("inventado") is None


def test_track_id_tipo_is_saved(tmp_path, monkeypatch):
    f = _run(tmp_path, monkeypatch, LINE.format("ia_dev") + "\n", "--save")
    assert not f.exists()
    row = sqlite3.connect(tmp_path / "t.db").execute("SELECT title FROM job_offers").fetchall()
    assert row == [("AI Engineer remoto",)]


def test_source_comes_from_the_url_domain():
    assert loader.source_from_url("https://es.indeed.com/viewjob?jk=1") == "indeed"
    assert loader.source_from_url("https://www.linkedin.com/jobs/view/1") == "linkedin"
    assert loader.source_from_url("https://www.infojobs.net/x/of-i1") == "infojobs"
    assert loader.source_from_url("https://www.tecnoempleo.com/x.php") == "tecnoempleo"
    assert loader.source_from_url("https://co.computrabajo.com/ofertas") == "computrabajo"


def test_unknown_or_missing_url_is_inbox():
    assert loader.source_from_url("https://careers.acme.test/job/1") == "inbox"
    assert loader.source_from_url("") == "inbox"
    assert loader.source_from_url("no es una url") == "inbox"


def test_saved_offer_keeps_its_real_source(tmp_path, monkeypatch):
    line = "ia_dev|AI Engineer remoto|ACME|Remoto|https://www.linkedin.com/jobs/view/9|2026-10-01|indefinido|nota\n"
    _run(tmp_path, monkeypatch, line, "--save")
    row = sqlite3.connect(tmp_path / "t.db").execute("SELECT source FROM job_offers").fetchall()
    assert row == [("linkedin",)]
