import re

from app.models.discovery import Job
from app.schemas.profile import ProfileInput

INDIA_CITIES = (
    r"india|bengaluru|bangalore|hyderabad|pune|mumbai|chennai|noida|gurugram|gurgaon|"
    r"new delhi|kolkata"
)
ROLES = r"software|backend|back.end|full.stack|sde|swe|frontend|front.end"


def eligibility(job: Job, profile: ProfileInput) -> tuple[str, list[str]]:
    title = job.title.lower()
    description = job.description_text.lower().replace("–", "-").replace("—", "-")
    location = job.location_text.lower()
    failures, unknowns, evidence = [], [], []
    if job.status != "OPEN":
        failures.append("The source no longer lists this opening after three successful scans.")
    if not re.search(rf"\b({ROLES})\b", title):
        failures.append("Title is outside the supported software engineering role families.")
    if re.search(r"\b(senior|staff|principal|lead|manager|architect|director|iii|iv)\b", title):
        failures.append("Title indicates a senior or leadership role.")
    if "intern" in title and not profile.preferences.internships:
        failures.append("Internships are disabled in your preferences.")
    preferences = [role.lower() for role in profile.preferences.roles]
    if not any(re.search(r"\b(software|sde|swe)\b", role) for role in preferences):
        if not any(
            ("backend" in role and re.search(r"back.end", title))
            or ("full" in role and re.search(r"full.stack", title))
            or ("front" in role and re.search(r"front.end", title))
            or role in title
            for role in preferences
        ):
            failures.append("Role does not match your selected role preferences.")
    india = bool(re.search(rf"\b({INDIA_CITIES})\b", location))
    remote = "remote" in location
    exclusion = re.search(
        r"(?:remote|location|based|applicants|candidates|residents|work).{0,45}"
        r"(?:us.only|usa.only|united states only|uk.only|europe.only|outside india)",
        location + " " + description,
    ) or re.search(
        r"(?:must|only).{0,35}(?:based|reside|located).{0,20}(?:united states|usa|uk|europe)",
        description,
    )
    exclusion = (
        exclusion
        or re.search(r"remote.{0,20}\b(us|usa|united states|uk|canada|europe)\b", location)
        and not india
        or re.search(r"(?:not available|not open|exclud(?:es|ing)).{0,20}\bindia\b", description)
    )
    if remote and not profile.preferences.india_eligible_remote:
        failures.append("Remote opportunities are disabled in your preferences.")
    if exclusion:
        failures.append("The listing restricts location outside India.")
    elif india:
        evidence.append("The listed location includes India or a recognized Indian city.")
    elif remote and profile.preferences.india_eligible_remote:
        if re.search(r"\b(worldwide|anywhere in the world|global remote)\b", location):
            evidence.append("The location explicitly advertises worldwide remote work.")
        elif re.search(
            r"(?:remote (?:in|from)|based in|(?:applicants|candidates) (?:from|in))\s+india\b",
            description,
        ):
            evidence.append("The description explicitly includes India for remote work.")
        else:
            unknowns.append("Remote work is listed, but India eligibility is not explicit.")
    elif remote:
        failures.append("Remote opportunities are disabled in your preferences.")
    elif location == "unspecified":
        unknowns.append("The job location is unspecified.")
    else:
        failures.append("The listed location is outside the supported India search area.")
    years = []
    patterns = [
        r"(?<![\d.])(\d{1,2})\s*(?:-|to)\s*\d{1,2}\s*years?\b.{0,45}?(?:experience|exp\b)",
        r"(?<![\d.])(\d{1,2})\s*\+?\s*years?\b.{0,45}?(?:experience|exp\b)",
        r"(?:experience|experienced)\s*(?:of|:|with)?\s*(\d{1,2})\s*\+?\s*years?\b",
    ]
    # Strip preferred-only sentences; required and ambiguous experience remain gates.
    sentences = re.split(r"[.;\n]", description)
    required_text = ". ".join(
        s
        for s in sentences
        if not re.search(r"preferred|nice.to.have|bonus", s)
        or re.search(r"required|must|minimum|at least", s)
    )
    required_text = re.sub(r"(\d+)\s*(?:-|to)\s*\d+\s*(years?)", r"\1 \2", required_text)
    patterns.append(r"(?:minimum|at least)\s*(?:of\s*)?(\d{1,2})\s*\+?\s*years?\b")
    for pattern in patterns:
        years.extend(int(value) for value in re.findall(pattern, required_text))
    if years:
        minimum = max(years)
        if minimum > profile.preferences.max_experience_years:
            failures.append(
                f"Requires at least {minimum} years; "
                f"your search limit is {profile.preferences.max_experience_years}."
            )
        else:
            evidence.append(f"Explicit experience requirement starts at {minimum} years.")
    elif re.search(
        r"new.grad|freshers?|entry.level|no (?:prior )?experience|graduate engineer",
        description + " " + title,
    ):
        evidence.append("The listing explicitly welcomes early-career applicants.")
    else:
        unknowns.append("An explicit compatible experience requirement was not found.")
    if re.search(
        r"(?:must|required|requires|mandatory).{0,60}"
        r"(?:degree|bachelor|master|ph\.?d|graduat|citizen|authorization|visa)",
        description,
    ):
        unknowns.append(
            "Education, graduation, or work-authorization requirements need manual verification."
        )
    if job.description_truncated or not description.strip():
        unknowns.append("The job description is missing or truncated.")
    if failures:
        return "INELIGIBLE", failures + unknowns + evidence
    if unknowns:
        return "NEEDS_REVIEW", unknowns + evidence
    return "ELIGIBLE", evidence
