"""
seed.py
-------
Populates the HR Copilot SQLite database with the assignment's reference data.

Run from the backend/ directory:
    python seed.py

Re-run safely at any time:
  - Existing records are UPDATED (merge / upsert) rather than duplicated.
  - On update, existing employee password hashes are preserved.
  - If any count or ID verification fails, an exception is raised and the
    entire transaction is rolled back so the DB is never left in an invalid state.

Data seeded
-----------
  Employees      :  6 (E001 - E006)
  Leave balances : 18 (6 employees x 3 leave types, year 2026)
  Attendance     : 14 rows (E001 x 4, E002 x 5, E004 x 5 - Oct 19-23, 2026)
  Leave requests :  3 (LR001 - LR003)
"""

import sys
import os
from datetime import date, time

import bcrypt

# ---------------------------------------------------------------------------
# Make sure "app" package is importable when running as python seed.py
# from the backend/ directory.
# ---------------------------------------------------------------------------
sys.path.insert(0, os.path.dirname(__file__))

from app.database import engine, Base, SessionLocal
from app.models import (
    Employee, LeaveBalance, Attendance, LeaveRequest,
    UserRole, LeaveType, LeaveStatus,
)


# ===========================================================================
# Helpers
# ===========================================================================

DEFAULT_PASSWORD = "Test@123"


def hash_password(plaintext: str) -> str:
    """Return a fresh bcrypt hash with a unique salt. Never store plaintext passwords."""
    return bcrypt.hashpw(plaintext.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def upsert_employee(db, data: dict, raw_password: str = DEFAULT_PASSWORD) -> tuple[Employee, str]:
    """
    Insert a new Employee with a freshly salted bcrypt hash,
    or update mutable fields of an existing one while preserving their password hash.
    Returns (employee_obj, action) where action is 'inserted' or 'updated'.
    """
    emp = db.get(Employee, data["employee_id"])
    if emp is None:
        emp_data = dict(data)
        emp_data["password_hash"] = hash_password(raw_password)
        emp = Employee(**emp_data)
        db.add(emp)
        return emp, "inserted"

    # Update mutable profile fields, preserving existing password_hash & primary key
    for key, value in data.items():
        if key not in ("employee_id", "password_hash"):
            setattr(emp, key, value)
    return emp, "updated"


def upsert_leave_balance(db, data: dict) -> tuple[LeaveBalance, str]:
    """Insert or update a LeaveBalance row (composite PK: emp_id, type, year)."""
    obj = db.get(LeaveBalance, (data["employee_id"], data["leave_type"], data["year"]))
    if obj is None:
        obj = LeaveBalance(**data)
        db.add(obj)
        return obj, "inserted"
    obj.total_days = data["total_days"]
    obj.used_days = data["used_days"]
    return obj, "updated"


def upsert_attendance(db, data: dict) -> tuple[Attendance, str]:
    """Insert or update an Attendance row (composite PK: emp_id, date)."""
    obj = db.get(Attendance, (data["employee_id"], data["date"]))
    if obj is None:
        obj = Attendance(**data)
        db.add(obj)
        return obj, "inserted"
    obj.check_in = data.get("check_in")
    obj.check_out = data.get("check_out")
    return obj, "updated"


def upsert_leave_request(db, data: dict) -> tuple[LeaveRequest, str]:
    """Insert or update a LeaveRequest row (PK: request_id)."""
    obj = db.get(LeaveRequest, data["request_id"])
    if obj is None:
        obj = LeaveRequest(**data)
        db.add(obj)
        return obj, "inserted"
    for key, value in data.items():
        if key != "request_id":
            setattr(obj, key, value)
    return obj, "updated"


# ===========================================================================
# Seed data definitions
# ===========================================================================

EMPLOYEES = [
    {
        "employee_id": "E001",
        "name": "Priya Nair",
        "email": "priya@acme.test",
        "role": UserRole.employee,
        "department": "Production",
        "shift_start": time(9, 0),
        "on_probation": False,
    },
    {
        "employee_id": "E002",
        "name": "Rahul Mehta",
        "email": "rahul@acme.test",
        "role": UserRole.employee,
        "department": "Production",
        "shift_start": time(9, 0),
        "on_probation": False,
    },
    {
        "employee_id": "E003",
        "name": "Sneha Kulkarni",
        "email": "sneha@acme.test",
        "role": UserRole.employee,
        "department": "Accounts",
        "shift_start": time(10, 0),
        "on_probation": False,
    },
    {
        "employee_id": "E004",
        "name": "Arjun Rao",
        "email": "arjun@acme.test",
        "role": UserRole.employee,
        "department": "Sales",
        "shift_start": time(9, 0),
        "on_probation": False,
    },
    {
        "employee_id": "E005",
        "name": "Fatima Shaikh",
        "email": "fatima@acme.test",
        "role": UserRole.hr_admin,
        "department": "HR",
        "shift_start": time(9, 30),
        "on_probation": False,
    },
    {
        "employee_id": "E006",
        "name": "Vikram Joshi",
        "email": "vikram@acme.test",
        "role": UserRole.employee,
        "department": "Sales",
        "shift_start": time(9, 0),
        "on_probation": True,
    },
]

# Each tuple: (employee_id, leave_type, total_days, used_days) - year 2026
_LB_RAW = [
    ("E001", LeaveType.CL, 8, 3),
    ("E001", LeaveType.SL, 6, 1),
    ("E001", LeaveType.EL, 15, 4),
    ("E002", LeaveType.CL, 8, 8),
    ("E002", LeaveType.SL, 6, 0),
    ("E002", LeaveType.EL, 15, 10),
    ("E003", LeaveType.CL, 8, 2),
    ("E003", LeaveType.SL, 6, 5),
    ("E003", LeaveType.EL, 15, 0),
    ("E004", LeaveType.CL, 8, 0),
    ("E004", LeaveType.SL, 6, 0),
    ("E004", LeaveType.EL, 15, 12),
    ("E005", LeaveType.CL, 8, 1),
    ("E005", LeaveType.SL, 6, 0),
    ("E005", LeaveType.EL, 15, 2),
    ("E006", LeaveType.CL, 8, 4),
    ("E006", LeaveType.SL, 6, 0),
    ("E006", LeaveType.EL, 0, 0),
]

LEAVE_BALANCES = [
    {
        "employee_id": emp,
        "leave_type": lt,
        "year": 2026,
        "total_days": total,
        "used_days": used,
    }
    for emp, lt, total, used in _LB_RAW
]

# Attendance records: exactly 14 records for Oct 19-23, 2026:
# - E001: 4 records (Oct 19, 20, 21, 23; Oct 22 has no attendance row)
# - E002: 5 records (Oct 19, 20, 21, 22, 23)
# - E004: 5 records (Oct 19, 20, 21 [NULL checkout / missed punch], 22, 23)
_ATT_RAW = [
    # E001 - Oct 19-23 (Oct 22 absent: no row)
    ("E001", date(2026, 10, 19), time(8, 55), time(18, 5)),
    ("E001", date(2026, 10, 20), time(9, 20), time(18, 10)),
    ("E001", date(2026, 10, 21), time(9, 10), time(18, 0)),
    ("E001", date(2026, 10, 23), time(9, 5), time(13, 30)),
    # E002 - Oct 19-23 (5 days)
    ("E002", date(2026, 10, 19), time(9, 40), time(18, 30)),
    ("E002", date(2026, 10, 20), time(9, 35), time(18, 0)),
    ("E002", date(2026, 10, 21), time(9, 16), time(18, 0)),
    ("E002", date(2026, 10, 22), time(9, 0), time(18, 0)),
    ("E002", date(2026, 10, 23), time(9, 2), time(18, 0)),
    # E004 - Oct 19-23 (5 days, Oct 21 check_out is NULL)
    ("E004", date(2026, 10, 19), time(8, 50), time(18, 0)),
    ("E004", date(2026, 10, 20), time(8, 58), time(18, 15)),
    ("E004", date(2026, 10, 21), time(9, 5), None),
    ("E004", date(2026, 10, 22), time(9, 0), time(19, 30)),
    ("E004", date(2026, 10, 23), time(8, 59), time(18, 0)),
]

ATTENDANCE = [
    {"employee_id": emp, "date": d, "check_in": ci, "check_out": co}
    for emp, d, ci, co in _ATT_RAW
]

LEAVE_REQUESTS = [
    {
        "request_id": "LR001",
        "employee_id": "E001",
        "leave_type": LeaveType.CL,
        "from_date": date(2026, 10, 22),
        "to_date": date(2026, 10, 22),
        "days": 1,
        "status": LeaveStatus.pending,
        "reason": "Family function.",
    },
    {
        "request_id": "LR002",
        "employee_id": "E003",
        "leave_type": LeaveType.SL,
        "from_date": date(2026, 10, 12),
        "to_date": date(2026, 10, 14),
        "days": 3,
        "status": LeaveStatus.approved,
        "reason": "Fever.",
    },
    {
        "request_id": "LR003",
        "employee_id": "E004",
        "leave_type": LeaveType.EL,
        "from_date": date(2026, 11, 2),
        "to_date": date(2026, 11, 6),
        "days": 5,
        "status": LeaveStatus.approved,
        "reason": "Vacation.",
    },
]

EXPECTED_EMP_IDS = ["E001", "E002", "E003", "E004", "E005", "E006"]
EXPECTED_LR_IDS = ["LR001", "LR002", "LR003"]


# ===========================================================================
# Main seeding function
# ===========================================================================

def seed():
    # Ensure all tables exist before seeding
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        print("=" * 60)
        print("  HR Copilot - Database Seeder")
        print("=" * 60)

        # -------------------------------------------------------------------
        # 1. Employees
        # -------------------------------------------------------------------
        print("\n[1/4] Seeding employees ...")
        emp_counts = {"inserted": 0, "updated": 0}
        for data in EMPLOYEES:
            _, action = upsert_employee(db, data)
            emp_counts[action] += 1
            print(f"      {action:8s}  {data['employee_id']}  {data['name']}")
        db.flush()

        # -------------------------------------------------------------------
        # 2. Leave balances
        # -------------------------------------------------------------------
        print("\n[2/4] Seeding leave balances ...")
        lb_counts = {"inserted": 0, "updated": 0}
        for data in LEAVE_BALANCES:
            _, action = upsert_leave_balance(db, data)
            lb_counts[action] += 1
            print(
                f"      {action:8s}  {data['employee_id']}  "
                f"{data['leave_type'].value}  "
                f"total={data['total_days']}  used={data['used_days']}"
            )
        db.flush()

        # -------------------------------------------------------------------
        # 3. Attendance
        # -------------------------------------------------------------------
        print("\n[3/4] Seeding attendance records ...")
        att_counts = {"inserted": 0, "updated": 0}
        for data in ATTENDANCE:
            _, action = upsert_attendance(db, data)
            att_counts[action] += 1
            co = data["check_out"].strftime("%H:%M") if data["check_out"] else "NULL"
            print(
                f"      {action:8s}  {data['employee_id']}  {data['date']}  "
                f"in={data['check_in'].strftime('%H:%M')}  out={co}"
            )
        db.flush()

        # -------------------------------------------------------------------
        # 4. Leave requests
        # -------------------------------------------------------------------
        print("\n[4/4] Seeding leave requests ...")
        lr_counts = {"inserted": 0, "updated": 0}
        for data in LEAVE_REQUESTS:
            _, action = upsert_leave_request(db, data)
            lr_counts[action] += 1
            print(
                f"      {action:8s}  {data['request_id']}  "
                f"{data['employee_id']}  {data['leave_type'].value}  "
                f"{data['status'].value}"
            )
        db.flush()

        # -------------------------------------------------------------------
        # Strict Verification (within the active transaction before commit)
        # -------------------------------------------------------------------
        from sqlalchemy import func, select

        total_emp = db.scalar(select(func.count()).select_from(Employee))
        total_lb = db.scalar(select(func.count()).select_from(LeaveBalance))
        total_att = db.scalar(select(func.count()).select_from(Attendance))
        total_lr = db.scalar(select(func.count()).select_from(LeaveRequest))

        emp_ids = [
            row[0]
            for row in db.execute(select(Employee.employee_id).order_by(Employee.employee_id)).all()
        ]
        lr_ids = [
            row[0]
            for row in db.execute(select(LeaveRequest.request_id).order_by(LeaveRequest.request_id)).all()
        ]

        print("\n" + "=" * 60)
        print("  Seeding complete - verification summary")
        print("=" * 60)
        print(f"  Employees      : {total_emp:3d}   (IDs: {', '.join(emp_ids)})")
        print(f"  Leave balances : {total_lb:3d}")
        print(f"  Attendance     : {total_att:3d}")
        print(f"  Leave requests : {total_lr:3d}   (IDs: {', '.join(lr_ids)})")
        print("=" * 60)

        # Strict checks: if any check fails, raise exception to trigger transaction rollback
        if total_emp != 6:
            raise ValueError(f"Strict verification failed: Employees count is {total_emp}, expected 6")
        if total_lb != 18:
            raise ValueError(f"Strict verification failed: Leave balances count is {total_lb}, expected 18")
        if total_att != 14:
            raise ValueError(f"Strict verification failed: Attendance count is {total_att}, expected 14")
        if total_lr != 3:
            raise ValueError(f"Strict verification failed: Leave requests count is {total_lr}, expected 3")
        if emp_ids != EXPECTED_EMP_IDS:
            raise ValueError(
                f"Strict verification failed: Employee IDs mismatch. Got {emp_ids}, expected {EXPECTED_EMP_IDS}"
            )
        if lr_ids != EXPECTED_LR_IDS:
            raise ValueError(
                f"Strict verification failed: Leave request IDs mismatch. Got {lr_ids}, expected {EXPECTED_LR_IDS}"
            )

        # Commit everything atomically only after all verifications pass
        db.commit()
        print("  All strict verification checks passed. [OK]\n")

    except Exception as exc:
        db.rollback()
        print(f"\n  ERROR during seeding - transaction rolled back.\n  {exc}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed()
