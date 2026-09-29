"""Run the plugin end to end from a local JSON file, without PAI/V3."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from pai_program_intelligence.database import apply_migrations, connect_database  # noqa: E402
from pai_program_intelligence.sources import FetchedPage, SearchHit  # noqa: E402
from pai_program_intelligence.standalone import run_standalone  # noqa: E402
from pai_program_intelligence.tavily import TavilyResearchClient  # noqa: E402


def _setting(name: str) -> str | None:
    import os

    if os.environ.get(name):
        return os.environ[name]
    path = ROOT / ".env"
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith(name + "="):
                return line.split("=", 1)[1].strip().strip('"').strip("'") or None
    return None


class FixtureClient:
    """Local public-page fixtures; no network or database is used."""

    def __init__(self, targets):
        self.pages = {page["url"]: page for target in targets for page in target.get("pages", [])}

    async def search(self, query, *, limit=10, domains=()):
        return [SearchHit(url, page.get("title", "")) for url, page in self.pages.items()][:limit]

    async def fetch(self, url):
        page = self.pages[url]
        return FetchedPage(url, page.get("title", url), page["text"], page["fetched_at"])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path, help="Local task-scoped JSON file")
    parser.add_argument("--live", action="store_true", help="Use Tavily and the plugin-only PostgreSQL database")
    args = parser.parse_args()
    payload = json.loads(args.input.read_text(encoding="utf-8"))
    targets = payload["programs"]
    context = payload.get("context", {})
    if args.live:
        if any("pages" in target for target in targets) or "as_of" in payload:
            parser.error("Live mode cannot use fixture pages or override verification time")
        key = _setting("TAVILY_API_KEY") or _setting("WEB_SEARCH_API_KEY")
        dsn = _setting("PROGRAM_INTELLIGENCE_DATABASE_URL")
        if not key or not dsn:
            parser.error("Live mode needs Tavily key and plugin database URL in this repo's ignored .env")
        client = TavilyResearchClient(api_key=key)
        with connect_database(dsn) as conn:
            apply_migrations(conn)
            result = asyncio.run(run_standalone(client, targets, context, conn=conn))
    else:
        if not all(target.get("pages") for target in targets):
            parser.error("Offline mode needs local pages for every target; add --live for Tavily")
        as_of = datetime.fromisoformat(payload["as_of"].replace("Z", "+00:00")) if "as_of" in payload else None
        result = asyncio.run(run_standalone(FixtureClient(targets), targets, context, now=as_of))
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
