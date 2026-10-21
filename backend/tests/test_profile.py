"""
tests/test_profile.py — Smoke tests for backend/profile.json.
Guards the schema fields consumed by ats_handlers/ and cover_letter.py so a
future edit to profile.json can't silently break real form-filling/emailing.
"""
import json
import pytest
import sys
from pathlib import Path
from config import PROFILE_PATH  # noqa: E402
sys.path.insert(0, str(Path(__file__).parent.parent))


def _load():
    return json.loads(PROFILE_PATH.read_text(encoding="utf-8"))


def test_profile_is_valid_json():
    profile = _load()
    assert isinstance(profile, dict)


def test_personal_has_fields_used_by_ats_handlers():
    personal = _load()["personal"]
    for field in ("name", "first_name", "last_name", "email", "phone", "linkedin", "portfolio"):
        assert field in personal
    assert '@' in personal["email"] and personal["email"].strip()


def test_dni_nie_has_valid_spanish_checksum():
    dni = _load()["personal"]["dni_nie"]
    letters = "TRWAGMYFPDXBNJZSQVHLCKE"
    number, letter = dni[:-1], dni[-1]
    assert letters[int(number) % 23] == letter


def test_availability_and_salary_expectation_present():
    profile = _load()
    assert "start_date" in profile["availability"]
    assert "amount" in profile["salary_expectation"]


def test_cover_letter_intro_keeps_company_name_placeholder():
    # cover_letter.py does .format(company_name=...) on this string — it must
    # keep the placeholder or letter generation breaks silently.
    profile = _load()
    assert "{company_name}" in profile["cover_letter_intro"]


def test_experience_entries_have_fields_used_by_jinja_templates():
    for exp in _load()["experience"]:
        for field in ("company", "role", "duration_months", "description"):
            assert field in exp


@pytest.mark.skipif(PROFILE_PATH.name == "profile.example.json", reason="los CVs reales no están versionados")
def test_cv_paths_point_to_existing_files():
    base = Path(__file__).parent.parent
    profile = _load()
    paths = {k: profile[k] for k in ("cv_path", "cv_sap_path", "cv_ia_path", "cv_ia_path_en", "cv_general_path")}
    paths.update({f"cv_sap_modules.{k}": v for k, v in profile["cv_sap_modules"].items()})
    for key, rel in paths.items():
        assert (base / rel).exists(), f"{key} -> {rel} missing"
