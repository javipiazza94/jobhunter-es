"""Alta individual: genera la línea que lee load_inbox_applications.py y no repite lo ya pendiente."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import add_application as aa  # noqa: E402


def test_line_has_the_six_loader_fields():
    line = aa.build_line("ACME S.L.", "Consultor SAP FI", "sent", "2026-10-08")
    assert line.split("|") == ["2026-10-08", "ACME S.L.", "Consultor SAP FI", "", "sent", "portal-acme-s-l-consultor-sap-fi"]


def test_key_is_stable_so_repeating_does_not_duplicate():
    a = aa.build_line("Ñandú Tech", "Analista SAP", when="2026-10-08")
    b = aa.build_line("  Ñandú   Tech ", "Analista SAP", when="2026-10-09")
    assert a.split("|")[5] == b.split("|")[5] == "portal-nandu-tech-analista-sap"


def test_pipes_and_newlines_cannot_break_the_format():
    cols = aa.build_line("A|B\nC", "X|Y", when="2026-10-08").split("|")
    assert len(cols) == 6 and cols[1] == "A B C" and cols[2] == "X Y"


@pytest.mark.parametrize("kwargs", [
    {"company": "", "position": "x"},
    {"company": "x", "position": " "},
    {"company": "x", "position": "y", "state": "enviada"},
    {"company": "x", "position": "y", "when": "08/10/2026"},
])
def test_invalid_input_is_rejected(kwargs):
    with pytest.raises(ValueError):
        aa.build_line(kwargs.pop("company"), kwargs.pop("position"), **{"state": "sent", **kwargs})


def test_append_does_not_repeat_a_pending_line(tmp_path):
    line = aa.build_line("ACME", "Dev", when="2026-10-08")
    aa.append_line(line, tmp_path)
    path = aa.append_line(line, tmp_path)
    assert path.name == "candidaturas_manual.txt"
    assert path.read_text(encoding="utf-8").splitlines() == [line]


def test_main_writes_to_the_inbox_and_reports_errors(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(aa, "INBOX_DIR", tmp_path)
    assert aa.main(["ACME", "Dev", "--fecha", "2026-10-08"]) == 0
    assert (tmp_path / aa.MANUAL_FILE).read_text(encoding="utf-8").startswith("2026-10-08|ACME|Dev|")
    assert aa.main(["ACME", "Dev", "--fecha", "mañana"]) == 2
    assert "Error" in capsys.readouterr().err
