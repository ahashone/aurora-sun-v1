"""
Shared test fixtures for Aurora Sun V1.

This module provides common fixtures used across all test modules:
- Environment setup (dev mode, hash salt)
- Database session (in-memory SQLite)
- EncryptionService with test key
- CrisisService instance
- Segment contexts for all 5 segments

Usage:
    All fixtures are automatically available to any test in the tests/ directory.
    pytest discovers conftest.py files and makes their fixtures available
    to all tests in the same directory and below.
"""

from __future__ import annotations

import base64
import os

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# ---------------------------------------------------------------------------
# 1. Environment setup -- must run before any application imports
#    so that EncryptionService / HashService can fall back to dev mode.
# ---------------------------------------------------------------------------

os.environ.setdefault("AURORA_DEV_MODE", "1")
os.environ.setdefault(
    "AURORA_HASH_SALT",
    base64.b64encode(b"test-salt-for-hashing-32bytes!!").decode(),
)

# ---------------------------------------------------------------------------
# Application imports (after env vars are set)
# ---------------------------------------------------------------------------

from src.core.segment_context import SegmentContext  # noqa: E402
from src.lib.encryption import EncryptionService  # noqa: E402
from src.models.base import Base  # noqa: E402
from src.models.consent import ConsentRecord  # noqa: E402, F401
from src.models.daily_plan import DailyPlan  # noqa: E402, F401
from src.models.goal import Goal  # noqa: E402, F401
from src.models.neurostate import (  # noqa: E402, F401
    BurnoutAssessment,
    ChannelState,
    EnergyLevelRecord,
    InertiaEvent,
    MaskingLog,
    SensoryProfile,
)
from src.models.session import Session  # noqa: E402, F401
from src.models.task import Task  # noqa: E402, F401

# Import ALL models so that they are registered with Base.metadata before
# create_all is called.  The Session model's ``metadata`` column was renamed
# to ``session_metadata`` (Python attr) to resolve the DeclarativeBase
# reserved-attribute conflict.
from src.models.user import User  # noqa: E402, F401
from src.models.vision import Vision  # noqa: E402, F401
from src.modules.capture import CapturedContent  # noqa: E402, F401
from src.services.crisis_service import CrisisService  # noqa: E402

# ---------------------------------------------------------------------------
# 2. db_session -- in-memory SQLite session for unit tests
# ---------------------------------------------------------------------------

@pytest.fixture()
def db_session():
    """
    Provide a SQLAlchemy session backed by an in-memory SQLite database.

    A fresh database is created for every test that requests this fixture.
    All tables registered with Base.metadata are created automatically.
    The session is closed and the engine disposed after the test finishes.
    """
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    TestingSession = sessionmaker(bind=engine)
    session = TestingSession()

    yield session

    session.close()
    engine.dispose()


# ---------------------------------------------------------------------------
# 3. encryption_service -- EncryptionService with a deterministic test key
# ---------------------------------------------------------------------------

@pytest.fixture()
def encryption_service():
    """
    Provide an ``EncryptionService`` initialised with a fixed test master key.

    The key is deterministic so that tests are reproducible, but it is
    NOT used in production.  ``AURORA_DEV_MODE=1`` is already set in the
    environment by the module-level setup above.
    """
    test_master_key = b"test-master-key-for-aurora-sun!!"  # exactly 32 bytes
    return EncryptionService(master_key=test_master_key)


# ---------------------------------------------------------------------------
# 4. crisis_service -- CrisisService wired to the test EncryptionService
# ---------------------------------------------------------------------------

@pytest.fixture()
def crisis_service(encryption_service):
    """
    Provide a ``CrisisService`` backed by the test ``EncryptionService``.
    """
    return CrisisService(encryption_service=encryption_service)


# ---------------------------------------------------------------------------
# 5. segment_contexts -- dict of all 5 pre-built SegmentContext objects
# ---------------------------------------------------------------------------

@pytest.fixture()
def segment_contexts():
    """
    Provide a dictionary mapping each working-style code to its
    ``SegmentContext``.

    Keys: ``"AD"``, ``"AU"``, ``"AH"``, ``"NT"``, ``"CU"``

    Example usage in a test::

        def test_adhd_sprint(segment_contexts):
            ctx = segment_contexts["AD"]
            assert ctx.core.sprint_minutes == 25
    """
    return {
        code: SegmentContext.from_code(code)
        for code in ("AD", "AU", "AH", "NT", "CU")
    }
