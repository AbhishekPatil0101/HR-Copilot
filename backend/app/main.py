from fastapi import FastAPI, Depends

from app.models import Employee, UserRole
from app.routers import auth
from app.security import get_current_user

app = FastAPI(
    title="HR Copilot API",
    description="AI-powered Human Resource Management System",
    version="1.0.0"
)

# Register routers
app.include_router(auth.router)


@app.get("/")
def home():
    return {
        "message": "Welcome to HR Copilot API",
        "status": "running"
    }


@app.get("/health")
def health_check():
    return {
        "status": "healthy"
    }


@app.get("/me", tags=["Users"])
def get_current_user_profile(current_user: Employee = Depends(get_current_user)):
    """
    Protected endpoint returning the profile of the currently logged-in employee.
    Requires a valid JWT Bearer token in the Authorization header.
    Never exposes password_hash.
    """
    role_str = (
        current_user.role.value
        if isinstance(current_user.role, UserRole)
        else str(current_user.role)
    )
    shift_str = (
        current_user.shift_start.isoformat()
        if current_user.shift_start
        else None
    )
    return {
        "id": current_user.employee_id,
        "employee_id": current_user.employee_id,
        "name": current_user.name,
        "email": current_user.email,
        "role": role_str,
        "department": current_user.department,
        "shift_start": shift_str,
        "on_probation": current_user.on_probation,
    }
