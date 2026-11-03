from collections.abc import Callable

from app.ingestion.connectors.ats import Ashby, Greenhouse, Lever, SmartRecruiters
from app.ingestion.connectors.generic import Browser, Feed, Generic
from app.ingestion.connectors.jobspy_optional import JobSpy
from app.ingestion.http import HTTP
from app.ingestion.schemas import JobConnector

CONNECTORS: dict[str, Callable[[HTTP], JobConnector]] = {}


def register(name: str, factory: Callable[[HTTP], JobConnector]) -> None:
    if name in CONNECTORS:
        raise ValueError(f"Connector already registered: {name}")
    CONNECTORS[name] = factory


for name, factory in [
    ("greenhouse", Greenhouse),
    ("lever", Lever),
    ("ashby", Ashby),
    ("smartrecruiters", SmartRecruiters),
]:
    register(name, factory)

for name, factory in [
    ("career_page", Generic),
    ("feed", Feed),
    ("browser", Browser),
    ("jobspy", JobSpy),
]:
    register(name, factory)

from app.ingestion.connectors.public_feeds import PUBLIC_FEEDS, PublicFeed  # noqa: E402

for name in sorted(PUBLIC_FEEDS):
    register(name, PublicFeed)
