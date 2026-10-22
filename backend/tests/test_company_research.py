"""
test_company_research.py — Pruebas para la caché de investigación de empresas con TTL.
"""

import sys
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from automation.company_research import (  # noqa: E402
    clear_expired_cache,
    get_cached_research,
    get_company_cache_path,
    list_cached_companies,
    normalize_company_name,
    save_cached_research,
)


class TestCompanyResearchCache(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.fake_cache_dir = Path(self.temp_dir.name) / "company_research"
        self.fake_cache_dir.mkdir(parents=True)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_normalize_company_name(self):
        self.assertEqual(normalize_company_name("Acme Corp, S.L."), "acme-corp-s-l")
        self.assertEqual(normalize_company_name("  Tech   Solutions  "), "tech-solutions")
        self.assertEqual(normalize_company_name("Novartis A/S"), "novartis-a-s")
        self.assertEqual(normalize_company_name(""), "unknown-company")

    def test_get_company_cache_path(self):
        with patch("config.COMPANY_RESEARCH_DIR", self.fake_cache_dir):
            p = get_company_cache_path("Acme Corp")
            self.assertEqual(p, self.fake_cache_dir / "acme-corp.json")

    def test_save_and_retrieve_fresh_cache(self):
        with patch("config.COMPANY_RESEARCH_DIR", self.fake_cache_dir):
            sources = {
                "website": {"url": "https://acme.com", "notes": "Líder en IA"},
                "reviews": {"url": "https://glassdoor.com/acme", "notes": "4.2 rating"},
            }
            saved_path = save_cached_research(
                company_name="Acme Corp",
                sources=sources,
                network_contacts_note="Conozco a un lead engineer",
            )
            self.assertTrue(saved_path.is_file())

            cached = get_cached_research("Acme Corp")
            self.assertIsNotNone(cached)
            self.assertEqual(cached["company"], "Acme Corp")
            self.assertEqual(cached["sources"]["website"]["url"], "https://acme.com")
            self.assertEqual(cached["_cache_age_days"], 0)

    def test_get_cached_research_expired(self):
        with patch("config.COMPANY_RESEARCH_DIR", self.fake_cache_dir):
            old_date = (date.today() - timedelta(days=35)).isoformat()
            save_cached_research(
                company_name="Old Company",
                sources={"website": {"url": "https://old.com"}},
                fetched_date=old_date,
            )

            # Por defecto TTL = 30 días, con 35 debe retornar None
            self.assertIsNone(get_cached_research("Old Company", max_age_days=30))
            # Con TTL = 40 días, debe ser válido
            fresh_with_higher_ttl = get_cached_research("Old Company", max_age_days=40)
            self.assertIsNotNone(fresh_with_higher_ttl)
            self.assertEqual(fresh_with_higher_ttl["_cache_age_days"], 35)

    def test_list_and_clear_expired_cache(self):
        with patch("config.COMPANY_RESEARCH_DIR", self.fake_cache_dir):
            # 1 fresh
            save_cached_research("Fresh Co", fetched_date=date.today().isoformat())
            # 1 expired
            save_cached_research("Expired Co", fetched_date=(date.today() - timedelta(days=45)).isoformat())

            listing = list_cached_companies(max_age_days=30)
            self.assertEqual(len(listing), 2)

            fresh_item = next(x for x in listing if x["company"] == "Fresh Co")
            expired_item = next(x for x in listing if x["company"] == "Expired Co")

            self.assertTrue(fresh_item["is_fresh"])
            self.assertFalse(expired_item["is_fresh"])

            # Limpiar expirados
            removed_count = clear_expired_cache(max_age_days=30)
            self.assertEqual(removed_count, 1)

            # Verificar que solo queda la fresca
            remaining = list_cached_companies(max_age_days=30)
            self.assertEqual(len(remaining), 1)
            self.assertEqual(remaining[0]["company"], "Fresh Co")


if __name__ == "__main__":
    unittest.main()
