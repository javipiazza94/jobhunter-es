import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))


def test_generate_returns_string():
    from automation.cover_letter import generate
    result = generate("Empresa Test", job_title="Python Dev", template="tech")
    assert isinstance(result, str)
    assert "Empresa Test" in result


def test_generate_variant_seed_same_seed_same_result():
    from automation.cover_letter import generate
    r1 = generate("ACME", "Python Dev", template="tech", variant_seed="ACME-Python Dev")
    r2 = generate("ACME", "Python Dev", template="tech", variant_seed="ACME-Python Dev")
    assert r1 == r2


def test_generate_different_seeds_may_differ():
    from automation.cover_letter import generate
    r1 = generate("ACME", "Python Dev", template="tech", variant_seed="ACME-Python Dev")
    r2 = generate("ACME", "Python Dev", template="tech", variant_seed="OtherCo-SAP Dev")
    # They might happen to be equal if same variant bucket; test just checks no crash
    assert isinstance(r1, str) and isinstance(r2, str)


def test_pick_variant_deterministic():
    from automation.cover_letter import _pick_variant
    variants = ["A", "B", "C"]
    r1 = _pick_variant(variants, "seed123")
    r2 = _pick_variant(variants, "seed123")
    assert r1 == r2
    assert r1 in variants


def test_generate_sap_template():
    from automation.cover_letter import generate
    result = generate("Capgemini", job_title="Consultor SAP PS", template="sap")
    assert isinstance(result, str)
    assert "Capgemini" in result
