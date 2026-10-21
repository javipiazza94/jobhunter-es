import sys
import tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))


def test_save_and_load_session_roundtrip():
    from scraper.linkedin_jobs import save_linkedin_session, load_linkedin_session
    cookies = [{"name": "li_at", "value": "abc123", "domain": ".linkedin.com"}]
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        path = Path(f.name)
    save_linkedin_session(cookies, path)
    assert load_linkedin_session(path) == cookies

def test_load_session_returns_none_if_missing():
    from scraper.linkedin_jobs import load_linkedin_session
    assert load_linkedin_session(Path("/nonexistent/linkedin_session.json")) is None

def test_load_session_returns_none_if_invalid_json():
    from scraper.linkedin_jobs import load_linkedin_session
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
        f.write("not-valid-json{{{")
        path = Path(f.name)
    assert load_linkedin_session(path) is None

def test_is_checkpoint_detects_authwall():
    from scraper.linkedin_jobs import _is_checkpoint
    assert _is_checkpoint("https://www.linkedin.com/authwall?trk=...", "") is True
    assert _is_checkpoint("https://www.linkedin.com/feed/", "") is False
