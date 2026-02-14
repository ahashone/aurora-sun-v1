"""
Tests for backup and restore service.

Test coverage:
- PostgreSQL backup/restore
- Redis backup/restore
- Neo4j backup
- Qdrant backup
- Backup cleanup
- Serialization
"""

from __future__ import annotations

import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.infra.backup import BackupResult, BackupService, BackupStatus, RestoreService

# =============================================================================
# Backup Service Tests
# =============================================================================


@pytest.fixture
def temp_backup_dir() -> Path:
    """Create temporary backup directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


def test_backup_service_init(temp_backup_dir: Path) -> None:
    """Test BackupService initialization."""
    service = BackupService(backup_dir=str(temp_backup_dir))

    assert service.backup_dir == temp_backup_dir
    assert service.retention_days == 30
    assert service.encrypt_backups is True


@pytest.mark.asyncio
async def test_backup_postgresql_success(temp_backup_dir: Path) -> None:
    """Test successful PostgreSQL backup."""
    service = BackupService(backup_dir=str(temp_backup_dir))

    mock_process = AsyncMock()
    mock_process.returncode = 0
    mock_process.communicate = AsyncMock(return_value=(b"", b""))

    with (
        patch("asyncio.create_subprocess_exec", return_value=mock_process),
        patch.object(Path, "stat") as mock_stat,
    ):
        mock_stat.return_value.st_size = 1024

        result = await service.backup_postgresql(db_url="postgresql://test")

        assert result.service == "postgresql"
        assert result.status == BackupStatus.SUCCESS
        assert result.backup_path is not None
        assert result.size_bytes == 1024


@pytest.mark.asyncio
async def test_backup_postgresql_failure(temp_backup_dir: Path) -> None:
    """Test PostgreSQL backup failure."""
    service = BackupService(backup_dir=str(temp_backup_dir))

    mock_process = AsyncMock()
    mock_process.returncode = 1
    mock_process.communicate = AsyncMock(return_value=(b"", b"Error message"))

    with patch("asyncio.create_subprocess_exec", return_value=mock_process):
        result = await service.backup_postgresql(db_url="postgresql://test")

        assert result.status == BackupStatus.FAILED
        assert result.error is not None
        assert "Error message" in result.error


@pytest.mark.asyncio
async def test_backup_redis_success(temp_backup_dir: Path) -> None:
    """Test successful Redis backup."""
    service = BackupService(backup_dir=str(temp_backup_dir))

    mock_redis_client = AsyncMock()
    mock_redis_client.save = AsyncMock()
    mock_redis_client.config_get = AsyncMock(
        side_effect=[
            {"dir": "/var/lib/redis"},
            {"dbfilename": "dump.rdb"},
        ]
    )
    mock_redis_client.close = AsyncMock()

    with (
        patch("redis.asyncio.Redis", return_value=mock_redis_client),
        patch("shutil.copy2"),
        patch.object(Path, "stat") as mock_stat,
    ):
        mock_stat.return_value.st_size = 512

        result = await service.backup_redis()

        assert result.service == "redis"
        assert result.status == BackupStatus.SUCCESS
        assert result.size_bytes == 512


@pytest.mark.asyncio
async def test_backup_neo4j_success(temp_backup_dir: Path) -> None:
    """Test successful Neo4j backup."""
    service = BackupService(backup_dir=str(temp_backup_dir))

    mock_process = AsyncMock()
    mock_process.returncode = 0
    mock_process.communicate = AsyncMock(return_value=(b"", b""))

    with (
        patch("asyncio.create_subprocess_exec", return_value=mock_process),
        patch.object(Path, "stat") as mock_stat,
    ):
        mock_stat.return_value.st_size = 2048

        result = await service.backup_neo4j()

        assert result.service == "neo4j"
        assert result.status == BackupStatus.SUCCESS
        assert result.size_bytes == 2048


@pytest.mark.asyncio
async def test_backup_qdrant_success(temp_backup_dir: Path) -> None:
    """Test successful Qdrant backup."""
    service = BackupService(backup_dir=str(temp_backup_dir))

    mock_response = MagicMock()
    mock_response.json.side_effect = [
        {"result": {"collections": [{"name": "test_collection"}]}},
        {"result": {"snapshot_id": "test-snapshot"}},
    ]
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock()

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await service.backup_qdrant()

        assert result.service == "qdrant"
        assert result.status == BackupStatus.SUCCESS
        assert result.backup_path is not None


@pytest.mark.asyncio
async def test_backup_all(temp_backup_dir: Path) -> None:
    """Test backup_all backs up all services."""
    service = BackupService(backup_dir=str(temp_backup_dir))

    # Mock all backup methods
    with (
        patch.object(service, "backup_postgresql") as mock_pg,
        patch.object(service, "backup_redis") as mock_redis,
        patch.object(service, "backup_neo4j") as mock_neo4j,
        patch.object(service, "backup_qdrant") as mock_qdrant,
    ):
        mock_pg.return_value = BackupResult(
            service="postgresql",
            status=BackupStatus.SUCCESS,
            backup_path="/path/pg.sql",
            size_bytes=1024,
            timestamp=datetime.utcnow(),
            message="OK",
        )
        mock_redis.return_value = BackupResult(
            service="redis",
            status=BackupStatus.SUCCESS,
            backup_path="/path/redis.rdb",
            size_bytes=512,
            timestamp=datetime.utcnow(),
            message="OK",
        )
        mock_neo4j.return_value = BackupResult(
            service="neo4j",
            status=BackupStatus.SUCCESS,
            backup_path="/path/neo4j.dump",
            size_bytes=2048,
            timestamp=datetime.utcnow(),
            message="OK",
        )
        mock_qdrant.return_value = BackupResult(
            service="qdrant",
            status=BackupStatus.SUCCESS,
            backup_path="/path/qdrant.json",
            size_bytes=256,
            timestamp=datetime.utcnow(),
            message="OK",
        )

        results = await service.backup_all(db_url="postgresql://test")

        assert len(results) == 4
        assert all(r.status == BackupStatus.SUCCESS for r in results)


@pytest.mark.asyncio
async def test_cleanup_old_backups(temp_backup_dir: Path) -> None:
    """Test cleanup of old backups."""
    service = BackupService(backup_dir=str(temp_backup_dir), retention_days=7)

    # Create test backup files
    old_backup = temp_backup_dir / "old_backup.sql"
    recent_backup = temp_backup_dir / "recent_backup.sql"
    old_backup.touch()
    recent_backup.touch()

    # Set old file mtime to 10 days ago
    old_time = (datetime.now() - timedelta(days=10)).timestamp()
    import os

    os.utime(old_backup, (old_time, old_time))

    deleted = await service.cleanup_old_backups()

    assert deleted == 1
    assert not old_backup.exists()
    assert recent_backup.exists()


# =============================================================================
# Restore Service Tests
# =============================================================================


@pytest.mark.asyncio
async def test_restore_postgresql_success(temp_backup_dir: Path) -> None:
    """Test successful PostgreSQL restore."""
    service = RestoreService(backup_dir=str(temp_backup_dir))

    mock_process = AsyncMock()
    mock_process.returncode = 0
    mock_process.communicate = AsyncMock(return_value=(b"", b""))

    with patch("asyncio.create_subprocess_exec", return_value=mock_process):
        result = await service.restore_postgresql(
            db_url="postgresql://test",
            backup_path="/path/backup.sql",
        )

        assert result.service == "postgresql"
        assert result.status == BackupStatus.SUCCESS


@pytest.mark.asyncio
async def test_restore_postgresql_failure(temp_backup_dir: Path) -> None:
    """Test PostgreSQL restore failure."""
    service = RestoreService(backup_dir=str(temp_backup_dir))

    mock_process = AsyncMock()
    mock_process.returncode = 1
    mock_process.communicate = AsyncMock(return_value=(b"", b"Restore failed"))

    with patch("asyncio.create_subprocess_exec", return_value=mock_process):
        result = await service.restore_postgresql(
            db_url="postgresql://test",
            backup_path="/path/backup.sql",
        )

        assert result.status == BackupStatus.FAILED
        assert result.error is not None


# =============================================================================
# Serialization Tests
# =============================================================================


def test_backup_result_to_dict() -> None:
    """Test BackupResult serialization."""
    result = BackupResult(
        service="test",
        status=BackupStatus.SUCCESS,
        backup_path="/path/backup",
        size_bytes=1024,
        timestamp=datetime(2026, 2, 14, 12, 0, 0),
        message="Test backup",
        error=None,
    )

    data = result.to_dict()

    assert data["service"] == "test"
    assert data["status"] == "success"
    assert data["backup_path"] == "/path/backup"
    assert data["size_bytes"] == 1024
    assert data["message"] == "Test backup"
    assert data["error"] is None
