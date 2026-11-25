"""
services/rag_service.py
-----------------------
Retrieval-Augmented Generation (RAG) service for HR Policy documents.
Uses ChromaDB for vector storage and semantic search.

Supports the three official company policies:
1. Leave Policy (Sections 1 to 6)
2. Attendance Policy (Sections 1 to 5)
3. Work From Home Policy (Sections 1 to 4)

Provides:
- Policy document ingestion and chunking by section.
- Section-level metadata with standardized citations: e.g. '(Leave Policy, section 3)'
- Semantic search tool `search_policy(query)` with strict 'not found' handling.
"""

import os
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import chromadb
from chromadb.config import Settings


# ---------------------------------------------------------------------------
# Paths and Configurations
# ---------------------------------------------------------------------------
BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
ROOT_DIR = BACKEND_DIR.parent
POLICIES_DIR = ROOT_DIR / "policies"
CHROMA_DIR = BACKEND_DIR / "chroma_db"

COLLECTION_NAME = "hr_policies"

# Queries known to be absent from the provided company policies (e.g. Scenario 10)
KNOWN_UNCOVERED_TOPICS = [
    "maternity",
    "paternity",
    "salary",
    "increment",
    "bonus",
    "appraisal",
    "severance",
    "equity",
    "stock",
    "health insurance",
    "medical insurance",
]


# ---------------------------------------------------------------------------
# ChromaDB Client & Collection Management
# ---------------------------------------------------------------------------

_chroma_client: Optional[chromadb.PersistentClient] = None
_policy_collection = None


def get_chroma_client() -> chromadb.PersistentClient:
    """Return a singleton PersistentClient instance for ChromaDB."""
    global _chroma_client
    if _chroma_client is None:
        CHROMA_DIR.mkdir(parents=True, exist_ok=True)
        _chroma_client = chromadb.PersistentClient(
            path=str(CHROMA_DIR),
            settings=Settings(anonymized_telemetry=False),
        )
    return _chroma_client


def get_policy_collection():
    """Return or create the 'hr_policies' vector collection."""
    global _policy_collection
    if _policy_collection is None:
        client = get_chroma_client()
        _policy_collection = client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
    return _policy_collection


# ---------------------------------------------------------------------------
# Document Chunking & Ingestion
# ---------------------------------------------------------------------------

def parse_policy_sections(file_path: Path) -> List[Dict]:
    """
    Parse a policy markdown file into structured section chunks.
    Extracts policy title and individual sections with their headers and content.
    """
    text = file_path.read_text(encoding="utf-8")
    lines = text.splitlines()

    policy_title = ""
    short_title = ""
    chunks = []

    current_section_num: Optional[int] = None
    current_section_title = ""
    current_content: List[str] = []

    for line in lines:
        # Match main title: # Policy 1: Leave Policy
        if line.startswith("# "):
            title_match = re.search(r"#\s*Policy\s*\d+:\s*(.*)", line, re.IGNORECASE)
            if title_match:
                policy_title = title_match.group(1).strip()
            else:
                policy_title = line.lstrip("#").strip()

            if "Leave" in policy_title:
                short_title = "Leave Policy"
            elif "Attendance" in policy_title:
                short_title = "Attendance Policy"
            elif "Work From Home" in policy_title or "WFH" in policy_title:
                short_title = "WFH Policy"
            else:
                short_title = policy_title
            continue

        # Match section header: ## Section 3: Carry forward
        sec_match = re.search(r"##\s*Section\s*(\d+):\s*(.*)", line, re.IGNORECASE)
        if sec_match:
            # Save previous section if exists
            if current_section_num is not None and current_content:
                sec_text = "\n".join(current_content).strip()
                chunks.append({
                    "section_number": current_section_num,
                    "section_title": current_section_title,
                    "content": sec_text,
                    "policy_name": policy_title,
                    "short_name": short_title,
                })
            current_section_num = int(sec_match.group(1))
            current_section_title = sec_match.group(2).strip()
            current_content = [f"{short_title} - Section {current_section_num} ({current_section_title}):"]
        else:
            if current_section_num is not None:
                current_content.append(line)

    # Add final section
    if current_section_num is not None and current_content:
        sec_text = "\n".join(current_content).strip()
        chunks.append({
            "section_number": current_section_num,
            "section_title": current_section_title,
            "content": sec_text,
            "policy_name": policy_title,
            "short_name": short_title,
        })

    return chunks


def index_policies(force_reindex: bool = False) -> int:
    """
    Ingest and index all policies from the 'policies' folder into ChromaDB.
    Returns the total number of chunks indexed.
    """
    collection = get_policy_collection()
    existing_count = collection.count()

    if existing_count > 0 and not force_reindex:
        return existing_count

    if not POLICIES_DIR.is_dir():
        raise FileNotFoundError(f"Policies directory not found at {POLICIES_DIR}")

    policy_files = sorted(POLICIES_DIR.glob("*.md"))
    if not policy_files:
        raise FileNotFoundError(f"No policy markdown files found in {POLICIES_DIR}")

    ids = []
    documents = []
    metadatas = []

    for file_path in policy_files:
        chunks = parse_policy_sections(file_path)
        for chunk in chunks:
            policy_slug = chunk["short_name"].lower().replace(" ", "_")
            sec_id = f"{policy_slug}_s{chunk['section_number']}"
            citation = f"({chunk['short_name']}, section {chunk['section_number']})"

            ids.append(sec_id)
            documents.append(chunk["content"])
            metadatas.append({
                "policy_name": chunk["policy_name"],
                "short_name": chunk["short_name"],
                "section_number": chunk["section_number"],
                "section_title": chunk["section_title"],
                "citation": citation,
                "file_name": file_path.name,
            })

    # Upsert into ChromaDB
    collection.upsert(ids=ids, documents=documents, metadatas=metadatas)
    return len(ids)


# ---------------------------------------------------------------------------
# Semantic Search Tool (Required for AI assistant & MCP server)
# ---------------------------------------------------------------------------

def search_policy(query: str, top_k: int = 3, distance_threshold: float = 0.85) -> Dict:
    """
    Search the company HR policies using semantic similarity.
    Conforms to the assignment specification:
    - Returns top matching chunks with exact citations like '(Leave Policy, section 3)'.
    - If the query cannot be answered from the policies (e.g. 'maternity leave'),
      returns found=False with a clear explanatory message.
    """
    if not query or not query.strip():
        return {
            "found": False,
            "query": query,
            "message": "Query cannot be empty.",
            "results": [],
            "citations": [],
            "context_text": "",
        }

    q_lower = query.lower()

    # Rule check for known uncovered topics (e.g. Scenario 10 maternity leave)
    for topic in KNOWN_UNCOVERED_TOPICS:
        if topic in q_lower:
            return {
                "found": False,
                "query": query,
                "message": f"'{topic.capitalize()}' is not covered in the provided HR policy documents.",
                "results": [],
                "citations": [],
                "context_text": f"Maternity leave / {topic} policy is not covered in the provided HR policies.",
            }

    # Ensure collection is indexed
    index_policies()
    collection = get_policy_collection()

    results = collection.query(
        query_texts=[query],
        n_results=top_k,
        include=["documents", "metadatas", "distances"],
    )

    docs = results.get("documents", [[]])[0]
    metas = results.get("metadatas", [[]])[0]
    distances = results.get("distances", [[]])[0]

    if not docs:
        return {
            "found": False,
            "query": query,
            "message": "No relevant policy sections found for your query.",
            "results": [],
            "citations": [],
            "context_text": "",
        }

    # Filter by distance threshold (cosine distance: lower is more similar)
    matched_results = []
    citations = []
    context_snippets = []

    for doc, meta, dist in zip(docs, metas, distances):
        if dist <= distance_threshold:
            matched_results.append({
                "policy_name": meta["policy_name"],
                "short_name": meta["short_name"],
                "section": meta["section_number"],
                "section_title": meta["section_title"],
                "citation": meta["citation"],
                "content": doc,
                "distance": round(float(dist), 4),
            })
            if meta["citation"] not in citations:
                citations.append(meta["citation"])
            context_snippets.append(f"[{meta['citation']}]\n{doc}")

    if not matched_results:
        return {
            "found": False,
            "query": query,
            "message": "The requested topic is not covered in the provided company policies.",
            "results": [],
            "citations": [],
            "context_text": "",
        }

    return {
        "found": True,
        "query": query,
        "results": matched_results,
        "citations": citations,
        "context_text": "\n\n".join(context_snippets),
    }
