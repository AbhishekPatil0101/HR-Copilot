"""
routers/auth.py
---------------
Authentication router for HR Copilot.
Handles user login, credential verification using bcrypt,
and JWT access token issuance.
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Employee, UserRole
from app.security import create_access_token, verify_password


router = APIRouter(prefix="/auth", tags=["Authentication"])


# ---------------------------------------------------------------------------
# Pydantic Schemas
# ---------------------------------------------------------------------------

class LoginRequest(BaseModel):
    """Payload for user login."""
    email: str
    password: str


class EmployeeDetails(BaseModel):
    """Public employee profile information. Never includes password_hash."""
    id: str
    employee_id: str
    name: str
    email: str
    role: str
    department: Optional[str] = None
    shift_start: Optional[str] = None
    on_probation: Optional[bool] = None


class LoginResponse(BaseModel):
    """Response returned upon successful authentication."""
    access_token: str
    token_type: str = "bearer"
    employee: EmployeeDetails
    # Convenience top-level fields
    id: str
    employee_id: str
    name: str
    email: str
    role: str
    department: Optional[str] = None


# ---------------------------------------------------------------------------
# POST /auth/login
# ---------------------------------------------------------------------------

@router.post(
    "/login",
    response_model=LoginResponse,
    summary="User Login",
    description="Authenticate an employee with email and password, returning a JWT access token.",
)
def login(credentials: LoginRequest, db: Session = Depends(get_db)):
    """
    Authenticate employee and return JWT access token with public details.
    Returns HTTP 401 for invalid email or password.
    Never exposes password_hash.
    """
    email_clean = credentials.email.strip().lower()
    
    # Query employee by email
    stmt = select(Employee).where(Employee.email == email_clean)
    employee = db.scalar(stmt)

    # Constant-time style failure if user not found or password incorrect
    if not employee or not verify_password(credentials.password, employee.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Generate JWT with employee_id as subject ('sub')
    role_str = employee.role.value if isinstance(employee.role, UserRole) else str(employee.role)
    access_token = create_access_token(
        data={
            "sub": employee.employee_id,
            "email": employee.email,
        }
    )

    shift_str = employee.shift_start.isoformat() if employee.shift_start else None

    emp_details = EmployeeDetails(
        id=employee.employee_id,
        employee_id=employee.employee_id,
        name=employee.name,
        email=employee.email,
        role=role_str,
        department=employee.department,
        shift_start=shift_str,
        on_probation=employee.on_probation,
    )

    return LoginResponse(
        access_token=access_token,
        token_type="bearer",
        employee=emp_details,
        id=employee.employee_id,
        employee_id=employee.employee_id,
        name=employee.name,
        email=employee.email,
        role=role_str,
        department=employee.department,
    )
