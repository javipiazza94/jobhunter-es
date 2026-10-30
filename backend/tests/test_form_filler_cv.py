"""form_filler: un formulario sin CV adjunto nunca se da por completo, pero la persona sigue pudiendo revisarlo."""
import logging
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from automation import form_filler  # noqa: E402

FORM_URL = "https://jobs.example.com/apply"


class _Page:
    async def goto(self, *_args, **_kwargs):
        return SimpleNamespace(status=200)


class _Context:
    async def add_init_script(self, _script):
        pass

    async def new_page(self):
        return _Page()


class _Browser:
    async def new_context(self, **_kwargs):
        return _Context()


class _Playwright:
    def __init__(self):
        self.chromium = SimpleNamespace(launch=self._launch)

    async def _launch(self, **_kwargs):
        return _Browser()

    async def stop(self):
        pass


class _PlaywrightStarter:
    async def start(self):
        return _Playwright()


@pytest.fixture
def run_fill(monkeypatch):
    """Ejecuta _run_fill con un navegador falso y un handler que devuelve `handler_result`.
    Devuelve (resultado, mensajes mostrados a la persona, handler_llamado_con_cv)."""

    async def no_browser_install():
        pass

    def run(cv_path, handler_result=True):
        import asyncio

        prompts: list[str] = []
        seen_cv: list[Path] = []

        async def handler(_page, _profile, cv, _cover_letter):
            seen_cv.append(cv)
            return handler_result

        monkeypatch.setattr(form_filler, "ensure_chromium_async", no_browser_install, raising=False)
        monkeypatch.setattr(form_filler, "async_playwright", lambda: _PlaywrightStarter())
        monkeypatch.setattr(form_filler, "detect_ats", lambda _url: "generic")
        monkeypatch.setattr(form_filler, "_HANDLER_MAP", {"generic": ("fake_handlers", "fill")})
        monkeypatch.setattr("builtins.input", lambda prompt="": prompts.append(prompt) or "")
        fake_importlib = SimpleNamespace(import_module=lambda _name: SimpleNamespace(fill=handler))
        monkeypatch.setattr(form_filler, "importlib", fake_importlib)  # solo en este módulo, no global
        result = asyncio.run(form_filler._run_fill(FORM_URL, {}, cv_path, "Carta", headless=False, pause_for_review=True))
        return result, prompts, seen_cv

    return run


def test_con_cv_el_formulario_se_da_por_completo(run_fill, tmp_path):
    cv = tmp_path / "cv.pdf"
    cv.write_bytes(b"%PDF")

    result, prompts, seen_cv = run_fill(cv)

    assert result is True
    assert seen_cv == [cv]
    assert "CV" not in prompts[0]


@pytest.mark.parametrize("missing_cv", [None, Path("/no/existe/cv.pdf")], ids=["sin-cv", "fichero-inexistente"])
def test_sin_cv_el_formulario_no_se_da_por_completo(run_fill, missing_cv, caplog):
    with caplog.at_level(logging.WARNING):
        result, _prompts, _seen_cv = run_fill(missing_cv)

    assert result is False
    assert "CV" in caplog.text


def test_sin_cv_la_persona_puede_revisar_y_adjuntarlo_a_mano(run_fill):
    result, prompts, seen_cv = run_fill(None)

    assert len(seen_cv) == 1  # el handler rellena igualmente el resto del formulario
    assert len(prompts) == 1  # se pausa para la revisión humana
    assert "CV" in prompts[0] and "a mano" in prompts[0]
    assert result is False


def test_si_el_handler_falla_no_se_pausa_ni_se_da_por_completo(run_fill, tmp_path):
    cv = tmp_path / "cv.pdf"
    cv.write_bytes(b"%PDF")

    result, prompts, _seen_cv = run_fill(cv, handler_result=False)

    assert result is False
    assert prompts == []
