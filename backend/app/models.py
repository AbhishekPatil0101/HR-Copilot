"""
models.py
---------
Defines all SQLAlchemy ORM models for the HR Copilot application.

Models:
  - Employee       : Core user record for all staff and HR admins.
  - LeaveBalance   : Tracks leave quota per employee, type, and year.
  - Attendance     : Daily check-in / check-out log per employee.
  - LeaveRequest   : Individual leave applications submitted by employees.

Uses SQLAlchemy 2.x typed syntax (Mapped / mapped_column).
Passwords are NEVER stored in plaintext — only a bcrypt hash is stored.
"""

import enum
from datetime import date, time
from typing import Optional, List

from sqlalchemy import (
    String,
    Integer,
    Boolean,
    Date,
    Time,
    Enum as SAEnum,
    ForeignKey,
    CheckConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


# ===========================================================================
# Enumerations
# ===========================================================================

class UserRole(str, enum.Enum):
    """Roles that determine what a user can do in the system."""
    employee = "employee"
    hr_admin = "hr_admin"


class LeaveType(str, enum.Enum):
    """
    Types of leave available to employees.
      CL  - Casual Leave
      SL  - Sick Leave
      EL  - Earned / Privileged Leave
    """
    CL = "CL"   # Casual Leave
    SL = "SL"   # Sick Leave
    EL = "EL"   # Earned / Privileged Leave


class LeaveStatus(str, enum.Enum):
    """Lifecycle states of a leave request."""
    pending  = "pending"
    approved = "approved"
    rejected = "rejected"


# ===========================================================================
# Model: Employee
# ===========================================================================

class Employee(Base):
    """
    Represents a person who uses the HR Copilot system.

    Every user — whether a regular employee or an HR administrator — has
    exactly one row in this table.  The `role` column determines access level.

    Fields
    ------
    employee_id  : Unique string identifier for the employee (e.g. "E001", "E002").
    name         : Full display name (e.g. "Priya Sharma").
    email        : Login email address; must be unique across all employees.
    password_hash: bcrypt hash of the user's password. Never store plaintext.
    role         : Either "employee" (default) or "hr_admin".
    department   : The team or department the employee belongs to
                   (e.g. "Engineering", "Finance").  Optional.
    shift_start  : The time of day the employee's shift begins (e.g. 09:00).
                   Optional; useful for attendance validation.
    on_probation : True while the employee is in their probationary period.
                   Defaults to False.
    """

    __tablename__ = "employees"

    employee_id : Mapped[str]           = mapped_column(String(10), primary_key=True)
    name        : Mapped[str]           = mapped_column(String(150), nullable=False)
    email       : Mapped[str]           = mapped_column(String(254), nullable=False, unique=True, index=True)
    password_hash: Mapped[str]          = mapped_column(String(255), nullable=False)
    role        : Mapped[UserRole]      = mapped_column(SAEnum(UserRole), nullable=False, default=UserRole.employee)
    department  : Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    shift_start : Mapped[Optional[time]]= mapped_column(Time, nullable=True)
    on_probation: Mapped[bool]          = mapped_column(Boolean, nullable=False, default=False)

    # -----------------------------------------------------------------------
    # Relationships (back-references for convenience)
    # -----------------------------------------------------------------------
    leave_balances : Mapped[List["LeaveBalance"]]  = relationship("LeaveBalance",  back_populates="employee", cascade="all, delete-orphan")
    attendances    : Mapped[List["Attendance"]]    = relationship("Attendance",    back_populates="employee", cascade="all, delete-orphan")
    leave_requests : Mapped[List["LeaveRequest"]]  = relationship("LeaveRequest",  back_populates="employee", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Employee id={self.employee_id} name={self.name!r} role={self.role}>"


# ===========================================================================
# Model: LeaveBalance
# ===========================================================================

class LeaveBalance(Base):
    """
    Tracks how many days of each leave type an employee has available
    in a given calendar year.

    Composite primary key: (employee_id, leave_type, year)
    — meaning there is exactly ONE balance row per employee, per leave type,
      per year.  For example, employee #3's SL balance for 2026.

    Fields
    ------
    employee_id : Links to the Employee this balance belongs to.
    leave_type  : One of CL, SL, or EL.
    year        : Calendar year the balance applies to (e.g. 2026).
    total_days  : The full quota granted for this leave type and year.
    used_days   : How many days have already been approved/consumed.
                  Remaining days = total_days - used_days.
    """

    __tablename__ = "leave_balances"

    employee_id : Mapped[str]       = mapped_column(String(10), ForeignKey("employees.employee_id", ondelete="CASCADE"), primary_key=True)
    leave_type  : Mapped[LeaveType] = mapped_column(SAEnum(LeaveType), primary_key=True)
    year        : Mapped[int]       = mapped_column(Integer, primary_key=True)
    total_days  : Mapped[int]       = mapped_column(Integer, nullable=False, default=0)
    used_days   : Mapped[int]       = mapped_column(Integer, nullable=False, default=0)

    # Constraint: used_days can never exceed total_days, and neither is negative
    __table_args__ = (
        CheckConstraint("total_days >= 0",              name="ck_leave_balance_total_non_negative"),
        CheckConstraint("used_days >= 0",               name="ck_leave_balance_used_non_negative"),
        CheckConstraint("used_days <= total_days",      name="ck_leave_balance_used_lte_total"),
    )

    # Relationship
    employee: Mapped["Employee"] = relationship("Employee", back_populates="leave_balances")

    def __repr__(self) -> str:
        return (
            f"<LeaveBalance emp={self.employee_id} "
            f"type={self.leave_type} year={self.year} "
            f"remaining={self.total_days - self.used_days}>"
        )


# ===========================================================================
# Model: Attendance
# ===========================================================================

class Attendance(Base):
    """
    Records daily attendance for each employee.

    Composite primary key: (employee_id, date)
    — only one record per employee per day.

    Fields
    ------
    employee_id : Links to the Employee.
    date        : The calendar date of this attendance record.
    check_in    : The time the employee clocked in. Nullable if absent or
                  if check-in hasn't happened yet.
    check_out   : The time the employee clocked out. Nullable if the
                  employee hasn't left yet or forgot to clock out.
    """

    __tablename__ = "attendance"

    employee_id : Mapped[str]           = mapped_column(String(10), ForeignKey("employees.employee_id", ondelete="CASCADE"), primary_key=True)
    date        : Mapped[date]          = mapped_column(Date, primary_key=True)
    check_in    : Mapped[Optional[time]]= mapped_column(Time, nullable=True)
    check_out   : Mapped[Optional[time]]= mapped_column(Time, nullable=True)

    # Relationship
    employee: Mapped["Employee"] = relationship("Employee", back_populates="attendances")

    def __repr__(self) -> str:
        return (
            f"<Attendance emp={self.employee_id} date={self.date} "
            f"in={self.check_in} out={self.check_out}>"
        )


# ===========================================================================
# Model: LeaveRequest
# ===========================================================================

class LeaveRequest(Base):
    """
    Represents a leave application submitted by an employee.

    An employee submits a request specifying leave type, date range, and
    reason.  An HR admin then approves or rejects it.  While it is waiting,
    its status is "pending".

    Fields
    ------
    request_id  : Unique string identifier for this application (e.g. "LR001", "LR002").
                  Assigned explicitly to match the assignment's fixed IDs.
    employee_id : The employee who submitted the request.
    leave_type  : CL, SL, or EL.
    from_date   : First day of the requested leave period (inclusive).
    to_date     : Last day of the requested leave period (inclusive).
    days        : Total number of leave days requested.  Must be > 0.
    status      : Current state — pending / approved / rejected.
    reason      : Optional free-text explanation from the employee.
    """

    __tablename__ = "leave_requests"

    request_id  : Mapped[str]           = mapped_column(String(10), primary_key=True)
    employee_id : Mapped[str]           = mapped_column(String(10), ForeignKey("employees.employee_id", ondelete="CASCADE"), nullable=False, index=True)
    leave_type  : Mapped[LeaveType]     = mapped_column(SAEnum(LeaveType), nullable=False)
    from_date   : Mapped[date]          = mapped_column(Date, nullable=False)
    to_date     : Mapped[date]          = mapped_column(Date, nullable=False)
    days        : Mapped[int]           = mapped_column(Integer, nullable=False)
    status      : Mapped[LeaveStatus]   = mapped_column(SAEnum(LeaveStatus), nullable=False, default=LeaveStatus.pending)
    reason      : Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # Constraints: dates and day count must make sense
    __table_args__ = (
        CheckConstraint("days > 0",             name="ck_leave_request_days_positive"),
        CheckConstraint("to_date >= from_date", name="ck_leave_request_date_order"),
    )

    # Relationship
    employee: Mapped["Employee"] = relationship("Employee", back_populates="leave_requests")

    def __repr__(self) -> str:
        return (
            f"<LeaveRequest id={self.request_id} emp={self.employee_id} "
            f"type={self.leave_type} status={self.status}>"
        )
