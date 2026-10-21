"""Las configuraciones de ejemplo de `examples/` son válidas y no llevan datos personales."""

import os
from pathlib import Path

import pytest

import search_config

EXAMPLES_DIR = Path(__file__).resolve().parents[2] / "examples"
EXAMPLE_FILES = sorted(EXAMPLES_DIR.glob("*.yaml"))
# Términos personales: viven fuera del repo (una cadena por línea), no se versionan aquí.
DENYLIST = Path(os.environ.get("JH_DENYLIST", Path.home() / ".config" / "jobhunter-oss" / "denylist.txt"))


def test_hay_los_tres_ejemplos_minimos():
    names = {p.name for p in EXAMPLE_FILES}
    assert {"developer.yaml", "sap-consultant.yaml", "data-ai.yaml"} <= names


@pytest.mark.parametrize("path", EXAMPLE_FILES, ids=lambda p: p.name)
def test_ejemplos_validos(path):
    cfg = search_config.load_config(path)  # ConfigError si el YAML o los pesos no valen
    s = cfg.scoring
    total = sum(g.weight for g in s.keyword_groups) + s.location.weight + s.experience.weight + s.salary.weight
    assert total == pytest.approx(1.0, abs=1e-6)
    assert cfg.standard_tracks()


@pytest.mark.parametrize("path", EXAMPLE_FILES, ids=lambda p: p.name)
def test_ejemplos_sin_datos_personales(path):
    if not DENYLIST.is_file():
        pytest.skip("sin denylist local (JH_DENYLIST): comprobación solo para el mantenedor")
    forbidden = [w.strip().lower() for w in DENYLIST.read_text(encoding="utf-8").splitlines() if w.strip()]
    text = path.read_text(encoding="utf-8").lower()
    found = [w for w in forbidden if w in text]
    assert not found, f"{path.name} contiene {len(found)} término(s) de la denylist"
