"""Stable codes for jurisdictions that can be identified from explicit records."""
ALIASES = {
    "kr": "KR", "kor": "KR", "한국": "KR", "대한민국": "KR", "south korea": "KR",
    "republic of korea": "KR", "korea (republic of)": "KR",
    "us": "US", "usa": "US", "미국": "US", "united states": "US", "united states of america": "US",
    "de": "DE", "germany": "DE", "deutschland": "DE", "독일": "DE",
    "fr": "FR", "france": "FR", "프랑스": "FR",
    "es": "ES", "spain": "ES", "españa": "ES", "스페인": "ES",
    "it": "IT", "italy": "IT", "italia": "IT", "이탈리아": "IT",
    "eu": "EU", "european union": "EU", "유럽연합": "EU",
}


def market_code(jurisdiction):
    return ALIASES.get((jurisdiction or "").strip().casefold(), "XX")
