"""Optional local FastAPI agent-service client. Standard library only."""
import json
import os
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


class AgentUnavailable(RuntimeError):
    pass


def investigate(case_id:str) -> dict:
    base=os.environ.get("ELYRA_AGENT_URL", "").strip().rstrip("/")
    parsed=urlparse(base)
    if parsed.scheme!="http" or parsed.hostname not in {"127.0.0.1","localhost"} or parsed.username or parsed.password or parsed.path not in {"","/"}:
        raise AgentUnavailable("Agent URL must be a trusted local http://127.0.0.1:<port> endpoint")
    headers={"Content-Type":"application/json"}
    if os.environ.get("ELYRA_AGENT_TOKEN"):
        headers["X-Agent-Token"]=os.environ["ELYRA_AGENT_TOKEN"]
    request=Request(base+"/v1/investigate",json.dumps({"case_id":case_id}).encode(),headers,method="POST")
    try:
        with urlopen(request,timeout=60) as response:
            result=json.load(response)
        if not isinstance(result,dict) or result.get("case_id")!=case_id or "status" not in result:
            raise AgentUnavailable("Agent service returned an invalid response")
        return result
    except (HTTPError, URLError, TimeoutError, ValueError) as exc:
        raise AgentUnavailable("Agent service unavailable; verify it is running on port 8091") from exc
