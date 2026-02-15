# Threat Model -- Aurora Sun V1

> Formal threat model using STRIDE methodology.
> Created: 2026-02-15. Review cadence: quarterly.

---

## 1. System Boundaries

```
User (Telegram) --> Caddy (HTTPS) --> FastAPI App --> LLM Providers (Anthropic, OpenAI)
                                          |
                              +-----------+-----------+
                              |           |           |
                          PostgreSQL    Redis      Neo4j/Qdrant/Letta
```

**External interfaces:** Telegram Bot API (inbound webhooks), LLM provider APIs (outbound), Caddy reverse proxy (HTTPS termination).

## 2. Trust Zones

| Zone | Components | Trust Level |
|------|-----------|-------------|
| **User** | Telegram client, user input | Untrusted |
| **Edge** | Caddy reverse proxy, Tailscale | Semi-trusted (TLS termination, network perimeter) |
| **Application** | FastAPI app, agents, services, modules | Trusted (validated input only) |
| **Data** | PostgreSQL, Redis, Neo4j, Qdrant, Letta | Trusted (internal network, no host-exposed ports) |
| **External APIs** | Anthropic, OpenAI, Telegram API | Semi-trusted (encrypted transit, shared-responsibility) |

## 3. STRIDE Threat Analysis

### S -- Spoofing

| Threat | Risk | Mitigation |
|--------|------|------------|
| Forged Telegram webhook calls | HIGH | HMAC webhook secret validation (`TELEGRAM_WEBHOOK_SECRET`) |
| User impersonation via Telegram ID | MED | Telegram authenticates users; we verify via bot API |
| Spoofed API requests | MED | No public API exposed; Tailscale-only admin access |

### T -- Tampering

| Threat | Risk | Mitigation |
|--------|------|------------|
| Input manipulation (XSS, injection) | HIGH | `InputSanitizer` (XSS, path traversal, markdown), parameterized SQL queries |
| Prompt injection via user messages | HIGH | `sanitize_for_llm()` strips injection patterns, delimiter tokens |
| Cypher/storage injection | MED | `sanitize_for_storage()` filters Cypher patterns before Neo4j/Qdrant |
| Tampered responses from LLM providers | LOW | Output validation in agent layer; no direct user-facing raw LLM output |

### R -- Repudiation

| Threat | Risk | Mitigation |
|--------|------|------------|
| User denies consent was given | MED | Consent record with `consent_text_hash`, version, timestamp stored |
| Admin action without audit trail | MED | `SecurityEventLogger` logs all security events with structured format |
| Untracked data access | LOW | Security event logging for `DATA_ACCESS`, `DATA_EXPORT`, `DATA_DELETE` |

### I -- Information Disclosure

| Threat | Risk | Mitigation |
|--------|------|------------|
| Art. 9 health data exposed in plaintext | CRIT | AES-256-GCM encryption for all SENSITIVE/ART_9/FINANCIAL fields |
| User IDs leaked in logs | HIGH | `hash_uid()` hashes all user IDs before logging |
| Database credentials exposed | HIGH | All secrets in `.env`, never in code or chat history |
| Sensitive data sent to LLM providers | MED | Data classification system; only required context sent to LLMs |
| Security headers missing | LOW | `SecurityHeadersMiddleware` adds HSTS (preload), CSP, X-Frame-Options, etc. |

### D -- Denial of Service

| Threat | Risk | Mitigation |
|--------|------|------------|
| Message flooding | HIGH | Per-user rate limiting (30/min, 100/hr chat) via Redis + memory fallback |
| Large payload attacks | MED | `MessageSizeValidator` (4096 char text, 60s/10MB voice limits) |
| Voice message abuse | MED | Duration and file size validation before processing |
| Redis unavailable degrades rate limiting | LOW | `InMemoryRateLimiter` fallback; configurable fail-open/fail-closed |

### E -- Elevation of Privilege

| Threat | Risk | Mitigation |
|--------|------|------------|
| User gains admin capabilities | MED | Admin access via Tailscale only; no public admin endpoints |
| Container escape | LOW | Non-root app user (`moltbot`); internal-only Docker network |
| Database ports exposed to internet | LOW | All DB containers use `expose` (internal only), no `ports` mapping |
| LLM manipulated to bypass consent | MED | Consent gate enforced at service layer, not LLM-dependent |

## 4. Current Security Controls Summary

- **Network:** Tailscale VPN, Caddy HTTPS, fail2ban, internal-only DB ports
- **Application:** Input sanitization (XSS/path/markdown), LLM prompt sanitization, rate limiting, security headers (HSTS preload, CSP, Permissions-Policy)
- **Data:** AES-256-GCM field-level encryption, data classification (PUBLIC/INTERNAL/SENSITIVE/ART_9/FINANCIAL), GDPR consent gate
- **Monitoring:** Structured security event logging, Prometheus/Grafana/Alertmanager
- **Process:** Security review at every phase transition, DPIA maintained

## 5. Red Team Schedule

| Quarter | Focus | Status |
|---------|-------|--------|
| Q1 2026 | Input validation, prompt injection, webhook auth | Planned |
| Q2 2026 | Data encryption verification, consent flow, GDPR compliance | Planned |
| Q3 2026 | Infrastructure (container security, network segmentation) | Planned |
| Q4 2026 | Full penetration test, LLM abuse scenarios | Planned |

**Process:** Each quarterly review produces findings logged as TODO items. Critical findings block deployment until resolved.

---

*Last updated: 2026-02-15. Next review: Q2 2026.*
