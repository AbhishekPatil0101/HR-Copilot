"""
mcp_server.py
-------------
Official Model Context Protocol (MCP) server for HR Copilot using mcp 2.x (MCPServer).

Exposes:
  Tools:
    - get_leave_balance(employee_id, requester_id="E001", year=2026)
    - get_attendance_summary(employee_id, requester_id="E005", from_date="2026-10-19", to_date="2026-10-23")
  Resources:
    - policy://leave       -> Policy 1: Leave Policy
    - policy://attendance  -> Policy 2: Attendance Policy
    - policy://wfh         -> Policy 3: Work From Home Policy

Run with stdio transport (for Claude Desktop or MCP Inspector):
    python mcp_server.py
Or with MCP Inspector:
    npx @modelcontextprotocol/inspector python mcp_server.py
"""

import json
import os
import sys
from datetime import date
from pathlib import Path
from typing import Optional

from mcp.server.mcpserver import MCPServer

# Ensure backend/ is on sys.path so app.* imports resolve from any cwd
BACKEND_DIR = Path(__file__).resolve().parent
ROOT_DIR = BACKEND_DIR.parent
POLICIES_DIR = ROOT_DIR / "policies"

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.database import SessionLocal
from app.models import Employee
from app.services.hr_service import (
    calculate_attendance_summary,
    get_employee_leave_balances,
)

mcp = MCPServer("HR Copilot MCP Server")


def _get_requester(db, requester_id: str) -> Employee:
    emp = db.get(Employee, requester_id.strip().upper())
    if not emp:
        raise ValueError(f"Requester employee '{requester_id}' not found in database.")
    return emp


# ===========================================================================
# MCP Tools (reusing shared hr_service.py so role checks live in one place)
# ===========================================================================

@mcp.tool()
def get_leave_balance(
    employee_id: str = "E001",
    requester_id: str = "E001",
    year: int = 2026,
) -> str:
    """
    Get leave balances (CL, SL, EL) and pending requests for an employee.
    Enforces role-based access: regular employees can only query themselves;
    hr_admin (e.g. E005) can query any employee.
    """
    db = SessionLocal()
    try:
        requester = _get_requester(db, requester_id)
        result = get_employee_leave_balances(
            db=db,
            employee_id=employee_id.strip().upper(),
            requester=requester,
            year=year,
        )
        return json.dumps(result, indent=2)
    except Exception as exc:
        detail = getattr(exc, "detail", str(exc))
        return json.dumps({"error": detail})
    finally:
        db.close()


@mcp.tool()
def get_attendance_summary(
    employee_id: str = "E001",
    requester_id: str = "E005",
    from_date: Optional[str] = "2026-10-19",
    to_date: Optional[str] = "2026-10-23",
) -> str:
    """
    Get attendance summary (full/half days, late marks, missed punches, overtime)
    for an employee. Enforces role-based access: regular employees can only
    view their own attendance; hr_admin (e.g. E005) can view anyone's.
    """
    db = SessionLocal()
    try:
        requester = _get_requester(db, requester_id)
        from_d = date.fromisoformat(from_date) if from_date else None
        to_d = date.fromisoformat(to_date) if to_date else None
        result = calculate_attendance_summary(
            db=db,
            employee_id=employee_id.strip().upper(),
            requester=requester,
            from_date=from_d,
            to_date=to_d,
        )
        return json.dumps(result, indent=2)
    except Exception as exc:
        detail = getattr(exc, "detail", str(exc))
        return json.dumps({"error": detail})
    finally:
        db.close()


# ===========================================================================
# MCP Resources (Company HR Policy Documents)
# ===========================================================================

@mcp.resource("policy://leave")
def read_leave_policy() -> str:
    """Policy 1: Leave Policy (CL, SL, EL quotas, notice periods, carry-forward, sandwich rule)."""
    return (POLICIES_DIR / "leave_policy.md").read_text(encoding="utf-8")


@mcp.resource("policy://attendance")
def read_attendance_policy() -> str:
    """Policy 2: Attendance Policy (shift grace time, late marks, working hours, missed punch, overtime)."""
    return (POLICIES_DIR / "attendance_policy.md").read_text(encoding="utf-8")


@mcp.resource("policy://wfh")
def read_wfh_policy() -> str:
    """Policy 3: Work From Home Policy (eligibility, monthly limits, availability, holidays)."""
    return (POLICIES_DIR / "wfh_policy.md").read_text(encoding="utf-8")


if __name__ == "__main__":
    mcp.run()
