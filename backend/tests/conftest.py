"""Los tests no deben depender de datos personales ni tocar la carpeta de datos real.

- JH_HOME se fuerza a una carpeta temporal (ignora el que haya exportado la shell) a nivel de módulo: pytest importa conftest.py antes de
  recolectar (y por tanto importar) cualquier test, y `config` lee JH_HOME al importarse. Un fixture
  (`tmp_path_factory`) no existe todavía en ese momento, por eso se usa `tempfile` y no un fixture.
- La carpeta temporal no tiene profile.json, así que se usa la plantilla versionada profile.example.json.
"""
import atexit
import os
import shutil
import tempfile
from pathlib import Path

_BACKEND = Path(__file__).parent.parent

# Siempre una carpeta temporal: un JH_HOME (o JH_DB_PATH/JH_INBOX_DIR/JH_PROFILE_PATH) exportado en la
# shell apuntaría a datos reales y los tests los leerían o modificarían.
for _var in ("JH_DB_PATH", "JH_INBOX_DIR", "JH_PROFILE_PATH"):
    os.environ.pop(_var, None)
_home = tempfile.mkdtemp(prefix="jh-home-tests-")
os.environ["JH_HOME"] = _home
atexit.register(shutil.rmtree, _home, ignore_errors=True)
os.environ["JH_PROFILE_PATH"] = str(_BACKEND / "profile.example.json")  # no hay profile.json en la carpeta temporal


import pytest  # noqa: E402


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "integration: compila con un motor LaTeX real (Tectonic puede descargar paquetes la primera vez)",
    )


@pytest.fixture(scope="session", autouse=True)
def _test_search_config():
    """Los tests no usan la configuración genérica de backend/defaults ni ninguna personal: se les da una
    configuración neutra y estable (tests/fixtures/config_test.yaml: ciudad y empresas ficticias,
    2 tracks estándar + 1 aislado). Los tests de la config real de Javi viven en tests/private/."""
    import search_config

    search_config.set_config(search_config.load_config(_BACKEND / "tests" / "fixtures" / "config_test.yaml"))
    yield
    search_config.set_config(None)
