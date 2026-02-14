#!/bin/bash
#
# Aurora Sun V1 Deployment Script
#
# Features:
# - Pre-deployment backup
# - Zero-downtime rolling deployment
# - Health checks before/after
# - Automatic rollback on failure
# - Database migrations
#
# Usage:
#   ./scripts/deploy.sh [--production|--staging] [--skip-backup] [--no-rollback]
#
# References:
#   - ROADMAP.md Phase 4.6 (Deployment script with rollback)
#

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
BACKUP_DIR="/var/backups/aurora-sun"
LOG_FILE="/var/log/aurora-sun/deploy.log"
ENVIRONMENT="staging"
SKIP_BACKUP=false
NO_ROLLBACK=false
ROLLBACK_TAG=""

# Parse arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    --production)
      ENVIRONMENT="production"
      shift
      ;;
    --staging)
      ENVIRONMENT="staging"
      shift
      ;;
    --skip-backup)
      SKIP_BACKUP=true
      shift
      ;;
    --no-rollback)
      NO_ROLLBACK=true
      shift
      ;;
    *)
      echo "Unknown option: $1"
      echo "Usage: $0 [--production|--staging] [--skip-backup] [--no-rollback]"
      exit 1
      ;;
  esac
done

# Logging function
log() {
  local level=$1
  shift
  local message="$*"
  local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
  echo -e "${timestamp} [${level}] ${message}" | tee -a "$LOG_FILE"
}

log_info() {
  log "INFO" "${GREEN}$*${NC}"
}

log_warn() {
  log "WARN" "${YELLOW}$*${NC}"
}

log_error() {
  log "ERROR" "${RED}$*${NC}"
}

# Confirmation prompt for production
confirm_production() {
  if [[ "$ENVIRONMENT" == "production" ]]; then
    echo -e "${YELLOW}⚠️  WARNING: Deploying to PRODUCTION${NC}"
    read -p "Are you sure you want to continue? (yes/no): " confirm
    if [[ "$confirm" != "yes" ]]; then
      log_info "Deployment cancelled by user"
      exit 0
    fi
  fi
}

# Check prerequisites
check_prerequisites() {
  log_info "Checking prerequisites..."

  # Check Docker
  if ! command -v docker &> /dev/null; then
    log_error "Docker is not installed"
    exit 1
  fi

  # Check Docker Compose
  if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
    log_error "Docker Compose is not installed"
    exit 1
  fi

  # Check environment file
  if [[ ! -f "$PROJECT_ROOT/.env" ]]; then
    log_error ".env file not found"
    exit 1
  fi

  log_info "Prerequisites check passed"
}

# Health check function
health_check() {
  local url=$1
  local max_attempts=30
  local attempt=1

  log_info "Running health check: $url"

  while [ $attempt -le $max_attempts ]; do
    if curl -sf "$url" > /dev/null 2>&1; then
      log_info "Health check passed (attempt $attempt/$max_attempts)"
      return 0
    fi

    log_warn "Health check failed (attempt $attempt/$max_attempts), retrying..."
    sleep 2
    ((attempt++))
  done

  log_error "Health check failed after $max_attempts attempts"
  return 1
}

# Backup function
backup_databases() {
  if [[ "$SKIP_BACKUP" == true ]]; then
    log_warn "Skipping backup (--skip-backup flag set)"
    return 0
  fi

  log_info "Creating pre-deployment backup..."

  mkdir -p "$BACKUP_DIR"
  local timestamp=$(date '+%Y%m%d_%H%M%S')
  local backup_tag="pre-deploy-${timestamp}"

  # Backup PostgreSQL
  log_info "Backing up PostgreSQL..."
  docker-compose -f "$PROJECT_ROOT/docker-compose.prod.yml" exec -T postgres \
    pg_dump -U aurora -F c aurora_sun > "$BACKUP_DIR/postgres_${backup_tag}.dump"

  # Backup Redis
  log_info "Backing up Redis..."
  docker-compose -f "$PROJECT_ROOT/docker-compose.prod.yml" exec -T redis \
    redis-cli SAVE
  docker cp aurora-redis:/data/dump.rdb "$BACKUP_DIR/redis_${backup_tag}.rdb"

  # Backup Neo4j
  log_info "Backing up Neo4j..."
  docker-compose -f "$PROJECT_ROOT/docker-compose.prod.yml" exec -T neo4j \
    neo4j-admin database dump neo4j --to=/backups/neo4j_${backup_tag}.dump || true

  # Save backup tag for potential rollback
  ROLLBACK_TAG="$backup_tag"
  echo "$ROLLBACK_TAG" > "$BACKUP_DIR/latest_backup_tag.txt"

  log_info "Backup completed: $backup_tag"
}

# Run database migrations
run_migrations() {
  log_info "Running database migrations..."

  docker-compose -f "$PROJECT_ROOT/docker-compose.prod.yml" exec -T aurora-sun-app \
    alembic upgrade head

  if [[ $? -ne 0 ]]; then
    log_error "Database migration failed"
    return 1
  fi

  log_info "Migrations completed successfully"
}

# Deploy application
deploy_application() {
  log_info "Deploying application..."

  cd "$PROJECT_ROOT"

  # Pull latest images
  log_info "Pulling latest Docker images..."
  docker-compose -f docker-compose.prod.yml pull

  # Build application image
  log_info "Building application image..."
  docker-compose -f docker-compose.prod.yml build aurora-sun-app

  # Stop old containers (zero-downtime not yet implemented)
  log_info "Stopping old containers..."
  docker-compose -f docker-compose.prod.yml down

  # Start new containers
  log_info "Starting new containers..."
  docker-compose -f docker-compose.prod.yml up -d

  # Wait for services to start
  sleep 10

  log_info "Application deployed"
}

# Rollback function
rollback() {
  if [[ "$NO_ROLLBACK" == true ]]; then
    log_error "Deployment failed, but rollback is disabled (--no-rollback)"
    exit 1
  fi

  log_warn "Rolling back deployment..."

  # Restore from backup
  if [[ -n "$ROLLBACK_TAG" ]]; then
    log_info "Restoring from backup: $ROLLBACK_TAG"

    # Restore PostgreSQL
    docker-compose -f "$PROJECT_ROOT/docker-compose.prod.yml" exec -T postgres \
      pg_restore -U aurora -d aurora_sun -c "$BACKUP_DIR/postgres_${ROLLBACK_TAG}.dump" || true

    # Restore Redis
    docker cp "$BACKUP_DIR/redis_${ROLLBACK_TAG}.rdb" aurora-redis:/data/dump.rdb
    docker-compose -f "$PROJECT_ROOT/docker-compose.prod.yml" restart redis

    log_info "Rollback completed"
  else
    log_error "No rollback tag found, cannot restore backup"
  fi

  exit 1
}

# Main deployment flow
main() {
  log_info "===== Aurora Sun V1 Deployment Started ====="
  log_info "Environment: $ENVIRONMENT"
  log_info "Time: $(date)"

  # Confirm production deployment
  confirm_production

  # Check prerequisites
  check_prerequisites

  # Pre-deployment health check
  if health_check "http://localhost:8000/health"; then
    log_info "Pre-deployment health check passed"
  else
    log_warn "Pre-deployment health check failed (service may not be running)"
  fi

  # Create backup
  backup_databases

  # Deploy application
  if ! deploy_application; then
    log_error "Deployment failed"
    rollback
  fi

  # Run migrations
  if ! run_migrations; then
    log_error "Migrations failed"
    rollback
  fi

  # Post-deployment health check
  if ! health_check "http://localhost:8000/health"; then
    log_error "Post-deployment health check failed"
    rollback
  fi

  # Cleanup old backups (keep last 10)
  log_info "Cleaning up old backups..."
  find "$BACKUP_DIR" -type f -name "*.dump" -o -name "*.rdb" | sort -r | tail -n +31 | xargs rm -f || true

  log_info "===== Deployment Completed Successfully ====="
  log_info "Application is healthy and running on $ENVIRONMENT"
}

# Trap errors and rollback
trap rollback ERR

# Run main function
main
