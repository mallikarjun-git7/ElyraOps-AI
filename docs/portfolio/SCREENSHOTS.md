# Recruiter-facing screenshot checklist

Five authentic local-demo screenshots are included in `docs/portfolio/screenshots/`. Never fake activity counts, policy citations, test passes, cloud deployment or benchmark outcomes.

| Suggested filename | Capture | Review before committing |
| --- | --- | --- |
| `01-overview.png` | Overview with synthetic organization and summary counts | No names other than synthetic demo labels |
| `02-billing-investigation.png` | Completed triage and `POL-001` policy citation | Case description contains synthetic details only |
| `03-pending-approval.png` | Analyst sees **Pending approval**, no approver action | No access token or internal request headers |
| `04-approval-audit.png` | Approver sees **Approved · simulated** and event timeline | Explicit simulation label visible |
| `05-github-ci.png` | Real GitHub Actions successful checks | Correct commit/branch, no non-green runs misrepresented |
| `06-local-docker.png` (optional) | Docker Compose container health output | Avoid database URLs, keys, or environment dumps |

Capture at a readable desktop resolution; crop out unrelated tabs and personal information; redact secrets **before** saving. Screen records should skip login-token entry. For any metric charts, use only actual results from [BENCHMARKS.md](BENCHMARKS.md).

GitHub Markdown can embed screenshots once created, e.g. `![Synthetic billing case investigation](docs/portfolio/screenshots/02-billing-investigation.png)` from the repository root. Do not include broken screenshot links in the README before files exist.
