from typing import List
from fastapi import APIRouter, HTTPException
from app.services.showcase_service import ShowcaseService, ShowcaseCase

router = APIRouter(prefix="/api/showcase", tags=["Showcase"])
showcase_svc = ShowcaseService()

@router.get("", response_model=List[ShowcaseCase])
def get_showcase_cases():
    """Retrieve the 4 canonical showcase cases (Corroboration, Contradiction, Reconciliation, Failure Analysis)."""
    return showcase_svc.get_canonical_showcases()

@router.get("/{case_id}", response_model=ShowcaseCase)
def get_showcase_case(case_id: str):
    """Retrieve a specific showcase case by ID."""
    cases = showcase_svc.get_canonical_showcases()
    for c in cases:
        if c.case_id == case_id:
            return c
    raise HTTPException(status_code=404, detail=f"Showcase case '{case_id}' not found.")
