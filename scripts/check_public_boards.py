"""Optional live smoke probe; prints shapes and counts, never archives job descriptions."""

import json

import httpx

ENDPOINTS = {
    "greenhouse": "https://boards-api.greenhouse.io/v1/boards/greenhouse/jobs",
    "lever": "https://api.lever.co/v0/postings/leverdemo?mode=json&limit=1",
    "ashby": "https://api.ashbyhq.com/posting-api/job-board/Ashby",
    "smartrecruiters": "https://api.smartrecruiters.com/v1/companies/smartrecruiters/postings?limit=1",
}


def main():
    with httpx.Client(
        timeout=20,
        follow_redirects=False,
        headers={"User-Agent": "ApplyrJobCollector/0.2"},
    ) as client:
        for provider, endpoint in ENDPOINTS.items():
            try:
                response = client.get(endpoint)
                result = {"provider": provider, "status": response.status_code}
                if response.status_code == 200:
                    data = response.json()
                    records = (
                        data
                        if isinstance(data, list)
                        else data.get("jobs", data.get("content", []))
                    )
                    result.update(
                        records=len(records),
                        first_record_fields=sorted(records[0]) if records else [],
                    )
                print(json.dumps(result))
            except httpx.HTTPError as error:
                print(json.dumps({"provider": provider, "error": type(error).__name__}))


if __name__ == "__main__":
    main()
