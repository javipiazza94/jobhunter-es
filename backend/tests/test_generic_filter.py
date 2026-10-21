from automation.generic_filter import score_isolated
from search_config import get_config


def _score(offer):
    return score_isolated(offer, get_config().track("generic"))


def _offer(title, location="Villanova", description="", salary_min=None):
    return {"title": title, "location": location, "description": description, "salary_min": salary_min}


def test_customer_service_in_villanova_scores_high():
    s = _score(_offer("Teleoperador atención al cliente", description="Sin experiencia"))
    assert s is not None and s >= 0.8


def test_remote_in_title_accepted_for_other_city():
    assert _score(_offer("Administrativo teletrabajo", location="Madrid")) is not None


def test_other_city_excluded():
    assert _score(_offer("Dependiente de tienda", location="Barcelona")) is None


def test_province_towns_accepted_other_provinces_excluded():
    assert _score(_offer("Camarero", location="Alto Verde, Villanova provincia")) is not None
    assert _score(_offer("Camarero", location="Villanova provincia")) is not None
    assert _score(_offer("Camarero", location="Costa Lira")) is not None
    assert _score(_offer("Camarero", location="Madrid")) is None
    assert _score(_offer("Camarero", location="Valdemar")) is not None
    assert _score(_offer("Camarero", location="Villanova, Villanova provincia")) is not None
    assert _score(_offer("Camarero", location="Villanova")) is not None


def test_internships_and_formative_contracts_excluded():
    assert _score(_offer("Receptionist trainee", description="Internship")) is None
    assert _score(_offer("Auxiliar administrativo", description="Prácticas no laborales")) is None
    assert _score(_offer("Camarero", description="Contrato para la formación, menores de 30 años")) is None


def test_other_region_excluded():
    assert _score(_offer("Camarero", location="Puerto Seco, Región Norte")) is None


def test_senior_and_qualified_roles_excluded():
    assert _score(_offer("Responsable de atención al cliente")) is None
    assert _score(_offer("Consultor SAP atención al cliente")) is None
    assert _score(_offer("Auxiliar administrativo", description="Titulación universitaria")) is None


def test_commission_only_excluded():
    assert _score(_offer("Comercial atención al cliente", description="100% comisiones")) is None


def test_experience_required_excluded_and_unknown_ranks_lower():
    assert _score(_offer("Camarero", description="Mínimo 3 años de experiencia")) is None
    junior = _score(_offer("Camarero", description="Sin experiencia"))
    unknown = _score(_offer("Camarero"))
    assert junior > unknown


def test_no_role_match_excluded():
    assert _score(_offer("Soldador industrial")) is None


def test_disability_reserved_offers_excluded():
    assert _score(_offer("Recepcionista CON DISCAPACIDAD para Villanova capital")) is None
    assert _score(_offer("Auxiliar administrativo", description="Con certificado de discapacidad")) is None
