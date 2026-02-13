"""
SQLAlchemy Base for Aurora Sun V1.

This module provides the declarative base for all SQLAlchemy models.
Uses the same Base class defined in src/models/consent.py.

Usage:
    from src.models.base import Base

    class MyModel(Base):
        __tablename__ = "my_table"
        ...
"""

# Re-export Base from consent.py to maintain a single source of truth
from src.models.consent import Base

__all__ = ["Base"]
