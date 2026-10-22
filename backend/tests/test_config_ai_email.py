"""Secciones `ai:` y `email:` de jobhunter.yaml y escritura atómica con save_config()."""
import re
from pathlib import Path

import pytest
import yaml

import config
import search_config
from search_config import AISettings, ConfigError, EmailSettings, load_config, save_config

_BASE = """
scoring:
  min_relevance: 0.5
  keyword_groups:
    - {id: a, weight: 0.5, keywords: [x]}
  location: {weight: 0.2}
  experience: {weight: 0.2}
  salary: {weight: 0.1}
tracks:
  - {id: dev, label: {es: Dev, en: Dev}}
"""


def _write(tmp_path, extra=""):
    path = tmp_path / "jobhunter.yaml"
    path.write_text(_BASE + extra, encoding="utf-8")
    return path


def test_sin_seccion_ai_el_proveedor_es_none(tmp_path):
    cfg = load_config(_write(tmp_path))
    assert cfg.ai == AISettings()
    assert cfg.ai.provider == "none"
    assert cfg.ai.timeout_seconds == 120


def test_sin_seccion_email_es_el_preset_gmail(tmp_path):
    cfg = load_config(_write(tmp_path))
    assert cfg.email == EmailSettings()
    assert (cfg.email.preset, cfg.email.smtp_host, cfg.email.smtp_port) == ("gmail", "smtp.gmail.com", 587)
    assert cfg.email.use_starttls is True


def test_proveedor_desconocido_se_rechaza(tmp_path):
    with pytest.raises(ConfigError, match="ai.provider"):
        load_config(_write(tmp_path, "ai: {provider: skynet}\n"))


def test_campo_desconocido_en_email_se_rechaza(tmp_path):
    with pytest.raises(ConfigError, match="email"):
        load_config(_write(tmp_path, "email: {password: hunter2}\n"))


def test_save_config_round_trip(tmp_path):
    cfg = load_config(_write(tmp_path, "ai: {provider: ollama, model: llama3.1}\nemail: {preset: custom, smtp_host: mail.acme.test}\n"))
    out = tmp_path / "out" / "jobhunter.yaml"
    out.parent.mkdir()
    assert save_config(cfg, out) == out
    assert load_config(out) == cfg
    assert not list(out.parent.glob("*.tmp"))


def test_save_config_no_escribe_secretos(tmp_path):
    cfg = load_config(_write(tmp_path))
    out = save_config(cfg, tmp_path / "w.yaml")

    def keys(node):
        if isinstance(node, dict):
            for k, v in node.items():
                yield str(k)
                yield from keys(v)
        elif isinstance(node, list):
            for v in node:
                yield from keys(v)

    names = [k.lower() for k in keys(yaml.safe_load(out.read_text(encoding="utf-8")))]
    secretos = [k for k in names if re.search(r"(^|_)(api_?key|key|password|passwd|secret|token)($|_)", k)]
    assert not set(secretos) - {"cover_letter_docx_key", "summary_key"}  # claves de plantilla de track, no secretos


def test_save_config_por_defecto_escribe_en_jh_home_y_recarga(tmp_path, monkeypatch):
    base = tmp_path / "base"
    base.mkdir()
    cfg = load_config(_write(base, "ai: {provider: ollama}\n"))
    home = tmp_path / "home"
    monkeypatch.setattr(config, "JH_HOME", home)
    try:
        path = save_config(cfg)
        assert path == home / "jobhunter.yaml"
        assert search_config.get_config().ai.provider == "ollama"  # reload_config() ya apunta al nuevo fichero
    finally:
        monkeypatch.undo()
        search_config.set_config(load_config(Path(__file__).parent / "fixtures" / "config_test.yaml"))
