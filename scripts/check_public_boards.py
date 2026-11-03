"""Live public board validation; archives counts and evidence, never full descriptions.

Without arguments, run the original four-provider smoke check. --candidates
accepts a JSON array of company/ats_provider/board_token/source_url entries.
Only endpoints returning actual India-located records enter --output.
"""

import argparse
import asyncio
import json
import re
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps/api"))
from app.ingestion.discovery.validation import board_endpoint, board_records  # noqa: E402
from app.ingestion.http import retry_seconds  # noqa: E402

ENDPOINTS = {
    "greenhouse": "https://boards-api.greenhouse.io/v1/boards/greenhouse/jobs",
    "lever": "https://api.lever.co/v0/postings/leverdemo?mode=json&limit=1",
    "ashby": "https://api.ashbyhq.com/posting-api/job-board/Ashby",
    "smartrecruiters": "https://api.smartrecruiters.com/v1/companies/smartrecruiters/postings?limit=1",
}
INDIA = re.compile(
    r"\b(india|bengaluru|bangalore|hyderabad|pune|chennai|mumbai|gurugram|gurgaon|noida|delhi)\b",
    re.I,
)


def location_text(provider, record):
    if provider == "lever":
        return str((record.get("categories") or {}).get("location") or "")
    loc = record.get("location")
    if isinstance(loc, dict):
        return " ".join(str(loc.get(k) or "") for k in ("name", "city", "country"))
    return str(loc or "")


async def verify(args):
    rows = json.loads(Path(args.candidates).read_text())
    verified, report = [], []
    # One request per provider host per second, bounded concurrency across hosts.
    locks = {p: asyncio.Lock() for p in ENDPOINTS}
    cooldowns = {p: 0.0 for p in ENDPOINTS}
    async with httpx.AsyncClient(timeout=20, follow_redirects=False) as client:

        async def probe(row):
            p, b = row["ats_provider"], row["board_token"]
            url, params = board_endpoint(p, b)
            async with locks[p]:
                if time.monotonic() < cooldowns[p]:
                    report.append(
                        {"provider": p, "board": b, "error": "PROVIDER_COOLDOWN"}
                    )
                    return
                try:
                    response = await client.get(url, params=params)
                    result = {"provider": p, "board": b, "status": response.status_code}
                    if response.status_code == 429:
                        cooldowns[p] = time.monotonic() + (
                            retry_seconds(response.headers.get("retry-after")) or 60
                        )
                    if response.status_code == 200:
                        records = board_records(p, response.json())
                        relevant = [
                            r
                            for r in records
                            if INDIA.search(location_text(p, r))
                            or (
                                p == "smartrecruiters"
                                and (r.get("location") or {}).get("country", "").lower()
                                == "in"
                            )
                        ]
                        result.update(records=len(records), india_records=len(relevant))
                        if relevant:
                            evidence = relevant[0]
                            company = (
                                evidence.get("company_name")
                                or (
                                    (evidence.get("company") or {}).get("name")
                                    if isinstance(evidence.get("company"), dict)
                                    else None
                                )
                                or row["company"]
                            )
                            verified.append(
                                {
                                    **row,
                                    "company": company,
                                    "country_focus": ["IN"],
                                    "enabled": True,
                                    "sync_interval_hours": 6,
                                    "verification": {
                                        "verified_at": datetime.now(UTC).isoformat(),
                                        "endpoint": url,
                                        "http_status": 200,
                                        "india_jobs_observed": len(relevant),
                                        "evidence_location": location_text(p, evidence),
                                        "evidence_job_url": evidence.get("absolute_url")
                                        or evidence.get("hostedUrl")
                                        or evidence.get("jobUrl")
                                        or evidence.get("ref"),
                                    },
                                }
                            )
                    report.append(result)
                    print(json.dumps(result), flush=True)
                except Exception as exc:
                    report.append(
                        {"provider": p, "board": b, "error": type(exc).__name__}
                    )
                await asyncio.sleep(1)

        await asyncio.gather(*(probe(row) for row in rows))
    Path(args.output).write_text(
        json.dumps(
            sorted(verified, key=lambda r: (r["ats_provider"], r["board_token"])),
            indent=2,
        )
        + "\n"
    )
    Path(args.output + ".report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(f"Verified India boards: {len(verified)} / {len(rows)}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--feeds", action="store_true")
    parser.add_argument("--candidates")
    parser.add_argument("--output")
    args = parser.parse_args()
    if args.feeds:
        with httpx.Client(timeout=25, follow_redirects=False) as client:
            for url, params in [
                ("https://himalayas.app/jobs/api", {"limit": 1}),
                (
                    "https://himalayas.app/jobs/api/search",
                    {"country": "IN", "page": 1, "limit": 20},
                ),
                ("https://jobicy.com/api/jobs", {"count": 1}),
            ]:
                response = client.get(url, params=params)
                result = {"url": url, "status": response.status_code}
                if response.status_code == 200:
                    data = response.json()
                    result["fields"] = list(data)
                    result["pagination"] = {
                        k: v for k, v in data.items() if k != "jobs"
                    }
                    result["first_record"] = {
                        k: v
                        for k, v in (data.get("jobs") or [{}])[0].items()
                        if k not in {"description", "jobDescription", "excerpt"}
                    }
                print(json.dumps(result))
        return
    if args.candidates:
        if not args.output:
            parser.error("--output is required with --candidates")
        asyncio.run(verify(args))
        return
    with httpx.Client(timeout=20, follow_redirects=False) as client:
        for provider, endpoint in ENDPOINTS.items():
            try:
                response = client.get(endpoint)
                result = {"provider": provider, "status": response.status_code}
                if response.status_code == 200:
                    records = board_records(provider, response.json())
                    result.update(
                        records=len(records),
                        first_record_fields=sorted(records[0]) if records else [],
                    )
                print(json.dumps(result))
            except httpx.HTTPError as error:
                print(json.dumps({"provider": provider, "error": type(error).__name__}))


if __name__ == "__main__":
    main()
