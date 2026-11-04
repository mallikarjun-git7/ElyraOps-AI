"""Local-only FastAPI orchestration service. Uses the same demo SQLite database.

Set host to 127.0.0.1. This service is NOT safe for public internet exposure.
"""
import json
import os
import uuid

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from elyraops import core
from .provider import ModelUnavailable
from .workflow import run_graph

app=FastAPI(title="ElyraOps Agent Service",version="0.2.0")


class InvestigationRequest(BaseModel):
    case_id: str = Field(pattern=r"^EC-[A-Za-z0-9-]+$", max_length=70)


@app.get("/health")
def health():
    gemini = bool(os.environ.get("GEMINI_API_KEY", "").strip())
    openai = bool(os.environ.get("OPENAI_API_KEY", "").strip())
    return {"status":"ok", "service":"elyraops-agents",
            "llm_enabled":gemini or openai,
            "llm_provider":"gemini" if gemini else ("openai" if openai else "demo")}


@app.post("/v1/investigate")
def investigate(payload: InvestigationRequest, x_agent_token: str | None = Header(default=None)):
    token=os.environ.get("ELYRA_AGENT_TOKEN", "")
    if token and x_agent_token != token:
        raise HTTPException(401,"Invalid internal service token")
    core.initialize()
    case=core.get_case(payload.case_id)
    if case is None:
        raise HTTPException(404,"Case not found")
    if case["status"] != "Open":
        return {"case_id":case["id"],"status":case["status"],"workflow_run_id":case["workflow_run_id"],"already_processed":True}
    try:
        result=run_graph(case)
    except ModelUnavailable:
        raise HTTPException(503,"AI provider unavailable; case unchanged")
    except ImportError:
        raise HTTPException(503,"LangGraph not installed in the agent service environment")
    run_id=str(uuid.uuid4())
    # Never keep a DB write lock open while waiting for model calls.
    with core.transaction() as db:
        fresh=db.execute("SELECT status,workflow_run_id FROM cases WHERE id=?",(payload.case_id,)).fetchone()
        if fresh is None:
            raise HTTPException(404,"Case not found")
        if fresh["status"] != "Open":
            return {"case_id":payload.case_id,"status":fresh["status"],"workflow_run_id":fresh["workflow_run_id"],"already_processed":True}
        db.execute("UPDATE cases SET status=?,proposed_action=?,reasoning=?,evidence=?,workflow_run_id=?,updated_at=? WHERE id=?", (
            "Pending approval",result["action"],result["reasoning"],json.dumps(result["evidence"]),run_id,core.now(),payload.case_id))
        for stage,message in (
            ("triage_agent",f"LangGraph triage: {result['domain']} | {result['priority']}"),
            ("retrieval_agent",f"LangGraph retrieved {len(result['evidence'])} policy references"),
            ("resolution_agent",f"Proposed a bounded recommendation ({result['mode']}); requires human approval"),
        ):
            core.event(db,payload.case_id,stage,message,"langgraph",{"run_id":run_id,"mode":result["mode"]})
        core.event(db,payload.case_id,"approval_requested","Explicit human approval required; no external action taken","langgraph",{"action":result["action"]})
    return {"case_id":payload.case_id,"status":"Pending approval","workflow_run_id":run_id,"already_processed":False,"mode":result["mode"]}
