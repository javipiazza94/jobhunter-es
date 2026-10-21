import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from automation.salary import classify_offer_location, resolve_salary, profile_for_offer
from config import PROFILE_PATH  # noqa: E402

PROFILE = {
    "salary_expectation": {
        "amount": 26000,
        "amount_remote_or_target_city": 26000,
        "amount_onsite_or_hybrid_outside_target_city": 30000,
    }
}


def _amount(location, title=None):
    return resolve_salary(PROFILE, {"location": location, "title": title})[0]


def test_target_city_any_modality_is_26k():
    assert _amount("Villanova") == 26000
    assert _amount("Villanova (Presencial)") == 26000
    assert _amount("Villanova (Híbrido)") == 26000
    assert _amount("Villanova y otras") == 26000


def test_target_province_towns_count_as_target_city():
    assert _amount("Valdemar (Híbrido)") == 26000
    assert _amount("Costa Lira") == 26000


def test_fully_remote_is_26k_wherever_the_company_is():
    assert _amount("100% remoto") == 26000
    assert _amount("España (En remoto)") == 26000
    assert _amount("Madrid (En remoto)") == 26000
    assert _amount("Barcelona", title="Consultor SAP (Remoto)") == 26000


def test_onsite_or_hybrid_outside_target_is_30k():
    assert _amount("Madrid (Híbrido)") == 30000
    assert _amount("Barcelona (Presencial)") == 30000
    assert _amount("Granada") == 30000  # ciudad concreta sin modalidad -> hay que desplazarse
    assert _amount("Madrid (Híbrido) y remoto ocasional") == 30000


def test_unknown_location_uses_default_never_guesses_up():
    assert classify_offer_location(None) == "unknown"
    assert _amount(None) == 26000
    assert _amount("") == 26000


def test_missing_new_keys_falls_back_to_amount():
    legacy = {"salary_expectation": {"amount": 30000}}
    assert resolve_salary(legacy, {"location": "Madrid (Híbrido)"})[0] == 30000
    assert resolve_salary(legacy, {"location": "Villanova"})[0] == 30000


def test_legacy_keys_backward_compatible(caplog):
    from automation.salary import LEGACY_SALARY_KEYS
    old_target, old_outside = (old for old, _new in LEGACY_SALARY_KEYS.items())
    assert set(LEGACY_SALARY_KEYS.values()) == {
        "amount_remote_or_target_city", "amount_onsite_or_hybrid_outside_target_city"}
    legacy = {"salary_expectation": {"amount": 20000, old_target: 25000, old_outside: 28000}}
    with caplog.at_level("WARNING", logger="automation.salary"):
        assert resolve_salary(legacy, {"location": "Villanova"})[0] == 25000
    warnings = [r for r in caplog.records if r.levelname == "WARNING"]
    assert len(warnings) == 1  # una vez por llamada, aunque haya dos claves antiguas
    assert "amount_remote_or_target_city" in warnings[0].getMessage()
    assert "amount_onsite_or_hybrid_outside_target_city" in warnings[0].getMessage()
    assert resolve_salary(legacy, {"location": "Madrid (Híbrido)"})[0] == 28000


def test_new_keys_do_not_warn(caplog):
    with caplog.at_level("WARNING", logger="automation.salary"):
        resolve_salary(PROFILE, {"location": "Villanova"})
    assert not [r for r in caplog.records if r.levelname == "WARNING"]


def test_unknown_prefixed_keys_are_not_matched():
    """Solo se aceptan las claves antiguas listadas, no cualquier `amount_remote_or_<algo>`."""
    custom = {
        "salary_expectation": {
            "amount": 20000,
            "amount_remote_or_custom_city": 25000,
            "amount_onsite_or_hybrid_outside_custom_city": 28000,
        }
    }
    assert resolve_salary(custom, {"location": "Villanova"})[0] == 20000
    assert resolve_salary(custom, {"location": "Madrid (Híbrido)"})[0] == 20000


def test_profile_for_offer_does_not_mutate_original_and_feeds_handlers():
    from automation.ats_handlers.generic import _map_field
    adjusted = profile_for_offer(PROFILE, {"location": "Madrid (Híbrido)"})
    assert adjusted["salary_expectation"]["amount"] == 30000
    assert PROFILE["salary_expectation"]["amount"] == 26000
    assert _map_field("salary_pretension", adjusted) == "30000"
    remote = profile_for_offer(PROFILE, {"location": "100% remoto"})
    assert _map_field("salary_pretension", remote) == "26000"


def test_real_profile_json_has_the_rule_keys():
    profile = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
    sal = profile["salary_expectation"]
    assert sal["amount_remote_or_target_city"] == 26000
    assert sal["amount_onsite_or_hybrid_outside_target_city"] == 30000
