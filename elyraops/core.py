"""Persistent case management, evidence retrieval, and approval-gated workflow.

Demo-only data. This implementation deliberately does not execute real financial
or administrative operations. fully implemented. An opt-in HTTP access guard provides demo-only
role and organization scoping; do not expose real business data.
"""
from __future__ import annotations

import json
import math
import os
import re
import sqlite3
import time
import uuid
from collections import Counter
from contextlib import contextmanager
from pathlib import Path
from . import pg_cases

DB_PATH = os.environ.get("ELYRA_DB_PATH", str(Path(__file__).resolve().parent.parent / "data" / "elyraops.db"))

SEED_CASES = [
    ("EC-1042", "Duplicate charge after plan upgrade", "Billing", "High", "Northstar Commerce", "Customer reports two charges on a recent subscription upgrade. Transaction reference TXN-8392. Request investigation and correction."),
    ("EC-1043", "Delayed international shipment", "Logistics", "Medium", "Meridian Global", "Shipment SHP-4822 has passed its estimated delivery date. Customer asks for an update and an escalation."),
    ("EC-1044", "Access blocked after password reset", "Identity", "Critical", "Atlas Retail", "Workspace administrator cannot sign in following MFA re-enrollment. Needs secure recovery without disabling authentication controls."),
    ("EC-1045", "Vendor invoice does not match purchase order", "Procurement", "Medium", "Orion Systems", "Supplier invoice INV-9021 differs from PO-8824 line items. Payment must be held until finance reviews the discrepancy."),
    ("EC-1046", "Refund request for damaged delivery", "Support", "Low", "Pacific Goods", "Customer provided photos of a damaged delivery, order ORD-5102. Wants a refund according to merchant policy."),
]

SEED_DOCS = [
    ("POL-001", "Billing and duplicate payments", "Billing", "When a customer reports a duplicate payment, validate both transaction identifiers and their amounts. Do not refund automatically. A finance approver must confirm any credit or refund before execution."),
    ("POL-002", "Delivery incident escalation", "Logistics", "When a shipment misses its estimated delivery date, check courier tracking, notify the customer, and create a carrier escalation. Do not guarantee a delivery time without carrier confirmation."),
    ("POL-003", "Secure account recovery", "Identity", "For account recovery after MFA reset, verify the requester's identity using an approved method. Never disclose reset tokens, bypass MFA, or disable protections based on an AI recommendation. Escalate to identity administrators."),
    ("POL-004", "Purchase order payment controls", "Procurement", "Invoices with line item or amount mismatches must be held for manual three-way matching against purchase orders and goods receipt records. A finance approver must release any hold."),
    ("POL-005", "Damaged delivery return policy", "Support", "For a damaged delivery, verify the order and accepted evidence. A refund may be proposed but only an authorized human can approve the transaction. Record the resolution for audit."),
    ("POL-006", "Operational audit requirements", "Governance", "Every suggested action must include a reason, evidence references, timestamp, and actor. High-impact actions require human authorization. Repeated requests must be idempotent."),
]


def connect():
    path = Path(DB_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(str(path), timeout=20)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA foreign_keys=ON")
    return db


@contextmanager
def transaction():
    db = connect()
    try:
        db.execute("BEGIN IMMEDIATE")
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def event(db, case_id, event_type, message, actor="system", details=None):
    db.execute("INSERT INTO events (id, case_id, type, message, actor, details, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
               (str(uuid.uuid4()), case_id, event_type, message, actor, json.dumps(details or {}), now()))


def initialize():
    if pg_cases.enabled():
        pg_cases.verify_backend()
    with transaction() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS cases (
          id TEXT PRIMARY KEY, title TEXT NOT NULL, domain TEXT NOT NULL,
          priority TEXT NOT NULL, organization TEXT NOT NULL,
          description TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'Open',
          created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
          proposed_action TEXT, reasoning TEXT, evidence TEXT NOT NULL DEFAULT '[]',
          workflow_run_id TEXT
        );
        CREATE TABLE IF NOT EXISTS knowledge (
          id TEXT PRIMARY KEY, title TEXT NOT NULL, domain TEXT NOT NULL, content TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS events (
          id TEXT PRIMARY KEY, case_id TEXT NOT NULL REFERENCES cases(id),
          type TEXT NOT NULL, message TEXT NOT NULL, actor TEXT NOT NULL,
          details TEXT NOT NULL, created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_events_case ON events(case_id, created_at);
        """)
        if db.execute("SELECT COUNT(*) FROM cases").fetchone()[0] == 0:
            for id_, title, domain, priority, org, description in SEED_CASES:
                db.execute("INSERT INTO cases(id,title,domain,priority,organization,description,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)",
                           (id_, title, domain, priority, org, description, "Open", now(), now()))
                event(db, id_, "created", "Case received and added to the investigation queue", "demo-import")
        if db.execute("SELECT COUNT(*) FROM knowledge").fetchone()[0] == 0:
            db.executemany("INSERT INTO knowledge VALUES (?,?,?,?)", SEED_DOCS)


def tokens(text):
    return [x for x in re.findall(r"[a-z0-9]+", text.lower()) if len(x) > 2]


def retrieve(db, query, domain, limit=3):
    """Local, transparent TF-IDF-like keyword retrieval; NOT an embedding model."""
    # Only policies for the case domain may be cited; keyword overlap does not
    # confer document access or business relevance.
    docs = [dict(x) for x in db.execute("SELECT * FROM knowledge WHERE domain=?", (domain,))]
    q = Counter(tokens(query))
    doc_tokens = [Counter(tokens(d["title"] + " " + d["content"])) for d in docs]
    n = max(len(docs), 1)
    ranked = []
    for d, dt in zip(docs, doc_tokens):
        score = sum((1 + math.log(n / (1 + sum(t in c for c in doc_tokens)))) * min(q[t], dt.get(t, 0)) for t in q)
        if d["domain"] == domain:
            score += 5.0
        ranked.append((score, d))
    return [{"id": d["id"], "title": d["title"], "domain": d["domain"], "excerpt": d["content"], "score": round(s, 2)}
            for s, d in sorted(ranked, key=lambda a: -a[0])[:limit] if s > 0]


ACTIONS = {
    "Billing": ("Flag duplicate payment for finance review", "Finance approval required before any credit or refund."),
    "Logistics": ("Create carrier escalation and customer update", "Logistics coordinator must verify courier tracking before sending an update."),
    "Identity": ("Escalate identity verification and secure recovery", "Identity administrators must verify ownership; never bypass MFA."),
    "Procurement": ("Hold invoice and initiate three-way matching", "Finance must authorize release after matching the purchase order and goods receipt."),
    "Support": ("Propose damage-related refund for human review", "Authorized support approver must verify order and evidence first."),
}


def list_cases(organization=None):
    if pg_cases.enabled():
        return pg_cases.list_cases(organization)
    with connect() as db:
        query = "SELECT id,title,domain,priority,organization,description,status,created_at,updated_at FROM cases"
        if organization is None:
            return [dict(r) for r in db.execute(query + " ORDER BY id")]
        return [dict(r) for r in db.execute(query + " WHERE organization=? ORDER BY id", (organization,))]


def get_case(case_id, organization=None):
    if pg_cases.enabled():
        return pg_cases.get_case(case_id, organization)
    with connect() as db:
        if organization is None:
            r = db.execute("SELECT * FROM cases WHERE id=?", (case_id,)).fetchone()
        else:
            r = db.execute("SELECT * FROM cases WHERE id=? AND organization=?", (case_id, organization)).fetchone()
        if not r:
            return None
        data = dict(r)
        data["evidence"] = json.loads(data["evidence"])
        data["events"] = [dict(e) for e in db.execute("SELECT * FROM events WHERE case_id=? ORDER BY rowid DESC LIMIT 30", (case_id,))]
        for e in data["events"]:
            e["details"] = json.loads(e["details"])
        return data


def investigate(case_id, organization=None):
    if pg_cases.enabled():
        return pg_cases.investigate(case_id, organization)
    with transaction() as db:
        if organization is None:
            row = db.execute("SELECT * FROM cases WHERE id=?", (case_id,)).fetchone()
        else:
            row = db.execute("SELECT * FROM cases WHERE id=? AND organization=?", (case_id, organization)).fetchone()
        if not row:
            raise KeyError(case_id)
        if row["status"] != "Open":
            # Idempotent: investigation never duplicates pending action.
            return {"case_id": case_id, "status": row["status"], "workflow_run_id": row["workflow_run_id"], "already_processed": True}
        evidence = retrieve(db, row["description"] + " " + row["title"], row["domain"])
        action, policy = ACTIONS.get(row["domain"], ("Escalate case for review", "Human review is required."))
        workflow_run_id = str(uuid.uuid4())
        stages = [
            ("triage_agent", "Classified case as " + row["domain"] + "; priority: " + row["priority"]),
            ("retrieval_agent", "Found " + str(len(evidence)) + " supporting policy documents"),
            ("resolution_agent", "Prepared a policy-constrained recommendation; execution blocked pending approval"),
        ]
        for typ, description in stages:
            event(db, case_id, typ, description, typ, {"run_id": workflow_run_id})
        reason = policy + " Recommended action: " + action
        db.execute("UPDATE cases SET status=?, proposed_action=?, reasoning=?, evidence=?, workflow_run_id=?, updated_at=? WHERE id=?",
                   ("Pending approval", action, reason, json.dumps(evidence), workflow_run_id, now(), case_id))
        event(db, case_id, "approval_requested", "Human authorization required before any execution", "workflow-engine", {"action": action})
        return {"case_id": case_id, "status": "Pending approval", "workflow_run_id": workflow_run_id, "already_processed": False}


def decide(case_id, decision, actor, organization=None):
    if decision not in {"approve", "reject"}:
        raise ValueError("Decision must be 'approve' or 'reject'")
    if not actor or not isinstance(actor, str) or len(actor) > 80:
        raise ValueError("A short approver name is required")
    if pg_cases.enabled():
        return pg_cases.decide(case_id, decision, actor, organization)
    with transaction() as db:
        if organization is None:
            r = db.execute("SELECT * FROM cases WHERE id=?", (case_id,)).fetchone()
        else:
            r = db.execute("SELECT * FROM cases WHERE id=? AND organization=?", (case_id, organization)).fetchone()
        if not r:
            raise KeyError(case_id)
        if r["status"] != "Pending approval":
            raise ValueError("Case must be pending approval")
        if decision == "approve":
            db.execute("UPDATE cases SET status=?, updated_at=? WHERE id=?", ("Approved · simulated", now(), case_id))
            event(db, case_id, "approved", "Action approved by demo operator", actor)
            event(db, case_id, "simulated_execution", "SIMULATION ONLY: workflow action recorded, no external system changed", "execution-adapter", {"action": r["proposed_action"]})
        else:
            db.execute("UPDATE cases SET status=?, updated_at=? WHERE id=?", ("Rejected", now(), case_id))
            event(db, case_id, "rejected", "Proposed action rejected by demo operator", actor)
        return {"case_id": case_id, "status": "Approved · simulated" if decision == "approve" else "Rejected"}


def knowledge():
    with connect() as db:
        return [dict(r) for r in db.execute("SELECT id,title,domain,content FROM knowledge ORDER BY id")]


def dashboard(organization=None):
    cases = list_cases(organization)
    return {
        "cases_total": len(cases),
        "pending_approvals": sum(c["status"] == "Pending approval" for c in cases),
        "resolved_simulations": sum(c["status"] == "Approved · simulated" for c in cases),
        "open_cases": sum(c["status"] == "Open" for c in cases),
        "high_priority": sum(c["priority"] in {"High", "Critical"} for c in cases),
        "domains": {d: sum(c["domain"] == d for c in cases) for d in sorted({c["domain"] for c in cases})},
    }


def create_case(payload, organization=None):
    title = str(payload.get("title", "")).strip()
    description = str(payload.get("description", "")).strip()
    domain = str(payload.get("domain", "Support"))
    priority = str(payload.get("priority", "Medium"))
    organization = str(organization if organization is not None else payload.get("organization", "Demo organization")).strip()
    if not (4 <= len(title) <= 140 and 10 <= len(description) <= 3000):
        raise ValueError("Title must be 4–140 characters and description 10–3000 characters")
    if domain not in ACTIONS or priority not in {"Low", "Medium", "High", "Critical"} or not (1 <= len(organization) <= 100):
        raise ValueError("Invalid domain, priority or organization")
    if pg_cases.enabled():
        return pg_cases.create_case({"title":title,"description":description,"domain":domain,"priority":priority},organization)
    case_id = "EC-" + str(uuid.uuid4().int % 900000 + 100000)
    with transaction() as db:
        db.execute("INSERT INTO cases(id,title,domain,priority,organization,description,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)",
                   (case_id, title, domain, priority, organization, description, "Open", now(), now()))
        event(db, case_id, "created", "New case created", "demo-operator")
    return {"id": case_id, "status": "Open"}
