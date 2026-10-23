"""Pruebas de cierre (finish-line) de SP4 — International & New Sources.

Verifica:
1. Meta-cobertura: Cada fuente registrada en `scraper.sources` tiene su ficha completa y está referenciada en la suite de tests.
2. Extensibilidad de idiomas: Añadir un idioma nuevo 'xx' (directorio de plantillas y etiquetas en temporal) funciona sin tocar código.
3. Integridad de diccionarios i18n (es/en) y paridad de claves.
"""

import json
from pathlib import Path

from automation.cover_letter import available_template_languages, generate, letter_language
import config
from scraper import sources as source_registry


SOURCE_TESTS: dict[str, tuple[str, str]] = {
    "tecnoempleo": ("test_source_characterisation.py", "test_cli_source_tecnoempleo_indeed_manfred"),
    "infojobs": ("test_infojobs.py", "test_parse_card_returns_expected_fields"),
    "computrabajo": ("test_computrabajo_countries.py", "test_parse_cards_per_country"),
    "manfred": ("test_source_characterisation.py", "test_cli_source_tecnoempleo_indeed_manfred"),
    "linkedin": ("test_linkedin_jobs.py", "test_is_checkpoint_detects_authwall"),
    "indeed": ("test_source_characterisation.py", "test_cli_source_tecnoempleo_indeed_manfred"),
    "remotive": ("test_sources_remote.py", "test_parsing_and_keyword_filter"),
    "remoteok": ("test_sources_remote.py", "test_parsing_and_keyword_filter"),
    "arbeitnow": ("test_sources_remote.py", "test_parsing_and_keyword_filter"),
    "freehire": ("test_sources_remote.py", "test_parsing_and_keyword_filter"),
    "company_direct": ("test_company_direct.py", "test_is_relevant_offer_with_custom_keywords"),
}


def test_meta_all_registered_sources_have_specs_and_tests():
    """Cada fuente registrada en scraper.sources tiene especificación completa y un test propio que la ejecuta."""
    reg = source_registry.registry()
    assert len(reg) >= 10, f"Se esperaban al menos 10 fuentes registradas, encontradas {len(reg)}"

    tests_dir = Path(__file__).parent

    for sid, spec in reg.items():
        # Verificación de ficha
        assert spec.id == sid
        assert "es" in spec.label and "en" in spec.label, f"Fuente {sid} carece de label es/en"
        assert spec.attribution is not None, f"Fuente {sid} carece de attribution"
        assert spec.attribution.name, f"Fuente {sid} carece de attribution.name"
        if sid != "company_direct":
            assert spec.attribution.url, f"Fuente {sid} carece de attribution.url"
        assert len(spec.markets) >= 1 or sid == "company_direct", f"Fuente {sid} no declara mercados"

        # Verificación de test propio dedicado
        assert sid in SOURCE_TESTS, f"La fuente registrada '{sid}' no tiene un test propio asignado en SOURCE_TESTS"
        test_file, test_fn = SOURCE_TESTS[sid]
        target_path = tests_dir / test_file
        assert target_path.exists(), f"El archivo de test '{test_file}' para la fuente '{sid}' no existe"
        file_content = target_path.read_text(encoding="utf-8")
        assert test_fn in file_content, f"La función de test '{test_fn}' no se encontró en '{test_file}' para la fuente '{sid}'"


def test_add_new_language_without_code_changes(tmp_path, monkeypatch):
    """Añadir un idioma nuevo (directorio de plantillas 'xx', ui_language y etiquetas) funciona sin tocar código."""
    import setup_builder
    from automation.profile_proposal import ProfileDraft

    # 1. El modelo de respuestas del asistente y perfil acepta el nuevo idioma 'xx'
    draft = ProfileDraft(
        personal={"name": "Carlos Dev", "city": "Madrid", "country": "España"},
        targets=[{"title": "Dev", "keywords": ["python"]}],
    )
    answers = setup_builder.SetupAnswers(draft=draft, ui_language="xx")
    assert answers.ui_language == "xx"

    # 2. Las fuentes del registro resuelven etiquetas y avisos para 'xx' cayendo a es/en sin fallar
    for spec in source_registry.registry().values():
        label_xx = spec.label_for("xx")
        assert label_xx, f"La fuente {spec.id} devolvió una etiqueta vacía para el idioma 'xx'"
        assert label_xx in (spec.label.get("es"), spec.label.get("en"), spec.id)

    # 3. El catálogo de mercados del asistente y setup_builder funciona con 'xx'
    catalog_xx = source_registry.market_catalog("xx")
    assert set(catalog_xx.keys()) == set(source_registry.MARKETS)
    markets_xx = setup_builder.load_markets("xx")
    assert "spain" in markets_xx and len(markets_xx["spain"]) > 0

    # 4. Plantillas y generación de cartas en el nuevo idioma
    custom_templates_dir = tmp_path / "custom_templates"
    xx_dir = custom_templates_dir / "xx"
    xx_dir.mkdir(parents=True)

    (xx_dir / "cover_letter_base.j2").write_text(
        "Guten Tag {{ company_name }}. Mein Name ist {{ name }}.\n", encoding="utf-8"
    )

    monkeypatch.setattr(config, "TEMPLATES_OVERRIDE_DIR", custom_templates_dir)

    avail = available_template_languages()
    assert "xx" in avail, "El idioma 'xx' no fue descubierto automáticamente"

    offer = {"title": "Software Engineer", "company_name": "Acme Corp", "language": "xx"}
    assert letter_language(offer, {}) == "xx"

    letter = generate(company_name="Acme Corp", job_title="Software Engineer", lang="xx")
    assert "Guten Tag Acme Corp." in letter


def test_frontend_i18n_dictionaries_integrity():
    """Los diccionarios es.json y en.json tienen paridad exacta de claves y variables."""
    root_dir = Path(__file__).parents[2]
    i18n_dir = root_dir / "frontend" / "lib" / "i18n"
    es_file = i18n_dir / "es.json"
    en_file = i18n_dir / "en.json"

    assert es_file.exists(), f"No existe {es_file}"
    assert en_file.exists(), f"No existe {en_file}"

    es_data = json.loads(es_file.read_text(encoding="utf-8"))
    en_data = json.loads(en_file.read_text(encoding="utf-8"))

    def flatten(d, prefix=""):
        res = {}
        for k, v in d.items():
            key = f"{prefix}.{k}" if prefix else k
            if isinstance(v, dict):
                res.update(flatten(v, key))
            else:
                res[key] = str(v)
        return res

    flat_es = flatten(es_data)
    flat_en = flatten(en_data)

    missing_in_en = set(flat_es.keys()) - set(flat_en.keys())
    missing_in_es = set(flat_en.keys()) - set(flat_es.keys())

    assert not missing_in_en, f"Claves presentes en es.json pero ausentes en en.json: {missing_in_en}"
    assert not missing_in_es, f"Claves presentes en en.json pero ausentes en es.json: {missing_in_es}"

    import re
    var_re = re.compile(r"\{([a-zA-Z0-9_]+)\}")
    for k, val_es in flat_es.items():
        val_en = flat_en[k]
        vars_es = set(var_re.findall(val_es))
        vars_en = set(var_re.findall(val_en))
        assert vars_es == vars_en, f"Discrepancia de variables en clave '{k}': es={vars_es} vs en={vars_en}"
