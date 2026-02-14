# Aurora Sun V1

AI coaching system for neurodivergent people (ADHD, Autism, AuDHD). Delivers fundamentally different experiences per neurotype segment through natural language conversation via Telegram.

## Architecture

- **3 Pillars:** Vision-to-Task, Second Brain, Money Management
- **3 Agents:** Aurora (coach), TRON (security), Avicenna (quality observer)
- **6 Services:** RIA, PatternDetection, NeurostateService, EffectivenessService, CoachingEngine, FeedbackService
- **8+ Modules:** Planning, Review, Capture, Habits, Beliefs, Motifs, Money, Future Letter

See [ARCHITECTURE.md](ARCHITECTURE.md) for the full system design.

## Prerequisites

- Python 3.11+
- PostgreSQL 15+
- Redis 7+
- Docker & Docker Compose (for containerized deployment)

## Setup

```bash
# Clone the repository
git clone <repo-url>
cd aurora-sun-v1

# Create virtual environment
python -m venv venv
source venv/bin/activate

# Install dependencies
pip install -e ".[dev]"

# Configure environment
cp .env.example .env
# Edit .env with your values (see Environment Variables below)

# Run database migrations
alembic upgrade head

# Run the application
python -m src
```

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `TELEGRAM_BOT_TOKEN` | Yes | Telegram bot API token |
| `DATABASE_URL` | Yes | PostgreSQL connection string |
| `REDIS_URL` | No | Redis connection string (default: `redis://localhost:6379/0`) |
| `AURORA_MASTER_KEY` | Yes* | AES-256-GCM master encryption key (base64) |
| `AURORA_HMAC_SECRET` | Yes* | HMAC secret for PII hashing |
| `AURORA_HASH_SALT` | Yes* | Salt for deterministic hashing |
| `AURORA_LOOKUP_SALT` | Yes* | Salt for lookup hashing |
| `AURORA_DEV_MODE` | No | Set to `1` for development mode |
| `AURORA_DEV_KEY` | No | Dev-only encryption key |
| `LOG_LEVEL` | No | Logging level (default: `INFO`) |
| `ANTHROPIC_API_KEY` | Yes | Anthropic API key for LLM |
| `OPENAI_API_KEY` | No | OpenAI API key (fallback LLM) |
| `GROQ_API_KEY` | No | Groq API key for voice STT |

\* Not required when `AURORA_DEV_MODE=1`.

## Development

```bash
# Run tests
pytest

# Run tests with coverage
pytest --cov=src --cov-report=term-missing

# Lint
ruff check src/ tests/

# Auto-fix lint issues
ruff check --fix src/ tests/

# Type checking
mypy src/
```

## Deployment

Deployed via Docker Compose on Hetzner VPS (Nuremberg). See `docker-compose.yml` for service configuration.

- **Reverse Proxy:** Caddy (HTTPS)
- **App User:** `moltbot` (non-root)
- **Security:** fail2ban, Tailscale, HTTPS via Caddy

Production deployments are NEVER automatic -- always require explicit approval.

## Project Status

See [ROADMAP.md](ROADMAP.md) for the phase plan and [TODO.md](TODO.md) for current work items.

## Known Limitations

- Test coverage is low (~7%) -- only encryption module fully tested
- Voice input (Groq Whisper STT) not yet implemented
- Neo4j, Qdrant, and Letta integrations planned for Phase 3+
