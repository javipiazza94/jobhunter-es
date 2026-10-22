"""Descarga de Chromium bajo demanda (automation/browser_install.py). El driver de Playwright va siempre simulado."""
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from automation import browser_install as bi  # noqa: E402


def _dry_run(base: Path, *, ffmpeg: bool = True) -> str:
    out = (f"Chrome for Testing 148 (playwright chromium v1223)\n  Install location:    {base / 'chromium-1223'}\n"
           f"  Download url:        https://x/y.zip\n\n"
           f"Chrome Headless Shell 148 (playwright chromium-headless-shell v1223)\n"
           f"  Install location:    {base / 'chromium_headless_shell-1223'}\n")
    if ffmpeg:
        out += f"\nFFmpeg (playwright ffmpeg v1011)\n  Install location:    {base / 'ffmpeg-1011'}\n"
    return out


def _mark_installed(base: Path) -> None:
    for name in ("chromium-1223", "chromium_headless_shell-1223"):
        (base / name).mkdir(parents=True, exist_ok=True)
        (base / name / bi._MARKER).write_text("")


class FakeDriver:
    """Sustituye a `_run_driver`: `install --dry-run` lista carpetas; `install` las crea (o falla)."""

    def __init__(self, base: Path, *, fail: str | None = None, delay: float = 0.0):
        self.base, self.fail, self.delay = base, fail, delay
        self.installs = 0

    def __call__(self, *args, timeout):
        if "--dry-run" in args:
            return subprocess.CompletedProcess(args, 0, _dry_run(self.base), "")
        self.installs += 1
        time.sleep(self.delay)
        if self.fail:
            return subprocess.CompletedProcess(args, 1, "", self.fail)
        _mark_installed(self.base)
        return subprocess.CompletedProcess(args, 0, "ok", "")


@pytest.fixture(autouse=True)
def sin_chromium_del_sistema(monkeypatch):
    monkeypatch.setattr(bi, "system_chromium", lambda: None)


def test_si_ya_esta_instalado_no_descarga_nada(tmp_path, monkeypatch):
    _mark_installed(tmp_path)
    driver = FakeDriver(tmp_path)
    monkeypatch.setattr(bi, "_run_driver", driver)
    bi.ensure_chromium()
    assert driver.installs == 0


def test_una_version_antigua_no_cuenta_como_instalada(tmp_path, monkeypatch):
    (tmp_path / "chromium-1194").mkdir()
    (tmp_path / "chromium-1194" / bi._MARKER).write_text("")
    driver = FakeDriver(tmp_path)
    monkeypatch.setattr(bi, "_run_driver", driver)
    bi.ensure_chromium()
    assert driver.installs == 1


def test_una_descarga_a_medias_se_repite(tmp_path, monkeypatch):
    (tmp_path / "chromium-1223").mkdir()  # sin INSTALLATION_COMPLETE
    driver = FakeDriver(tmp_path)
    monkeypatch.setattr(bi, "_run_driver", driver)
    bi.ensure_chromium()
    assert driver.installs == 1


def test_con_un_chromium_del_sistema_no_se_consulta_ni_se_descarga(monkeypatch):
    monkeypatch.setattr(bi, "system_chromium", lambda: "/usr/bin/chromium")

    def boom(*a, **k):
        raise AssertionError("no debe llamar al driver")

    monkeypatch.setattr(bi, "_run_driver", boom)
    bi.ensure_chromium()


def test_dos_llamadas_simultaneas_descargan_una_sola_vez(tmp_path, monkeypatch):
    driver = FakeDriver(tmp_path, delay=0.3)
    monkeypatch.setattr(bi, "_run_driver", driver)
    hilos = [threading.Thread(target=bi.ensure_chromium) for _ in range(3)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join(10)
    assert driver.installs == 1


def test_sin_red_el_error_es_legible(tmp_path, monkeypatch):
    monkeypatch.setattr(bi, "_run_driver", FakeDriver(tmp_path, fail="getaddrinfo ENOTFOUND cdn.playwright.dev"))
    with pytest.raises(bi.BrowserInstallError) as exc:
        bi.ensure_chromium()
    assert "sin conexión" in str(exc.value) and "ENOTFOUND" in str(exc.value)


def test_tiempo_agotado_da_un_error_legible(tmp_path, monkeypatch):
    def lento(*args, timeout):
        if "--dry-run" in args:
            return subprocess.CompletedProcess(args, 0, _dry_run(tmp_path), "")
        raise subprocess.TimeoutExpired(args, timeout)

    monkeypatch.setattr(bi, "_run_driver", lento)
    with pytest.raises(bi.BrowserInstallError, match="tardó demasiado"):
        bi.ensure_chromium()


def test_si_el_driver_no_responde_al_consultar_el_error_es_legible(monkeypatch):
    monkeypatch.setattr(bi, "_run_driver", lambda *a, timeout: subprocess.CompletedProcess(a, 1, "", "boom"))
    with pytest.raises(bi.BrowserInstallError, match="qué Chromium necesita"):
        bi.ensure_chromium()


def test_la_version_async_delega_en_la_sincrona(tmp_path, monkeypatch):
    import asyncio

    llamadas = []
    monkeypatch.setattr(bi, "ensure_chromium", lambda: llamadas.append(1))
    asyncio.run(bi.ensure_chromium_async())
    assert llamadas == [1]


def test_el_driver_real_describe_las_carpetas_de_chromium():
    """Sin red: `install --dry-run` solo imprime rutas. Comprueba que el formato que parseamos sigue vigente."""
    try:
        dirs = bi._required_dirs()
    except bi.BrowserInstallError as exc:
        pytest.skip(f"driver de Playwright no disponible: {exc}")
    assert dirs and all(d.name.startswith("chromium") for d in dirs)


def test_todo_lanzamiento_de_chromium_pasa_antes_por_ensure_chromium():
    """Si alguien añade un `chromium.launch(` nuevo sin preparar el navegador, la app de escritorio fallaría
    la primera vez en un equipo sin Chromium."""
    backend = Path(__file__).parent.parent
    for path in list(backend.glob("scraper/*.py")) + list(backend.glob("automation/**/*.py")):
        text = path.read_text(encoding="utf-8")
        if "chromium.launch(" not in text or path.name == "browser_install.py":
            continue
        assert text.count("ensure_chromium_async()") >= text.count("async_playwright().start()"), path.name
