"""
routers/policies.py
-------------------
Endpoints for querying company HR policies using RAG:
- POST /policies/search
"""

from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from app.models import Employee
from app.security import get_current_user
from app.services.rag_service import search_policy


router = APIRouter(prefix="/policies", tags=["Policies (RAG)"])


class PolicySearchRequest(BaseModel):
    query: str = Field(..., description="Question or search query regarding HR policies", example="Can I carry forward my earned leave?")
    top_k: int = Field(3, ge=1, le=10, description="Maximum number of relevant sections to retrieve")


class PolicySectionResult(BaseModel):
    policy_name: str
    short_name: str
    section: int
    section_title: str
    citation: str
    content: str
    distance: float


class PolicySearchResponse(BaseModel):
    found: bool
    query: str
    message: Optional[str] = None
    results: List[PolicySectionResult] = []
    citations: List[str] = []
    context_text: Optional[str] = None


@router.post(
    "/search",
    response_model=PolicySearchResponse,
    summary="Search HR Policies",
    description="Semantically searches the 3 company policies using ChromaDB. Returns relevant sections and citations.",
)
def search_hr_policies(
    payload: PolicySearchRequest,
    current_user: Employee = Depends(get_current_user),
):
    return search_policy(query=payload.query, top_k=payload.top_k)
