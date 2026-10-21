import sys
from pathlib import Path
from config import PROFILE_PATH  # noqa: E402
sys.path.insert(0, str(Path(__file__).parent.parent))


def test_fill_form_importable():
    from automation.form_filler import fill_form
    assert callable(fill_form)

def test_fill_form_dry_run_returns_true():
    import json
    from automation.form_filler import fill_form
    profile = json.loads(PROFILE_PATH.read_text())
    result = fill_form(
        "https://boards.greenhouse.io/acme/jobs/123",
        profile, None, "Test cover letter", dry_run=True
    )
    assert result is True

def test_fill_form_dry_run_detects_lever():
    from automation.form_filler import fill_form
    from automation.ats_handlers import detect_ats
    url = "https://jobs.lever.co/globex/abc123"
    assert detect_ats(url) == "lever"
    result = fill_form(url, {}, None, "", dry_run=True)
    assert result is True
