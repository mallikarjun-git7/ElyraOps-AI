"""Optional local-only hybrid retrieval: pgvector + PostgreSQL full-text ranking.

Local CLI ingestion is owner-only; guarded RAG retrieval can opt into a non-owner
PostgreSQL connection with row-level security. This remains a localhost demo.
"""
from __future__ import annotations

import argparse
import json
import math
import os
from contextlib import contextmanager
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from elyraops import core

DIMENSION = 768
EMBEDDING_MODEL = "gemini-embedding-001"
RRF_K = 60


class RagUnavailable(RuntimeError):
    """A backend dependency could not serve a safe retrieval request."""


def _pg_deps():
    try:
        import psycopg
        from psycopg.rows import dict_row
        from pgvector.psycopg import register_vector
    except ImportError as exc:
        raise RagUnavailable("Install requirements-rag.txt for PostgreSQL retrieval") from exc
    return psycopg, dict_row, register_vector


def embedding(text: str, task_type: str) -> list[float]:
    """A genuine Gemini semantic embedding. Never fall back to fake vectors."""
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        raise RagUnavailable("GEMINI_API_KEY required for vector retrieval")
    if task_type not in {"RETRIEVAL_DOCUMENT", "RETRIEVAL_QUERY"}:
        raise ValueError("Unsupported embedding task")
    if not text or len(text) > 6000:
        raise ValueError("Embedding input must be between 1 and 6000 characters")
    model = EMBEDDING_MODEL  # Fixed model/version: do not mix incompatible vectors.
    body = {
        "model": "models/" + model,
        "content": {"parts": [{"text": text}]},
        "taskType": task_type,
        "outputDimensionality": DIMENSION,
    }
    request = Request(
        "https://generativelanguage.googleapis.com/v1beta/models/"
        + model + ":embedContent",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "x-goog-api-key": key},
        method="POST",
    )
    try:
        with urlopen(request, timeout=40) as response:
            values = json.load(response)["embedding"]["values"]
    except (HTTPError, URLError, TimeoutError, ValueError, KeyError, TypeError) as exc:
        # Never include provider payload, key or user documents in an HTTP error.
        raise RagUnavailable("Gemini embedding request failed") from exc
    if not isinstance(values, list) or len(values) != DIMENSION:
        raise RagUnavailable("Unexpected embedding dimension")
    try:
        vector = [float(x) for x in values]
    except (ValueError, TypeError) as exc:
        raise RagUnavailable("Invalid embedding result") from exc
    if not all(math.isfinite(x) for x in vector):
        raise RagUnavailable("Nonfinite embedding values")
    magnitude = math.sqrt(sum(x * x for x in vector))
    if magnitude < 1e-12:
        raise RagUnavailable("Zero-length embedding")
    # gemini-embedding-001 output truncated to 768 dims needs normalization.
    return [x / magnitude for x in vector]


def _db_url() -> str:
    url = os.environ.get("ELYRA_RAG_DATABASE_URL", "").strip()
    if not url:
        raise RagUnavailable("Set ELYRA_RAG_DATABASE_URL for PostgreSQL retrieval")
    return url


def secure_rag_enabled() -> bool:
    """Explicit opt-in. Unknown values are errors, never silent insecure fallback."""
    mode = os.environ.get("ELYRA_RAG_RLS_MODE", "").strip()
    if mode not in {"", "required"}:
        raise RagUnavailable("ELYRA_RAG_RLS_MODE must be unset or 'required'")
    return mode == "required"


def _runtime_url(organization: str) -> str:
    """Use only the existing non-owner case role for guarded RAG reads."""
    from elyraops import security
    try:
        guarded = security.enabled()
    except security.SecurityError as exc:
        raise RagUnavailable("Guarded authentication must be configured") from exc
    if not guarded:
        raise RagUnavailable("Secure RAG requires ELYRA_SECURITY_MODE=required")
    if (not isinstance(organization, str) or not 1 <= len(organization) <= 100
            or organization == "shared"):
        raise RagUnavailable("An authenticated, non-shared organization is required")
    url = os.environ.get("ELYRA_CASES_DATABASE_URL", "").strip()
    if not url:
        raise RagUnavailable("Secure RAG requires the non-owner ELYRA_CASES_DATABASE_URL")
    return url


@contextmanager
def secure_rag_connection(organization: str):
    """RLS-scoped transaction; no owner URL or cross-request tenant leakage."""
    if not secure_rag_enabled():
        raise RagUnavailable("Secure RAG mode not activated")
    url = _runtime_url(organization)
    psycopg, dict_row, register_vector = _pg_deps()
    try:
        with psycopg.connect(url, row_factory=dict_row, connect_timeout=5) as conn:
            register_vector(conn)
            actor = conn.execute("SELECT current_user AS name").fetchone()["name"]
            if actor != "elyra_cases_runtime":
                raise RagUnavailable("RAG runtime must use the dedicated non-owner role")
            role = conn.execute("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname=current_user").fetchone()
            if not role or role["rolsuper"] or role["rolbypassrls"]:
                raise RagUnavailable("Unsafe PostgreSQL RAG runtime privileges")
            state = conn.execute("""
                SELECT c.relrowsecurity, c.relforcerowsecurity, c.relowner =
                       (SELECT oid FROM pg_roles WHERE rolname=current_user) AS is_owner
                  FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                 WHERE n.nspname='public' AND c.relname='rag_chunks'
            """).fetchone()
            if not state or not state["relrowsecurity"] or not state["relforcerowsecurity"] or state["is_owner"]:
                raise RagUnavailable("RAG table RLS not enabled and forced for the non-owner role")
            policy = conn.execute("""
                SELECT 1 FROM pg_policies WHERE schemaname='public'
                 AND tablename='rag_chunks' AND policyname='rag_tenant_read'
            """).fetchone()
            if not policy:
                raise RagUnavailable("Secure RAG retrieval policy is missing")
            conn.execute("SELECT set_config(%s, %s, true)", ("elyra.tenant_id", organization))
            yield conn
    except psycopg.Error as exc:
        raise RagUnavailable("Secure RAG PostgreSQL query failed") from exc


def init_db() -> None:
    psycopg, _, _ = _pg_deps()
    try:
        with psycopg.connect(_db_url(), connect_timeout=5) as conn:
            conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS rag_chunks (
                    tenant_id TEXT NOT NULL,
                    document_id TEXT NOT NULL,
                    chunk_index INTEGER NOT NULL,
                    domain TEXT NOT NULL,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    embedding_model TEXT NOT NULL DEFAULT 'gemini-embedding-001',
                    embedding VECTOR(768) NOT NULL,
                    PRIMARY KEY (tenant_id, document_id, chunk_index)
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS rag_chunks_text_idx
                ON rag_chunks USING GIN
                (to_tsvector('english', title || ' ' || content))
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS rag_chunks_embedding_idx
                ON rag_chunks USING hnsw (embedding vector_cosine_ops)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS rag_chunks_scope_idx
                ON rag_chunks (tenant_id, domain)
            """)
    except psycopg.Error as exc:
        raise RagUnavailable("PostgreSQL initialization failed") from exc


def split_chunks(text: str, size: int = 1100, overlap: int = 160) -> list[str]:
    if not (100 <= size <= 3000 and 0 <= overlap < size // 2):
        raise ValueError("Invalid chunking configuration")
    text = " ".join(text.split())
    if not text:
        return []
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        if end < len(text):
            boundary = text.rfind(" ", start + int(size * .75), end)
            if boundary > start:
                end = boundary
        segment = text[start:end].strip()
        if segment:
            chunks.append(segment)
        if end == len(text):
            break
        start = end - overlap
    return chunks


def ingest(document_id: str, title: str, domain: str, content: str,
           tenant_id: str = "shared") -> int:
    """Local CLI ingestion only. No HTTP interface or production access control."""
    if not (1 <= len(document_id) <= 90 and 1 <= len(title) <= 180 and
            1 <= len(tenant_id) <= 100 and domain in {*core.ACTIONS, "Governance"}):
        raise ValueError("Invalid document metadata")
    if len(content) > 120_000:
        raise ValueError("Document exceeds 120 KB limit")
    parts = split_chunks(content)
    if not parts:
        raise ValueError("Empty document")
    vectors = [embedding(title + "\n" + part, "RETRIEVAL_DOCUMENT") for part in parts]
    psycopg, _, register_vector = _pg_deps()
    try:
        with psycopg.connect(_db_url(), connect_timeout=5) as conn:
            register_vector(conn)
            with conn.transaction():
                conn.execute("DELETE FROM rag_chunks WHERE tenant_id=%s AND document_id=%s", (tenant_id, document_id))
                for i, (part, vec) in enumerate(zip(parts, vectors)):
                    conn.execute("""
                        INSERT INTO rag_chunks(tenant_id,document_id,chunk_index,domain,title,content,embedding_model,embedding)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                    """, (tenant_id, document_id, i, domain, title, part, EMBEDDING_MODEL, vec))
    except psycopg.Error as exc:
        raise RagUnavailable("PostgreSQL document ingestion failed") from exc
    return len(parts)


def seed_demo_documents() -> None:
    init_db()
    for doc_id, title, domain, content in core.SEED_DOCS:
        count = ingest(doc_id, title, domain, content, "shared")
        print(f"Indexed {doc_id}: {count} chunk(s)")


def fuse_ranked(vector_hits: list[dict], lexical_hits: list[dict], limit: int = 3) -> list[dict]:
    """Reciprocal rank fusion with transparent per-source scores."""
    combined: dict[tuple, dict] = {}
    for ranked, weight in ((vector_hits, 1.0), (lexical_hits, 1.25)):
        for rank, hit in enumerate(ranked, start=1):
            key = (hit["tenant_id"], hit["document_id"], hit["chunk_index"])
            if key not in combined:
                combined[key] = {**hit, "rrf_score": 0.0}
            combined[key]["rrf_score"] += weight / (RRF_K + rank)
    top = sorted(combined.values(), key=lambda h: (-h["rrf_score"], h["document_id"], h["chunk_index"]))[:limit]
    return [{"id": item["document_id"], "title": item["title"], "domain": item["domain"],
             "excerpt": item["content"], "score": round(item["rrf_score"], 5)} for item in top]


def search(query: str, domain: str, organization: str, limit: int = 3) -> list[dict]:
    """Searches only domain-scoped, shared or organization-labelled documents.

    In secure RAG mode, the organization must come from the authenticated
    case loaded by the trusted internal agent service, not raw user input.
    """
    if domain not in core.ACTIONS or not (1 <= len(organization) <= 100):
        raise ValueError("Invalid retrieval scope")
    if not (1 <= len(query) <= 4000) or not (1 <= limit <= 10):
        raise ValueError("Invalid retrieval request")
    protected = secure_rag_enabled()
    if protected:
        # Validate guard and RLS runtime before consuming Gemini embedding quota.
        _runtime_url(organization)
    query_vec = embedding(query, "RETRIEVAL_QUERY")
    psycopg, dict_row, register_vector = _pg_deps()
    # Bind a native pgvector value, not a PostgreSQL float8[] array.
    from pgvector import Vector
    fields = "tenant_id, document_id, chunk_index, title, domain, content"
    scope = "tenant_id IN ('shared', %s) AND domain = %s AND embedding_model = %s"
    vector_sql = (f"SELECT {fields} FROM rag_chunks WHERE {scope} "
                  "ORDER BY embedding <=> %s LIMIT 20")
    text_sql = (f"SELECT {fields} FROM rag_chunks WHERE {scope} AND "
                "to_tsvector('english', title || ' ' || content) @@ websearch_to_tsquery('english', %s) "
                "ORDER BY ts_rank_cd(to_tsvector('english', title || ' ' || content), "
                "websearch_to_tsquery('english', %s)) DESC LIMIT 20")
    try:
        if protected:
            # Database policy is the authorization boundary; predicates remain
            # as defence-in-depth and for efficient query planning.
            with secure_rag_connection(organization) as conn:
                vector_hits = conn.execute(vector_sql, (organization, domain, EMBEDDING_MODEL, Vector(query_vec))).fetchall()
                lexical_hits = conn.execute(text_sql, (organization, domain, EMBEDDING_MODEL, query, query)).fetchall()
        else:
            # Legacy local demo only. The configured URL may be the table owner;
            # NEVER use this path for protected production documents.
            with psycopg.connect(_db_url(), row_factory=dict_row, connect_timeout=5) as conn:
                register_vector(conn)
                vector_hits = conn.execute(vector_sql, (organization, domain, EMBEDDING_MODEL, Vector(query_vec))).fetchall()
                lexical_hits = conn.execute(text_sql, (organization, domain, EMBEDDING_MODEL, query, query)).fetchall()
    except psycopg.Error as exc:
        raise RagUnavailable("PostgreSQL hybrid retrieval failed") from exc
    return fuse_ranked(vector_hits, lexical_hits, limit)


def retrieve_for_case(case: dict) -> list[dict]:
    query = (case["title"] + " " + case["description"])[:4000]
    if secure_rag_enabled() or os.environ.get("ELYRA_RAG_DATABASE_URL", "").strip():
        return search(query, case["domain"], case["organization"])
    # Offline fallback is domain-filtered but NOT semantic/vector search.
    with core.connect() as db:
        return core.retrieve(db, query, case["domain"])


def main() -> None:
    parser = argparse.ArgumentParser(description="ElyraOps local RAG administration")
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("init")
    sub.add_parser("seed")
    add = sub.add_parser("ingest")
    add.add_argument("--file", required=True)
    add.add_argument("--id", required=True)
    add.add_argument("--title", required=True)
    add.add_argument("--domain", choices=[*core.ACTIONS, "Governance"], required=True)
    add.add_argument("--tenant", default="shared")
    args = parser.parse_args()
    if args.action == "init":
        init_db()
        print("PostgreSQL RAG initialized")
    elif args.action == "seed":
        seed_demo_documents()
    else:
        path = Path(args.file)
        if path.suffix.lower() not in {".txt", ".md"} or path.stat().st_size > 120_000:
            parser.error("Only .txt/.md files under 120KB are supported")
        count = ingest(args.id, args.title, args.domain, path.read_text(encoding="utf-8"), args.tenant)
        print(f"Indexed {args.id}: {count} chunk(s)")


if __name__ == "__main__":
    main()
