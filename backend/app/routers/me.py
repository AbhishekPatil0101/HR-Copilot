"""
routers/me.py
-------------
Endpoints for the authenticated employee's personal HR data:
- GET  /me/leave-balance
- GET  /me/attendance?from=&to=
- POST /me/leave-requests
"""

from datetime import date
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Employee
from app.security import get_current_user
from app.services.hr_service import (
    create_leave_request,
    get_employee_attendance,
    get_employee_leave_balances,
)


router = APIRouter(prefix="/me", tags=["Me"])


# ---------------------------------------------------------------------------
# Pydantic Schemas
# ---------------------------------------------------------------------------

class LeaveApplyRequest(BaseModel):
    """Schema for applying for leave."""
    leave_type: str = Field(..., description="Leave type: CL, SL, or EL", example="CL")
    from_date: date = Field(..., description="Start date (YYYY-MM-DD)", example="2026-11-12")
    to_date: date = Field(..., description="End date (YYYY-MM-DD)", example="2026-11-13")
    days: int = Field(..., gt=0, description="Total days requested", example=2)
    reason: Optional[str] = Field(None, description="Reason for leave", example="Family wedding")


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get(
    "/leave-balance",
    summary="Get My Leave Balances",
    description="Returns the logged-in employee's 2026 leave balances (CL, SL, EL) and pending requests.",
)
def get_my_leave_balances(
    year: int = Query(2026, description="Calendar year"),
    current_user: Employee = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return get_employee_leave_balances(
        db=db,
        employee_id=current_user.employee_id,
        requester=current_user,
        year=year,
    )


@router.get(
    "/attendance",
    summary="Get My Attendance Records",
    description="Returns the logged-in employee's raw attendance records filtered by date range.",
)
def get_my_attendance(
    from_date: Optional[date] = Query(None, alias="from", description="Start date (YYYY-MM-DD)"),
    to_date: Optional[date] = Query(None, alias="to", description="End date (YYYY-MM-DD)"),
    current_user: Employee = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return get_employee_attendance(
        db=db,
        employee_id=current_user.employee_id,
        requester=current_user,
        from_date=from_date,
        to_date=to_date,
    )


@router.post(
    "/leave-requests",
    status_code=status.HTTP_201_CREATED,
    summary="Apply for Leave",
    description="Submit a new leave application. Validates business constraints, probation rules, and available balance.",
)
def apply_for_leave(
    payload: LeaveApplyRequest,
    current_user: Employee = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return create_leave_request(
        db=db,
        employee_id=current_user.employee_id,
        leave_type=payload.leave_type,
        from_date=payload.from_date,
        to_date=payload.to_date,
        days=payload.days,
        reason=payload.reason,
        requester=current_user,
    )
