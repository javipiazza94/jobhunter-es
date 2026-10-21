import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from automation.cv_selector import cover_template_for, cv_tag_key, select_cv  # noqa: E402
from search_config import get_config  # noqa: E402


def sap_cv_key(tag, title):
    return cv_tag_key(get_config().track("sap"), tag, title)


def test_module_column_wins_over_title():
    assert sap_cv_key("MM", "Consultor SD") == "MM"
    assert sap_cv_key("FI-CO", None) == "FI_CO"


def test_title_inference_when_no_module():
    assert sap_cv_key(None, "Consultor/a SAP FICO") == "FI_CO"
    assert sap_cv_key(None, "Consultor SAP MM (Barcelona)") == "MM"
    assert sap_cv_key(None, "Consultor SAP SD") == "SD"


def test_ambiguous_or_unknown_falls_back_to_generic():
    assert sap_cv_key(None, "Consultor SAP MM y SD") is None
    assert sap_cv_key(None, "Consultor SAP") is None
    assert sap_cv_key("Otro", "Consultor SAP MM") is None


def test_select_cv_uses_module_then_generic_then_ia(tmp_path, monkeypatch):
    import config
    monkeypatch.setattr(config, "JH_HOME", tmp_path)  # los CV de profile.json son relativos a JH_HOME
    for name in ("mm.pdf", "gen.pdf", "ia.pdf"):
        (tmp_path / name).write_bytes(b"x")
    profile = {"cv_sap_modules": {"MM": "mm.pdf", "SD": "falta.pdf"}, "cv_sap_path": "gen.pdf", "cv_ia_path": "ia.pdf"}
    assert select_cv("sap", profile, "MM", None).name == "mm.pdf"
    assert select_cv("sap", profile, None, "Consultor SAP").name == "gen.pdf"
    assert select_cv("ia_dev", profile).name == "ia.pdf"
    assert select_cv("sap", profile, "SD", None) is None  # el CV del módulo no existe


def test_cover_template_por_track():
    assert cover_template_for("sap") == "sap"
    assert cover_template_for("ia_dev") == "tech"


def test_ruta_relativa_en_config_se_resuelve_bajo_jh_home(tmp_path, monkeypatch):
    import config
    from search_config import JobHunterConfig
    monkeypatch.setattr(config, "JH_HOME", tmp_path)
    (tmp_path / "x.pdf").write_bytes(b"x")
    cfg = JobHunterConfig.model_validate({
        "scoring": {"profile_confidence_threshold": 0.2, "keyword_groups": [{"id": "g", "weight": 0.5, "keywords": ["x"]}],
                    "location": {"weight": 0.2}, "experience": {"weight": 0.2}, "salary": {"weight": 0.1}},
        "tracks": [{"id": "t", "label": {"es": "t"}, "cv": {"default": "x.pdf"}}],
    })
    assert select_cv("t", {}, cfg=cfg).name == "x.pdf"
