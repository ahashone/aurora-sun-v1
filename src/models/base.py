"""
SQLAlchemy Base for Aurora Sun V1.

This module provides the single declarative base for all SQLAlchemy models.

Usage:
    from src.models.base import Base

    class MyModel(Base):
        __tablename__ = "my_table"
        ...
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """SQLAlchemy declarative base for Aurora Sun V1 models."""

    pass


__all__ = ["Base"]
