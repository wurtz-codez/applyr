"""Versioned geographic relevance, separate from a candidate's right to work."""

import re

from app.models import now

VERSION = 2
INDIA = (
    r"\b(?:india|bengaluru|bangalore|hyderabad|pune|chennai|mumbai|gurugram|gurgaon|"
    r"noida|new delhi|delhi|kolkata|ahmedabad|kochi|coimbatore|"
    r"thiruvananthapuram|indore|jaipur)\b"
)
FOREIGN = (
    r"\b(?:united states|usa|united "
    r"kingdom|uk|germany|berlin|london|canada|toronto|australia|sydney|singapore|"
    r"france|paris|netherlands|amsterdam|poland|warsaw|spain|madrid|portugal|"
    r"lisbon|brazil|japan|tokyo|new york|san francisco)\b"
)
WORLD = r"\b(?:worldwide|anywhere in the world|work from anywhere|global(?:ly)? remote)\b"


def evaluate(job):
    """Explicit applicant restrictions outrank workplace labels; ambiguity stays visible."""
    desc = job.description or ""
    locations = [job.location, *job.additional_locations]
    evidence = []

    def result(status, reason, proof, confidence=0.95):
        return dict(
            status=status,
            reason=reason,
            evidence={"observations": proof},
            method="deterministic",
            confidence=confidence,
            version=VERSION,
        )

    exclusion = re.search(
        r"\b(?:excluding|except|not (?:available|open) (?:in|to)|cannot "
        r"(?:hire|employ) (?:in|from))\s+(?:candidates (?:in|from)\s+)?India\b",
        desc,
        re.I,
    )
    if exclusion:
        return result("NOT_ELIGIBLE", "explicit_india_exclusion", [exclusion[0]])
    foreign_only = re.search(
        r"\b(?:must be "
        r"(?:based|located|resident)|(?:candidates|applicants) (?:based|located)|remote)"
        r"\s+(?:in |from )?(?:the )?(?:US|USA|United States|UK|United Kingdom|"
        r"Canada|Europe|EU|Australia)\s+only\b",
        desc,
        re.I,
    )
    if foreign_only:
        return result("NOT_ELIGIBLE", "explicit_foreign_only", [foreign_only[0]])
    # Applicant restrictions from structured source metadata are more reliable than an office.
    restrictions = [loc.eligible_countries for loc in locations if loc.eligible_countries]
    if restrictions:
        countries = {c for codes in restrictions for c in codes}
        return result(
            "CONFIRMED" if "IN" in countries else "NOT_ELIGIBLE",
            "explicit_applicant_countries",
            sorted(countries),
        )
    for loc in locations:
        label = loc.label or ""
        if re.search(r"\b(?:except|excluding)\s+India\b", label, re.I):
            return result("NOT_ELIGIBLE", "explicit_india_exclusion", [label])
        if re.search(INDIA, label, re.I):
            evidence.append(label)
        elif loc.country == "IN" and loc.remote_type != "remote":
            evidence.append(f"workplace country: {loc.country}")
    if evidence:
        return result("CONFIRMED", "explicit_indian_work_location", evidence)
    # Description evidence must state where applicants can work, not mention a company office.
    explicit = re.search(
        r"\b(?:remote\s*[-—–:]?\s*(?:from |in "
        r")?India|(?:candidates|applicants)\s+(?:based |located )?in India|"
        r"(?:work|working) remotely from India)\b",
        desc,
        re.I,
    )
    if explicit:
        return result("CONFIRMED", "explicit_india_applicant_text", [explicit[0]], 0.9)
    for loc in locations:
        label = loc.label or ""
        if loc.globally_remote is True or re.search(WORLD, label, re.I):
            contradictions = re.search(
                r"\b(?:except|excluding|only|timezone|time zone|UTC|GMT)\b", f"{label} {desc}", re.I
            )
            if not contradictions and not job.derived.get("timezone_restrictions"):
                return result(
                    "CONFIRMED",
                    "explicit_worldwide_remote",
                    [label or "source worldwide flag"],
                    0.9,
                )
        if re.search(
            r"\b(?:US|USA|UK|United States|United "
            r"Kingdom|Canada|Europe|EU|Australia)\s*(?:[-—–:]?\s*remote\s*)?only\b",
            label,
            re.I,
        ):
            return result("NOT_ELIGIBLE", "explicit_foreign_only", [label])
    if locations and all(
        loc.remote_type in {"onsite", "hybrid", "unknown"}
        and (loc.country not in {None, "IN"} or re.search(FOREIGN, loc.label or "", re.I))
        for loc in locations
    ):
        return result(
            "NOT_ELIGIBLE",
            "explicit_foreign_work_location",
            [loc.label or loc.country for loc in locations],
        )
    return result(
        "UNCERTAIN",
        "insufficient_or_ambiguous_geography",
        [loc.label for loc in locations if loc.label],
        None,
    )


def apply_evaluation(row, job):
    evaluation = evaluate(job)
    row.india_status = evaluation["status"]
    row.india_eligible = {"CONFIRMED": True, "NOT_ELIGIBLE": False, "UNCERTAIN": None}[
        row.india_status
    ]
    row.eligibility_reason = evaluation["reason"]
    row.eligibility_evidence = evaluation["evidence"]
    row.eligibility_method = evaluation["method"]
    row.eligibility_confidence = evaluation["confidence"]
    row.eligibility_evaluated_at = now()
    row.normalization_version = VERSION
    job.location.india_eligible = row.india_eligible
    job.derived["india_eligibility"] = evaluation
    return evaluation
