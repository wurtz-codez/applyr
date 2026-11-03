"""Conservative deterministic enrichment; no LLM and no inferred publication dates."""

import re

from app.ingestion.schemas import Experience, Location, NormalizedJob

COUNTRIES = {
    "india": "IN",
    "in": "IN",
    "ind": "IN",
    "usa": "US",
    "us": "US",
    "united states": "US",
    "uk": "GB",
    "gbr": "GB",
    "deu": "DE",
    "germany": "DE",
    "canada": "CA",
    "australia": "AU",
    "singapore": "SG",
    "philippines": "PH",
    "united arab emirates": "AE",
    "netherlands": "NL",
    "france": "FR",
    "poland": "PL",
    "portugal": "PT",
    "spain": "ES",
    "brazil": "BR",
    "japan": "JP",
    "indonesia": "ID",
    "vietnam": "VN",
    "malaysia": "MY",
    "thailand": "TH",
    "mexico": "MX",
    "south africa": "ZA",
    "pakistan": "PK",
    "bangladesh": "BD",
    "sri lanka": "LK",
    "nepal": "NP",
    "china": "CN",
    "south korea": "KR",
    "new zealand": "NZ",
    "ireland": "IE",
    "italy": "IT",
    "sweden": "SE",
    "switzerland": "CH",
    "austria": "AT",
    "belgium": "BE",
    "finland": "FI",
    "denmark": "DK",
    "norway": "NO",
    "israel": "IL",
    "argentina": "AR",
    "colombia": "CO",
    "chile": "CL",
    "united kingdom": "GB",
}
CITIES = {
    "bangalore": "Bengaluru",
    "bengaluru": "Bengaluru",
    "bombay": "Mumbai",
    "mumbai": "Mumbai",
    "hyderabad": "Hyderabad",
    "pune": "Pune",
    "chennai": "Chennai",
    "gurgaon": "Gurugram",
    "gurugram": "Gurugram",
    "noida": "Noida",
    "delhi": "Delhi",
}


def country_code(value: str | None) -> str | None:
    if not value:
        return None
    return COUNTRIES.get(value.casefold(), value.upper() if len(value) == 2 else None)


def location(label=None, mode=None, country=None, eligible=None, globally_remote=None):
    label = re.sub(r"\bbangalore\b", "Bengaluru", label or "", flags=re.I) or None
    city = next((v for k, v in CITIES.items() if re.search(rf"\b{k}\b", label or "", re.I)), None)
    code = country_code(country)
    if not code:
        code = next(
            (
                v
                for k, v in COUNTRIES.items()
                if len(k) > 2 and re.search(rf"\b{re.escape(k)}\b", label or "", re.I)
            ),
            None,
        )
    if not code and city:
        code = "IN"
    mode = (mode or "unknown").lower().replace("-", "")
    mode = {"onsite": "onsite", "remote": "remote", "hybrid": "hybrid"}.get(mode, "unknown")
    if mode == "unknown" and re.search(r"\bremote\b", label or "", re.I):
        mode = "remote"
    eligible_codes = (
        None
        if eligible is None
        else sorted({code for item in eligible if (code := country_code(item))})
    )
    # A remote office address alone does not establish applicant eligibility.
    india = None
    if mode != "remote" and code:
        india = code == "IN"
    if eligible_codes:
        india = "IN" in eligible_codes
    if (
        mode == "remote"
        and eligible_codes is None
        and re.search(r"\b(worldwide|global|anywhere in the world)\b", label or "", re.I)
        and not re.search(r"except|excluding|only", label or "", re.I)
    ):
        globally_remote = True
    if globally_remote is True and not eligible_codes:
        india = True
    return Location(
        label=label,
        country=code,
        city=city,
        remote_type=mode,
        eligible_countries=eligible_codes,
        globally_remote=globally_remote,
        india_eligible=india,
        confidence=0.9 if code else None,
        evidence="source address/label" if code else None,
    )


def experience(description: str) -> Experience:
    matches = list(
        re.finditer(
            r"\b(\d{1,2})(?:\s*[-–to]+\s*(\d{1,2}))?\s*(\+)?\s*years?\s+(?:of\s+)?"
            r"(?:(?:relevant|professional|software|development|engineering|work|industry)\s+)*experience",
            description,
            re.I,
        )
    )
    if matches:
        match = max(matches, key=lambda m: int(m[1]))
        return Experience(
            min_years=int(match[1]),
            max_years=int(match[2]) if match[2] else None,
            confidence=0.85,
            evidence=match[0],
        )
    if re.search(r"\b(no (?:prior )?experience required|freshers? welcome)\b", description, re.I):
        return Experience(min_years=0, confidence=0.9, evidence="explicit no experience required")
    return Experience()


def enrich(job: NormalizedJob) -> NormalizedJob:
    if job.experience.confidence is None:
        job.experience = experience(job.description)
    skills = [
        s
        for s in [
            "Python",
            "SQL",
            "Java",
            "JavaScript",
            "TypeScript",
            "Go",
            "React",
            "PostgreSQL",
            "Docker",
            "Kubernetes",
            "AWS",
        ]
        if re.search(rf"\b{s}\b", job.description, re.I)
    ]
    job.skills = sorted(set(job.skills + skills))
    senior = bool(
        re.search(r"\b(senior|sr\.?|staff|principal|lead|manager|director|head)\b", job.title, re.I)
    )
    role = bool(
        re.search(r"software|\bsde\b|backend|back.end|full.stack|developer", job.title, re.I)
    )
    from app.ingestion.eligibility import evaluate

    evaluation = evaluate(job)
    job.location.india_eligible = {"CONFIRMED": True, "NOT_ELIGIBLE": False, "UNCERTAIN": None}[
        evaluation["status"]
    ]
    job.derived["india_eligibility"] = evaluation
    job.derived.update(
        senior=senior,
        target_role=role,
        junior_fit=False
        if senior or (job.experience.min_years or 0) > 2
        else True
        if job.experience.confidence
        else None,
        skills_method="keyword",
        experience_method="regex",
    )
    return job


def feed_location(provider, label, mode):
    """These two feeds explicitly label applicant countries, rather than employer offices."""
    eligible, worldwide = None, None
    if provider in {"jobicy", "remotive"} and label:
        if label.strip().casefold() in {"anywhere", "worldwide", "worldwide remote"}:
            worldwide = True
        else:
            parts = re.split(r"[,;|]|\s+and\s+|\s+/\s+", label, flags=re.I)
            codes = [country_code(p.strip()) for p in parts]
            if codes and all(codes):
                eligible = codes
    return location(label, mode, eligible=eligible, globally_remote=worldwide)
