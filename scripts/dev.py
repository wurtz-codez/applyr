#!/usr/bin/env python3
"""Install everything and run the Applyr API + web dashboard together."""

from __future__ import annotations

import json
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API_PROJECT = ROOT / "apps" / "api"
WEB_PROJECT = ROOT / "apps" / "web"
API_PORT = os.environ.get("API_PORT", "8000")
WEB_PORT = os.environ.get("WEB_PORT", os.environ.get("PORT", "3000"))
API_HOST = "127.0.0.1"


def say(message: str) -> None:
    print(f"\n▶ {message}", flush=True)


def fail(message: str) -> None:
    print(f"\n✖ {message}", file=sys.stderr, flush=True)
    raise SystemExit(1)


def find_uv() -> str:
    local = ROOT / ".tools" / "python" / "bin" / "uv"
    if local.is_file():
        return str(local)
    found = shutil.which("uv")
    if found:
        return found
    fail(
        "uv is required but was not found. Install it from "
        "https://docs.astral.sh/uv/getting-started/installation/ and run this command again."
    )
    raise AssertionError


def find_pnpm() -> list[str]:
    found = shutil.which("pnpm")
    if found:
        return [found]
    npx = shutil.which("npx")
    if npx and shutil.which("node"):
        print("pnpm was not found; using npx pnpm@10.24.0 instead.", flush=True)
        return [npx, "--yes", "pnpm@10.24.0"]
    fail(
        "pnpm is required but was not found. Install Node.js 24 and pnpm 10 "
        "(npm install --global pnpm@10.24.0) and run this command again."
    )
    raise AssertionError


def port_busy(port: str) -> bool:
    try:
        with socket.create_connection((API_HOST, int(port)), timeout=0.3):
            return True
    except (OSError, ValueError):
        return False


def running_next_dev() -> dict | None:
    """Next dev is single-instance per directory, even on another port."""
    try:
        lock = json.loads((WEB_PROJECT / ".next" / "dev" / "lock").read_text())
        pid = int(lock.get("pid", 0))
        if pid > 0:
            os.kill(pid, 0)
            return lock
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return None
    return None


def run_install(command: list[str], label: str, env: dict[str, str]) -> None:
    say(f"Installing {label} dependencies")
    print("  " + " ".join(command), flush=True)
    try:
        subprocess.run(command, cwd=ROOT, env=env, check=True)
    except FileNotFoundError:
        fail(f"Could not run {command[0]}. Check your local installation.")
    except subprocess.CalledProcessError as error:
        fail(f"{label} dependency installation failed (exit {error.returncode}).")


def env_value(key: str) -> str:
    value = os.environ.get(key, "").strip()
    if value:
        return value
    path = ROOT / ".env"
    try:
        contents = path.read_text()
    except OSError:
        return ""
    match = re.search(
        rf"^(?:export\s+)?{re.escape(key)}\s*=\s*(.*)$", contents, re.MULTILINE
    )
    return match.group(1).strip().strip("'\"") if match else ""


def env_has_token() -> bool:
    value = env_value("API_TOKEN")
    return bool(value) and not value.startswith("replace_")


def wait_for(url: str, timeout: float, process: subprocess.Popen) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            return False
        try:
            with urllib.request.urlopen(url, timeout=1.0) as response:
                if response.status < 500:
                    return True
        except (urllib.error.URLError, OSError, ValueError):
            pass
        time.sleep(0.4)
    return False


def popen_kwargs() -> dict:
    if os.name == "nt":
        return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    return {"start_new_session": True}


def stop(process: subprocess.Popen | None, label: str) -> None:
    if process is None or process.poll() is not None:
        return
    print(f"Stopping {label}…", flush=True)
    try:
        if os.name == "nt":
            process.terminate()
        else:
            os.killpg(os.getpgid(process.pid), signal.SIGTERM)
        process.wait(timeout=8)
    except (ProcessLookupError, subprocess.TimeoutExpired):
        try:
            if os.name == "nt":
                process.kill()
            else:
                os.killpg(os.getpgid(process.pid), signal.SIGKILL)
        except ProcessLookupError:
            pass


def main() -> None:
    if not API_PROJECT.is_dir() or not WEB_PROJECT.is_dir():
        fail("Run this command from a complete Applyr checkout (apps/api and apps/web).")

    if not API_PORT.isdigit() or not WEB_PORT.isdigit():
        fail("API_PORT and WEB_PORT must be numeric.")
    if not (1 <= int(API_PORT) <= 65535 and 1 <= int(WEB_PORT) <= 65535):
        fail("API_PORT and WEB_PORT must be between 1 and 65535.")
    if API_PORT == WEB_PORT:
        fail("API_PORT and WEB_PORT must be different.")

    if port_busy(API_PORT):
        fail(f"Port {API_PORT} is already in use. Stop the existing API or set API_PORT.")
    if port_busy(WEB_PORT):
        fail(f"Port {WEB_PORT} is already in use. Stop the existing web app or set WEB_PORT.")

    existing_next = running_next_dev()
    if existing_next:
        fail(
            "A Next.js dashboard is already running for this checkout at "
            f"{existing_next.get('appUrl', 'http://' + API_HOST + ':3000')} "
            f"(PID {existing_next.get('pid')}). Stop it, then run this command again."
        )

    uv = find_uv()
    pnpm = find_pnpm()

    env = os.environ.copy()
    env.setdefault("UV_CACHE_DIR", str(ROOT / ".cache" / "uv"))
    env["PYTHONUNBUFFERED"] = "1"

    if not (ROOT / ".env").exists():
        say("Creating local configuration")
        subprocess.run([sys.executable, str(ROOT / "scripts" / "bootstrap.py")], cwd=ROOT, env=env, check=True)
    if not env_has_token():
        fail(
            "The root .env has no usable API_TOKEN. Run `python3 scripts/bootstrap.py`, "
            "or add API_TOKEN to the root .env."
        )

    database_url = env_value("JOBS_DATABASE_URL")
    if not database_url:
        fail(
            "Set JOBS_DATABASE_URL to a PostgreSQL database before starting. "
            "See .env.example and the README quick start."
        )
    if not database_url.startswith(
        ("postgres://", "postgresql://", "postgresql+psycopg://")
    ):
        fail("JOBS_DATABASE_URL must be a PostgreSQL URL.")

    run_install([uv, "sync", "--project", "apps/api", "--frozen"], "backend", env)
    run_install(pnpm + ["--dir", "apps/web", "install", "--frozen-lockfile"], "frontend", env)

    say("Checking PostgreSQL connection")
    probe = subprocess.run(
        [
            uv,
            "run",
            "--project",
            "apps/api",
            "--frozen",
            "python",
            "-c",
            "from app.database import get_engine; get_engine().connect().close()",
        ],
        cwd=ROOT,
        env=env,
    )
    if probe.returncode:
        fail(
            "Could not connect to PostgreSQL. Start the database, create the target database, "
            "and check JOBS_DATABASE_URL."
        )

    api: subprocess.Popen | None = None
    web: subprocess.Popen | None = None

    def interrupt(_signum, _frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, interrupt)

    try:
        say(f"Starting API on http://{API_HOST}:{API_PORT}")
        api = subprocess.Popen(
            [
                uv,
                "run",
                "--project",
                "apps/api",
                "--frozen",
                "uvicorn",
                "app.main:app",
                "--host",
                API_HOST,
                "--port",
                API_PORT,
                "--reload",
                "--reload-dir",
                "apps/api/app",
            ],
            cwd=ROOT,
            env=env,
            **popen_kwargs(),
        )

        if not wait_for(f"http://{API_HOST}:{API_PORT}/healthz", 60, api):
            fail("The API did not become healthy. Check the API output above.")

        web_env = env.copy()
        web_env.setdefault("API_BASE_URL", f"http://{API_HOST}:{API_PORT}")
        web_env.setdefault("PORT", WEB_PORT)

        say(f"Starting dashboard on http://{API_HOST}:{WEB_PORT}")
        web = subprocess.Popen(
            pnpm + ["--dir", "apps/web", "dev"],
            cwd=ROOT,
            env=web_env,
            **popen_kwargs(),
        )

        if web.poll() is not None:
            fail(f"The dashboard failed to start (exit {web.returncode}).")
        if not wait_for(f"http://{API_HOST}:{WEB_PORT}", 45, web):
            if web.poll() is not None:
                fail(f"The dashboard failed to start (exit {web.returncode}).")
            print(
                "The dashboard is still compiling; check the output above if it does not appear.",
                flush=True,
            )

        print(
            "\n"
            "  Applyr is running\n"
            f"  Feed       http://{API_HOST}:{WEB_PORT}/jobs\n"
            f"  Landing    http://{API_HOST}:{WEB_PORT}/\n"
            f"  API docs   http://{API_HOST}:{API_PORT}/docs\n"
            "\n"
            "  Press Ctrl-C to stop both servers.\n",
            flush=True,
        )

        while True:
            if api.poll() is not None:
                fail(f"The API stopped unexpectedly (exit {api.returncode}).")
            if web.poll() is not None:
                fail(f"The dashboard stopped unexpectedly (exit {web.returncode}).")
            time.sleep(0.5)

    except KeyboardInterrupt:
        print()
    finally:
        stop(web, "dashboard")
        stop(api, "API")


if __name__ == "__main__":
    main()
