"""Three-stage LangGraph workflow with local policy retrieval and bounded LLM planning.

This is an actual LangGraph graph when dependencies are installed. It is *not*
production multi-agent autonomy, does not use persistent graph checkpoints, and
never executes real business actions.
"""
import os
from typing import TypedDict

from elyraops import core
from .provider import draft_rationale


class CaseState(TypedDict, total=False):
    case: dict
    domain: str
    priority: str
    evidence: list[dict]
    action: str
    reasoning: str
    mode: str


def triage_node(state: CaseState) -> dict:
    case=state["case"]
    # Domain is validated by core.create_case; never let an LLM override it.
    return {"domain":case["domain"], "priority":case["priority"]}


def retrieve_node(state: CaseState) -> dict:
    case=state["case"]
    with core.connect() as db:
        evidence=core.retrieve(db, case["title"]+" "+case["description"], state["domain"])
    return {"evidence":evidence}


def plan_node(state: CaseState) -> dict:
    action,policy=core.ACTIONS.get(state["domain"],(
        "Escalate case for manual review", "Human review is required."))
    ids=", ".join(d["id"] for d in state["evidence"]) or "no matching policy"
    if os.environ.get("GEMINI_API_KEY", "").strip() or os.environ.get("OPENAI_API_KEY", "").strip():
        rationale=draft_rationale(state["case"], state["evidence"],action)
        mode="langgraph-llm"
    else:
        rationale=f"{policy} Recommended action: {action}. Source references: {ids}."
        mode="langgraph-demo"
    # The action is server-selected, not LLM-selected. Approval is still mandatory.
    return {"action":action,"reasoning":rationale,"mode":mode}


def run_graph(case:dict) -> CaseState:
    from langgraph.graph import END, START, StateGraph
    builder=StateGraph(CaseState)
    builder.add_node("triage",triage_node)
    builder.add_node("policy_retrieval",retrieve_node)
    builder.add_node("resolution_planning",plan_node)
    builder.add_edge(START,"triage")
    builder.add_edge("triage","policy_retrieval")
    builder.add_edge("policy_retrieval","resolution_planning")
    builder.add_edge("resolution_planning",END)
    return builder.compile().invoke({"case":case})
