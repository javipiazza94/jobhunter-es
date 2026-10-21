import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))


def test_classify_track_sap_offer():
    from automation.filter_engine import classify_track
    offer = {
        "title": "Consultor SAP PS Senior",
        "description": "Proyecto de implantación SAP S/4HANA. ABAP, SAP BTP, SAP Fiori.",
    }
    profile, confidence = classify_track(offer)
    assert profile == "sap"
    assert confidence >= 0.2


def test_classify_track_iadev_offer():
    from automation.filter_engine import classify_track
    offer = {
        "title": "Python Developer / AI Engineer",
        "description": "Desarrollamos con FastAPI, LLM, RAG, Python, Next.js y scraping Playwright.",
    }
    profile, confidence = classify_track(offer)
    assert profile == "ia_dev"
    assert confidence >= 0.2


def test_classify_track_ambiguous_returns_manual_review():
    from automation.filter_engine import classify_track
    offer = {
        "title": "Consultor tecnológico",
        "description": "Trabajamos con varios ERPs y también con Python.",
    }
    profile, _ = classify_track(offer)
    assert profile in ("manual_review", "sap", "ia_dev")


def test_classify_track_empty_offer_returns_manual_review():
    from automation.filter_engine import classify_track
    profile, confidence = classify_track({"title": None, "description": None})
    assert profile == "manual_review"
    assert confidence == 0.0


def test_filter_offers_includes_cv_profile():
    from automation.filter_engine import filter_offers
    offers = [
        {"title": "SAP Consultant", "description": "SAP S/4HANA ABAP BTP", "location": "Villanova"},
        {"title": "Python Dev", "description": "Python FastAPI LLM React", "location": "remoto"},
    ]
    result = filter_offers(offers)
    for r in result:
        assert "cv_profile" in r
        assert r["cv_profile"] in ("sap", "ia_dev", "manual_review")


def test_c_level_keywords_only_zero_score_when_in_title():
    from automation.filter_engine import score_offer
    base = {"location": "Madrid (remoto)", "tech_stack": "python llm rag"}
    junior = {**base, "title": "Junior AI Engineer", "description": "Reporta al CEO y al director técnico"}
    boss = {**base, "title": "Director de IA", "description": "python llm rag"}
    assert score_offer(junior) > 0
    assert score_offer(boss) == 0.0


# ── Scoring desde la configuración (jobhunter.yaml) ──────────────────────────

import pytest  # noqa: E402

_BACKEND_DIR = Path(__file__).parent.parent


@pytest.fixture
def restore_legacy_config():
    import search_config

    previous = search_config.get_config()
    try:
        yield
    finally:
        search_config.set_config(previous)


def _two_group_config(city=None):
    from search_config import JobHunterConfig

    base = JobHunterConfig.model_validate(
        __import__("yaml").safe_load((_BACKEND_DIR / "defaults" / "jobhunter.yaml").read_text(encoding="utf-8"))
    )
    data = base.model_dump()
    data["scoring"]["keyword_groups"] = [
        {"id": "a", "weight": 0.25, "keywords": ["alpha1", "alpha2", "alpha3", "alpha4", "alpha5"]},
        {"id": "b", "weight": 0.25, "keywords": ["betaone", "betatwo", "betathree", "betafour", "betafive"]},
    ]
    data["scoring"]["location"].update(weight=0.2, city=city, area=[])
    data["scoring"]["experience"]["weight"] = 0.15
    data["scoring"]["salary"]["weight"] = 0.15
    return JobHunterConfig.model_validate(data)


def test_score_con_config_generica_no_depende_de_sap(restore_legacy_config):
    import search_config
    from automation.filter_engine import score_offer

    generic = search_config.load_config(_BACKEND_DIR / "defaults" / "jobhunter.yaml")
    python_remote = {"title": "Python developer", "description": "Backend con python, sql y api", "location": "Remoto"}
    sap_onsite = {"title": "Consultor SAP FI", "description": "Consultor SAP FI en S/4HANA", "location": "Madrid presencial"}
    assert score_offer(python_remote, cfg=generic) > score_offer(sap_onsite, cfg=generic)
    search_config.set_config(generic)
    assert score_offer(python_remote) > score_offer(sap_onsite)


def test_grupos_de_keywords_ponderan_segun_config():
    from automation.filter_engine import score_offer

    cfg = _two_group_config()
    base = {"title": "x", "description": "", "location": ""}
    none = score_offer(base, cfg=cfg)
    all_a = score_offer({**base, "description": "alpha1 alpha2 alpha3 alpha4 alpha5"}, cfg=cfg)
    all_ab = score_offer({**base, "description": "alpha1 alpha2 alpha3 alpha4 alpha5 betaone betatwo betathree betafour betafive"}, cfg=cfg)
    assert round(all_a - none, 3) == 0.25
    assert round(all_ab - none, 3) == 0.5


def test_ciudad_vacia_no_da_bonus_de_ciudad():
    from automation.filter_engine import score_offer
    from automation.location import in_target_area

    base = {"title": "x", "description": "", "location": "Villanova"}
    with_city = score_offer(base, cfg=_two_group_config(city="villanova"))
    without_city = score_offer(base, cfg=_two_group_config(city=None))
    assert with_city > without_city
    assert in_target_area("Villanova", cfg=_two_group_config(city=None)) is False
    assert in_target_area("Villanova", cfg=_two_group_config(city="villanova")) is True
