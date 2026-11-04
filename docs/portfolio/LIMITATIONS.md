# ElyraOps AI — security and production-readiness boundaries

This is an **educational, local portfolio demo**. It is not suitable for public deployment or real customer records.

| Implemented and tested | Not implemented / not claimed |
| --- | --- |
| Guarded local token roles and scoped case operations | OIDC, MFA, corporate SSO, canonical tenant membership registry |
| Non-owner PostgreSQL roles and RLS for case/audit and RAG tables | Protection from compromised DB credentials, privileged SQL injection or hostile local Docker users |
| Constrained LangGraph recommendation + policy citations | Autonomous execution, verified reimbursement or financial disbursement |
| Private Gemini API key supplied on local host | Production secret vault, key rotation and managed egress controls |
| Structured JSON logs, request IDs, protected metrics, timeouts | Full distributed OpenTelemetry collector, operational SLOs and incident on-call |
| Local Docker Compose and CI smoke test | Cloud production hosting, secure public ingress, backup drills, HA or autoscaling |
| Read-only k6 endpoint smoke (when run) | Measured RAG throughput, LLM latency, database concurrency or end-to-end throughput |

**Threat model:** The trusted local host, Docker daemon, runtime configuration and demo-generated tokens are prerequisites. Application-layer authorization and RLS defense-in-depth reduce accidental cross-tenant SQL exposure; they do not cover malicious administrators or stolen connection secrets. RAG content may be sent to Gemini for embedding/reasoning, so use *only synthetic* text.

**Accuracy policy:** Cite actual CI logs, screenshots and measured benchmark artifacts. No synthetic performance numbers should be presented as empirical results. Respect third-party attribution; see [../../ORIGINS.md](../../ORIGINS.md).
