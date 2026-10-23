import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import check_version as cv  # noqa: E402


def test_las_versiones_del_repositorio_coinciden():
    assert cv.check(cv.versions()) == []


def test_detecta_versiones_distintas():
    assert cv.check({"a": "0.1.0", "b": "0.2.0"})


def test_el_tag_debe_coincidir():
    found = {"a": "0.1.0", "b": "0.1.0"}
    assert cv.check(found, "v0.1.0") == []
    assert cv.check(found, "0.1.0") == []
    assert cv.check(found, "v0.2.0")
    assert cv.check(found, "v0.1.0-rc1")
