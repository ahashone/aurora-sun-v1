.PHONY: dev test lint typecheck coverage security-scan

# Development server with auto-reload
dev:
	python3 main.py

# Run test suite
test:
	python3 -m pytest tests/ -v

# Lint with ruff
lint:
	python3 -m ruff check src/ tests/

# Type checking with mypy (strict mode)
typecheck:
	python3 -m mypy src/ --strict

# Run tests with coverage report
coverage:
	python3 -m pytest tests/ --cov=src --cov-report=term-missing --cov-fail-under=80

# Security scan with bandit (HIGH severity)
security-scan:
	python3 -m bandit -r src/ --severity-level high
