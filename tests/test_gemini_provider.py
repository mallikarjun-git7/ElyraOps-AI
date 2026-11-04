"""Tests Gemini routing using mocked HTTP; never sends real API requests."""
import io
import json
import os
import unittest
from unittest.mock import patch

from agent_service import provider


class GeminiProviderTests(unittest.TestCase):
    CASE = {"title":"Duplicate charge", "description":"Two charges for one subscription", "domain":"Billing"}
    EVIDENCE = [{"id":"POL-001", "excerpt":"Finance approval is required before issuing any refund."}]
    ACTION = "Flag duplicate payment for finance review"

    def fake_http(self, req, timeout):
        self.seen_url = req.full_url
        self.seen_header = req.get_header("Authorization")
        body = json.loads(req.data)
        self.seen_model = body["model"]
        content = json.dumps({"reason":"POL-001 requires finance review before a duplicate-payment refund."})
        return io.BytesIO(json.dumps({"choices":[{"message":{"content":content}}]}).encode())

    def test_gemini_endpoint_and_precedence(self):
        with patch.dict(os.environ, {"GEMINI_API_KEY":"dummy-gemini", "OPENAI_API_KEY":"dummy-openai", "GEMINI_MODEL":"gemini-3.5-flash-lite"}):
            with patch.object(provider, "urlopen", self.fake_http):
                result = provider.draft_rationale(self.CASE, self.EVIDENCE, self.ACTION)
        self.assertIn("POL-001", result)
        self.assertIn("generativelanguage.googleapis.com/v1beta/openai/chat/completions", self.seen_url)
        self.assertEqual(self.seen_header, "Bearer dummy-gemini")
        self.assertEqual(self.seen_model, "gemini-3.5-flash-lite")

    def test_openai_still_supported(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY":"dummy-openai", "GEMINI_API_KEY":""}):
            with patch.object(provider, "urlopen", self.fake_http):
                provider.draft_rationale(self.CASE, self.EVIDENCE, self.ACTION)
        self.assertEqual(self.seen_url, "https://api.openai.com/v1/chat/completions")
        self.assertEqual(self.seen_header, "Bearer dummy-openai")

    def test_no_key_rejected(self):
        with patch.dict(os.environ, {"GEMINI_API_KEY":"", "OPENAI_API_KEY":""}):
            with self.assertRaises(provider.ModelUnavailable):
                provider.draft_rationale(self.CASE, self.EVIDENCE, self.ACTION)


if __name__ == "__main__":
    unittest.main()
