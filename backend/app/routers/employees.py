"""
routers/employees.py
--------------------
Endpoints for HR Administration:
- GET /employees/{employee_id}/attendance-summary (hr_admin only)
"""

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Employee, UserRole
from app.security import require_role
from app.services.hr_service import calculate_attendance_summary


router = APIRouter(prefix="/employees", tags=["Employees (HR Admin)"])


@router.get(
    "/{employee_id}/attendance-summary",
    summary="Get Employee Attendance Summary",
    description="HR Admin only. Computes full days, half days, late marks, missed punches, and overtime.",
)
def get_attendance_summary_endpoint(
    employee_id: str,
    from_date: Optional[date] = Query(None, alias="from", description="Start date (YYYY-MM-DD)"),
    to_date: Optional[date] = Query(None, alias="to", description="End date (YYYY-MM-DD)"),
    # Enforces hr_admin role at endpoint level
    current_admin: Employee = Depends(require_role(UserRole.hr_admin)),
    db: Session = Depends(get_db),
):
    return calculate_attendance_summary(
        db=db,
        employee_id=employee_id,
        requester=current_admin,
        from_date=from_date,
        to_date=to_date,
    )
