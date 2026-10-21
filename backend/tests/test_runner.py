import sys
import argparse
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))


def _make_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source",
        choices=["seed", "tecnoempleo", "contacts", "all", "sap", "linkedin-login"],
    )
    return parser

def test_parser_accepts_sap_source():
    args = _make_parser().parse_args(["--source", "sap"])
    assert args.source == "sap"

def test_parser_accepts_linkedin_login_source():
    args = _make_parser().parse_args(["--source", "linkedin-login"])
    assert args.source == "linkedin-login"

def test_runner_module_has_run_track_source():
    import scraper.runner as r
    assert callable(getattr(r, "run_track_source", None))
