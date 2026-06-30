"""
SQLAlchemy engine & session factory.

If DATABASE_URL is set (e.g. postgresql://user:pass@host/db), Postgres is used.
If not set, falls back to a local SQLite file (complaints.db) — no extra deps needed.
"""
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# ── Connection URL ─────────────────────────────────────────────────────────────
_DATABASE_URL: str = os.getenv("DATABASE_URL", "")

if _DATABASE_URL:
    # Postgres (or any other full RDBMS)
    engine = create_engine(
        _DATABASE_URL,
        pool_pre_ping=True,          # detect stale connections
        pool_size=5,
        max_overflow=10,
    )
else:
    # SQLite fallback — same file the old raw-sqlite store used
    _db_path = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "complaints.db")
    )
    engine = create_engine(
        f"sqlite:///{_db_path}",
        connect_args={"check_same_thread": False},  # needed for FastAPI threading
    )

# ── Session & Base ─────────────────────────────────────────────────────────────
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    """FastAPI dependency — yields a DB session and ensures it is closed."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
