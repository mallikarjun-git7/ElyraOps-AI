"""Optional local FastAPI agent-service client. Standard library only."""
import json
import os
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from . import security
from . import observability as obs


class AgentUnavailable(RuntimeError):
    pass


def investigate(case_id:str, organization:str | None = None) -> dict:
    base=os.environ.get("ELYRA_AGENT_URL", "").strip().rstrip("/")
    parsed=urlparse(base)
    if parsed.scheme!="http" or parsed.hostname not in {"127.0.0.1","localhost"} or parsed.username or parsed.password or parsed.path not in {"","/"}:
        raise AgentUnavailable("Agent URL must be a trusted local http://127.0.0.1:<port> endpoint")
    headers={"Content-Type":"application/json"}
    rid = obs.current_request_id()
    if rid:
        headers["X-Request-ID"] = rid
    try:
        timeout = int(os.environ.get("ELYRA_AGENT_TIMEOUT_SECONDS", "60"))
    except ValueError as exc:
        raise AgentUnavailable("Agent timeout must be an integer between 5 and 120") from exc
    if not 5 <= timeout <= 120:
        raise AgentUnavailable("Agent timeout must be between 5 and 120 seconds")
    internal=os.environ.get("ELYRA_AGENT_TOKEN", "")
    if security.enabled() and len(internal) < 32:
        raise AgentUnavailable("An internal agent token of at least 32 characters is required")
    if internal:
        headers["X-Agent-Token"]=internal
    if security.enabled() and not organization:
        raise AgentUnavailable("Scoped organization required for guarded agent request")
    body={"case_id":case_id}
    if organization is not None:
        body["organization"]=organization
    request=Request(base+"/v1/investigate",json.dumps(body).encode(),headers,method="POST")
    try:
        with urlopen(request,timeout=timeout) as response:
            result=json.load(response)
        if not isinstance(result,dict) or result.get("case_id")!=case_id or "status" not in result:
            raise AgentUnavailable("Agent service returned an invalid response")
        return result
    except (HTTPError, URLError, TimeoutError, ValueError) as exc:
        raise AgentUnavailable("Agent service unavailable; verify it is running on port 8091") from exc
