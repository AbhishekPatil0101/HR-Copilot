from pathlib import Path

from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from app.models import Employee, UserRole
from app.routers import auth, me, employees, policies, chat
from app.security import get_current_user

UI_HTML_PATH = Path(__file__).resolve().parent / "static" / "ui.html"

app = FastAPI(
    title="HR Copilot API",
    description="AI-powered Human Resource Management System",
    version="1.0.0"
)

# Enable CORS for local React frontend development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(auth.router)
app.include_router(me.router)
app.include_router(employees.router)
app.include_router(policies.router)
app.include_router(chat.router)


@app.get("/ui", include_in_schema=False)
def serve_ui():
    """Serve the zero-build React Chat UI directly from FastAPI."""
    return FileResponse(UI_HTML_PATH)


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
