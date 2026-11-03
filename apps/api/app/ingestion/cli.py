"""Registry seeding and offline-friendly worker-equivalent maintenance."""

import argparse
import asyncio
import json
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_engine, migrate
from app.ingestion.discovery.company_finder import discover
from app.ingestion.engine import execute, publish, queue_run
from app.ingestion.schemas import SourceCreate
from app.ingestion.service import register_source, run_response, source_response
from app.models import IngestionRun, IngestionSource


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    seed = commands.add_parser("seed")
    seed.add_argument("path")
    commands.add_parser("sources")
    sync = commands.add_parser("sync")
    sync.add_argument("source_id", type=UUID)
    sync.add_argument("--inline", action="store_true", help="Run in this maintenance process")
    finding = commands.add_parser("discover")
    finding.add_argument("query")
    args = parser.parse_args()
    if args.command == "discover":

        async def finding():
            async with httpx.AsyncClient(follow_redirects=False) as client:
                return await discover(args.query, client)

        print(json.dumps(asyncio.run(finding()), indent=2))
        return
    migrate()
    with Session(get_engine()) as session:
        if args.command == "seed":
            with open(args.path) as file:
                records = json.load(file)
            for record in records:
                try:
                    row = register_source(session, SourceCreate.model_validate(record))
                    print(f"Registered {row.provider} {row.board_id}: {row.id}")
                except ValueError as exc:
                    session.rollback()
                    if str(exc) != "SOURCE_ALREADY_REGISTERED":
                        raise
                    print("Already registered; skipped")
        elif args.command == "sources":
            rows = session.scalars(select(IngestionSource).order_by(IngestionSource.created_at))
            print(
                json.dumps([source_response(session, row) for row in rows], default=str, indent=2)
            )
        else:
            run = queue_run(session, args.source_id)
            run_id = run.id
            if args.inline:
                execute(str(run_id))
                session.expire_all()
                print(
                    json.dumps(
                        run_response(session.get(IngestionRun, run_id)), default=str, indent=2
                    )
                )
            else:
                print(json.dumps({"run_id": str(run_id), "dispatched": publish(run_id)}))


if __name__ == "__main__":
    main()
