# Breach Notification Procedure

> **Legal Basis:** GDPR Art. 33 (72-hour notification) + Art. 34 (user notification)
> **Document Status:** Phase 1.0
> **Last Updated:** 2026-02-13

---

## 1. Overview

### 1.1 Purpose

This procedure ensures compliance with **GDPR Article 33** (notification to supervisory authority) and **Article 34** (communication to the data subject) in the event of a personal data breach. A personal data breach is a security incident that leads to accidental or unlawful destruction, loss, alteration, unauthorized disclosure of, or access to personal data.

### 1.2 Scope

This procedure applies to **all security incidents involving personal data** processed by Aurora Sun V1, including but not limited to:

- Unauthorized access to user data (PUBLIC/INTERNAL/SENSITIVE/ART_9_SPECIAL/FINANCIAL classifications)
- Data exfiltration or theft
- System compromise leading to data exposure
- Accidental data disclosure
- Ransomware attacks affecting user data
- Credential compromise affecting user accounts

### 1.3 Legal Framework

| Regulation | Requirement |
|------------|-------------|
| **GDPR Art. 33** | Notify supervisory authority within **72 hours** of becoming aware of a breach, unless unlikely to result in risk to rights and freedoms |
| **GDPR Art. 34** | Communicate breach to data subject "without undue delay" when likely to result in high risk to rights and freedoms |
| **GDPR Art. 34(3)(a)** | No user notification required if encryption rendered data unintelligible (keys not compromised) |

---

## 2. Detection

### 2.1 Who Can Detect a Breach

| Source | Description |
|--------|-------------|
| **TRON (Security Agent)** | Automated anomaly detection, failed login patterns, suspicious access patterns, unusual data access volumes |
| **Avicenna (Health Agent)** | Unusual patterns in health-related data access, potential exposure of Art. 9 data |
| **External Report** | User report via Telegram, security researcher, third-party notification, public disclosure |
| **System Monitoring** | Prometheus alerts, container failures, unexpected network traffic, database access logs |

### 2.2 What Triggers Investigation

The following events **immediately trigger a breach investigation**:

- Any alert from TRON's security monitoring (severity >= MEDIUM)
- Any report of suspected data access from a user
- Any unauthorized access detected in audit logs
- Any system compromise (container breach, credential theft)
- Any data leak discovered internally or externally
- Any ransomware detection or unusual encryption activity
- Any unusual pattern in Avicenna's health data access logs

**All suspected breaches are treated as confirmed until assessment proves otherwise.** False alarms are documented as such after assessment, not before.

---

## 3. Containment (0-1 Hour)

Immediate actions to limit breach scope.

### 3.1 Isolate Affected Systems

| Action | Responsible |
|--------|-------------|
| Identify and isolate affected containers/services | TRON / Admin |
| Disable affected API endpoints | TRON |
| Enable enhanced logging on affected systems | TRON |
| Snapshot affected database state (for forensics) | Admin |

### 3.2 Revoke Compromised Credentials

| Action | Responsible |
|--------|-------------|
| Rotate all potentially compromised API keys | TRON |
| Invalidate session tokens for affected users | TRON |
| Force re-authentication for affected accounts | TRON |
| Review and revoke suspicious user sessions | TRON |
| Rotate database credentials if compromised | Admin |

### 3.3 TRON Auto-Block (Auto-High Mode)

If TRON is operating in **Auto-High mode**, it will automatically:

1. Block suspicious IP addresses
2. Temporarily suspend affected user accounts
3. Disable potentially compromised integrations
4. Enable maximum logging and monitoring
5. Alert admin via Telegram with severity assessment

**Note:** Auto-High mode is triggered automatically when TRON detects patterns consistent with active exploitation (e.g., mass data access, credential stuffing, lateral movement).

---

## 4. Assessment (1-24 Hours)

### 4.1 Data Assessment Questions

The incident response team must answer the following:

| Question | Purpose |
|----------|---------|
| What data was accessed or potentially exfiltrated? | Determine classification and legal obligation |
| How many users are affected? | Scale the response |
| What is the data classification level? | PUBLIC/INTERNAL/SENSITIVE/ART_9_SPECIAL/FINANCIAL |
| Was the data encrypted at rest? | Assess risk (encryption lowers severity) |
| Was the data encrypted in transit? | Assess risk |
| Were encryption keys compromised? | If NO + encrypted: may reduce notification requirement |
| What is the current threat vector? | Prevent recurrence |
| Is the breach ongoing? | Continue containment |

### 4.2 Severity Classification

| Level | Criteria | Notification Timeline |
|-------|----------|----------------------|
| **LOW** | No personal data exposed, or encrypted data with keys NOT compromised | Authority: Not required. Users: Not required. Log only. |
| **MEDIUM** | INTERNAL/SENSITIVE data exposed, but not likely to cause harm | Authority: Not required (unless cumulative). Users: Optional. |
| **HIGH** | SENSITIVE/Art.9 data exposed, or clear risk to individuals | Authority: Within 72h. Users: Without undue delay. |
| **CRITICAL** | Art.9 health data exposed, financial data exposed, large-scale breach, active exploitation | Authority: Immediately (<24h). Users: Immediately. |

### 4.3 Risk Factors That Increase Severity

- Art. 9 data (health, neurotype, mental health)
- Financial data (payment information, transaction history)
- Authentication credentials exposed
- Large number of affected users (>100)
- Vulnerable individuals (minors, protected characteristics)
- Ongoing/uncontained breach
- Public disclosure
- No encryption at rest

### 4.4 Risk Factors That Decrease Severity

- Data was encrypted at rest (AES-256-GCM)
- Encryption keys were NOT compromised
- Data was encrypted in transit
- Rapid containment (<1 hour)
- Limited access scope
- No Art.9 or financial data involved

---

## 5. Notification (Within 72 Hours - GDPR Art. 33)

### 5.1 Decision Matrix

| Scenario | Authority Notification | User Notification |
|----------|----------------------|------------------|
| Art.9 data involved | YES (within 72h) | YES (without undue delay) |
| HIGH severity | YES (within 72h) | YES (without undue delay) |
| Encrypted data, keys NOT compromised | YES (still required) | NO (Art.34(3)(a)) |
| LOW severity, no sensitive data | NO | NO |
| External sub-processor breach | YES (you are responsible) | Depends on severity |

### 5.2 Supervisory Authority Notification

**Deadline:** Within **72 hours** of becoming aware of the breach.

**Required Content (Art. 33(3)):**

1. Nature of the breach (categories, approximate number of data subjects, records)
2. DPO contact details
3. Likely consequences of the breach
4. Measures taken or proposed to address the breach

**If notification exceeds 72 hours:** Provide reasons for delay.

**Where to submit:** German supervisory authority (BfDI for federal bodies, or relevant state authority for commercial entities).

### 5.3 User Notification

**Deadline:** "Without undue delay" (Art. 34) -- typically within 24-72 hours of confirmation.

**Required Content (Art. 34(2)):**

1. Clear, plain-language description of what happened
2. DPO contact details
3. Likely consequences
4. Measures taken to address the breach
5. Specific steps users can take to protect themselves

**Exception (Art. 34(3)(a)):** No user notification required if:
- Data was encrypted (rendered unintelligible to unauthorized parties)
- Keys were NOT compromised
- Post-breach measures effectively mitigate risk

### 5.4 Documentation Requirements

All breach incidents must be documented regardless of notification requirements:

- Facts of the breach
- Effects of the breach
- Remedial actions taken
- Records retained for at least 3 years (GDPR Art. 33(4))

---

## 6. Remediation

### 6.1 Root Cause Analysis

| Step | Description |
|------|-------------|
| Forensic analysis | Determine exact attack vector, timeline, scope |
| System hardening | Close vulnerabilities, update dependencies, enhance controls |
| Process review | Identify gaps in monitoring, detection, response |

### 6.2 User-Facing Remediation

| Action | Trigger |
|--------|---------|
| Mandatory password reset | If credentials exposed |
| Key rotation | If API keys compromised |
| Session invalidation | If session tokens exposed |
| Account review | User can review affected data |
| Fraud monitoring | If financial data exposed |

### 6.3 Security Measure Updates

| Area | Actions |
|------|---------|
| Access Control | Review RBAC, implement additional checks |
| Encryption | Re-encrypt sensitive data, rotate keys |
| Monitoring | Enhance TRON rules, add alerts |
| Network | Isolation, firewall rules, rate limiting |
| Authentication | MFA enforcement, session limits |

### 6.4 Post-Incident Report

A comprehensive post-incident report must be created and archived to `docs/archive/incident-{YYYY-MM-DD}-{severity}.md`:

- Executive summary
- Timeline (detection → containment → assessment → notification → remediation)
- Root cause analysis
- Impact assessment (users, data, severity)
- Remediation actions taken
- Lessons learned
- Recommendations for prevention
- Evidence preserved

---

## 7. Templates

### 7.1 Incident Report Template

```markdown
# Incident Report: {INCIDENT-ID}

**Date Detected:** {YYYY-MM-DD HH:MM UTC}
**Date Contained:** {YYYY-MM-DD HH:MM UTC}
**Severity:** {LOW / MEDIUM / HIGH / CRITICAL}
**Status:** {CONTAINED / REMEDIATED / CLOSED}

## Summary
{Brief description of what happened}

## Detection
- **Detected By:** {TRON / Avicenna / External / Admin}
- **Detection Time:** {YYYY-MM-DD HH:MM UTC}
- **Time to Contain:** {X hours}

## Data Impact
- **Classification:** {PUBLIC / INTERNAL / SENSITIVE / ART_9_SPECIAL / FINANCIAL}
- **Records Affected:** {number}
- **Users Affected:** {number}
- **Art.9 Data Involved:** {YES / NO}

## Technical Details
- **Attack Vector:** {description}
- **Systems Affected:** {list}
- **Credentials Compromised:** {YES / NO}
- **Keys Compromised:** {YES / NO}

## Containment Actions
1. {action}
2. {action}
3. {action}

## Assessment
- **Risk to Individuals:** {low / medium / high / critical}
- **Likely Consequences:** {description}

## Notification
- **Authority Notified:** {YES / NO} | Date: {YYYY-MM-DD}
- **Users Notified:** {YES / NO} | Date: {YYYY-MM-DD}
- **Reason for Decision:** {explanation}

## Remediation
1. {action}
2. {action}
3. {action}

## Lessons Learned
{What could be improved}

## Recommendations
{Preventive measures for future}

---
**Prepared By:** {name/role}
**Date:** {YYYY-MM-DD}
```

### 7.2 User Notification Template

```
Subject: Important: Security Notice for Your Aurora Sun Account

Dear {USER_NAME},

We are writing to inform you about a security incident that may have affected your personal data.

## What Happened
{Brief, plain-language description of the incident - e.g., "On [DATE], we detected unauthorized access to our systems."}

## What Information Was Involved
- {Type of data, e.g., "Your account email and usage patterns"}
- {Include specific data categories}

## What We Are Doing
1. {Action taken, e.g., "Secured the affected systems"}
2. {Action taken, e.g., "Invalidated compromised sessions"}
3. {Action taken, e.g., "Enhanced our security monitoring"}

## What You Can Do
1. {Recommendation, e.g., "Change your password as a precaution"}
2. {Recommendation, e.g., "Review your account for any suspicious activity"}
3. {Recommendation, e.g., "Enable two-factor authentication in settings"}

## Contact
If you have questions, please contact us via Telegram or email: {dpo@aurora-sun.ai}

We sincerely apologize for any concern this may cause.

---
Aurora Sun Security Team
{Date}
```

### 7.3 Authority Notification Template

```
To: {Supervisory Authority}

Subject: Personal Data Breach Notification - Aurora Sun V1

## 1. Controller Details
- **Name:** Aurora Sun V1 (operated by {Operator Name})
- **Address:** {Address}
- **DPO Contact:** {Name}, {Email}, {Phone}

## 2. Description of the Breach
- **Date Detected:** {YYYY-MM-DD}
- **Nature of Breach:** {e.g., "Unauthorized access to user database"}
- **Categories of Data:** {e.g., "Email addresses, behavioral patterns, neurotype information"}
- **Approximate Records:** {number}
- **Approximate Data Subjects:** {number}

## 3. Likely Consequences
{Description of potential consequences for data subjects, e.g., "Users may receive targeted communications, potential identity correlation..."}

## 4. Measures Taken
1. {Description of technical measures}
2. {Description of organizational measures}
3. {Description of remediation}

## 5. DPO Contact
{Name}
{Email}
{Phone}

---
This notification is made pursuant to Article 33 of the General Data Protection Regulation (GDPR).

{Date}
{Authorized Signatory}
```

---

## 8. Roles & Responsibilities

### 8.1 Role Matrix

| Role | Responsibilities |
|------|------------------|
| **Admin (Ahash)** | Final decision on severity, notifications, remediation strategy. Authority notification sign-off. User notification approval. |
| **TRON (Security Agent)** | Breach detection, containment execution, credential revocation, auto-blocking, forensic data collection. |
| **Avicenna (Health Agent)** | Detection of Art.9 data exposure, health data impact assessment, health-specific risk evaluation. |
| **Aurora (Coach Agent)** | User communication (after approval), user support during incident, tone-appropriate messaging. |
| **DPO** | Legal compliance review, authority notification, DPIA updates, documentation oversight. |

### 8.2 Communication Chain

```
DETECTION
    |
    v
TRON / Avicenna --> Admin (immediate alert)
    |
    v
CONTAINMENT
    |
    v
TRON executes --> Admin approves --> TRON reports
    |
    v
ASSESSMENT
    |
    v
TRON + Avicenna + Admin --> Severity Classification
    |
    v
NOTIFICATION DECISION
    |
    v
Admin + DPO --> Authority Notification (within 72h)
Admin + Aurora --> User Notification (without undue delay)
    |
    v
REMEDIATION
    |
    v
Admin --> Root Cause Analysis
TRON --> Security Hardening
Admin --> Post-Incident Report --> docs/archive/
```

### 8.3 Escalation Timeline

| Time | Milestone | Action |
|------|-----------|--------|
| **0 hours** | Breach detected | TRON alerts Admin, begins containment |
| **1 hour** | Containment complete | TRON reports to Admin |
| **4 hours** | Assessment complete | Severity classification + notification decision |
| **24 hours** | User notification (if required) | Aurora sends user notification |
| **72 hours** | Authority notification deadline | DPO submits authority notification |
| **1-2 weeks** | Remediation complete | All technical fixes applied |
| **2-4 weeks** | Post-incident report | Report archived to docs/archive/ |

---

## 9. Related Documents

| Document | Location |
|----------|----------|
| Architecture | `/ARCHITECTURE.md` |
| Security & Privacy Architecture | `/ARCHITECTURE.md` Section 10 |
| DPIA | `/docs/DPIA.md` |
| Data Classification Policy | `/ARCHITECTURE.md` Section 8 |
| Incident Reports Archive | `/docs/archive/incident-*.md` |

---

## 10. Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-02-13 | Aurora Sun | Initial document for Phase 1.0 |

---

*This document is part of Aurora Sun V1's GDPR compliance framework. For questions, contact the DPO or refer to ARCHITECTURE.md Section 10.*
