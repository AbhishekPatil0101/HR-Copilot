"""
security.py
-----------
Security and authentication utilities for HR Copilot.
Handles JWT token generation and verification (HS256, 30 min expiry),
password hashing/verification with bcrypt, loading JWT_SECRET_KEY
from the root .env, validating tokens, and role-based access control.
"""

import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional, List, Callable, Union

import bcrypt
from dotenv import load_dotenv
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Employee, UserRole


# ---------------------------------------------------------------------------
# Load root .env
# ---------------------------------------------------------------------------
# Path to workspace root .env file:
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
ROOT_ENV_PATH = ROOT_DIR / ".env"

if ROOT_ENV_PATH.is_file():
    load_dotenv(dotenv_path=ROOT_ENV_PATH, override=True)
else:
    load_dotenv()


# ---------------------------------------------------------------------------
# Security Configuration
# ---------------------------------------------------------------------------
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

INSECURE_PLACEHOLDER_SECRETS = {
    "",
    "your-secret-key-here",
    "your_jwt_secret_key",
    "your-jwt-secret-key",
    "placeholder",
    "changeme",
    "secret",
    "secretkey",
    "test",
    "admin",
    "default",
}


def get_jwt_secret_key() -> str:
    """
    Retrieve JWT_SECRET_KEY from environment.
    Strictly rejects missing, empty, or placeholder secret keys.
    """
    # Re-check in case .env was populated or updated
    if ROOT_ENV_PATH.is_file():
        load_dotenv(dotenv_path=ROOT_ENV_PATH, override=False)

    key = os.getenv("JWT_SECRET_KEY", "").strip()
    if not key or key.lower() in INSECURE_PLACEHOLDER_SECRETS or len(key) < 32:
        raise RuntimeError(
            "JWT_SECRET_KEY is missing, empty, or using an insecure placeholder. "
            "Please configure a secure JWT_SECRET_KEY (at least 32 characters) in the root .env file."
        )
    return key


# ---------------------------------------------------------------------------
# Password utilities (bcrypt)
# ---------------------------------------------------------------------------

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain password against a bcrypt hash."""
    if not plain_password or not hashed_password:
        return False
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            hashed_password.encode("utf-8"),
        )
    except Exception:
        return False


def get_password_hash(password: str) -> str:
    """Generate a bcrypt hash with a fresh salt."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


# ---------------------------------------------------------------------------
# JWT Token generation and verification
# ---------------------------------------------------------------------------

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create a signed JWT access token with 30-minute default expiration."""
    to_encode = data.copy()
    now = datetime.now(timezone.utc)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire, "iat": now})
    secret_key = get_jwt_secret_key()
    return jwt.encode(to_encode, secret_key, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict:
    """
    Decode and validate a JWT access token.
    Raises HTTPException(401) on missing, expired, or invalid tokens.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired authentication token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        secret_key = get_jwt_secret_key()
        payload = jwt.decode(token, secret_key, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        raise credentials_exception


# ---------------------------------------------------------------------------
# Current User Dependency
# ---------------------------------------------------------------------------

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)


def get_current_user(
    token: Optional[str] = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> Employee:
    """
    Validate the bearer token and retrieve the employee from the SQLite database.
    Rejects missing, invalid, or expired tokens.
    Never trusts frontend claims - always fetches employee record from the DB.
    """
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = decode_access_token(token)
    employee_id: Optional[str] = payload.get("sub")
    if not employee_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token payload missing subject identifier",
            headers={"WWW-Authenticate": "Bearer"},
        )

    employee = db.get(Employee, employee_id)
    if employee is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return employee


# ---------------------------------------------------------------------------
# Role-based Authorization
# ---------------------------------------------------------------------------

def require_roles(*allowed_roles: Union[UserRole, str]) -> Callable:
    """
    Dependency factory to enforce role-based access control.
    Authorizes the user based strictly on their database role (never client-supplied).
    Raises HTTPException(403) if the user role is not permitted.
    """
    normalized_allowed = {
        r.value if isinstance(r, UserRole) else str(r)
        for r in allowed_roles
    }

    def role_checker(current_user: Employee = Depends(get_current_user)) -> Employee:
        user_role_val = (
            current_user.role.value
            if isinstance(current_user.role, UserRole)
            else str(current_user.role)
        )
        if user_role_val not in normalized_allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Forbidden: role '{user_role_val}' has insufficient permissions",
            )
        return current_user

    return role_checker


def require_role(role: Union[UserRole, str]) -> Callable:
    """Convenience helper for requiring a single role."""
    return require_roles(role)
