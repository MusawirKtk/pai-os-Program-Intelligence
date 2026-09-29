"""End-to-end standalone research uses only public targets and task context."""

import asyncio
import json
import unittest
from datetime import datetime, timezone
from pathlib import Path

from pai_program_intelligence.standalone import run_standalone
from pai_program_intelligence.sources import FetchedPage, SearchHit
from pai_program_intelligence.schemas import ErrorCode
from pai_program_intelligence.sources import SourceLayerError


FIXTURE = Path(__file__).resolve().parents[1] / "examples" / "standalone_demo.json"


class FakeClient:
    def __init__(self, targets):
        self.pages = {page["url"]: page for target in targets for page in target["pages"]}
        self.queries = []

    async def search(self, query, *, limit=10, domains=()):
        self.queries.append(query)
        return [SearchHit(url) for url in self.pages][:limit]

    async def fetch(self, url):
        page = self.pages[url]
        return FetchedPage(url, page["title"], page["text"], page["fetched_at"])


class StandaloneTests(unittest.TestCase):
    def setUp(self):
        self.payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
        self.now = datetime(2026, 9, 29, 12, tzinfo=timezone.utc)

    def test_full_offline_flow_and_no_context_sent_to_search(self):
        targets = self.payload["programs"]
        targets[0]["query"] = "MSc Artificial Intelligence Demo University"
        self.payload["context"]["private_marker"] = "never-send-to-provider"
        client = FakeClient(targets)
        result = asyncio.run(run_standalone(client, targets, self.payload["context"], now=self.now))
        self.assertEqual(result["errors"], [])
        self.assertEqual(len(result["research"]), 2)
        self.assertEqual(len(result["research"][0]["requirements"]), 2)
        self.assertEqual(len(result["research"][0]["costs"]), 1)
        self.assertEqual(result["eligibility"][0]["status"], "needs_context")
        self.assertEqual(result["eligibility"][0]["missing_student_context"], ("undergraduate_course_history",))
        self.assertEqual(result["eligibility"][1]["overall"], "NOT_MET")
        self.assertEqual(result["comparison"]["programs"][0]["values"]["language"]["value"][0]["match"], "MET")
        self.assertEqual(len(result["comparison"]["programs"][0]["values"]["language"]["source_ids"]), 2)
        self.assertEqual(client.queries, [targets[0]["query"]])
        self.assertNotIn("never-send-to-provider", str(client.queries))

    def test_wrong_program_page_is_rejected_without_breaking_valid_sources(self):
        targets = self.payload["programs"]
        targets[0]["source_urls"].append(targets[1]["official_url"])
        result = asyncio.run(run_standalone(FakeClient(targets), targets, self.payload["context"], now=self.now))
        self.assertEqual(result["errors"], [])
        self.assertEqual(result["search"][0]["rejected_sources"][0]["reason"], "program identity not established")
        self.assertEqual(len(result["research"]), 2)

    def test_stale_evidence_cannot_mark_eligibility_met(self):
        future = datetime(2026, 10, 8, tzinfo=timezone.utc)
        result = asyncio.run(run_standalone(FakeClient(self.payload["programs"]), self.payload["programs"], self.payload["context"], now=future))
        self.assertEqual(result["eligibility"][0]["overall"], "NEEDS_REVIEW")
        self.assertEqual(result["comparison"]["programs"][0]["values"]["language"]["verification_status"], "stale")

    def test_conflicting_official_values_remain_visible(self):
        targets = self.payload["programs"]
        second_page = targets[0]["pages"][1]
        second_page["text"] = second_page["text"].replace("IELTS 6.5", "IELTS 7.5").replace("GBP 10000", "GBP 11000")
        result = asyncio.run(run_standalone(FakeClient(targets), targets, self.payload["context"], now=self.now))
        record = result["research"][0]
        self.assertEqual(len([rule for rule in record["requirements"] if rule["type"] == "language_test"]), 2)
        self.assertEqual(len(record["costs"]), 2)
        self.assertEqual(result["eligibility"][0]["overall"], "NEEDS_REVIEW")
        cells = result["comparison"]["programs"][0]["values"]
        self.assertEqual(cells["language"]["verification_status"], "conflicting")
        self.assertEqual(cells["tuition"]["verification_status"], "conflicting")
        self.assertEqual({row["amount"] for row in cells["tuition"]["value"]}, {10000, 11000})
        self.assertEqual({row["amount"]: len(row["source_ids"]) for row in cells["tuition"]["value"]}, {10000: 1, 11000: 1})

    def test_known_urls_continue_when_optional_search_fails(self):
        targets = self.payload["programs"]
        targets[0]["query"] = "MSc Artificial Intelligence"

        class SearchDown(FakeClient):
            async def search(self, query, *, limit=10, domains=()):
                raise SourceLayerError(ErrorCode.PROVIDER_ERROR, "search unavailable")

        result = asyncio.run(run_standalone(SearchDown(targets), targets, self.payload["context"], now=self.now))
        self.assertEqual(result["errors"], [])
        self.assertEqual(result["search"][0]["search_error"], "provider_error")
        self.assertEqual(len(result["research"]), 2)


if __name__ == "__main__":
    unittest.main()
