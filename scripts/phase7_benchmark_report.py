"""Turn a real k6 JSON summary into a scoped, evidence-backed Markdown report.

Does not run any network request, collect secrets, or invent missing metrics.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path


class InvalidSummary(ValueError):
    """A k6 summary is missing values needed for a truthful report."""


def _num(values: dict, key: str, label: str) -> float:
    value = values.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise InvalidSummary(f"Missing or nonfinite {label}.{key} metric")
    return float(value)


def parse_summary(data: dict) -> dict:
    # Normalize flattened k6 v2 summary-export metrics.
    if isinstance(data, dict) and isinstance(data.get("metrics"), dict):
        raw = data["metrics"]
        http = raw.get("http_reqs")

        if isinstance(http, dict) and "values" not in http:
            normalized = {}

            for name in (
                "http_reqs",
                "http_req_duration",
                "http_req_failed",
            ):
                metric = raw.get(name)
                if isinstance(metric, dict):
                    normalized[name] = {"values": metric}

            check = raw.get(
                "checks",
                raw.get("checks_succeeded"),
            )
            if isinstance(check, dict):
                normalized["checks"] = {"values": check}

            data = {"metrics": normalized}

    # k6 v2 machine-readable summary: version + results.metrics array.
    if isinstance(data, dict) and isinstance(data.get("results"), dict):
        results = data["results"]
        entries = results.get("metrics")
        if not isinstance(entries, list):
            raise InvalidSummary("Expected k6 v2 results.metrics array")
        metrics = {}
        for item in entries:
            if isinstance(item, dict) and isinstance(item.get("name"), str):
                name = item["name"]
                if name in metrics:
                    raise InvalidSummary(f"Duplicate metric: {name}")
                metrics[name] = item
        checks = results.get("checks")
        if not isinstance(checks, dict) or not isinstance(checks.get("metrics"), list):
            raise InvalidSummary("Missing k6 v2 checks.metrics array")
        for item in checks["metrics"]:
            if isinstance(item, dict) and item.get("name") == "checks_succeeded":
                metrics["checks"] = {"values": item.get("values")}
                break
        data = {"metrics": metrics}

    # Legacy k6 summary; retains all original validation safeguards.
    if not isinstance(data, dict) or not isinstance(data.get('metrics'), dict):
        raise InvalidSummary('Expected legacy metrics or k6 v2 results.metrics')
    metrics = data['metrics']
    required = ('http_reqs', 'http_req_duration', 'http_req_failed', 'checks')
    for metric in required:
        if not isinstance(metrics.get(metric), dict) or not isinstance(metrics[metric].get('values'), dict):
            raise InvalidSummary(f'Missing metric: {metric}')
    reqs = _num(metrics['http_reqs']['values'], 'count', 'http_reqs')
    if reqs < 1 or not reqs.is_integer():
        raise InvalidSummary('At least one whole HTTP request must be measured')
    dur = metrics['http_req_duration']['values']
    percentiles = {
        'p50': _num(dur, 'med', 'http_req_duration'),
        'p90': _num(dur, 'p(90)', 'http_req_duration'),
        'p95': _num(dur, 'p(95)', 'http_req_duration'),
        'max': _num(dur, 'max', 'http_req_duration'),
    }
    if not all(value >= 0 for value in percentiles.values()):
        raise InvalidSummary('Latency cannot be negative')
    # Normalize k6 flattened rate metrics.
    for name in ('http_req_failed', 'checks'):
        fields = metrics[name]['values']
        if 'rate' not in fields and 'value' in fields:
            fields['rate'] = fields['value']

    error_rate = _num(metrics['http_req_failed']['values'], 'rate', 'http_req_failed')
    checks_rate = _num(metrics['checks']['values'], 'rate', 'checks')
    if not 0 <= error_rate <= 1 or not 0 <= checks_rate <= 1:
        raise InvalidSummary('A rate must be in the interval [0,1]')
    thresholds = {}
    for key in ('http_req_failed', 'http_req_duration'):
        reported = metrics[key].get('thresholds', {})
        if isinstance(reported, dict):
            for threshold, state in reported.items():
                if isinstance(state, dict) and isinstance(state.get('ok'), bool):
                    thresholds[f'{key}: {threshold}'] = state['ok']
    return {'requests': int(reqs), 'latencies': percentiles,
            'error_rate': error_rate, 'checks_rate': checks_rate,
            'thresholds': thresholds}


def render_markdown(summary: dict, environment: str, commit: str = 'Not recorded',
                    collected: str | None = None) -> str:
    if '\n' in environment or '\r' in environment or '\n' in commit or '\r' in commit:
        raise ValueError('Metadata must use a single line')
    if len(environment) > 160 or len(commit) > 100:
        raise ValueError('Metadata is too long')
    if '://' in environment or '://' in commit or '`' in environment or '`' in commit:
        raise ValueError('Metadata must not contain URLs, connection strings or Markdown syntax')
    timestamp = collected or datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
    result = [
        '# ElyraOps AI — measured local HTTP smoke benchmark', '',
        '> **Workload limitation:** Only dashboard `GET /health` and `GET /api/auth/config` '
        'on localhost:18082. Does NOT benchmark SQL, pgvector, LangGraph, Gemini, case '
        'writes, approvals or end-to-end latency.', '',
        f'- Report generated: {timestamp}',
        f'- Environment (operator supplied): {environment or "Not recorded"}',
        f'- Source commit (operator supplied): {commit}',
        '- Workload: bounded read-only k6 script `load/k6_portfolio.js`',
        '', '| Metric | Actual k6 value |', '| --- | ---: |',
        f'| HTTP requests | {summary["requests"]:,} |',
        f'| HTTP error rate | {summary["error_rate"] * 100:.2f}% |',
        f'| Successful checks (ratio) | {summary["checks_rate"] * 100:.2f}% |',
    ]
    for metric, label in [('p50', 'Request latency p50'), ('p90', 'Request latency p90'),
                          ('p95', 'Request latency p95'), ('max', 'Request latency max')]:
        result.append(f'| {label} | {summary["latencies"][metric]:.2f} ms |')
    result.extend(['', '## Configured threshold checks', '',
                   'Passing the thresholds is not evidence of a production SLA.', ''])
    if summary['thresholds']:
        for label, ok in sorted(summary['thresholds'].items()):
            result.append(f'- `{label}`: **{"PASS" if ok else "FAIL"}**')
    else:
        result.append('- The k6 summary did not report threshold results; no pass/fail claim made.')
    result.extend(['', '## Before publishing', '',
                   'Record k6 version, Mac hardware, Docker Desktop resources, repetition count, '
                   'warmup policy and background load. Preserve the bounded endpoint scope. '
                   'Do not claim a speedup without comparable baseline measurements.', ''])
    return '\n'.join(result)


def main() -> None:
    parser = argparse.ArgumentParser(description='Report actual read-only k6 results; no networking')
    parser.add_argument('--summary', type=Path, required=True, help='JSON exported by k6 --summary-export')
    parser.add_argument('--output', type=Path, required=True, help='Markdown report output')
    parser.add_argument('--environment', default='Local Docker Desktop; hardware not recorded')
    parser.add_argument('--commit', default='Not recorded')
    args = parser.parse_args()
    if args.summary.resolve() == args.output.resolve():
        parser.error('Do not overwrite the input summary')
    try:
        parsed = parse_summary(json.loads(args.summary.read_text(encoding='utf-8')))
        result = render_markdown(parsed, args.environment, args.commit)
    except (InvalidSummary, ValueError, OSError, json.JSONDecodeError) as exc:
        parser.error(f'Invalid benchmark input: {exc}')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(result, encoding='utf-8')
    print(f'Measured read-only HTTP report written: {args.output}')


if __name__ == '__main__':
    main()
