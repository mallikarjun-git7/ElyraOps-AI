"""Phase 7 offline guards: scoped evidence, safe benchmark parsing, no fictitious numbers."""
from __future__ import annotations

import math
from pathlib import Path
import unittest

from scripts.phase7_benchmark_report import InvalidSummary, parse_summary, render_markdown

ROOT = Path(__file__).resolve().parents[1]


def example_summary():
    """Synthetic unit-test fixture only, NOT an empirical ElyraOps benchmark."""
    return {'metrics': {
        'http_reqs': {'values': {'count': 100}},
        'http_req_duration': {'values': {'med': 10.0, 'p(90)': 20.0, 'p(95)': 25.0, 'max': 40.0},
                              'thresholds': {'p(95)<1000': {'ok': True}}},
        'http_req_failed': {'values': {'rate': 0.01},
                            'thresholds': {'rate<0.01': {'ok': False}}},
        'checks': {'values': {'rate': 0.99}},
    }}


class Phase7BenchmarkTests(unittest.TestCase):
    def test_parses_real_k6_fields_and_keeps_report_scoped(self):
        data = parse_summary(example_summary())
        self.assertEqual(data['requests'], 100)
        self.assertEqual(data['latencies']['p95'], 25.0)
        self.assertEqual(data['thresholds']['http_req_failed: rate<0.01'], False)
        report = render_markdown(data, 'Local test machine', 'abc123', 'Synthetic fixture (test only)')
        self.assertIn('100', report)
        self.assertIn('25.00 ms', report)
        self.assertIn('**FAIL**', report)
        self.assertIn('Does NOT benchmark SQL', report)
        self.assertNotIn('production SLA achieved', report)

    def test_refuses_missing_summary_instead_of_inventing_numbers(self):
        for value in ({}, {'metrics': {}}, {'metrics': {'http_reqs': {'values': {'count': 2}}}}):
            with self.subTest(value=value), self.assertRaises(InvalidSummary):
                parse_summary(value)

    def test_refuses_nan_bad_rates_and_empty_run(self):
        for metric, key, invalid in [
            ('http_reqs', 'count', 0), ('http_reqs', 'count', 1.5),
            ('http_req_failed', 'rate', 1.5), ('checks', 'rate', -0.1),
            ('http_req_duration', 'p(95)', math.nan),
        ]:
            data = example_summary()
            data['metrics'][metric]['values'][key] = invalid
            with self.subTest(metric=metric, key=key), self.assertRaises(InvalidSummary):
                parse_summary(data)

    def test_report_metadata_rejects_urls_and_newlines(self):
        data = parse_summary(example_summary())
        for value in ('postgresql://user:pass@server/database', 'Line\nSecret', '`bad`'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                render_markdown(data, value)

    def test_k6_script_only_reads_local_health_and_auth(self):
        script = (ROOT / 'load' / 'k6_portfolio.js').read_text()
        self.assertIn('127\\.0\\.0\\.1', script)
        self.assertIn('localhost', script)
        self.assertIn('http.get', script)
        self.assertIn('/health', script)
        self.assertIn('/api/auth/config', script)
        self.assertNotIn('http.post', script)
        self.assertNotIn('/v1/investigate', script)
        self.assertNotIn('Bearer ', script)

    def test_docs_define_real_workflow_without_deployment_overclaim(self):
        readme = (ROOT / 'README.md').read_text()
        demo = (ROOT / 'docs' / 'portfolio' / 'DEMO.md').read_text()
        benchmarks = (ROOT / 'docs' / 'portfolio' / 'BENCHMARKS.md').read_text()
        self.assertIn('PostgreSQL', readme)
        self.assertIn('RLS', readme)
        self.assertIn('simulated', readme.lower())
        self.assertIn('Approve simulation', demo)
        self.assertIn('read-only', benchmarks)
        self.assertIn('not measure', benchmarks)


if __name__ == '__main__':
    unittest.main()
