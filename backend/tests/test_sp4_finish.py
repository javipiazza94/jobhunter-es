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


def test_meta_all_registered_sources_have_specs_and_tests():
    """Cada fuente registrada en scraper.sources tiene especificación completa y tests asociados."""
    reg = source_registry.registry()
    assert len(reg) >= 10, f"Se esperaban al menos 10 fuentes registradas, encontradas {len(reg)}"

    tests_dir = Path(__file__).parent
    test_files = list(tests_dir.glob("test_*.py"))
    all_test_content = "\n".join(f.read_text(encoding="utf-8") for f in test_files)

    for sid, spec in reg.items():
        # Verificación de ficha
        assert spec.id == sid
        assert "es" in spec.label and "en" in spec.label, f"Fuente {sid} carece de label es/en"
        assert spec.attribution is not None, f"Fuente {sid} carece de attribution"
        assert spec.attribution.name, f"Fuente {sid} carece de attribution.name"
        if sid != "company_direct":
            assert spec.attribution.url, f"Fuente {sid} carece de attribution.url"
        assert len(spec.markets) >= 1 or sid == "company_direct", f"Fuente {sid} no declara mercados"

        # Verificación de que la fuente está probada en los tests
        assert sid in all_test_content, f"La fuente registrada '{sid}' no está referenciada en ningún test de backend"


def test_add_new_language_without_code_changes(tmp_path, monkeypatch):
    """Añadir un idioma nuevo (directorio de plantillas 'xx' y etiquetas) funciona sin tocar código."""
    custom_templates_dir = tmp_path / "custom_templates"
    xx_dir = custom_templates_dir / "xx"
    xx_dir.mkdir(parents=True)

    # 1. Crear plantilla de carta en el nuevo idioma
    (xx_dir / "cover_letter_base.j2").write_text(
        "Guten Tag {{ company_name }}. Mein Name ist {{ name }}.\n", encoding="utf-8"
    )

    monkeypatch.setattr(config, "TEMPLATES_OVERRIDE_DIR", custom_templates_dir)

    # 2. Descubrimiento automático del nuevo idioma
    avail = available_template_languages()
    assert "xx" in avail, "El idioma 'xx' no fue descubierto automáticamente"

    # 3. Resolución del idioma de la oferta
    offer = {"title": "Software Engineer", "company_name": "Acme Corp", "language": "xx"}
    assert letter_language(offer, {}) == "xx"

    # 4. Generación de carta en el nuevo idioma sin modificar código
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
