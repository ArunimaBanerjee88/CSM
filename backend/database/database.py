"""Database Connection Module for Quantum City.

Configures the SQLAlchemy engine and connection pooling for the local SQLite
database. Provides the declarative base for ORM models and a dependency for
injecting database sessions into FastAPI routes.
"""

import os
from pathlib import Path
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker, Session

# Define path for SQLite database
# Ensures backend/database/quantum_city.db
DB_DIR = Path(__file__).resolve().parent
DB_DIR.mkdir(parents=True, exist_ok=True)
SQLALCHEMY_DATABASE_URL = f"sqlite:///{DB_DIR}/quantum_city.db"

# Create SQLAlchemy engine
# check_same_thread=False is needed for SQLite in FastAPI (which creates threads for requests)
engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)

# Session factory for route dependencies
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Declarative base for ORM models (models.py)
Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency to yield a database session and ensure it is safely closed."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
