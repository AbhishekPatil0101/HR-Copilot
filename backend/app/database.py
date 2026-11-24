"""
database.py
-----------
Configures the SQLite database connection using SQLAlchemy 2.x.
Provides the declarative Base, engine, session factory, and
the get_db() dependency for FastAPI route injection.
"""

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, DeclarativeBase


# ---------------------------------------------------------------------------
# Database URL
# ---------------------------------------------------------------------------
# SQLite stores data in a single file at the project root (backend/).
# The three slashes after "sqlite:" mean a relative path; use four slashes
# for an absolute path (e.g. "sqlite:////absolute/path/to/hr_copilot.db").
DATABASE_URL = "sqlite:///./hr_copilot.db"


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------
# `check_same_thread=False` is required for SQLite when used with FastAPI
# because FastAPI can handle a request across multiple threads.
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
    echo=False,          # Set True to log all SQL statements during development
)


# ---------------------------------------------------------------------------
# Enable foreign key constraints for SQLite
# ---------------------------------------------------------------------------
# SQLite does NOT enforce foreign keys by default.
# This event listener runs PRAGMA foreign_keys = ON for every new connection,
# ensuring referential integrity is enforced at the database level.
@event.listens_for(engine, "connect")
def enable_foreign_keys(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys = ON")
    cursor.close()


# ---------------------------------------------------------------------------
# Session factory
# ---------------------------------------------------------------------------
# autocommit=False  → we control when to commit (explicit transactions)
# autoflush=False   → we control when SQLAlchemy syncs pending changes to DB
SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
)


# ---------------------------------------------------------------------------
# Declarative Base
# ---------------------------------------------------------------------------
# All ORM models will inherit from this Base so SQLAlchemy knows about them.
class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# FastAPI dependency: get_db()
# ---------------------------------------------------------------------------
def get_db():
    """
    Yield a database session for use in a FastAPI route, then close it.

    Usage in a route:
        from app.database import get_db
        from sqlalchemy.orm import Session
        from fastapi import Depends

        @router.get("/example")
        def example(db: Session = Depends(get_db)):
            ...
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
