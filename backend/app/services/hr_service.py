"""
services/hr_service.py
----------------------
Core HR business logic shared across:
1. REST API endpoints
2. AI Assistant tool calls (Part 2)
3. Model Context Protocol (MCP) server (Part 4)

This ensures role verification, attendance calculations, and leave rules
are implemented once in a single location as required by the specification.
"""

from datetime import date, datetime, time, timedelta
from typing import Dict, List, Optional, Tuple, Union

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    Attendance,
    Employee,
    LeaveBalance,
    LeaveRequest,
    LeaveStatus,
    LeaveType,
    UserRole,
)


# ===========================================================================
# Permission & Access Control Helpers
# ===========================================================================

def verify_employee_access(
    target_employee_id: str,
    requester: Employee,
) -> None:
    """
    Ensure the requester has permission to view/modify the target employee's data.
    - An employee may only access their own data.
    - An hr_admin may access any employee's data.
    Raises HTTPException(403) if unauthorized.
    """
    requester_role = (
        requester.role.value
        if isinstance(requester.role, UserRole)
        else str(requester.role)
    )
    if requester_role != UserRole.hr_admin.value and requester.employee_id != target_employee_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Access denied: You do not have permission to view or manage data for employee {target_employee_id}.",
        )


# ===========================================================================
# 1. Leave Balance Service
# ===========================================================================

def get_employee_leave_balances(
    db: Session,
    employee_id: str,
    requester: Employee,
    year: int = 2026,
) -> Dict:
    """
    Retrieve leave balances for an employee for a specific year.
    Enforces role-based permissions (self or hr_admin).
    """
    verify_employee_access(employee_id, requester)

    employee = db.get(Employee, employee_id)
    if not employee:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Employee '{employee_id}' not found.",
        )

    stmt = (
        select(LeaveBalance)
        .where(
            LeaveBalance.employee_id == employee_id,
            LeaveBalance.year == year,
        )
        .order_by(LeaveBalance.leave_type)
    )
    balances = db.scalars(stmt).all()

    balance_dict = {}
    for b in balances:
        lt_val = b.leave_type.value if isinstance(b.leave_type, LeaveType) else str(b.leave_type)
        balance_dict[lt_val] = {
            "leave_type": lt_val,
            "year": b.year,
            "total_days": b.total_days,
            "used_days": b.used_days,
            "remaining_days": b.total_days - b.used_days,
        }

    # Also check pending leave requests for this employee in this year
    pending_stmt = select(LeaveRequest).where(
        LeaveRequest.employee_id == employee_id,
        LeaveRequest.status == LeaveStatus.pending,
    )
    pending_requests = db.scalars(pending_stmt).all()
    pending_list = [
        {
            "request_id": r.request_id,
            "leave_type": r.leave_type.value if isinstance(r.leave_type, LeaveType) else str(r.leave_type),
            "from_date": r.from_date.isoformat(),
            "to_date": r.to_date.isoformat(),
            "days": r.days,
            "reason": r.reason,
            "status": "pending",
        }
        for r in pending_requests
    ]

    return {
        "employee_id": employee.employee_id,
        "name": employee.name,
        "year": year,
        "balances": balance_dict,
        "pending_requests": pending_list,
    }


# ===========================================================================
# 2. Attendance Service & Detailed Calculations
# ===========================================================================

def parse_time_delta(t_start: time, t_end: time) -> timedelta:
    """Calculate timedelta between two time objects assuming same day."""
    dt_start = datetime.combine(date.min, t_start)
    dt_end = datetime.combine(date.min, t_end)
    return dt_end - dt_start


def get_employee_attendance(
    db: Session,
    employee_id: str,
    requester: Employee,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
) -> List[Dict]:
    """
    Retrieve raw attendance records for an employee within an optional date range.
    Enforces role-based permissions (self or hr_admin).
    """
    verify_employee_access(employee_id, requester)

    employee = db.get(Employee, employee_id)
    if not employee:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Employee '{employee_id}' not found.",
        )

    if from_date and to_date and from_date > to_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="from_date cannot be later than to_date.",
        )

    stmt = select(Attendance).where(Attendance.employee_id == employee_id)
    if from_date:
        stmt = stmt.where(Attendance.date >= from_date)
    if to_date:
        stmt = stmt.where(Attendance.date <= to_date)
    stmt = stmt.order_by(Attendance.date)

    records = db.scalars(stmt).all()
    return [
        {
            "employee_id": r.employee_id,
            "date": r.date.isoformat(),
            "check_in": r.check_in.strftime("%H:%M") if r.check_in else None,
            "check_out": r.check_out.strftime("%H:%M") if r.check_out else None,
        }
        for r in records
    ]


def calculate_attendance_summary(
    db: Session,
    employee_id: str,
    requester: Employee,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
) -> Dict:
    """
    Compute attendance summary conforming to Company Policy 2:
    - Shift grace: check-in > 15 mins after shift_start is a late mark.
    - Working hours: >= 8h is full day; 4h to <8h is half day; <4h is absence.
    - Missed punch: check_in without check_out.
    - Overtime: time worked beyond 9h on working day.
    """
    verify_employee_access(employee_id, requester)

    employee = db.get(Employee, employee_id)
    if not employee:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Employee '{employee_id}' not found.",
        )

    if from_date and to_date and from_date > to_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="from_date cannot be later than to_date.",
        )

    # Default to the week of Oct 19 to 23, 2026 if no dates specified
    effective_from = from_date or date(2026, 10, 19)
    effective_to = to_date or date(2026, 10, 23)

    # Fetch attendance
    att_stmt = (
        select(Attendance)
        .where(
            Attendance.employee_id == employee_id,
            Attendance.date >= effective_from,
            Attendance.date <= effective_to,
        )
        .order_by(Attendance.date)
    )
    records = db.scalars(att_stmt).all()

    # Fetch leaves within range
    leave_stmt = select(LeaveRequest).where(
        LeaveRequest.employee_id == employee_id,
        LeaveRequest.from_date <= effective_to,
        LeaveRequest.to_date >= effective_from,
    )
    leave_requests = db.scalars(leave_stmt).all()
    leave_by_date = {}
    for lr in leave_requests:
        curr = lr.from_date
        while curr <= lr.to_date:
            leave_by_date[curr] = lr
            curr += timedelta(days=1)

    shift_start = employee.shift_start or time(9, 0)
    grace_cutoff = (
        datetime.combine(date.min, shift_start) + timedelta(minutes=15)
    ).time()

    total_days_worked = 0
    full_days = 0
    half_days = 0
    late_marks = 0
    missed_punches = 0
    total_overtime_minutes = 0
    daily_details = []

    # Map attendance by date
    att_by_date = {r.date: r for r in records}

    curr_d = effective_from
    while curr_d <= effective_to:
        # Skip weekends (5=Saturday, 6=Sunday)
        if curr_d.weekday() >= 5:
            curr_d += timedelta(days=1)
            continue

        att = att_by_date.get(curr_d)
        leave = leave_by_date.get(curr_d)

        day_info = {
            "date": curr_d.isoformat(),
            "check_in": None,
            "check_out": None,
            "hours_worked": 0.0,
            "hours_worked_formatted": "0h 0m",
            "status": "absent",
            "is_late": False,
            "is_missed_punch": False,
            "overtime_minutes": 0,
            "overtime_formatted": "0h 0m",
            "leave_status": None,
        }

        if leave:
            l_status = leave.status.value if isinstance(leave.status, LeaveStatus) else str(leave.status)
            l_type = leave.leave_type.value if isinstance(leave.leave_type, LeaveType) else str(leave.leave_type)
            day_info["leave_status"] = f"{l_status} {l_type} leave"

        if att:
            day_info["check_in"] = att.check_in.strftime("%H:%M") if att.check_in else None
            day_info["check_out"] = att.check_out.strftime("%H:%M") if att.check_out else None

            # Check late mark: check-in > 15 mins after shift_start
            if att.check_in and att.check_in > grace_cutoff:
                day_info["is_late"] = True
                late_marks += 1

            if att.check_in and not att.check_out:
                day_info["is_missed_punch"] = True
                day_info["status"] = "missed_punch"
                missed_punches += 1
            elif att.check_in and att.check_out:
                total_days_worked += 1
                worked_delta = parse_time_delta(att.check_in, att.check_out)
                total_seconds = max(0, int(worked_delta.total_seconds()))
                hours = total_seconds // 3600
                minutes = (total_seconds % 3600) // 60
                hours_decimal = round(total_seconds / 3600.0, 2)

                day_info["hours_worked"] = hours_decimal
                day_info["hours_worked_formatted"] = f"{hours}h {minutes}m"

                # Check Policy 2: 8h+ is full day, 4h-<8h is half day
                if hours_decimal >= 8.0:
                    day_info["status"] = "full_day"
                    full_days += 1
                elif hours_decimal >= 4.0:
                    day_info["status"] = "half_day"
                    half_days += 1
                else:
                    day_info["status"] = "absent"

                # Check Policy 2: Overtime beyond 9 hours
                nine_hours_seconds = 9 * 3600
                if total_seconds > nine_hours_seconds:
                    ot_seconds = total_seconds - nine_hours_seconds
                    ot_mins = ot_seconds // 60
                    ot_h = ot_mins // 60
                    ot_m = ot_mins % 60
                    day_info["overtime_minutes"] = ot_mins
                    day_info["overtime_formatted"] = f"{ot_h}h {ot_m}m"
                    total_overtime_minutes += ot_mins
        else:
            if leave:
                day_info["status"] = f"leave_{leave.status.value if isinstance(leave.status, LeaveStatus) else leave.status}"
            else:
                day_info["status"] = "absent"

        daily_details.append(day_info)
        curr_d += timedelta(days=1)

    ot_hours_total = total_overtime_minutes // 60
    ot_mins_total = total_overtime_minutes % 60

    # Policy 2 s2: Every 3 late marks deduct 0.5 CL
    late_deductions_count = late_marks // 3
    cl_deduction_days = late_deductions_count * 0.5

    return {
        "employee_id": employee.employee_id,
        "name": employee.name,
        "shift_start": shift_start.strftime("%H:%M"),
        "period": {
            "from_date": effective_from.isoformat(),
            "to_date": effective_to.isoformat(),
        },
        "summary": {
            "total_days_worked": total_days_worked,
            "full_days": full_days,
            "half_days": half_days,
            "late_marks": late_marks,
            "late_marks_rule": "Every 3 late marks in a month deduct 0.5 CL (or 0.5 day pay if 0 CL)",
            "leave_deduction_from_late_marks": cl_deduction_days,
            "missed_punches": missed_punches,
            "total_overtime_minutes": total_overtime_minutes,
            "total_overtime_formatted": f"{ot_hours_total}h {ot_mins_total}m",
        },
        "daily_breakdown": daily_details,
    }


# ===========================================================================
# 3. Apply Leave Request Service
# ===========================================================================

def generate_next_leave_request_id(db: Session) -> str:
    """Generate sequential ID like 'LR004'."""
    stmt = select(LeaveRequest.request_id).order_by(LeaveRequest.request_id.desc())
    existing_ids = db.scalars(stmt).all()
    max_num = 0
    for req_id in existing_ids:
        if req_id.startswith("LR"):
            try:
                num = int(req_id[2:])
                if num > max_num:
                    max_num = num
            except ValueError:
                pass
    return f"LR{max_num + 1:03d}"


def create_leave_request(
    db: Session,
    employee_id: str,
    leave_type: str,
    from_date: date,
    to_date: date,
    days: int,
    reason: Optional[str],
    requester: Employee,
) -> Dict:
    """
    Create a leave application with business validation:
    - Enforces self-application or hr_admin authorization.
    - Dates must be valid (to_date >= from_date).
    - Days must be > 0.
    - Validates leave_type enum (CL, SL, EL).
    - Checks probation status (Probationers not eligible for EL).
    - Validates sufficient remaining leave balance in DB.
    """
    verify_employee_access(employee_id, requester)

    employee = db.get(Employee, employee_id)
    if not employee:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Employee '{employee_id}' not found.",
        )

    # Validate leave type
    try:
        lt_enum = LeaveType[leave_type.upper()]
    except KeyError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid leave type '{leave_type}'. Allowed types are: CL, SL, EL.",
        )

    # Validate dates
    if to_date < from_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="to_date cannot be earlier than from_date.",
        )
    if days <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Leave days must be greater than 0.",
        )

    # Policy 1 check: Probation eligibility
    if employee.on_probation and lt_enum == LeaveType.EL:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Employees on probation are eligible for Casual Leave (CL) and Sick Leave (SL) only. Earned Leave (EL) is not permitted.",
        )

    # Check leave balance in database
    year = from_date.year
    lb_stmt = select(LeaveBalance).where(
        LeaveBalance.employee_id == employee_id,
        LeaveBalance.leave_type == lt_enum,
        LeaveBalance.year == year,
    )
    lb = db.scalar(lb_stmt)
    if not lb:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"No leave balance record found for employee '{employee_id}' and leave type '{lt_enum.value}' in year {year}.",
        )

    remaining = lb.total_days - lb.used_days
    if remaining < days:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Insufficient leave balance. You have {remaining} days of {lt_enum.value} remaining, but requested {days} days.",
        )

    # Create record
    new_request_id = generate_next_leave_request_id(db)
    new_leave = LeaveRequest(
        request_id=new_request_id,
        employee_id=employee_id,
        leave_type=lt_enum,
        from_date=from_date,
        to_date=to_date,
        days=days,
        status=LeaveStatus.pending,
        reason=reason,
    )

    db.add(new_leave)
    db.commit()
    db.refresh(new_leave)

    return {
        "request_id": new_leave.request_id,
        "employee_id": new_leave.employee_id,
        "leave_type": new_leave.leave_type.value,
        "from_date": new_leave.from_date.isoformat(),
        "to_date": new_leave.to_date.isoformat(),
        "days": new_leave.days,
        "status": new_leave.status.value,
        "reason": new_leave.reason,
    }
