"""Explicit, optional Tavily company discovery; never creates jobs or enables sources."""

from app.config import get_settings
from app.ingestion.discovery.ats_detector import detect
from app.ingestion.http import FetchFailure


async def discover(query: str, client) -> list[dict]:
    key = get_settings().tavily_api_key
    if not key:
        raise FetchFailure("TAVILY_NOT_CONFIGURED", False)
    response = await client.post(
        "https://api.tavily.com/search",
        timeout=20,
        headers={"Authorization": f"Bearer {key.get_secret_value()}"},
        json={
            "query": query,
            "max_results": 10,
            "include_answer": False,
            "search_depth": "basic",
            "auto_parameters": False,
        },
    )
    if response.status_code != 200:
        raise FetchFailure(f"DISCOVERY_HTTP_{response.status_code}")
    suggestions = []
    for item in response.json().get("results", []):
        try:
            if detected := detect(item.get("url", "")):
                suggestions.append(
                    {
                        "provider": detected[0],
                        "board_id": detected[1],
                        "career_url": item["url"],
                        "verified": False,
                    }
                )
        except ValueError:
            continue
    return suggestions
