"""Local maintenance commands. Keys are read from .env and never printed."""

import argparse
import json

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.database import get_engine, migrate
from app.discovery import create_run, execute_run, run_response
from app.models import DiscoveryRun
from app.queries import Filters, list_jobs
from app.schemas import DiscoveryInput
from app.sources import PROVIDERS


def main():
    parser = argparse.ArgumentParser(description="Applyr job collection backend")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("init-db")
    refresh = commands.add_parser("refresh")
    refresh.add_argument("--query", default="")
    refresh.add_argument("--provider", choices=list(PROVIDERS), action="append")
    listing = commands.add_parser("jobs")
    listing.add_argument("--q", default="")
    listing.add_argument("--limit", default=10, type=int)
    args = parser.parse_args()
    migrate()
    if args.command == "refresh":
        with Session(get_engine()) as session:
            try:
                run = create_run(session, DiscoveryInput(query=args.query, providers=args.provider))
            except HTTPException as error:
                parser.exit(2, f"Refresh not started: {error.detail}\n")
            run_id = run.id
        execute_run(run_id)
        with Session(get_engine()) as session:
            result = run_response(session.get(DiscoveryRun, run_id))
            print(result.model_dump_json(indent=2))
            if result.status == "FAILED":
                raise SystemExit(1)
    elif args.command == "jobs":
        with Session(get_engine()) as session:
            page = list_jobs(session, Filters(q=args.q, page_size=min(100, max(1, args.limit))))
            print(
                json.dumps(
                    {
                        "total": page.total,
                        "items": [
                            {
                                "id": str(item.id),
                                "title": item.title,
                                "company": item.company,
                                "location": item.location,
                                "type": item.listing_type,
                                "url": item.canonical_url,
                            }
                            for item in page.items
                        ],
                    },
                    indent=2,
                )
            )
    else:
        print("Job database initialized.")


if __name__ == "__main__":
    main()
