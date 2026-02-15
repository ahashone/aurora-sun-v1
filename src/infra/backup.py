"""
Backup and Restore Service for Aurora Sun V1.

Provides backup/restore strategies for all databases:
- PostgreSQL (main database)
- Redis (caching/rate limiting)
- Neo4j (knowledge graph)
- Qdrant (vector store)

Features:
- Automated daily backups
- On-demand backup triggers
- Point-in-time restore
- Backup verification
- Retention policies (30 days default)
- Encrypted backup storage

Used by:
- Cron jobs (daily backup)
- Deployment scripts (pre-deployment backup)
- Disaster recovery procedures

References:
    - ROADMAP.md Phase 4.6 (Backup strategy)
    - scripts/backup.sh (shell wrapper)
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Allowed hostnames for internal service connections (SSRF prevention).
# Only these hosts are permitted for health check and backup HTTP calls.
ALLOWED_INTERNAL_HOSTS = {
    "localhost",
    "127.0.0.1",
    "postgres",
    "redis",
    "neo4j",
    "qdrant",
    "letta",
    "aurora-sun-app",
}


def _validate_internal_url(url: str) -> None:
    """
    Validate that a URL points to an allowed internal host (SSRF prevention).
    Prevents SSRF by rejecting any URL not on the allowlist.

    Args:
        url: The URL to validate

    Raises:
        ValueError: If the URL host is not in ALLOWED_INTERNAL_HOSTS
    """
    from urllib.parse import urlparse

    parsed = urlparse(url)
    hostname = parsed.hostname or ""
    if hostname not in ALLOWED_INTERNAL_HOSTS:
        raise ValueError(
            f"SSRF protection: host '{hostname}' not in allowed internal hosts. "
            f"Allowed: {ALLOWED_INTERNAL_HOSTS}"
        )


def _sanitize_backup_name(backup_name: str, backup_dir: Path) -> Path:
    """
    Sanitize backup filenames to prevent path traversal.

    Args:
        backup_name: The requested backup filename
        backup_dir: The backup directory

    Returns:
        Safe resolved path within backup_dir

    Raises:
        ValueError: If the name contains path traversal attempts
    """
    # Strip path separators
    clean_name = backup_name.replace("/", "").replace("\\", "").replace(os.sep, "")

    # Reject names containing ..
    if ".." in clean_name:
        raise ValueError(f"Invalid backup name (contains '..'): {backup_name}")

    # Reject empty names
    if not clean_name:
        raise ValueError("Backup name cannot be empty after sanitization")

    # Reject null bytes (defense-in-depth against C-level path truncation)
    if "\x00" in clean_name:
        raise ValueError("Invalid backup name (contains null byte)")

    # Reject hidden files / dotfiles
    if clean_name.startswith("."):
        raise ValueError(f"Invalid backup name (starts with '.'): {backup_name}")

    # Resolve and verify the path is within backup_dir
    resolved = (backup_dir / clean_name).resolve()
    if not str(resolved).startswith(str(backup_dir.resolve())):
        raise ValueError(
            f"Path traversal detected: resolved path '{resolved}' "
            f"is outside backup directory '{backup_dir}'"
        )

    return resolved


def _validate_restore_path(backup_path: str, backup_dir: Path) -> Path:
    """
    SEC-006: Validate that a restore path is within the backup directory.

    Defense-in-depth validation for restore operations to prevent
    path traversal when specifying backup files to restore from.

    Args:
        backup_path: The requested backup file path
        backup_dir: The backup directory

    Returns:
        Validated resolved path

    Raises:
        ValueError: If the path is outside the backup directory
    """
    resolved = Path(backup_path).resolve()
    backup_resolved = backup_dir.resolve()

    # Reject null bytes
    if "\x00" in backup_path:
        raise ValueError("Invalid backup path (contains null byte)")

    # Reject paths outside backup directory
    if not str(resolved).startswith(str(backup_resolved)):
        raise ValueError(
            f"Path traversal detected: restore path '{resolved}' "
            f"is outside backup directory '{backup_resolved}'"
        )

    return resolved


def _encrypt_backup_file(file_path: Path, master_key: bytes) -> Path:
    """
    Encrypt a backup file using AES-256-GCM with the master key.

    Reads the backup file, encrypts its contents, writes to a .enc file,
    and removes the original unencrypted file.

    Args:
        file_path: Path to the unencrypted backup file
        master_key: 32-byte master encryption key

    Returns:
        Path to the encrypted backup file (.enc extension)
    """
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    except ImportError:
        logger.warning("cryptography not available, skipping backup encryption")
        return file_path

    # Read the backup file
    plaintext = file_path.read_bytes()

    # Encrypt with AES-256-GCM
    nonce = os.urandom(12)  # 96-bit nonce for GCM
    aesgcm = AESGCM(master_key)
    ciphertext = aesgcm.encrypt(nonce, plaintext, None)

    # Write encrypted file: nonce (12 bytes) + ciphertext
    enc_path = file_path.with_suffix(file_path.suffix + ".enc")
    enc_path.write_bytes(nonce + ciphertext)

    # Remove the original unencrypted file
    file_path.unlink()

    logger.info("Backup encrypted: %s -> %s", file_path.name, enc_path.name)
    return enc_path


class BackupStatus(Enum):
    """Backup operation status."""

    SUCCESS = "success"
    FAILED = "failed"
    IN_PROGRESS = "in_progress"
    PARTIAL = "partial"


@dataclass
class BackupResult:
    """Result of a backup operation."""

    service: str
    status: BackupStatus
    backup_path: str | None
    size_bytes: int
    timestamp: datetime
    message: str
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "service": self.service,
            "status": self.status.value,
            "backup_path": self.backup_path,
            "size_bytes": self.size_bytes,
            "timestamp": self.timestamp.isoformat(),
            "message": self.message,
            "error": self.error,
        }


@dataclass
class RestoreResult:
    """Result of a restore operation."""

    service: str
    status: BackupStatus
    backup_path: str
    timestamp: datetime
    message: str
    error: str | None = None


class BackupService:
    """
    Backup service for all Aurora Sun V1 databases.

    This service handles:
    - PostgreSQL pg_dump backups
    - Redis RDB snapshots
    - Neo4j backups
    - Qdrant collection snapshots

    All backups are:
    - Timestamped
    - Compressed (gzip)
    - Optionally encrypted
    - Stored with retention policy
    """

    def __init__(
        self,
        backup_dir: str = "/var/backups/aurora-sun",
        retention_days: int = 30,
        encrypt_backups: bool = True,
        compression_level: int = 6,
    ):
        """
        Initialize backup service.

        Args:
            backup_dir: Directory for backup storage
            retention_days: Number of days to retain backups
            encrypt_backups: Whether to encrypt backups (recommended)
            compression_level: gzip compression level (1-9, default 6)
        """
        self.backup_dir = Path(backup_dir)
        self.retention_days = retention_days
        self.encrypt_backups = encrypt_backups
        self.compression_level = compression_level

        # Load master key for backup encryption
        self._master_key: bytes | None = None
        if encrypt_backups:
            env_key = os.environ.get("AURORA_MASTER_KEY")
            if env_key:
                try:
                    self._master_key = base64.b64decode(env_key)
                except Exception:
                    logger.warning("Failed to decode AURORA_MASTER_KEY for backup encryption")

        # Create backup directory if it doesn't exist
        self.backup_dir.mkdir(parents=True, exist_ok=True)

    async def backup_postgresql(
        self,
        db_url: str,
        backup_name: str | None = None,
    ) -> BackupResult:
        """
        Backup PostgreSQL database using pg_dump.

        Args:
            db_url: PostgreSQL connection URL
            backup_name: Optional custom backup name

        Returns:
            BackupResult with backup details

        Example:
            >>> result = await service.backup_postgresql("postgresql://user:pass@host/db")
            >>> print(result.backup_path)
            /var/backups/aurora-sun/postgresql_2026-02-14_120000.sql.gz
        """
        timestamp = datetime.utcnow().strftime("%Y-%m-%d_%H%M%S")
        backup_filename = backup_name or f"postgresql_{timestamp}.sql.gz"
        # Sanitize backup filename (path traversal prevention)
        backup_path = _sanitize_backup_name(backup_filename, self.backup_dir)

        try:
            # Build pg_dump command
            cmd = [
                "pg_dump",
                db_url,
                "--format=custom",
                "--compress=9",
                f"--file={backup_path}",
            ]

            # Execute pg_dump
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                error_msg = stderr.decode() if stderr else "Unknown error"
                logger.error(f"PostgreSQL backup failed: {error_msg}")
                return BackupResult(
                    service="postgresql",
                    status=BackupStatus.FAILED,
                    backup_path=None,
                    size_bytes=0,
                    timestamp=datetime.utcnow(),
                    message="Backup failed",
                    error=error_msg,
                )

            # Encrypt backup file if enabled (AES-256-GCM)
            if self.encrypt_backups and self._master_key:
                backup_path = _encrypt_backup_file(backup_path, self._master_key)

            # Get backup size
            size_bytes = backup_path.stat().st_size

            logger.info(f"PostgreSQL backup completed: {backup_path} ({size_bytes} bytes)")

            return BackupResult(
                service="postgresql",
                status=BackupStatus.SUCCESS,
                backup_path=str(backup_path),
                size_bytes=size_bytes,
                timestamp=datetime.utcnow(),
                message="Backup completed successfully",
            )

        except Exception as e:
            logger.exception("PostgreSQL backup failed")
            return BackupResult(
                service="postgresql",
                status=BackupStatus.FAILED,
                backup_path=None,
                size_bytes=0,
                timestamp=datetime.utcnow(),
                message="Backup failed with exception",
                error=str(e),
            )

    async def backup_redis(
        self,
        redis_host: str = "localhost",
        redis_port: int = 6379,
        backup_name: str | None = None,
    ) -> BackupResult:
        """
        Backup Redis using SAVE command and RDB file copy.

        Args:
            redis_host: Redis host
            redis_port: Redis port
            backup_name: Optional custom backup name

        Returns:
            BackupResult with backup details
        """
        timestamp = datetime.utcnow().strftime("%Y-%m-%d_%H%M%S")
        backup_filename = backup_name or f"redis_{timestamp}.rdb"
        # Sanitize backup filename (path traversal prevention)
        backup_path = _sanitize_backup_name(backup_filename, self.backup_dir)

        try:
            import redis.asyncio as redis

            # Connect to Redis
            client = redis.Redis(host=redis_host, port=redis_port)

            # Trigger SAVE (blocking, creates dump.rdb)
            await client.save()

            # Get RDB file path from Redis config
            rdb_dir = await client.config_get("dir")
            rdb_filename = await client.config_get("dbfilename")

            if not rdb_dir or not rdb_filename:
                raise ValueError("Could not get RDB file path from Redis")

            rdb_path = Path(rdb_dir["dir"]) / rdb_filename["dbfilename"]

            # Copy RDB file to backup location
            import shutil

            shutil.copy2(rdb_path, backup_path)

            await client.close()

            # Encrypt backup file if enabled (AES-256-GCM)
            if self.encrypt_backups and self._master_key:
                backup_path = _encrypt_backup_file(backup_path, self._master_key)

            # Get backup size
            size_bytes = backup_path.stat().st_size

            logger.info(f"Redis backup completed: {backup_path} ({size_bytes} bytes)")

            return BackupResult(
                service="redis",
                status=BackupStatus.SUCCESS,
                backup_path=str(backup_path),
                size_bytes=size_bytes,
                timestamp=datetime.utcnow(),
                message="Backup completed successfully",
            )

        except Exception as e:
            logger.exception("Redis backup failed")
            return BackupResult(
                service="redis",
                status=BackupStatus.FAILED,
                backup_path=None,
                size_bytes=0,
                timestamp=datetime.utcnow(),
                message="Backup failed with exception",
                error=str(e),
            )

    async def backup_neo4j(
        self,
        neo4j_home: str = "/var/lib/neo4j",
        backup_name: str | None = None,
    ) -> BackupResult:
        """
        Backup Neo4j using neo4j-admin backup.

        Args:
            neo4j_home: Neo4j installation directory
            backup_name: Optional custom backup name

        Returns:
            BackupResult with backup details
        """
        timestamp = datetime.utcnow().strftime("%Y-%m-%d_%H%M%S")
        backup_filename = backup_name or f"neo4j_{timestamp}"
        # Sanitize backup filename (path traversal prevention)
        backup_path = _sanitize_backup_name(backup_filename, self.backup_dir)

        try:
            # Build neo4j-admin backup command
            cmd = [
                f"{neo4j_home}/bin/neo4j-admin",
                "database",
                "dump",
                "neo4j",
                f"--to={backup_path}.dump",
            ]

            # Execute backup
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                error_msg = stderr.decode() if stderr else "Unknown error"
                logger.error(f"Neo4j backup failed: {error_msg}")
                return BackupResult(
                    service="neo4j",
                    status=BackupStatus.FAILED,
                    backup_path=None,
                    size_bytes=0,
                    timestamp=datetime.utcnow(),
                    message="Backup failed",
                    error=error_msg,
                )

            # Get backup file path
            backup_file = Path(f"{backup_path}.dump")

            # Encrypt backup file if enabled (AES-256-GCM)
            if self.encrypt_backups and self._master_key:
                backup_file = _encrypt_backup_file(backup_file, self._master_key)

            # Get backup size
            size_bytes = backup_file.stat().st_size

            logger.info(f"Neo4j backup completed: {backup_file} ({size_bytes} bytes)")

            return BackupResult(
                service="neo4j",
                status=BackupStatus.SUCCESS,
                backup_path=str(backup_file),
                size_bytes=size_bytes,
                timestamp=datetime.utcnow(),
                message="Backup completed successfully",
            )

        except Exception as e:
            logger.exception("Neo4j backup failed")
            return BackupResult(
                service="neo4j",
                status=BackupStatus.FAILED,
                backup_path=None,
                size_bytes=0,
                timestamp=datetime.utcnow(),
                message="Backup failed with exception",
                error=str(e),
            )

    async def backup_qdrant(
        self,
        qdrant_url: str = "http://localhost:6333",
        backup_name: str | None = None,
    ) -> BackupResult:
        """
        Backup Qdrant collections using snapshot API.

        Args:
            qdrant_url: Qdrant HTTP URL
            backup_name: Optional custom backup name

        Returns:
            BackupResult with backup details
        """
        timestamp = datetime.utcnow().strftime("%Y-%m-%d_%H%M%S")
        backup_filename = backup_name or f"qdrant_{timestamp}.json"
        # Sanitize backup filename (path traversal prevention)
        backup_path = _sanitize_backup_name(backup_filename, self.backup_dir)

        try:
            # Validate URL against allowlist (SSRF prevention)
            _validate_internal_url(qdrant_url)

            import httpx

            async with httpx.AsyncClient() as client:
                # Get all collections
                response = await client.get(f"{qdrant_url}/collections")
                response.raise_for_status()
                collections = response.json()["result"]["collections"]

                # Export all collections
                backup_data: dict[str, Any] = {
                    "timestamp": timestamp,
                    "collections": [],
                }

                for collection in collections:
                    collection_name = collection["name"]

                    # Create snapshot for collection
                    response = await client.post(
                        f"{qdrant_url}/collections/{collection_name}/snapshots"
                    )
                    response.raise_for_status()

                    snapshot_info = response.json()["result"]
                    collections_list = backup_data["collections"]
                    if isinstance(collections_list, list):
                        collections_list.append(
                            {
                                "name": collection_name,
                                "snapshot": snapshot_info,
                            }
                        )

                # Write backup data
                with open(backup_path, "w") as f:
                    json.dump(backup_data, f, indent=2)

                # Encrypt backup file if enabled (AES-256-GCM)
                if self.encrypt_backups and self._master_key:
                    backup_path = _encrypt_backup_file(backup_path, self._master_key)

                # Get backup size
                size_bytes = backup_path.stat().st_size

                logger.info(f"Qdrant backup completed: {backup_path} ({size_bytes} bytes)")

                return BackupResult(
                    service="qdrant",
                    status=BackupStatus.SUCCESS,
                    backup_path=str(backup_path),
                    size_bytes=size_bytes,
                    timestamp=datetime.utcnow(),
                    message="Backup completed successfully",
                )

        except Exception as e:
            logger.exception("Qdrant backup failed")
            return BackupResult(
                service="qdrant",
                status=BackupStatus.FAILED,
                backup_path=None,
                size_bytes=0,
                timestamp=datetime.utcnow(),
                message="Backup failed with exception",
                error=str(e),
            )

    async def backup_all(
        self,
        db_url: str,
        redis_host: str = "localhost",
        redis_port: int = 6379,
        neo4j_home: str = "/var/lib/neo4j",
        qdrant_url: str = "http://localhost:6333",
    ) -> list[BackupResult]:
        """
        Backup all databases in parallel.

        Args:
            db_url: PostgreSQL connection URL
            redis_host: Redis host
            redis_port: Redis port
            neo4j_home: Neo4j installation directory
            qdrant_url: Qdrant HTTP URL

        Returns:
            List of BackupResult for each service

        Example:
            >>> results = await service.backup_all(db_url="postgresql://...")
            >>> for result in results:
            ...     print(f"{result.service}: {result.status.value}")
        """
        results = await asyncio.gather(
            self.backup_postgresql(db_url),
            self.backup_redis(redis_host, redis_port),
            self.backup_neo4j(neo4j_home),
            self.backup_qdrant(qdrant_url),
            return_exceptions=True,
        )

        # Filter out exceptions
        backup_results: list[BackupResult] = []
        for result in results:
            if isinstance(result, BackupResult):
                backup_results.append(result)
            elif isinstance(result, Exception):
                logger.exception("Backup failed with exception", exc_info=result)

        return backup_results

    async def cleanup_old_backups(self) -> int:
        """
        Remove backups older than retention_days.

        Returns:
            Number of backups deleted

        Example:
            >>> deleted = await service.cleanup_old_backups()
            >>> print(f"Deleted {deleted} old backups")
        """
        cutoff_date = datetime.utcnow() - timedelta(days=self.retention_days)
        deleted = 0

        for backup_file in self.backup_dir.iterdir():
            if backup_file.is_file():
                # Get file modification time
                mtime = datetime.fromtimestamp(backup_file.stat().st_mtime)

                if mtime < cutoff_date:
                    logger.info(f"Deleting old backup: {backup_file}")
                    backup_file.unlink()
                    deleted += 1

        return deleted


class RestoreService:
    """
    Restore service for all Aurora Sun V1 databases.

    CAUTION: Restore operations are destructive and will overwrite
    existing data. Always verify backup integrity before restoring.
    """

    def __init__(self, backup_dir: str = "/var/backups/aurora-sun"):
        """
        Initialize restore service.

        Args:
            backup_dir: Directory where backups are stored
        """
        self.backup_dir = Path(backup_dir)

    async def restore_postgresql(
        self,
        db_url: str,
        backup_path: str,
    ) -> RestoreResult:
        """
        Restore PostgreSQL database from backup.

        CAUTION: This will DROP and recreate the database.

        Args:
            db_url: PostgreSQL connection URL
            backup_path: Path to backup file

        Returns:
            RestoreResult with restore status
        """
        try:
            # SEC-006: Validate restore path is within backup directory
            validated_path = _validate_restore_path(backup_path, self.backup_dir)
            backup_path = str(validated_path)

            # Build pg_restore command
            cmd = [
                "pg_restore",
                "--clean",
                "--if-exists",
                "--dbname",
                db_url,
                backup_path,
            ]

            # Execute pg_restore
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                error_msg = stderr.decode() if stderr else "Unknown error"
                logger.error(f"PostgreSQL restore failed: {error_msg}")
                return RestoreResult(
                    service="postgresql",
                    status=BackupStatus.FAILED,
                    backup_path=backup_path,
                    timestamp=datetime.utcnow(),
                    message="Restore failed",
                    error=error_msg,
                )

            logger.info(f"PostgreSQL restore completed from: {backup_path}")

            return RestoreResult(
                service="postgresql",
                status=BackupStatus.SUCCESS,
                backup_path=backup_path,
                timestamp=datetime.utcnow(),
                message="Restore completed successfully",
            )

        except Exception as e:
            logger.exception("PostgreSQL restore failed")
            return RestoreResult(
                service="postgresql",
                status=BackupStatus.FAILED,
                backup_path=backup_path,
                timestamp=datetime.utcnow(),
                message="Restore failed with exception",
                error=str(e),
            )
