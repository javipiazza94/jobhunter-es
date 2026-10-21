def test_sap_keywords_non_empty():
    from search_config import get_config
    kws = get_config().track("sap").search_keywords
    assert len(kws) >= 10
    assert "SAP BTP" in kws
    assert "S/4HANA" in kws

def test_sap_companies_direct_structure():
    from search_config import source_settings
    companies = source_settings("company_direct")["companies"]
    assert len(companies) >= 5
    for c in companies:
        assert "name" in c
        assert "careers_url" in c
        assert c["careers_url"].startswith("https://")

def test_linkedin_sap_searches_structure():
    from search_config import source_settings
    searches = [s for s in source_settings("linkedin")["searches"] if s.get("track") == "sap"]
    assert len(searches) >= 3
    for s in searches:
        assert "keywords" in s
        assert "location" in s

def test_sessions_paths_defined():
    from config import SESSIONS_DIR, LINKEDIN_SESSION_PATH
    assert "sessions" in str(SESSIONS_DIR)
    assert str(LINKEDIN_SESSION_PATH).endswith(".json")

def test_new_profile_constants_exist():
    from config import RECONTACT_COOLDOWN_DAYS
    assert RECONTACT_COOLDOWN_DAYS > 0

def test_max_emails_per_day_is_positive():
    from config import MAX_EMAILS_PER_DAY
    assert MAX_EMAILS_PER_DAY > 0
