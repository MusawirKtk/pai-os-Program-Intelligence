"""Tavily adapter tests with all HTTP calls replaced by local fakes."""

import json
import os
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from pai_program_intelligence.schemas import ErrorCode
from pai_program_intelligence.sources import (
    SourceLayerError,
    discover_official_sources,
    fetch_official_source,
)
from pai_program_intelligence.tavily import TavilyResearchClient


class TavilyAdapterTests(unittest.IsolatedAsyncioTestCase):
    async def test_adapter_plugs_into_official_source_pipeline(self):
        client = TavilyResearchClient(api_key="test-key")

        def fake_post(endpoint, payload):
            if endpoint == "search":
                return {"results": [{"url": "https://example.edu/programs/ai", "title": "AI", "content": "lead"}]}
            return {"results": [{"url": payload["urls"][0], "raw_content": "Official program text"}]}

        with patch.object(client, "_post", side_effect=fake_post):
            candidates = await discover_official_sources(
                client, "MSc AI", official_domains=("example.edu",)
            )
            fetched = await fetch_official_source(
                client, candidates[0], official_domains=("example.edu",), publisher="Example University"
            )
        self.assertEqual(fetched.source.source_type, "official_program_page")
        self.assertEqual(fetched.raw_text, "Official program text")

    async def test_search_restricts_domains_and_returns_leads(self):
        client = TavilyResearchClient(api_key="test-key")
        fake_response = {"results": [{"url": "https://example.edu/programs/ai", "title": "AI", "content": "snippet"}]}
        with patch.object(client, "_post", return_value=fake_response) as post:
            hits = await client.search("MSc AI", limit=5, domains=("example.edu",))
        self.assertEqual(hits[0].url, "https://example.edu/programs/ai")
        self.assertEqual(hits[0].snippet, "snippet")
        self.assertEqual(post.call_args.args[0], "search")
        self.assertEqual(post.call_args.args[1]["include_domains"], ["example.edu"])
        self.assertEqual(post.call_args.args[1]["include_domains_mode"], "restrict")
        self.assertFalse(post.call_args.args[1]["include_answer"])

    async def test_extract_checks_results_even_on_successful_http_response(self):
        client = TavilyResearchClient(api_key="test-key")
        with patch.object(client, "_post", return_value={"results": [], "failed_results": [{"url": "https://example.edu"}]}):
            with self.assertRaises(SourceLayerError) as failure:
                await client.fetch("https://example.edu/programs/ai")
        self.assertEqual(failure.exception.code, ErrorCode.SOURCE_UNAVAILABLE)

    async def test_extract_returns_reported_url_and_raw_content(self):
        client = TavilyResearchClient(api_key="test-key")
        fake_response = {"results": [{"url": "https://example.edu/programs/ai", "raw_content": "# MSc AI"}]}
        with patch.object(client, "_post", return_value=fake_response) as post:
            page = await client.fetch("https://example.edu/programs/ai")
        self.assertEqual(page.reported_url, "https://example.edu/programs/ai")
        self.assertEqual(page.text, "# MSc AI")
        self.assertIn("+00:00", page.fetched_at)
        self.assertEqual(post.call_args.args[0], "extract")
        self.assertEqual(post.call_args.args[1]["urls"], ["https://example.edu/programs/ai"])

    async def test_private_url_does_not_reach_tavily(self):
        client = TavilyResearchClient(api_key="test-key")
        with patch.object(client, "_post") as post:
            with self.assertRaises(SourceLayerError):
                await client.fetch("http://127.0.0.1/admin")
        post.assert_not_called()

    async def test_post_uses_fixed_api_host_and_bearer_header(self):
        client = TavilyResearchClient(api_key="test-key")

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self, size):
                return json.dumps({"results": []}).encode("utf-8")

        with patch("pai_program_intelligence.tavily.urlopen", return_value=FakeResponse()) as urlopen:
            result = client._post("search", {"query": "MSc AI"})
        request = urlopen.call_args.args[0]
        self.assertEqual(request.full_url, "https://api.tavily.com/search")
        self.assertEqual(request.get_header("Authorization"), "Bearer test-key")
        self.assertEqual(result, {"results": []})

    async def test_rate_limit_is_structured_without_provider_body(self):
        client = TavilyResearchClient(api_key="test-key")
        error = HTTPError("https://api.tavily.com/search", 429, "secret body", None, None)
        with patch("pai_program_intelligence.tavily.urlopen", side_effect=error):
            with self.assertRaises(SourceLayerError) as failure:
                client._post("search", {"query": "MSc AI"})
        self.assertEqual(failure.exception.code, ErrorCode.RATE_LIMITED)
        self.assertNotIn("secret", str(failure.exception))

    async def test_key_is_required_from_injection_or_environment(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ValueError):
                TavilyResearchClient()


if __name__ == "__main__":
    unittest.main()
