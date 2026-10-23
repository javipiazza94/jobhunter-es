"""Caracterización de las fuentes antes del registro (SP4): qué función de scraper se llama, con qué argumentos,
y qué `source` queda guardado en la BD, para una config como la de una instalación existente
(tests/fixtures/config_legacy_like.yaml, datos inventados). Mismo resultado antes y después del refactor:
`--track` (CLI), `--source` (CLI), trabajos de la API (`python -m scraper.jobs <fuente>` y `track:<ids>`)
y el catálogo de mercados que ve el asistente."""
import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import database  # noqa: E402
import search_config  # noqa: E402

_FIXTURE = Path(__file__).parent / "fixtures" / "config_legacy_like.yaml"


@pytest.fixture(autouse=True)
def legacy(tmp_path, monkeypatch):
    original = search_config.get_config()
    search_config.set_config(search_config.load_config(_FIXTURE))
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "legacy.db")
    conn = database.get_conn()
    database.init_db(conn)
    conn.close()
    yield
    search_config.set_config(original)


@pytest.fixture
def calls(monkeypatch):
    """Sustituye las funciones de cada scraper por grabadoras que devuelven una oferta inventada por llamada."""
    import scraper.company_direct
    import scraper.computrabajo
    import scraper.indeed
    import scraper.infojobs
    import scraper.linkedin_jobs
    import scraper.manfred
    import scraper.tecnoempleo

    log: list = []
    unset = scraper.infojobs._UNSET

    def offers(name: str) -> list[dict]:
        n = len(log) - 1
        return [{"url": f"https://ofertas.test/{name}/{n}", "title": f"Consultor Odoo {n}",
                 "company_name": f"Empresa {name} {n}", "location": "Pradoverde", "source": name}]

    async def run_tecnoempleo(max_pages=3):
        log.append(("tecnoempleo.run_tecnoempleo", {"max_pages": max_pages}))
        return offers("tecnoempleo")

    class FakeTecnoempleoScraper:
        async def scrape_keyword(self, keyword, location, max_pages=5):
            log.append(("tecnoempleo.scrape_keyword", {"keyword": keyword, "location": location,
                                                       "max_pages": max_pages}))
            return offers("tecnoempleo")

    async def run_indeed(keywords=None, locations=None, max_pages=3):
        log.append(("indeed.run_indeed", {"keywords": keywords, "locations": locations, "max_pages": max_pages}))
        return offers("indeed")

    def run_manfred(max_pages=5):
        log.append(("manfred.run_manfred", {"max_pages": max_pages}))
        return offers("manfred")

    async def run_linkedin_jobs(max_per_search=25, track=None):
        log.append(("linkedin_jobs.run_linkedin_jobs", {"max_per_search": max_per_search, "track": track}))
        return offers("linkedin")

    async def run_infojobs(keywords, max_pages=3, normalized_location=unset, province_id=unset, scroll=False):
        log.append(("infojobs.run_infojobs", {
            "keywords": list(keywords), "max_pages": max_pages,
            "normalized_location": "UNSET" if normalized_location is unset else normalized_location,
            "province_id": "UNSET" if province_id is unset else province_id, "scroll": scroll,
        }))
        return offers("infojobs")

    async def run_computrabajo(keywords, max_pages=3, location=None, country="es"):
        log.append(("computrabajo.run_computrabajo", {"keywords": list(keywords), "max_pages": max_pages,
                                                      "location": location}))
        return offers("computrabajo")

    async def run_company_direct(dry_run=False):
        log.append(("company_direct.run_company_direct", {"dry_run": dry_run}))
        return 0, 0

    monkeypatch.setattr(scraper.tecnoempleo, "run_tecnoempleo", run_tecnoempleo)
    monkeypatch.setattr(scraper.tecnoempleo, "TecnoempleoScraper", FakeTecnoempleoScraper)
    monkeypatch.setattr(scraper.indeed, "run_indeed", run_indeed)
    monkeypatch.setattr(scraper.manfred, "run_manfred", run_manfred)
    monkeypatch.setattr(scraper.linkedin_jobs, "run_linkedin_jobs", run_linkedin_jobs)
    monkeypatch.setattr(scraper.infojobs, "run_infojobs", run_infojobs)
    monkeypatch.setattr(scraper.computrabajo, "run_computrabajo", run_computrabajo)
    monkeypatch.setattr(scraper.company_direct, "run_company_direct", run_company_direct)
    monkeypatch.setattr("scraper.robots_gate.check_robots", lambda *a, **kw: True)
    return log


def _saved() -> dict[str, str]:
    """Empresa → `source` guardado (lo que recibe save_scored_offers)."""
    conn = database.get_conn()
    try:
        return {r["name"]: r["source"] for r in conn.execute("SELECT name, source FROM companies")}
    finally:
        conn.close()


def _cli(monkeypatch, *argv):
    import scraper.runner as runner

    monkeypatch.setattr(sys, "argv", ["runner", *argv])
    monkeypatch.setattr(runner, "print_stats", lambda: None)
    runner.main()


TRACK_ERP_CALLS = [
    ("tecnoempleo.scrape_keyword", {"keyword": "Consultor Odoo", "location": "Pradoverde", "max_pages": 2}),
    ("tecnoempleo.scrape_keyword", {"keyword": "Consultor Odoo", "location": "remoto", "max_pages": 2}),
    ("tecnoempleo.scrape_keyword", {"keyword": "ERP funcional", "location": "Pradoverde", "max_pages": 2}),
    ("tecnoempleo.scrape_keyword", {"keyword": "ERP funcional", "location": "remoto", "max_pages": 2}),
    ("infojobs.run_infojobs", {"keywords": ["Consultor Odoo", "ERP funcional"], "max_pages": 2,
                               "normalized_location": "UNSET", "province_id": "UNSET", "scroll": False}),
    ("computrabajo.run_computrabajo", {"keywords": ["Consultor Odoo", "ERP funcional"], "max_pages": 2,
                                       "location": None}),
    ("company_direct.run_company_direct", {"dry_run": False}),
    ("linkedin_jobs.run_linkedin_jobs", {"max_per_search": 25, "track": "erp"}),
]


# ── --track (CLI) ───────────────────────────────────────────────────────────────


def test_cli_track_llama_a_cada_portal_con_las_keywords_del_track_y_guarda_con_el_id_del_track(calls, monkeypatch):
    _cli(monkeypatch, "--track", "erp", "--max-pages", "2")
    assert calls == TRACK_ERP_CALLS
    saved = _saved()
    # Cada oferta de un track se guarda con source = id del track (también las de InfoJobs/LinkedIn/Computrabajo).
    assert saved == {
        "Empresa tecnoempleo 0": "erp", "Empresa tecnoempleo 1": "erp", "Empresa tecnoempleo 2": "erp",
        "Empresa tecnoempleo 3": "erp", "Empresa infojobs 4": "erp", "Empresa computrabajo 5": "erp",
        "Empresa linkedin 7": "erp",
    }


def test_cli_track_dry_run_no_guarda(calls, monkeypatch):
    _cli(monkeypatch, "--track", "erp", "--max-pages", "2", "--dry-run")
    expected = [(name, {**kw, "dry_run": True}) if name.startswith("company_direct") else (name, kw)
                for name, kw in TRACK_ERP_CALLS]
    assert calls == expected
    assert _saved() == {}


# ── --source (CLI) ──────────────────────────────────────────────────────────────


def test_cli_source_tecnoempleo_indeed_manfred(calls, monkeypatch):
    _cli(monkeypatch, "--source", "tecnoempleo", "--max-pages", "4")
    _cli(monkeypatch, "--source", "indeed")
    _cli(monkeypatch, "--source", "manfred", "--max-pages", "9")
    assert calls == [
        ("tecnoempleo.run_tecnoempleo", {"max_pages": 4}),
        ("indeed.run_indeed", {"keywords": ["odoo developer"], "locations": ["Pradoverde"], "max_pages": 3}),
        ("manfred.run_manfred", {"max_pages": 5}),  # Manfred no usa --max-pages
    ]
    assert _saved() == {"Empresa tecnoempleo 0": "tecnoempleo", "Empresa indeed 1": "indeed",
                        "Empresa manfred 2": "manfred"}


def test_cli_source_dry_run_no_guarda(calls, monkeypatch):
    _cli(monkeypatch, "--source", "tecnoempleo", "--dry-run")
    assert calls == [("tecnoempleo.run_tecnoempleo", {"max_pages": 3})]
    assert _saved() == {}


def test_cli_source_all_no_incluye_portales_de_track(calls, monkeypatch):
    import scraper.runner as runner

    monkeypatch.setattr(runner, "load_seed", lambda: None)
    monkeypatch.setattr(runner, "run_contacts_source", lambda dry: asyncio.sleep(0))
    _cli(monkeypatch, "--source", "all")
    assert [name for name, _ in calls] == ["tecnoempleo.run_tecnoempleo", "indeed.run_indeed", "manfred.run_manfred"]


# ── Trabajos de la API (python -m scraper.jobs) ─────────────────────────────────


def test_api_fuentes_sueltas(calls):
    from scraper import jobs

    for source in ("tecnoempleo", "indeed", "manfred", "linkedin", "infojobs"):
        jobs.run(source)
    assert calls == [
        ("tecnoempleo.run_tecnoempleo", {"max_pages": 3}),
        ("indeed.run_indeed", {"keywords": ["odoo developer"], "locations": ["Pradoverde"], "max_pages": 3}),
        ("manfred.run_manfred", {"max_pages": 5}),
        ("linkedin_jobs.run_linkedin_jobs", {"max_per_search": 25, "track": None}),
        ("infojobs.run_infojobs", {"keywords": ["consultor odoo", "data engineer"], "max_pages": 3,
                                   "normalized_location": "UNSET", "province_id": "UNSET", "scroll": False}),
    ]
    assert _saved() == {"Empresa tecnoempleo 0": "tecnoempleo", "Empresa indeed 1": "indeed",
                        "Empresa manfred 2": "manfred", "Empresa linkedin 3": "linkedin",
                        "Empresa infojobs 4": "infojobs"}


def test_api_fuentes_aceptadas_y_reservas_de_track():
    from scraper import jobs

    assert set(jobs.SOURCES) == {"seed", "tecnoempleo", "contacts", "indeed", "manfred", "linkedin", "infojobs",
                                 "inbox", "inbox-apply", "remotive", "remoteok", "arbeitnow", "freehire"}
    assert tuple(jobs.TRACK_PIPELINE_SOURCES) == ("tecnoempleo", "infojobs", "computrabajo", "linkedin")
    for source in ("computrabajo", "company_direct", "generic"):
        with pytest.raises(SystemExit, match="Fuente desconocida"):
            jobs.run(source)


def test_api_track_varios_tracks_con_todas_las_fuentes_activadas(calls):
    from scraper import jobs

    jobs.run("track:erp,datos")
    erp = [(n, kw) for n, kw in TRACK_ERP_CALLS]
    datos = [
        ("tecnoempleo.scrape_keyword", {"keyword": "Ingeniero de datos", "location": "Pradoverde", "max_pages": 3}),
        ("tecnoempleo.scrape_keyword", {"keyword": "Ingeniero de datos", "location": "remoto", "max_pages": 3}),
        ("infojobs.run_infojobs", {"keywords": ["Ingeniero de datos"], "max_pages": 3,
                                   "normalized_location": "UNSET", "province_id": "UNSET", "scroll": False}),
        ("computrabajo.run_computrabajo", {"keywords": ["Ingeniero de datos"], "max_pages": 3, "location": None}),
        ("company_direct.run_company_direct", {"dry_run": False}),
        ("linkedin_jobs.run_linkedin_jobs", {"max_per_search": 25, "track": "datos"}),
    ]
    erp3 = [(n, {**kw, "max_pages": 3}) if "max_pages" in kw and not n.startswith("linkedin") else (n, kw)
            for n, kw in erp]
    assert calls == erp3 + datos
    saved = _saved()
    assert {name: src for name, src in saved.items() if src == "datos"} == {
        "Empresa tecnoempleo 8": "datos", "Empresa tecnoempleo 9": "datos", "Empresa infojobs 10": "datos",
        "Empresa computrabajo 11": "datos", "Empresa linkedin 13": "datos",
    }
    assert sum(1 for src in saved.values() if src == "erp") == 7


def test_api_track_omite_fuentes_no_activadas_pero_no_la_web_de_empresas(calls):
    from scraper import jobs

    cfg = search_config.get_config()
    sources = {k: v for k, v in cfg.sources.items() if k not in ("infojobs", "linkedin", "company_direct")}
    search_config.set_config(cfg.model_copy(update={"sources": sources}))
    jobs.run("track:datos")
    assert [n for n, _ in calls] == [
        "tecnoempleo.scrape_keyword", "tecnoempleo.scrape_keyword", "computrabajo.run_computrabajo",
        "company_direct.run_company_direct",
    ]


# ── Catálogo de mercados (asistente y Ajustes → Fuentes) ────────────────────────


MARKETS = {
    "spain": [
        {"id": "tecnoempleo", "label": "Tecnoempleo", "requires_ack": False, "default_on": True},
        {"id": "infojobs", "label": "InfoJobs", "requires_ack": True, "default_on": False},
        {"id": "manfred", "label": "Manfred", "requires_ack": False, "default_on": True},
        {"id": "computrabajo", "label": "Computrabajo", "requires_ack": False, "default_on": True},
    ],
    "latam": [
        {"id": "computrabajo", "label": "Computrabajo", "requires_ack": False, "default_on": True},
        {"id": "linkedin", "label": "LinkedIn", "requires_ack": True, "default_on": False},
    ],
    "remote": [
        {"id": "tecnoempleo", "label": "Tecnoempleo (remoto)", "requires_ack": False, "default_on": True},
        {"id": "manfred", "label": "Manfred", "requires_ack": False, "default_on": True},
        {"id": "linkedin", "label": "LinkedIn", "requires_ack": True, "default_on": False},
        {"id": "remotive", "label": "Remotive", "requires_ack": False, "default_on": False},
        {"id": "remoteok", "label": "RemoteOK", "requires_ack": False, "default_on": False},
        {"id": "arbeitnow", "label": "Arbeitnow", "requires_ack": False, "default_on": False},
        {"id": "freehire", "label": "Freehire", "requires_ack": False, "default_on": False},
    ],
    "global": [
        {"id": "linkedin", "label": "LinkedIn", "requires_ack": True, "default_on": False},
        {"id": "remotive", "label": "Remotive", "requires_ack": False, "default_on": False},
        {"id": "remoteok", "label": "RemoteOK", "requires_ack": False, "default_on": False},
        {"id": "arbeitnow", "label": "Arbeitnow", "requires_ack": False, "default_on": False},
        {"id": "freehire", "label": "Freehire", "requires_ack": False, "default_on": False},
        {"id": "indeed", "label": "Indeed (requiere SCRAPERAPI_KEY)", "requires_ack": False, "default_on": False},
    ],
}


def test_mercados_del_asistente():
    import setup_builder

    markets = setup_builder.load_markets()
    base_markets = {
        m: [{k: s[k] for k in ("id", "label", "requires_ack", "default_on")} for s in sources]
        for m, sources in markets.items()
    }
    assert base_markets == MARKETS
    assert list(markets) == ["spain", "latam", "remote", "global"]
    for sources in markets.values():
        for s in sources:
            assert "ack_warning" in s
            assert "attribution" in s


def test_catalogo_y_vista_de_fuentes():
    import setup_builder

    catalog = setup_builder.source_catalog()
    assert list(catalog) == [
        "tecnoempleo", "infojobs", "manfred", "computrabajo", "linkedin",
        "remotive", "remoteok", "arbeitnow", "freehire", "indeed",
    ]
    assert {sid: (e["label"], e["requires_ack"]) for sid, e in catalog.items()} == {
        "tecnoempleo": ("Tecnoempleo", False), "infojobs": ("InfoJobs", True), "manfred": ("Manfred", False),
        "computrabajo": ("Computrabajo", False), "linkedin": ("LinkedIn", True),
        "remotive": ("Remotive", False), "remoteok": ("RemoteOK", False),
        "arbeitnow": ("Arbeitnow", False), "freehire": ("Freehire", False),
        "indeed": ("Indeed (requiere SCRAPERAPI_KEY)", False),
    }
    view = setup_builder.sources_view()
    base_view = [
        {k: s[k] for k in ("id", "label", "markets", "requires_ack", "enabled", "acknowledged")}
        for s in view
    ]
    assert base_view == [
        {"id": "tecnoempleo", "label": "Tecnoempleo", "markets": ["spain", "remote"], "requires_ack": False,
         "enabled": True, "acknowledged": False},
        {"id": "infojobs", "label": "InfoJobs", "markets": ["spain"], "requires_ack": True, "enabled": True,
         "acknowledged": True},
        {"id": "manfred", "label": "Manfred", "markets": ["spain", "remote"], "requires_ack": False,
         "enabled": True, "acknowledged": False},
        {"id": "computrabajo", "label": "Computrabajo", "markets": ["spain", "latam"], "requires_ack": False,
         "enabled": True, "acknowledged": False},
        {"id": "linkedin", "label": "LinkedIn", "markets": ["latam", "remote", "global"], "requires_ack": True,
         "enabled": True, "acknowledged": True},
        {"id": "remotive", "label": "Remotive", "markets": ["remote", "global"], "requires_ack": False,
         "enabled": False, "acknowledged": False},
        {"id": "remoteok", "label": "RemoteOK", "markets": ["remote", "global"], "requires_ack": False,
         "enabled": False, "acknowledged": False},
        {"id": "arbeitnow", "label": "Arbeitnow", "markets": ["remote", "global"], "requires_ack": False,
         "enabled": False, "acknowledged": False},
        {"id": "freehire", "label": "Freehire", "markets": ["remote", "global"], "requires_ack": False,
         "enabled": False, "acknowledged": False},
        {"id": "indeed", "label": "Indeed (requiere SCRAPERAPI_KEY)", "markets": ["global"],
         "requires_ack": False, "enabled": True, "acknowledged": False},
        {"id": "company_direct", "label": "company_direct", "markets": [], "requires_ack": False,
         "enabled": True, "acknowledged": False},
    ]
    for s in view:
        assert "country" in s
        assert "locations" in s


# ── URLs que construyen los portales con la config existente (sin `country`) ────


def test_urls_de_busqueda_con_la_config_existente():
    from scraper import computrabajo, infojobs, tecnoempleo

    assert tecnoempleo.build_search_url("odoo", "Pradoverde", 1) == \
        "https://www.tecnoempleo.com/ofertas-trabajo/?te=odoo&pagina=1&pr=%2C321%2C"
    assert tecnoempleo.build_search_url("odoo", "remoto", 2) == \
        "https://www.tecnoempleo.com/ofertas-trabajo/?te=odoo+remoto&pagina=2"
    assert infojobs.build_search_url("consultor odoo", 1, "pradoverde", "77") == (
        "https://www.infojobs.net/jobsearch/search-results/list.xhtml?keyword=consultor+odoo&page=1&provinceIds=77")
    assert computrabajo.COMPUTRABAJO_BASE == "https://www.computrabajo.es"
    assert computrabajo._location_param(None) == "?l=pradoverde"
