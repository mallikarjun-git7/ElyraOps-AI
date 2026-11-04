# ElyraOps AI — reproducible 2–3 minute demo

**Audience:** SDE / backend / AI engineering reviewers. **Data:** synthetic only. **Environment:** trusted local Mac + Docker Desktop, with the previous PostgreSQL/RLS setup already completed.

## Preflight

```bash
cd ~/Downloads/ElyraOps-AI
bash scripts/phase6_local.sh up
bash scripts/phase6_local.sh check
```

The helper reuses existing PostgreSQL tables and the local ignored config files. It may ask for a private Gemini key. **Do not show or record the key, `.env.*` files, token list or Docker environment variables.** The browser is `http://127.0.0.1:18082`.

## Demonstration script

| Approximate segment | Action | What to point out |
| --- | --- | --- |
| 0:00–0:25 | Open Overview as Analyst | Organization scope; cases are synthetic |
| 0:25–0:55 | Create high-priority Billing case about double charge | Validation + persisted case in PostgreSQL |
| 0:55–1:30 | Run investigation once | Agent activity: triage → retrieval → recommendation |
| 1:30–1:55 | Open evidence | `POL-001` and finance-review recommendation; no automated refund |
| 1:55–2:20 | Show Pending approval and Analyst restriction | Separate human authorization gate |
| 2:20–2:50 | Sign out / sign in as Approver, select **Approve simulation** | Append-only-style audit timeline within demo; **no external action** |

Use your real local test result rather than narrating an unverified execution. Network/provider latency may vary. Don't publish your login-token file or screen-record the token entry step.

## Optional developer-terminal evidence

```bash
# No tokens or keys printed
bash scripts/phase6_local.sh check
# CI status is public on the repository Actions page
```

The resulting dashboard and agent logs can be correlated using request IDs. Do not show raw headers or environment dumps.

## Screenshots to capture from actual application

Follow [SCREENSHOTS.md](SCREENSHOTS.md). At minimum: dashboard, policy-grounded investigation, pending approval, Approver resolution/audit timeline, and green GitHub Actions run. Store images under `docs/portfolio/screenshots/` **only after** personally checking them for secrets and sensitive details. No screenshot image is supplied by this Phase 7 upgrade.

## Failure handling

- `000` on dashboard health: check Docker Desktop and `bash scripts/phase6_local.sh ps`.
- `503` readiness: check PostgreSQL/RLS prerequisites without dumping connection URLs.
- `401` on protected API: use the correct **Analyst** or **Approver** token locally. Never use the internal agent token for browser login.
- Gemini/API error: check the agent's sanitized logs, provider quota and local environment. Do not repeatedly retry mutations blindly.

Stop Phase 6 services using `bash scripts/phase6_local.sh down`. Do **not** remove the PostgreSQL data volume.
