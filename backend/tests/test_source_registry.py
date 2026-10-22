"""Registro de fuentes (scraper/sources): descubrimiento, fichas válidas y catálogo de mercados."""
import asyncio
import sys
import textwrap
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from scraper import sources  # noqa: E402

EXISTING = {"tecnoempleo", "infojobs", "computrabajo", "manfred", "linkedin", "indeed", "company_direct"}

_DUMMY = '''
from scraper.sources import Attribution, SourceSpec


def run(ctx):
    return [{"url": "https://ficticio.test/1", "title": "Oferta inventada"}]


SPEC = SourceSpec(
    id="@ID@",
    label={"es": "Ficticia", "en": "Dummy"},
    markets=("remote",),
    attribution=Attribution(name="Ficticia", url="https://ficticio.test", required=True),
    run=run,
)
'''


def _dummy(source_id: str) -> str:
    return _DUMMY.replace("@ID@", source_id)


def test_descubre_las_fuentes_existentes():
    reg = sources.registry()
    assert EXISTING <= set(reg)
    assert list(reg)[:3] == ["tecnoempleo", "infojobs", "manfred"]
    assert sources.get("manfred").kind == "json"
    with pytest.raises(KeyError):
        sources.get("no_existe")


@pytest.mark.parametrize("spec", list(sources.registry().values()), ids=lambda s: s.id)
def test_cada_ficha_es_valida(spec):
    sources.validate(spec)
    assert spec.label["es"] and spec.label["en"]
    assert set(spec.markets) <= set(sources.MARKETS)
    assert spec.attribution.name
    assert not (spec.requires_ack and spec.default_on)
    assert all(isinstance(p, sources.ParamSpec) for p in spec.params.values())


def test_flags_de_las_fuentes_existentes():
    reg = sources.registry()
    assert {s.id for s in reg.values() if s.requires_ack} == {"infojobs", "linkedin"}
    assert [s.id for s in sources.track_pipeline()] == [
        "tecnoempleo", "infojobs", "computrabajo", "company_direct", "linkedin"]
    assert {"tecnoempleo", "infojobs", "manfred", "linkedin", "indeed"} <= set(sources.standalone_ids())
    assert reg["indeed"].requires_secret == "SCRAPERAPI_KEY"
    assert reg["company_direct"].track_always and reg["company_direct"].persists_itself
    assert reg["company_direct"].markets == ()


def test_catalogo_de_mercados_en_ingles_con_atribucion():
    catalog = sources.market_catalog("en")
    assert list(catalog) == list(sources.MARKETS)
    remote = {s["id"]: s for s in catalog["remote"]}
    assert remote["tecnoempleo"]["label"] == "Tecnoempleo (remote)"
    assert remote["linkedin"]["attribution"] == {"name": "LinkedIn", "url": "https://www.linkedin.com/jobs",
                                                 "required": False}
    assert sources.market_catalog("es")["spain"][0]["label"] == "Tecnoempleo"


def test_un_modulo_nuevo_en_el_paquete_se_descubre(tmp_path, monkeypatch):
    (tmp_path / "ficticia.py").write_text(textwrap.dedent(_dummy("ficticia")), encoding="utf-8")
    monkeypatch.setattr(sources, "__path__", [*sources.__path__, str(tmp_path)])
    sources.reset_cache()
    try:
        reg = sources.registry()
        assert "ficticia" in reg and EXISTING <= set(reg)
        assert "ficticia" in sources.standalone_ids()
        assert [s["id"] for s in sources.market_catalog()["remote"]][-1] == "ficticia"
        ctx = sources.RunContext(settings={}, keywords=[])
        assert asyncio.run(sources.execute(reg["ficticia"], ctx))[0]["title"] == "Oferta inventada"
    finally:
        monkeypatch.undo()
        sys.modules.pop("scraper.sources.ficticia", None)
        sources.reset_cache()
    assert "ficticia" not in sources.registry()


def _package(tmp_path, monkeypatch, name: str, files: dict[str, str]) -> str:
    pkg = tmp_path / name
    pkg.mkdir()
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    for fname, body in files.items():
        (pkg / fname).write_text(textwrap.dedent(body), encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    return name


def test_ids_duplicados_o_invalidos_o_sin_spec_fallan(tmp_path, monkeypatch):
    dup = _package(tmp_path, monkeypatch, "fuentes_dup",
                   {"a.py": _dummy("repetida"), "b.py": _dummy("repetida")})
    with pytest.raises(ValueError, match="duplicado"):
        sources.discover(dup)
    bad = _package(tmp_path, monkeypatch, "fuentes_mal", {"a.py": _dummy("Con-Guion")})
    with pytest.raises(ValueError, match="inválido"):
        sources.discover(bad)
    nospec = _package(tmp_path, monkeypatch, "fuentes_sin_spec", {"a.py": "X = 1\n"})
    with pytest.raises(ValueError, match="SPEC"):
        sources.discover(nospec)


def test_validate_rechaza_fichas_incompletas():
    base = sources.get("manfred")
    from dataclasses import replace

    with pytest.raises(ValueError, match="'en'"):
        sources.validate(replace(base, label={"es": "Manfred"}))
    with pytest.raises(ValueError, match="mercados"):
        sources.validate(replace(base, markets=("marte",)))
    with pytest.raises(ValueError, match="atribución"):
        sources.validate(replace(base, attribution=sources.Attribution(name="", url="")))
    with pytest.raises(ValueError, match="por defecto"):
        sources.validate(replace(base, requires_ack=True, default_on=True))


def test_execute_acepta_run_sincrono_y_asincrono():
    async def asinc(ctx):
        return [{"n": ctx.max_pages}]

    spec = sources.get("manfred")
    from dataclasses import replace

    ctx = sources.RunContext(settings={}, keywords=[], max_pages=7)
    assert asyncio.run(sources.execute(replace(spec, run=asinc), ctx)) == [{"n": 7}]
    assert asyncio.run(sources.execute(replace(spec, run=lambda c: None), ctx)) == []


def test_el_cli_acepta_las_fuentes_sueltas_del_registro():
    import scraper.runner as runner

    assert set(sources.standalone_ids()) <= set(runner._STEPS)
    assert runner._ALL_SOURCES == ("seed", "tecnoempleo", "indeed", "manfred", "contacts")
