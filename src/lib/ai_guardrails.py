"""
AI Guardrails for Aurora Sun V1.

Pre-LLM prompt injection detection and post-LLM output validation.
Designed to sit between user input and the LLM pipeline, and between
LLM output and user delivery.

Components:
- PromptInjectionDetector: Scans user input for injection attempts
  (system prompt overrides, encoded payloads, role switching)
- OutputValidator: Validates LLM responses before delivery
  (leaked system prompts, harmful content, length bounds)
- AIGuardrails: Facade combining both components

Usage:
    from src.lib.ai_guardrails import AIGuardrails

    # Before sending to LLM
    result = AIGuardrails.check_input(user_message, user_id=123)
    if result.blocked:
        return result.safe_response
    safe_input = result.sanitized_text

    # After receiving from LLM
    validation = AIGuardrails.check_output(llm_response, user_id=123)
    if not validation.safe:
        return validation.safe_response
    safe_output = validation.sanitized_text

References:
    - ARCHITECTURE.md Section 10 (Security & Privacy Architecture)
    - MED-4 audit finding: AI guardrails before LLM activation
"""

from __future__ import annotations

import base64
import re
import unicodedata
from dataclasses import dataclass, field
from enum import StrEnum

import structlog

from src.lib.security import SecurityEventLogger, SecurityEventType

logger = structlog.get_logger(__name__)


# =============================================================================
# Enums & Data Classes
# =============================================================================


class InjectionType(StrEnum):
    """Types of prompt injection attempts detected."""

    SYSTEM_OVERRIDE = "system_override"
    ROLE_SWITCH = "role_switch"
    DELIMITER_MANIPULATION = "delimiter_manipulation"
    ENCODED_PAYLOAD = "encoded_payload"
    UNICODE_TRICK = "unicode_trick"
    INSTRUCTION_LEAK = "instruction_leak"
    MULTI_TURN_MANIPULATION = "multi_turn_manipulation"


class OutputIssueType(StrEnum):
    """Types of issues detected in LLM output."""

    LEAKED_SYSTEM_PROMPT = "leaked_system_prompt"
    INTERNAL_DATA_LEAK = "internal_data_leak"
    HARMFUL_CONTENT = "harmful_content"
    EXCESSIVE_LENGTH = "excessive_length"
    EMPTY_RESPONSE = "empty_response"


@dataclass
class InjectionDetection:
    """A single detected injection pattern."""

    injection_type: InjectionType
    pattern_name: str
    matched_text: str
    confidence: float  # 0.0-1.0


@dataclass
class InputCheckResult:
    """Result of input guardrail check."""

    blocked: bool
    sanitized_text: str
    detections: list[InjectionDetection] = field(default_factory=list)
    risk_score: float = 0.0  # 0.0-1.0 aggregate risk
    safe_response: str = "I'm not able to process that request. Could you rephrase?"

    @property
    def has_detections(self) -> bool:
        return len(self.detections) > 0


@dataclass
class OutputCheckResult:
    """Result of output guardrail check."""

    safe: bool
    sanitized_text: str
    issues: list[str] = field(default_factory=list)
    issue_types: list[OutputIssueType] = field(default_factory=list)
    safe_response: str = "I'm sorry, I couldn't generate a proper response. Please try again."


# =============================================================================
# Prompt Injection Detector
# =============================================================================


class PromptInjectionDetector:
    """
    Detects prompt injection attempts in user input.

    Detection categories:
    1. System prompt overrides ("ignore previous instructions", etc.)
    2. Role switching ("you are now", "act as", etc.)
    3. Delimiter manipulation (chat-ml tokens, markdown tricks)
    4. Encoded payloads (base64, unicode homoglyphs)
    5. Instruction leak attempts ("repeat your instructions", etc.)
    6. Multi-turn manipulation ("in your previous response you said...")

    Each detection has a confidence score. The aggregate risk_score
    determines whether input is blocked (threshold: 0.7) or allowed
    with sanitization.
    """

    # Risk threshold: inputs with aggregate score >= this are blocked
    BLOCK_THRESHOLD = 0.7

    # --- System prompt override patterns ---
    SYSTEM_OVERRIDE_PATTERNS: list[tuple[re.Pattern[str], str, float]] = [
        (
            re.compile(
                r"(?:ignore|forget|disregard|override|bypass|skip)\s+"
                r"(?:all\s+)?(?:(?:your|the|my|any)\s+)?"
                r"(?:previous|prior|above|earlier|system)\s+"
                r"(?:instructions?|prompts?|rules?|context|guidelines?|directives?|constraints?|programming)",
                re.IGNORECASE,
            ),
            "ignore_previous_instructions",
            0.9,
        ),
        (
            re.compile(
                r"(?:do\s+not|don'?t)\s+follow\s+"
                r"(?:(?:your|the|any)\s+)?(?:previous\s+)?"
                r"(?:instructions?|prompts?|rules?|guidelines?)",
                re.IGNORECASE,
            ),
            "dont_follow_instructions",
            0.85,
        ),
        (
            re.compile(
                r"(?:new|updated?|replacement|override)\s*"
                r"(?:system\s*)?(?:prompt|instructions?|rules?|directives?)\s*"
                r"(?::|follows?|below|are)",
                re.IGNORECASE,
            ),
            "new_system_prompt",
            0.9,
        ),
        (
            re.compile(
                r"from\s+now\s+on\s*,?\s*(?:you|your|the\s+(?:system|ai))\s+"
                r"(?:will|should|must|are\s+(?:going\s+)?to)",
                re.IGNORECASE,
            ),
            "from_now_on",
            0.8,
        ),
    ]

    # --- Role switching patterns ---
    ROLE_SWITCH_PATTERNS: list[tuple[re.Pattern[str], str, float]] = [
        (
            re.compile(
                r"(?:you\s+are\s+now|act\s+as|pretend\s+(?:to\s+be|you(?:'re|\s+are))|roleplay\s+as|"
                r"imagine\s+you(?:'re|\s+are)|behave\s+(?:as|like)|"
                r"simulate\s+(?:being)?|impersonate)\s+",
                re.IGNORECASE,
            ),
            "role_switch",
            0.8,
        ),
        (
            re.compile(
                r"(?:enter|switch\s+to|activate|enable)\s+"
                r"(?:developer|debug|admin|god|jailbreak|unrestricted|unfiltered|"
                r"sudo|root|dan|evil|chaos)\s*(?:mode)?",
                re.IGNORECASE,
            ),
            "mode_switch",
            0.95,
        ),
    ]

    # --- Delimiter manipulation patterns ---
    DELIMITER_PATTERNS: list[tuple[re.Pattern[str], str, float]] = [
        (
            re.compile(
                r"<\|?\s*(?:system|assistant|user|im_start|im_end|endoftext)\s*\|?>",
                re.IGNORECASE,
            ),
            "chatml_tokens",
            0.9,
        ),
        (
            re.compile(r"\[(?:SYSTEM|INST|/INST|SYS|/SYS)\]", re.IGNORECASE),
            "instruction_tags",
            0.9,
        ),
        (
            re.compile(r"```\s*(?:system|instruction|prompt)\b", re.IGNORECASE),
            "markdown_system_block",
            0.85,
        ),
        (
            re.compile(r"###\s*(?:system|instruction|human|assistant|prompt)\s*:", re.IGNORECASE),
            "markdown_header_injection",
            0.85,
        ),
        (
            re.compile(r"<\s*/?(?:system_message|system_prompt|instructions?)\s*>", re.IGNORECASE),
            "xml_system_tags",
            0.9,
        ),
    ]

    # --- Instruction leak patterns ---
    INSTRUCTION_LEAK_PATTERNS: list[tuple[re.Pattern[str], str, float]] = [
        (
            re.compile(
                r"(?:repeat|show|print|reveal|display|output|tell\s+me|what\s+(?:are|is))\s+"
                r"(?:me\s+)?(?:(?:your|the|all|full|entire|complete|system|original|initial)\s+)+"
                r"(?:instructions?|prompts?|rules?|guidelines?|directives?|configuration)",
                re.IGNORECASE,
            ),
            "reveal_instructions",
            0.85,
        ),
        (
            re.compile(
                r"(?:what\s+(?:were?\s+)?(?:you|your)\s+(?:told|instructed|programmed|configured))",
                re.IGNORECASE,
            ),
            "query_instructions",
            0.7,
        ),
    ]

    # --- Multi-turn manipulation patterns ---
    MULTI_TURN_PATTERNS: list[tuple[re.Pattern[str], str, float]] = [
        (
            re.compile(
                r"(?:in\s+your\s+(?:previous|last|earlier)\s+(?:response|message|reply)\s+"
                r"you\s+(?:said|agreed|confirmed|mentioned)\s+(?:that\s+)?(?:you\s+)?(?:would|will|can|should))",
                re.IGNORECASE,
            ),
            "false_history",
            0.6,
        ),
        (
            re.compile(
                r"(?:we\s+(?:already|previously)\s+agreed|you\s+(?:already|previously)\s+(?:confirmed|approved))\s+",
                re.IGNORECASE,
            ),
            "false_agreement",
            0.65,
        ),
    ]

    # Common delimiter tokens to strip (exact strings)
    DELIMITER_TOKENS: list[str] = [
        "<|endoftext|>",
        "<|im_start|>",
        "<|im_end|>",
        "<|system|>",
        "<|user|>",
        "<|assistant|>",
        "[INST]",
        "[/INST]",
        "[SYS]",
        "[/SYS]",
    ]

    @classmethod
    def detect(cls, text: str) -> list[InjectionDetection]:
        """
        Scan text for prompt injection patterns.

        Args:
            text: User input text

        Returns:
            List of InjectionDetection objects for each match found
        """
        if not text:
            return []

        detections: list[InjectionDetection] = []

        # Check system override patterns
        for pattern, name, confidence in cls.SYSTEM_OVERRIDE_PATTERNS:
            match = pattern.search(text)
            if match:
                detections.append(
                    InjectionDetection(
                        injection_type=InjectionType.SYSTEM_OVERRIDE,
                        pattern_name=name,
                        matched_text=match.group(0)[:100],
                        confidence=confidence,
                    )
                )

        # Check role switch patterns
        for pattern, name, confidence in cls.ROLE_SWITCH_PATTERNS:
            match = pattern.search(text)
            if match:
                detections.append(
                    InjectionDetection(
                        injection_type=InjectionType.ROLE_SWITCH,
                        pattern_name=name,
                        matched_text=match.group(0)[:100],
                        confidence=confidence,
                    )
                )

        # Check delimiter patterns
        for pattern, name, confidence in cls.DELIMITER_PATTERNS:
            match = pattern.search(text)
            if match:
                detections.append(
                    InjectionDetection(
                        injection_type=InjectionType.DELIMITER_MANIPULATION,
                        pattern_name=name,
                        matched_text=match.group(0)[:100],
                        confidence=confidence,
                    )
                )

        # Check instruction leak patterns
        for pattern, name, confidence in cls.INSTRUCTION_LEAK_PATTERNS:
            match = pattern.search(text)
            if match:
                detections.append(
                    InjectionDetection(
                        injection_type=InjectionType.INSTRUCTION_LEAK,
                        pattern_name=name,
                        matched_text=match.group(0)[:100],
                        confidence=confidence,
                    )
                )

        # Check multi-turn manipulation patterns
        for pattern, name, confidence in cls.MULTI_TURN_PATTERNS:
            match = pattern.search(text)
            if match:
                detections.append(
                    InjectionDetection(
                        injection_type=InjectionType.MULTI_TURN_MANIPULATION,
                        pattern_name=name,
                        matched_text=match.group(0)[:100],
                        confidence=confidence,
                    )
                )

        # Check for encoded payloads
        encoded_detections = cls._detect_encoded_payloads(text)
        detections.extend(encoded_detections)

        # Check for unicode tricks
        unicode_detections = cls._detect_unicode_tricks(text)
        detections.extend(unicode_detections)

        return detections

    @classmethod
    def _detect_encoded_payloads(cls, text: str) -> list[InjectionDetection]:
        """
        Detect base64-encoded injection attempts.

        Looks for base64-encoded strings that, when decoded, contain
        injection patterns.
        """
        detections: list[InjectionDetection] = []

        # Find potential base64 strings (at least 20 chars, valid base64 alphabet)
        base64_pattern = re.compile(r"[A-Za-z0-9+/]{20,}={0,2}")
        for match in base64_pattern.finditer(text):
            candidate = match.group(0)
            try:
                decoded = base64.b64decode(candidate).decode("utf-8", errors="ignore")
                # Check if decoded content contains injection patterns
                if cls._contains_injection_keywords(decoded):
                    detections.append(
                        InjectionDetection(
                            injection_type=InjectionType.ENCODED_PAYLOAD,
                            pattern_name="base64_injection",
                            matched_text=candidate[:50] + "...",
                            confidence=0.85,
                        )
                    )
            except Exception:
                # Not valid base64, skip
                pass

        return detections

    @classmethod
    def _detect_unicode_tricks(cls, text: str) -> list[InjectionDetection]:
        """
        Detect unicode-based injection tricks.

        Checks for:
        - Homoglyph attacks (Cyrillic/Greek letters that look like Latin)
        - Zero-width characters used to hide injections
        - Right-to-left override characters
        """
        detections: list[InjectionDetection] = []

        # Check for zero-width characters (often used to hide injections)
        zero_width_chars = [
            "\u200b",  # Zero-width space
            "\u200c",  # Zero-width non-joiner
            "\u200d",  # Zero-width joiner
            "\ufeff",  # Zero-width no-break space (BOM)
            "\u2060",  # Word joiner
        ]
        zero_width_count = sum(text.count(c) for c in zero_width_chars)
        if zero_width_count > 3:
            detections.append(
                InjectionDetection(
                    injection_type=InjectionType.UNICODE_TRICK,
                    pattern_name="excessive_zero_width",
                    matched_text=f"{zero_width_count} zero-width characters found",
                    confidence=0.7,
                )
            )

        # Check for RTL override characters
        rtl_override_chars = [
            "\u202e",  # Right-to-left override
            "\u202d",  # Left-to-right override
            "\u202a",  # Left-to-right embedding
            "\u202b",  # Right-to-left embedding
        ]
        for char in rtl_override_chars:
            if char in text:
                detections.append(
                    InjectionDetection(
                        injection_type=InjectionType.UNICODE_TRICK,
                        pattern_name="rtl_override",
                        matched_text=f"U+{ord(char):04X} found",
                        confidence=0.75,
                    )
                )
                break  # One detection is enough for RTL

        # Check for mixed script homoglyph attacks
        # (Cyrillic/Greek chars mixed with Latin in the same word)
        has_mixed_scripts = cls._detect_mixed_scripts(text)
        if has_mixed_scripts:
            detections.append(
                InjectionDetection(
                    injection_type=InjectionType.UNICODE_TRICK,
                    pattern_name="mixed_script_homoglyph",
                    matched_text="Mixed Latin/Cyrillic/Greek scripts in same word",
                    confidence=0.6,
                )
            )

        return detections

    @classmethod
    def _detect_mixed_scripts(cls, text: str) -> bool:
        """
        Detect mixed-script homoglyph attacks within individual words.

        Returns True if any single word contains characters from
        both Latin and Cyrillic/Greek scripts (common in homoglyph attacks).
        """
        words = text.split()
        for word in words:
            if len(word) < 3:
                continue
            has_latin = False
            has_cyrillic_or_greek = False
            for char in word:
                cat = unicodedata.category(char)
                if cat.startswith("L"):  # Letter category
                    try:
                        name = unicodedata.name(char, "")
                    except ValueError:
                        continue
                    if "LATIN" in name:
                        has_latin = True
                    elif "CYRILLIC" in name or "GREEK" in name:
                        has_cyrillic_or_greek = True
                if has_latin and has_cyrillic_or_greek:
                    return True
        return False

    @classmethod
    def _contains_injection_keywords(cls, text: str) -> bool:
        """Check if text contains common injection keywords."""
        keywords = [
            "ignore",
            "system",
            "instruction",
            "prompt",
            "override",
            "admin",
            "jailbreak",
            "bypass",
            "you are now",
            "act as",
            "pretend",
        ]
        text_lower = text.lower()
        # Require at least 2 keyword matches to reduce false positives
        matches = sum(1 for kw in keywords if kw in text_lower)
        return matches >= 2

    @classmethod
    def sanitize(cls, text: str) -> str:
        """
        Sanitize text by removing/neutralizing injection patterns.

        This is a more aggressive sanitization than sanitize_for_llm()
        in security.py. It strips:
        - All delimiter tokens
        - Zero-width characters
        - RTL override characters

        Args:
            text: User input text

        Returns:
            Sanitized text with injection patterns neutralized
        """
        if not text:
            return ""

        result = text

        # Strip delimiter tokens
        for token in cls.DELIMITER_TOKENS:
            result = result.replace(token, "")
            # Also try case-insensitive replacement
            result = re.sub(re.escape(token), "", result, flags=re.IGNORECASE)

        # Strip zero-width characters
        zero_width = "\u200b\u200c\u200d\ufeff\u2060"
        for char in zero_width:
            result = result.replace(char, "")

        # Strip RTL/LTR override characters
        bidi_overrides = "\u202a\u202b\u202c\u202d\u202e"
        for char in bidi_overrides:
            result = result.replace(char, "")

        # Replace injection-like patterns with [filtered]
        injection_patterns = [
            re.compile(
                r"(?:ignore|forget|disregard|override|bypass)\s+"
                r"(?:all\s+)?(?:previous|prior|above|earlier|your|the|system)\s+"
                r"(?:instructions?|prompts?|rules?|context|guidelines?|directives?|constraints?)",
                re.IGNORECASE,
            ),
            re.compile(
                r"(?:new|updated?|replacement|override)\s*"
                r"(?:system\s*)?(?:prompt|instructions?|rules?|directives?)\s*:",
                re.IGNORECASE,
            ),
            re.compile(
                r"(?:enter|switch\s+to|activate|enable)\s+"
                r"(?:developer|debug|admin|god|jailbreak|unrestricted|unfiltered|"
                r"sudo|root|dan|evil|chaos)\s*(?:mode)?",
                re.IGNORECASE,
            ),
            re.compile(
                r"<\|?\s*(?:system|assistant|im_start|im_end|endoftext)\s*\|?>",
                re.IGNORECASE,
            ),
            re.compile(r"\[(?:SYSTEM|INST|/INST|SYS|/SYS)\]", re.IGNORECASE),
            re.compile(
                r"<\s*/?(?:system_message|system_prompt|instructions?)\s*>",
                re.IGNORECASE,
            ),
        ]

        for pattern in injection_patterns:
            result = pattern.sub("[filtered]", result)

        return result

    @classmethod
    def compute_risk_score(cls, detections: list[InjectionDetection]) -> float:
        """
        Compute aggregate risk score from individual detections.

        Uses a non-linear combination: the highest single confidence
        sets the floor, and additional detections push it higher.

        Args:
            detections: List of injection detections

        Returns:
            Aggregate risk score (0.0-1.0)
        """
        if not detections:
            return 0.0

        confidences = sorted(
            [d.confidence for d in detections], reverse=True
        )

        # Highest confidence is the base
        score = confidences[0]

        # Each additional detection adds a fraction of remaining headroom
        for conf in confidences[1:]:
            remaining = 1.0 - score
            score += remaining * conf * 0.3

        return min(score, 1.0)


# =============================================================================
# Output Validator
# =============================================================================


class OutputValidator:
    """
    Validates LLM responses before delivering to users.

    Checks:
    1. Leaked system prompts or internal configuration
    2. Internal data patterns (API keys, database URIs, etc.)
    3. Harmful content patterns
    4. Response length bounds
    5. Empty/null responses
    """

    # Default response length bounds
    MIN_RESPONSE_LENGTH = 1
    MAX_RESPONSE_LENGTH = 8000  # characters

    # Patterns indicating leaked system prompts
    SYSTEM_PROMPT_LEAK_PATTERNS: list[tuple[re.Pattern[str], str]] = [
        (
            re.compile(
                r"(?:my\s+)?(?:system\s+)?(?:prompt|instructions?)\s+(?:is|are|says?|tells?)\s*:",
                re.IGNORECASE,
            ),
            "system_prompt_disclosure",
        ),
        (
            re.compile(
                r"(?:as\s+(?:an?\s+)?(?:ai|language\s+model|assistant),?\s+)?i\s+(?:was|am)\s+"
                r"(?:instructed|programmed|told|configured)\s+to",
                re.IGNORECASE,
            ),
            "instruction_disclosure",
        ),
        (
            re.compile(
                r"(?:my|the)\s+(?:original|initial|base|core)\s+"
                r"(?:system\s+)?(?:prompt|instructions?|guidelines?|rules?)",
                re.IGNORECASE,
            ),
            "original_prompt_reference",
        ),
        (
            re.compile(r"CLAUDE\.md|ARCHITECTURE\.md|ROADMAP\.md"),
            "internal_doc_reference",
        ),
    ]

    # Patterns indicating internal data leaks
    INTERNAL_DATA_PATTERNS: list[tuple[re.Pattern[str], str]] = [
        (
            re.compile(r"(?:sk-|pk-|api[_-]?key[=:])\s*[A-Za-z0-9_-]{20,}"),
            "api_key_leak",
        ),
        (
            re.compile(r"postgres(?:ql)?://\S+", re.IGNORECASE),
            "database_uri_leak",
        ),
        (
            re.compile(r"redis://\S+", re.IGNORECASE),
            "redis_uri_leak",
        ),
        (
            re.compile(r"(?:AURORA|TELEGRAM|OPENAI|ANTHROPIC)_\w+\s*=\s*\S+", re.IGNORECASE),
            "env_var_leak",
        ),
        (
            re.compile(r"-----BEGIN (?:RSA |EC )?PRIVATE KEY-----"),
            "private_key_leak",
        ),
        (
            re.compile(r"(?:neo4j|bolt)://\S+", re.IGNORECASE),
            "neo4j_uri_leak",
        ),
    ]

    # Harmful content patterns (conservative — catches obvious issues)
    HARMFUL_CONTENT_PATTERNS: list[tuple[re.Pattern[str], str]] = [
        (
            re.compile(
                r"(?:how\s+to|steps?\s+to|instructions?\s+(?:for|to)|guide\s+(?:for|to))\s+"
                r"(?:make|build|create|synthesize|manufacture)\s+(?:a\s+)?(?:bomb|explosive|weapon|poison)",
                re.IGNORECASE,
            ),
            "weapon_instructions",
        ),
        (
            re.compile(
                r"(?:you\s+should|you\s+deserve\s+to|just)\s+"
                r"(?:kill\s+yourself|end\s+(?:your\s+)?(?:life|it\s+all)|commit\s+suicide|die)",
                re.IGNORECASE,
            ),
            "self_harm_encouragement",
        ),
    ]

    @classmethod
    def validate(
        cls,
        response_text: str,
        max_length: int | None = None,
    ) -> OutputCheckResult:
        """
        Validate LLM response text.

        Args:
            response_text: The LLM's response text
            max_length: Optional override for max response length

        Returns:
            OutputCheckResult with validation results
        """
        effective_max = max_length or cls.MAX_RESPONSE_LENGTH
        issues: list[str] = []
        issue_types: list[OutputIssueType] = []

        # Check for empty response
        if not response_text or not response_text.strip():
            return OutputCheckResult(
                safe=False,
                sanitized_text="",
                issues=["Empty response from LLM"],
                issue_types=[OutputIssueType.EMPTY_RESPONSE],
            )

        # Check response length
        if len(response_text) > effective_max:
            issues.append(
                f"Response exceeds maximum length ({len(response_text)} > {effective_max})"
            )
            issue_types.append(OutputIssueType.EXCESSIVE_LENGTH)

        # Check for system prompt leaks
        for pattern, name in cls.SYSTEM_PROMPT_LEAK_PATTERNS:
            if pattern.search(response_text):
                issues.append(f"Possible system prompt leak: {name}")
                issue_types.append(OutputIssueType.LEAKED_SYSTEM_PROMPT)

        # Check for internal data leaks
        for pattern, name in cls.INTERNAL_DATA_PATTERNS:
            if pattern.search(response_text):
                issues.append(f"Internal data leak detected: {name}")
                issue_types.append(OutputIssueType.INTERNAL_DATA_LEAK)

        # Check for harmful content
        for pattern, name in cls.HARMFUL_CONTENT_PATTERNS:
            if pattern.search(response_text):
                issues.append(f"Harmful content detected: {name}")
                issue_types.append(OutputIssueType.HARMFUL_CONTENT)

        # Determine if safe
        # Harmful content and internal data leaks are always unsafe
        critical_types = {
            OutputIssueType.INTERNAL_DATA_LEAK,
            OutputIssueType.HARMFUL_CONTENT,
        }
        has_critical = bool(critical_types & set(issue_types))

        # Sanitize output
        sanitized = cls.sanitize(response_text, effective_max)

        return OutputCheckResult(
            safe=not has_critical and not issues,
            sanitized_text=sanitized,
            issues=issues,
            issue_types=issue_types,
        )

    @classmethod
    def sanitize(cls, response_text: str, max_length: int | None = None) -> str:
        """
        Sanitize LLM response by removing sensitive patterns and enforcing length.

        Args:
            response_text: LLM response text
            max_length: Optional max length override

        Returns:
            Sanitized response text
        """
        if not response_text:
            return ""

        effective_max = max_length or cls.MAX_RESPONSE_LENGTH
        result = response_text

        # Redact internal data patterns
        for pattern, name in cls.INTERNAL_DATA_PATTERNS:
            result = pattern.sub("[REDACTED]", result)

        # Truncate if too long
        if len(result) > effective_max:
            result = result[:effective_max]

        return result


# =============================================================================
# AIGuardrails Facade
# =============================================================================


class AIGuardrails:
    """
    Facade combining prompt injection detection and output validation.

    Provides two simple entry points:
    - check_input(): Before sending user message to LLM
    - check_output(): After receiving LLM response, before delivery

    Both methods log security events via SecurityEventLogger when
    issues are detected.
    """

    @classmethod
    def check_input(
        cls,
        text: str,
        user_id: int | None = None,
        block_threshold: float | None = None,
    ) -> InputCheckResult:
        """
        Check user input for prompt injection before LLM processing.

        Args:
            text: User message text
            user_id: Optional user ID for logging
            block_threshold: Optional override for blocking threshold

        Returns:
            InputCheckResult with detection results and sanitized text
        """
        if not text:
            return InputCheckResult(
                blocked=False,
                sanitized_text="",
                detections=[],
                risk_score=0.0,
            )

        threshold = block_threshold or PromptInjectionDetector.BLOCK_THRESHOLD

        # Detect injection patterns
        detections = PromptInjectionDetector.detect(text)
        risk_score = PromptInjectionDetector.compute_risk_score(detections)

        # Decide: block or sanitize
        blocked = risk_score >= threshold

        # Sanitize regardless (even if not blocked, clean up the text)
        sanitized = PromptInjectionDetector.sanitize(text)

        # Log security event if detections found
        if detections:
            detection_summary = [
                {"type": d.injection_type.value, "pattern": d.pattern_name, "confidence": d.confidence}
                for d in detections
            ]
            log_kwargs: dict[str, object] = {
                "vector": "prompt_injection",
                "risk_score": round(risk_score, 3),
                "blocked": blocked,
                "detection_count": len(detections),
                "detection_types": [d.injection_type.value for d in detections],
            }
            if user_id is not None:
                log_kwargs["user_id"] = user_id

            SecurityEventLogger.injection_attempt(**log_kwargs)

            logger.warning(
                "ai_guardrail_input_check",
                risk_score=round(risk_score, 3),
                blocked=blocked,
                detections=detection_summary,
            )

        return InputCheckResult(
            blocked=blocked,
            sanitized_text=sanitized,
            detections=detections,
            risk_score=risk_score,
        )

    @classmethod
    def check_output(
        cls,
        response_text: str,
        user_id: int | None = None,
        max_length: int | None = None,
    ) -> OutputCheckResult:
        """
        Validate LLM output before delivering to user.

        Args:
            response_text: LLM response text
            user_id: Optional user ID for logging
            max_length: Optional max response length override

        Returns:
            OutputCheckResult with validation results
        """
        result = OutputValidator.validate(response_text, max_length)

        # Log security event if issues found
        if result.issues:
            log_kwargs: dict[str, object] = {
                "vector": "llm_output_validation",
                "issues": result.issues,
                "issue_types": [t.value for t in result.issue_types],
                "safe": result.safe,
            }
            if user_id is not None:
                log_kwargs["user_id"] = user_id

            SecurityEventLogger.injection_attempt(**log_kwargs)

            logger.warning(
                "ai_guardrail_output_check",
                safe=result.safe,
                issues=result.issues,
            )

        return result
