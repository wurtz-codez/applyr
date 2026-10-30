"""Isolated HTTP form smoke test; never discovers live jobs or submits applications.

Serve fixtures: apps/api/.venv/bin/python scripts/smoke_mvp.py serve
Run frontend separately with API_BASE_URL=http://127.0.0.1:8011 on port 3001.
Check forms: apps/api/.venv/bin/python scripts/smoke_mvp.py check
"""

import hashlib
import os
import sys
import tempfile
import time
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOKEN = "smoke-fixture-token-" + "a" * 48
WEB = "http://127.0.0.1:3001"


class Forms(HTMLParser):
    def __init__(self, markup):
        super().__init__()
        self.forms = []
        self.current = None
        self.textarea = None
        self.select = None
        self.feed(markup)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "form":
            self.current = {"fields": {}, "text": ""}
            self.forms.append(self.current)
        if self.current is None:
            return
        fields = self.current["fields"]
        if tag == "input" and "name" in attrs and attrs.get("type") not in {"file", "checkbox"}:
            fields[attrs["name"]] = attrs.get("value", "")
        if (
            tag == "input"
            and "name" in attrs
            and attrs.get("type") == "checkbox"
            and "checked" in attrs
        ):
            fields[attrs["name"]] = attrs.get("value", "on")
        if tag == "select":
            self.select = attrs.get("name")
        if tag == "option" and self.select:
            if self.select not in fields or "selected" in attrs:
                fields[self.select] = attrs.get("value", "")
        if tag == "textarea":
            self.textarea = attrs.get("name")
            if self.textarea:
                fields[self.textarea] = ""

    def handle_data(self, data):
        if self.current is not None:
            self.current["text"] += data
            if self.textarea:
                self.current["fields"][self.textarea] += data

    def handle_endtag(self, tag):
        if tag == "form":
            self.current = None
        if tag == "textarea":
            self.textarea = None
        if tag == "select":
            self.select = None


def pdf():
    # Minimal one-page PDF. This fixture has no candidate data.
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >>",
    ]
    data, offsets = bytearray(b"%PDF-1.4\n"), [0]
    for index, obj in enumerate(objects, 1):
        offsets.append(len(data))
        data.extend(f"{index} 0 obj\n".encode() + obj + b"\nendobj\n")
    start = len(data)
    data.extend(f"xref\n0 {len(offsets)}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]:
        data.extend(f"{offset:010} 00000 n \n".encode())
    data.extend(
        f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{start}\n%%EOF\n".encode()
    )
    return bytes(data)


def serve():
    with tempfile.TemporaryDirectory(prefix="applyr-mvp-smoke-") as directory:
        os.environ.update(
            {
                "APP_ENV": "test",
                "API_TOKEN": TOKEN,
                "DATABASE_URL": f"sqlite:///{directory}/test.db",
                "STORAGE_DIR": directory,
                "LLM_PROVIDER": "gemini",
                "GEMINI_API_KEY": "fixture-key",
                "LLM_MODEL": "fixture-model",
                "DISCOVERY_SCHEDULE_ENABLED": "false",
            }
        )
        sys.path.insert(0, str(ROOT / "apps/api"))
        os.chdir(ROOT / "apps/api")
        import uvicorn
        from alembic import command
        from alembic.config import Config
        from app.integrations.ats.greenhouse import normalize
        from app.main import app
        from app.schemas.discovery import AIResult
        from app.services import discovery, matching

        command.upgrade(Config("alembic.ini"), "head")
        record = normalize(
            {
                "id": 1,
                "title": "Software Engineer - Fixture",
                "location": {"name": "Bengaluru, India"},
                "content": "0-2 years of experience. Build Python REST APIs.",
                "absolute_url": "https://job-boards.greenhouse.io/fixture/jobs/1",
            },
            "fixture",
        )
        discovery.fetch_jobs = lambda board: ([record], 0)

        def fake_ai(settings, profile, title, description):
            return AIResult(
                required_skills=["Python"],
                missing_skills=[],
                matched_profile_fact_ids=[profile.facts[0].id],
                component_scores={
                    "skills": 100,
                    "role": 50,
                    "experience": 0,
                    "projects": 0,
                },
                confidence="low",
                reason="Fixture response backed by the verified Python fact.",
            )

        matching.analyze = fake_ai
        uvicorn.run(app, host="127.0.0.1", port=8011)


def check():
    import httpx

    def get(client, path):
        response = client.get(WEB + path)
        response.raise_for_status()
        return response

    def submit(client, path, text, values=None, files=None):
        page = get(client, path)
        matches = [form for form in Forms(page.text).forms if text in form["text"]]
        assert len(matches) == 1, f"Expected one form for {text!r}; found {len(matches)}"
        fields = {**matches[0]["fields"], **(values or {})}
        assert any(key.startswith("$ACTION") for key in fields), "Missing Server Action marker"
        parts = {key: (None, str(value)) for key, value in fields.items()}
        parts.update(files or {})
        response = client.post(WEB + path, files=parts, headers={"Origin": WEB})
        response.raise_for_status()
        assert "?error=" not in str(response.url), f"Form failed: {text}"
        return response

    with httpx.Client(timeout=90, follow_redirects=True) as client:
        for attempt in range(60):
            try:
                client.get(WEB + "/login").raise_for_status()
                break
            except httpx.HTTPError:
                if attempt == 59:
                    raise
                time.sleep(1)
        submit(client, "/login", "Sign in", {"token": TOKEN})
        assert client.cookies.get("jobpilot_session") == TOKEN
        print("PASS: sign-in through the real Server Action")
        submit(
            client,
            "/profile",
            "Save verified profile",
            {
                "full_name": "Smoke Candidate",
                "statement_0": "Python",
                "category_0": "skill",
                "evidence_0": "Fixture confirmation",
                "verified": "on",
            },
        )
        assert "Python" in get(client, "/profile").text
        print("PASS: profile form persistence")
        submit(
            client,
            "/settings",
            "Add board",
            {"name": "Fixture Company", "board_token": "fixture"},
        )
        assert "Fixture Company" in get(client, "/settings").text
        print("PASS: source configuration")
        submit(client, "/jobs", "Discover jobs", {"use_ai": "on"})
        auth = {"Authorization": f"Bearer {TOKEN}"}
        with httpx.Client(base_url="http://127.0.0.1:8011", headers=auth, timeout=30) as api:
            jobs = api.get("/api/v1/jobs").json()
            assert jobs["total"] == 1
            job = jobs["items"][0]
            assert job["match"]["provider"] == "gemini"
            job_id = job["id"]
            assert "Fixture" in get(client, f"/jobs/{job_id}").text
            print("PASS: discovery, matching and job details (fixture provider)")
            submit(client, f"/jobs/{job_id}", "Save job")
            assert api.get("/api/v1/jobs?shortlisted=true").json()["total"] == 1
            print("PASS: shortlist action")
            data = pdf()
            submit(
                client,
                "/resumes",
                "Upload resume",
                files={"resume": ("smoke.pdf", data, "application/pdf")},
            )
            resume = api.get("/api/v1/resumes/default").json()
            assert resume["sha256"] == hashlib.sha256(data).hexdigest()
            downloaded = get(client, f"/resumes/{resume['id']}/download")
            assert downloaded.content == data
            print("PASS: resume upload, default and private frontend download")
            submit(
                client,
                f"/jobs/{job_id}",
                "Record manual application",
                {"notes": "Fixture manual record"},
            )
            applications = api.get("/api/v1/applications").json()
            assert (
                applications["total"] == 1 and applications["items"][0]["resume_id"] == resume["id"]
            )
            submit(
                client,
                "/applications",
                "Save update",
                {"status": "INTERVIEW", "notes": "Fixture interview"},
            )
            assert api.get("/api/v1/applications").json()["items"][0]["status"] == "INTERVIEW"
            print("PASS: manual application recording and status update")
            submit(client, "/jobs", "Discover jobs", {"use_ai": "on"})
            assert api.get("/api/v1/jobs").json()["total"] == 1
            print("PASS: repeat scan remains deduplicated")
        submit(client, "/dashboard", "Sign out")
        assert client.cookies.get("jobpilot_session") is None
        print("PASS: sign-out")
    print("All isolated MVP HTTP form checks passed. No live applications were submitted.")


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in {"serve", "check"}:
        raise SystemExit("Usage: smoke_mvp.py serve|check")
    serve() if sys.argv[1] == "serve" else check()
