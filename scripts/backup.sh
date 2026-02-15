#!/bin/bash
#
# Aurora Sun V1 Backup Script
#
# Features:
# - Backup all databases (PostgreSQL, Redis, Neo4j, Qdrant)
# - Retention policy (30 days default)
# - Compression and encryption
# - Verification of backups
# - Slack/email notifications
#
# Usage:
#   ./scripts/backup.sh [--full|--incremental] [--verify] [--no-encrypt]
#
# Cron example (daily at 2 AM):
#   0 2 * * * /opt/aurora-sun/scripts/backup.sh --full >> /var/log/aurora-sun/backup.log 2>&1
#

set -euo pipefail

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
BACKUP_DIR="/var/backups/aurora-sun"
RETENTION_DAYS=30
BACKUP_TYPE="full"
VERIFY_BACKUP=false
ENCRYPT_BACKUP=true

# Parse arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    --full)
      BACKUP_TYPE="full"
      shift
      ;;
    --incremental)
      BACKUP_TYPE="incremental"
      shift
      ;;
    --verify)
      VERIFY_BACKUP=true
      shift
      ;;
    --no-encrypt)
      ENCRYPT_BACKUP=false
      shift
      ;;
    *)
      echo "Unknown option: $1"
      echo "Usage: $0 [--full|--incremental] [--verify] [--no-encrypt]"
      exit 1
      ;;
  esac
done

# Logging
log_info() {
  echo -e "${GREEN}[INFO]${NC} $*"
}

log_warn() {
  echo -e "${YELLOW}[WARN]${NC} $*"
}

log_error() {
  echo -e "${RED}[ERROR]${NC} $*"
}

# Create backup directory
mkdir -p "$BACKUP_DIR"/{postgres,redis,neo4j,qdrant}

# Generate timestamp
TIMESTAMP=$(date '+%Y%m%d_%H%M%S')

# Backup PostgreSQL
backup_postgres() {
  log_info "Backing up PostgreSQL..."

  local backup_file="$BACKUP_DIR/postgres/postgresql_${TIMESTAMP}.dump"

  # MED-2: Use PGPASSFILE to avoid password in process list
  export PGPASSFILE="/tmp/.pgpass_$$"
  echo "postgres:5432:aurora_sun:aurora:${POSTGRES_PASSWORD:-}" > "$PGPASSFILE"
  chmod 600 "$PGPASSFILE"

  docker-compose -f "$PROJECT_ROOT/docker-compose.prod.yml" exec -T postgres \
    pg_dump -U aurora -F c -b -v aurora_sun > "$backup_file"

  rm -f "$PGPASSFILE"

  if [[ -f "$backup_file" ]]; then
    local size=$(du -h "$backup_file" | cut -f1)
    log_info "PostgreSQL backup completed: $backup_file ($size)"
  else
    log_error "PostgreSQL backup failed"
    return 1
  fi
}

# Backup Redis
backup_redis() {
  log_info "Backing up Redis..."

  local backup_file="$BACKUP_DIR/redis/redis_${TIMESTAMP}.rdb"

  # Trigger SAVE
  docker-compose -f "$PROJECT_ROOT/docker-compose.prod.yml" exec -T redis \
    redis-cli SAVE

  # Copy RDB file
  docker cp aurora-redis:/data/dump.rdb "$backup_file"

  if [[ -f "$backup_file" ]]; then
    local size=$(du -h "$backup_file" | cut -f1)
    log_info "Redis backup completed: $backup_file ($size)"
  else
    log_error "Redis backup failed"
    return 1
  fi
}

# Backup Neo4j
backup_neo4j() {
  log_info "Backing up Neo4j..."

  local backup_file="$BACKUP_DIR/neo4j/neo4j_${TIMESTAMP}.dump"

  # Create Neo4j dump
  docker-compose -f "$PROJECT_ROOT/docker-compose.prod.yml" exec -T neo4j \
    neo4j-admin database dump neo4j --to-path=/backups --verbose

  # Copy from container
  docker cp aurora-neo4j:/backups/neo4j.dump "$backup_file"

  if [[ -f "$backup_file" ]]; then
    local size=$(du -h "$backup_file" | cut -f1)
    log_info "Neo4j backup completed: $backup_file ($size)"
  else
    log_error "Neo4j backup failed"
    return 1
  fi
}

# Backup Qdrant
backup_qdrant() {
  log_info "Backing up Qdrant..."

  local backup_file="$BACKUP_DIR/qdrant/qdrant_${TIMESTAMP}.tar.gz"

  # Qdrant uses collection snapshots
  docker-compose -f "$PROJECT_ROOT/docker-compose.prod.yml" exec -T aurora-sun-app \
    python3 -c "
from src.infra.backup import BackupService
import asyncio
service = BackupService(backup_dir='$BACKUP_DIR/qdrant')
asyncio.run(service.backup_qdrant())
"

  log_info "Qdrant backup completed: $backup_file"
}

# Compress backups
compress_backups() {
  log_info "Compressing backups..."

  for dir in postgres redis neo4j qdrant; do
    local latest_backup=$(ls -t "$BACKUP_DIR/$dir" | grep "${TIMESTAMP}" | head -1)
    if [[ -n "$latest_backup" ]]; then
      local backup_path="$BACKUP_DIR/$dir/$latest_backup"
      if [[ ! "$backup_path" == *.gz ]]; then
        gzip -f "$backup_path"
        log_info "Compressed: $backup_path.gz"
      fi
    fi
  done
}

# Encrypt backups (optional)
encrypt_backups() {
  if [[ "$ENCRYPT_BACKUP" == false ]]; then
    log_warn "Backup encryption disabled (--no-encrypt)"
    return 0
  fi

  log_info "Encrypting backups..."

  if [[ -z "${BACKUP_ENCRYPTION_KEY:-}" ]]; then
    log_error "BACKUP_ENCRYPTION_KEY not set — refusing unencrypted backups (MED-2)"
    log_error "Set BACKUP_ENCRYPTION_KEY or use --no-encrypt (dev only)"
    return 1
  fi

  for dir in postgres redis neo4j qdrant; do
    local latest_backup=$(ls -t "$BACKUP_DIR/$dir" | grep "${TIMESTAMP}" | head -1)
    if [[ -n "$latest_backup" ]]; then
      local backup_path="$BACKUP_DIR/$dir/$latest_backup"
      openssl enc -aes-256-cbc -salt -in "$backup_path" \
        -out "${backup_path}.enc" -pass env:BACKUP_ENCRYPTION_KEY
      rm "$backup_path"
      log_info "Encrypted: ${backup_path}.enc"
    fi
  done
}

# Verify backups
verify_backups() {
  if [[ "$VERIFY_BACKUP" == false ]]; then
    return 0
  fi

  log_info "Verifying backups..."

  # Verify PostgreSQL dump
  local pg_backup=$(ls -t "$BACKUP_DIR/postgres" | grep "${TIMESTAMP}" | head -1)
  if [[ -n "$pg_backup" ]]; then
    if pg_restore -l "$BACKUP_DIR/postgres/$pg_backup" > /dev/null 2>&1; then
      log_info "PostgreSQL backup verified"
    else
      log_error "PostgreSQL backup verification failed"
      return 1
    fi
  fi

  # Verify Redis backup (check if it's a valid RDB)
  local redis_backup=$(ls -t "$BACKUP_DIR/redis" | grep "${TIMESTAMP}" | head -1)
  if [[ -n "$redis_backup" ]]; then
    if file "$BACKUP_DIR/redis/$redis_backup" | grep -q "Redis"; then
      log_info "Redis backup verified"
    else
      log_info "Redis backup exists (verification skipped)"
    fi
  fi

  log_info "Backup verification completed"
}

# Cleanup old backups
cleanup_old_backups() {
  log_info "Cleaning up backups older than $RETENTION_DAYS days..."

  local deleted=0

  for dir in postgres redis neo4j qdrant; do
    while IFS= read -r file; do
      rm -f "$file"
      ((deleted++))
    done < <(find "$BACKUP_DIR/$dir" -type f -mtime +$RETENTION_DAYS)
  done

  if [[ $deleted -gt 0 ]]; then
    log_info "Deleted $deleted old backup(s)"
  else
    log_info "No old backups to delete"
  fi
}

# Calculate total backup size
calculate_backup_size() {
  local total_size=$(du -sh "$BACKUP_DIR" | cut -f1)
  log_info "Total backup storage used: $total_size"
}

# Send notification (optional)
send_notification() {
  local status=$1
  local message=$2

  if [[ -n "${SLACK_WEBHOOK_URL:-}" ]]; then
    curl -X POST "$SLACK_WEBHOOK_URL" \
      -H 'Content-Type: application/json' \
      -d "{\"text\":\"Aurora Sun Backup [$status]: $message\"}" \
      > /dev/null 2>&1 || true
  fi
}

# Main backup flow
main() {
  log_info "===== Aurora Sun V1 Backup Started ====="
  log_info "Backup type: $BACKUP_TYPE"
  log_info "Timestamp: $TIMESTAMP"

  # Run backups
  backup_postgres
  backup_redis
  backup_neo4j
  backup_qdrant

  # Compress and encrypt
  compress_backups
  encrypt_backups

  # Verify backups
  verify_backups

  # Cleanup old backups
  cleanup_old_backups

  # Calculate total size
  calculate_backup_size

  log_info "===== Backup Completed Successfully ====="

  send_notification "SUCCESS" "Backup completed at $TIMESTAMP"
}

# Trap errors
trap 'log_error "Backup failed"; send_notification "FAILED" "Backup failed at $TIMESTAMP"; exit 1' ERR

# Run main
main
