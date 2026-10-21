_ATS_PATTERNS = {
    "workday":        ["myworkdayjobs.com", "workday.com/job"],
    "greenhouse":     ["greenhouse.io"],
    "lever":          ["jobs.lever.co"],
    "successfactors": ["successfactors.eu", "successfactors.com", "jobs.sap.com", "sapsf.eu", "sapsf.com", "sapsf.cn"],
}


def detect_ats(url: str) -> str:
    url_lower = url.lower()
    for name, patterns in _ATS_PATTERNS.items():
        if any(p in url_lower for p in patterns):
            return name
    return "generic"
