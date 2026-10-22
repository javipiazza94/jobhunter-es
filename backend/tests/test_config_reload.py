"""get_config() recarga jobhunter.yaml cuando cambia; si el nuevo es inválido conserva el último válido."""
import os
from pathlib import Path

import pytest

import config
import search_config
from search_config import ConfigError, get_config, set_config

_YAML = """
scoring:
  min_relevance: {relevance}
  keyword_groups:
    - {{id: a, weight: 0.5, keywords: [x]}}
  location: {{weight: 0.2}}
  experience: {{weight: 0.2}}
  salary: {{weight: 0.1}}
tracks:
  - {{id: dev, label: {{es: Dev, en: Dev}}}}
"""


def _write(home: Path, relevance: float, bump: int = 0) -> Path:
    path = home / "jobhunter.yaml"
    path.write_text(_YAML.format(relevance=relevance), encoding="utf-8")
    stamp = path.stat().st_mtime_ns + bump * 1_000_000_000
    os.utime(path, ns=(stamp, stamp))
    return path


@pytest.fixture
def home(tmp_path, monkeypatch):
    legacy = get_config()
    monkeypatch.setattr(config, "JH_HOME", tmp_path)
    set_config(None)
    yield tmp_path
    set_config(legacy)


def test_recarga_al_cambiar_el_fichero(home):
    _write(home, 0.5)
    assert get_config().scoring.min_relevance == 0.5
    _write(home, 0.7, bump=1)
    assert get_config().scoring.min_relevance == 0.7


def test_sin_cambios_no_vuelve_a_leer_el_fichero(home, monkeypatch):
    _write(home, 0.5)
    first = get_config()
    monkeypatch.setattr(search_config, "load_config", lambda *a, **k: pytest.fail("no debía recargar"))
    assert get_config() is first


def test_fichero_invalido_conserva_la_ultima_config_valida_y_lo_registra(home, caplog):
    path = _write(home, 0.5)
    good = get_config()
    path.write_text("scoring: {}\ntracks: []\n  roto", encoding="utf-8")
    bump = path.stat().st_mtime_ns + 1_000_000_000
    os.utime(path, ns=(bump, bump))
    with caplog.at_level("ERROR"):
        assert get_config() is good  # no revienta
        assert get_config() is good
    assert caplog.text.count("jobhunter.yaml") >= 1
    assert caplog.text.count("conservando") == 1  # se registra una vez por versión del fichero
    _write(home, 0.9, bump=2)  # al corregirlo, se aplica
    assert get_config().scoring.min_relevance == 0.9


def test_primer_arranque_con_fichero_invalido_sigue_fallando(home):
    (home / "jobhunter.yaml").write_text("scoring: {}\n", encoding="utf-8")
    with pytest.raises(ConfigError):
        get_config()


def test_set_config_fija_la_config_y_desactiva_la_recarga_hasta_set_none(home):
    _write(home, 0.5)
    pinned = get_config()
    set_config(pinned)
    _write(home, 0.7, bump=1)
    assert get_config() is pinned
    set_config(None)
    assert get_config().scoring.min_relevance == 0.7


def test_aparece_el_fichero_del_usuario_despues_de_usar_los_defaults(home):
    assert get_config().track("developer") is not None  # defaults: aún no hay fichero
    _write(home, 0.5)
    assert get_config().track("dev") is not None
