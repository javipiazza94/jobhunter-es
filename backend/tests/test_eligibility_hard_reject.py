"""Requisitos duros de elegibilidad dejan la oferta a 0, solo si `scoring.eligibility_hard_reject` está activo."""
import json
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import search_config  # noqa: E402
from automation import eligibility_gate as gate  # noqa: E402
from automation.eligibility_gate import eligibility_gate  # noqa: E402
from automation.filter_engine import score_offer  # noqa: E402
from database import init_db  # noqa: E402
from scraper.persist import save_scored_offer  # noqa: E402

_FIXTURE = Path(__file__).parent / "fixtures" / "config_test.yaml"
_PROFILE = {"personal": {"country_code": "ES", "nationality": "Española", "work_permit": True,
                         "dni_nie": "12345678Z", "needs_sponsorship": True},
            "education": [{"title": "Grado en Ingeniería"}]}
_GOOD = "SAP S/4HANA Public Cloud Consultant"
_US_ONLY = "We do not offer visa sponsorship."


@pytest.fixture(autouse=True)
def _profile(monkeypatch):
    monkeypatch.setattr(gate, "_load_profile", lambda: json.loads(json.dumps(_PROFILE)))


def _set_flag(value: bool):
    cfg = search_config.load_config(_FIXTURE)
    cfg.scoring.eligibility_hard_reject = value
    search_config.set_config(cfg)


@pytest.fixture
def conn(tmp_path, monkeypatch):
    import database
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "t.db", raising=False)
    c = sqlite3.connect(tmp_path / "t.db")
    c.row_factory = sqlite3.Row
    init_db(c)
    return c


def _offer(desc="", n=1):
    return {"title": _GOOD, "company_name": "ACME", "url": f"https://x/{n}", "location": "Villanova",
            "description": desc}


def _row(conn, n=1):
    return conn.execute("SELECT * FROM job_offers WHERE url=?", (f"https://x/{n}",)).fetchone()


def test_fixture_config_defaults_to_flag_off():
    assert search_config.load_config(_FIXTURE).scoring.eligibility_hard_reject is False


def test_flag_off_scores_identical_to_plain_score_offer(conn):
    _set_flag(False)
    offer = _offer(_US_ONLY)
    expected = score_offer(offer)
    assert expected > 0
    save_scored_offer(conn, offer, "t")
    row = _row(conn)
    assert row["relevance_score"] == expected
    assert row["is_relevant"] == int(expected >= search_config.get_config().scoring.min_relevance)


def test_flag_on_reject_zeroes_score_and_flags_reason(conn):
    _set_flag(False)
    base = score_offer(_offer(_US_ONLY))
    _set_flag(True)
    save_scored_offer(conn, _offer(_US_ONLY), "t")
    row = _row(conn)
    assert base > 0
    assert row["relevance_score"] == 0
    assert row["is_relevant"] == 0
    flags = json.loads(row["review_flags"])
    assert any(f.startswith("elegibilidad: ") and "patrocina visado" in f for f in flags)
    assert not any(f.startswith("elegibilidad: elegibilidad") for f in flags)


def test_flag_on_clean_offer_unchanged(conn):
    _set_flag(True)
    offer = _offer("Trabajo híbrido en Villanova.")
    save_scored_offer(conn, offer, "t")
    assert _row(conn)["relevance_score"] == score_offer(offer)


def test_flag_on_doubtful_only_warns(conn, monkeypatch):
    _set_flag(True)
    monkeypatch.setattr(gate, "_load_profile", lambda: {"personal": {"country_code": "ES"}, "education": [{"title": "Grado"}]})
    offer = _offer("Imprescindible carné de conducir.")
    assert eligibility_gate(offer, profile_data={"personal": {"country_code": "ES"}})[0] == "flag"
    save_scored_offer(conn, offer, "t")
    row = _row(conn)
    assert row["relevance_score"] == score_offer(offer) > 0
    assert any("carné" in f for f in json.loads(row["review_flags"]))


def test_sponsorship_needed_rejects_generic_no_sponsorship():
    offer = {"title": "Dev", "description": "We do not offer visa sponsorship."}
    assert eligibility_gate(offer, profile_data={"personal": {"country_code": "ES"}}, extended=True)[0] == "ok"
    assert eligibility_gate(offer, profile_data={"personal": {"country_code": "ES"}, "eligibility": {"needs_sponsorship": True}})[0] == "ok"  # sin extended: igual que hoy
    needs = {"personal": {"country_code": "ES"}, "eligibility": {"needs_sponsorship": True}}
    verdict, reasons = eligibility_gate(offer, profile_data=needs, extended=True)
    assert verdict == "reject" and "patrocina visado" in reasons[0]


def test_required_residence_other_country_rejects_non_spain_candidate():
    offer = {"title": "Dev", "description": "Candidate must be based in the United States."}
    verdict, _ = eligibility_gate(offer, profile_data={"personal": {"country_code": "FR"}}, extended=True)
    assert verdict == "reject"
    assert eligibility_gate(offer, profile_data={"personal": {"country_code": "US"}}, extended=True)[0] == "ok"


def test_inbox_loader_uses_same_helper(tmp_path):
    src = (Path(__file__).parent.parent / "scripts" / "load_inbox_offers.py").read_text(encoding="utf-8")
    assert "apply_hard_requirements" in src
