"""
test_eligibility_gate.py — Pruebas del filtro de elegibilidad ampliado
(permiso de trabajo, visado, residencia, titulación y carné de conducir).
"""

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from automation.eligibility_gate import eligibility_gate  # noqa: E402


class TestEligibilityGate(unittest.TestCase):
    def setUp(self):
        self.spain_profile = {
            "personal": {
                "name": "Javi",
                "country": "España",
                "country_code": "ES",
                "nationality": "Española",
                "dni_nie": "12345678Z",
                "driving_license": None,
            },
            "education": [
                {"title": "Grado en Periodismo"},
                {"title": "Máster en Inteligencia Artificial"},
            ],
            "languages": [
                {"language": "Español", "level": "Nativo"},
                {"language": "Inglés", "level": "B2"},
            ],
        }

    def test_clean_offer_is_ok(self):
        offer = {
            "title": "Desarrollador Python",
            "description": "Trabajo remoto desde España. Stack: FastAPI, PostgreSQL.",
        }
        verdict, reasons = eligibility_gate(offer, profile_data=self.spain_profile)
        self.assertEqual(verdict, "ok")
        self.assertEqual(reasons, [])

    def test_delegates_language_gate_rejection(self):
        offer = {
            "title": "Backend Engineer",
            "description": "Imprescindible alemán C1 fluido para comunicarse con clientes.",
        }
        verdict, reasons = eligibility_gate(offer, profile_data=self.spain_profile)
        self.assertEqual(verdict, "reject")
        self.assertTrue(any("alemán" in r for r in reasons))

    def test_delegates_language_gate_flag(self):
        offer = {
            "title": "Python Specialist",
            "description": "Requisito: nivel de inglés C1 para reuniones técnicas.",
        }
        verdict, reasons = eligibility_gate(offer, profile_data=self.spain_profile)
        self.assertEqual(verdict, "flag")
        self.assertTrue(any("inglés" in r for r in reasons))

    def test_rejects_us_citizenship_requirement(self):
        offer = {
            "title": "Cloud Architect",
            "description": "US citizenship required for government defense systems.",
        }
        verdict, reasons = eligibility_gate(offer, profile_data=self.spain_profile)
        self.assertEqual(verdict, "reject")
        self.assertTrue(any("ciudadanía estadounidense" in r for r in reasons))

    def test_rejects_security_clearance_requirement(self):
        offer = {
            "title": "Security Analyst",
            "description": "Active top secret clearance required before onboarding.",
        }
        verdict, reasons = eligibility_gate(offer, profile_data=self.spain_profile)
        self.assertEqual(verdict, "reject")
        self.assertTrue(any("habilitación de seguridad" in r for r in reasons))

    def test_rejects_us_no_sponsorship(self):
        offer = {
            "title": "Software Engineer",
            "description": "Candidate must be authorized to work in the US without sponsorship.",
        }
        verdict, reasons = eligibility_gate(offer, profile_data=self.spain_profile)
        self.assertEqual(verdict, "reject")
        self.assertTrue(any("sin patrocinio" in r for r in reasons))

    def test_passes_spain_work_permit_for_spanish_resident(self):
        offer = {
            "title": "Desarrollador Frontend",
            "description": "Imprescindible permiso de trabajo en España.",
        }
        verdict, reasons = eligibility_gate(offer, profile_data=self.spain_profile)
        self.assertEqual(verdict, "ok")
        self.assertEqual(reasons, [])

    def test_rejects_spain_work_permit_if_explicitly_false(self):
        profile = dict(self.spain_profile)
        profile["personal"] = dict(profile["personal"], work_permit=False, country_code="OTHER")
        offer = {
            "title": "Desarrollador Frontend",
            "description": "Imprescindible permiso de trabajo en España.",
        }
        verdict, reasons = eligibility_gate(offer, profile_data=profile)
        self.assertEqual(verdict, "reject")
        self.assertTrue(any("permiso de trabajo" in r for r in reasons))

    def test_rejects_non_eu_residency(self):
        offer = {
            "title": "Fullstack Engineer",
            "description": "Remote position, but candidate must be based in the US.",
        }
        verdict, reasons = eligibility_gate(offer, profile_data=self.spain_profile)
        self.assertEqual(verdict, "reject")
        self.assertTrue(any("residencia" in r for r in reasons))

    def test_degree_requirement_passes_when_candidate_has_degree(self):
        offer = {
            "title": "Consultor Tecnológico",
            "description": "Grado universitario obligatorio para acceder al puesto.",
        }
        verdict, reasons = eligibility_gate(offer, profile_data=self.spain_profile)
        self.assertEqual(verdict, "ok")

    def test_degree_requirement_rejects_when_candidate_has_no_degree(self):
        profile = dict(self.spain_profile)
        profile["education"] = [{"title": "Bachillerato"}]
        offer = {
            "title": "Consultor Tecnológico",
            "description": "Grado universitario obligatorio para acceder al puesto.",
        }
        verdict, reasons = eligibility_gate(offer, profile_data=profile)
        self.assertEqual(verdict, "reject")
        self.assertTrue(any("titulación universitaria" in r for r in reasons))

    def test_degree_requirement_passes_if_or_equivalent_experience(self):
        profile = dict(self.spain_profile)
        profile["education"] = [{"title": "Bachillerato"}]
        offer = {
            "title": "Software Engineer",
            "description": "Bachelor degree or equivalent experience required.",
        }
        verdict, reasons = eligibility_gate(offer, profile_data=profile)
        self.assertEqual(verdict, "ok")

    def test_driving_license_handling(self):
        offer = {
            "title": "Técnico de Campo",
            "description": "Carné de conducir imprescindible para visitas presenciales.",
        }
        # 1. Sin carné especificado (None) -> flag (aviso para el usuario)
        v1, r1 = eligibility_gate(offer, profile_data=self.spain_profile)
        self.assertEqual(v1, "flag")
        self.assertTrue(any("carné" in r for r in r1))

        # 2. Con carné declarado explícitamente en True o ['B'] -> ok
        p2 = dict(self.spain_profile)
        p2["personal"] = dict(p2["personal"], driving_license=["B"])
        v2, r2 = eligibility_gate(offer, profile_data=p2)
        self.assertEqual(v2, "ok")

        # 3. Con carné declarado explícitamente en False -> reject
        p3 = dict(self.spain_profile)
        p3["personal"] = dict(p3["personal"], driving_license=False)
        v3, r3 = eligibility_gate(offer, profile_data=p3)
        self.assertEqual(v3, "reject")
        self.assertTrue(any("declaras no tenerlo" in r for r in r3))


if __name__ == "__main__":
    unittest.main()
