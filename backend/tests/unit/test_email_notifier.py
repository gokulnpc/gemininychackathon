"""Unit tests for services/integrations/email_notifier.py — mocked paths only.

No real SendGrid calls made. Safe to run without API keys.

Usage:
    cd backend && .venv/bin/python tests/unit/test_email_notifier.py
"""

from __future__ import annotations

import asyncio
import os
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from services.integrations.email_notifier import (
    _send_email_sync,
    _sendgrid_available,
    send_generation_failed,
    send_video_ready,
)


def _settings(api_key: str = "", from_email: str = "test@example.com") -> SimpleNamespace:
    return SimpleNamespace(
        sendgrid_api_key=api_key,
        notification_from_email=from_email,
    )


# ── _sendgrid_available ──────────────────────────────────────────────────────

def test_sendgrid_available_when_installed():
    """sendgrid importable → True."""
    # If sendgrid is actually installed, this will pass naturally.
    # If not, we mock the import to succeed.
    import builtins
    real_import = builtins.__import__

    def allow_sendgrid(name, *args, **kwargs):
        if name == "sendgrid":
            return MagicMock()
        return real_import(name, *args, **kwargs)

    with patch("builtins.__import__", side_effect=allow_sendgrid):
        result = _sendgrid_available()
    assert result is True, f"Expected True, got: {result}"
    print("  ✓ sendgrid importable → True")


def test_sendgrid_not_available_when_missing():
    """sendgrid import raises ImportError → False."""
    import builtins
    real_import = builtins.__import__

    def block_sendgrid(name, *args, **kwargs):
        if name == "sendgrid":
            raise ImportError("sendgrid not installed")
        return real_import(name, *args, **kwargs)

    with patch("builtins.__import__", side_effect=block_sendgrid):
        result = _sendgrid_available()
    assert result is False, f"Expected False, got: {result}"
    print("  ✓ sendgrid not importable → False")


# ── _send_email_sync — guard paths ───────────────────────────────────────────

def test_send_skips_when_no_api_key():
    """Empty sendgrid_api_key → no-op, no error."""
    with patch("config.get_settings",
               return_value=_settings(api_key="")):
        # Should not raise
        _send_email_sync("test@example.com", "Subject", "<p>Body</p>")
    print("  ✓ no API key → skips silently")


def test_send_skips_when_sendgrid_not_installed():
    """API key set but sendgrid package missing → no-op."""
    with patch("config.get_settings",
               return_value=_settings(api_key="SG.fake")), \
         patch("services.integrations.email_notifier._sendgrid_available", return_value=False):
        # Should not raise
        _send_email_sync("test@example.com", "Subject", "<p>Body</p>")
    print("  ✓ sendgrid not installed → skips silently")


def test_send_calls_sendgrid_when_configured():
    """API key + sendgrid installed → SendGridAPIClient.send() called."""
    mock_client_instance = MagicMock()
    mock_client_instance.send.return_value = MagicMock(status_code=202)
    mock_client_class = MagicMock(return_value=mock_client_instance)
    mock_mail_class = MagicMock()

    with patch("config.get_settings",
               return_value=_settings(api_key="SG.test_key_123")), \
         patch("services.integrations.email_notifier._sendgrid_available", return_value=True), \
         patch.dict("sys.modules", {
             "sendgrid": MagicMock(SendGridAPIClient=mock_client_class),
             "sendgrid.helpers.mail": MagicMock(Mail=mock_mail_class),
         }):
        _send_email_sync("user@example.com", "Test Subject", "<p>Hello</p>")

    mock_client_class.assert_called_once_with("SG.test_key_123")
    mock_client_instance.send.assert_called_once()
    print("  ✓ configured → SendGridAPIClient.send() called")


# ── send_video_ready — HTML construction ─────────────────────────────────────

async def test_video_ready_html_contains_project_id():
    """Generated HTML includes the project_id."""
    captured = {}

    async def fake_to_thread(fn, to_email, subject, html_body):
        captured["html"] = html_body
        captured["subject"] = subject

    with patch("services.integrations.email_notifier.asyncio.to_thread", side_effect=fake_to_thread):
        await send_video_ready(
            to_email="test@example.com",
            project_id="proj-abc-123",
            video_urls={"instagram_reels": "https://example.com/v1"},
            thumbnail_url=None,
        )

    assert "proj-abc-123" in captured["html"], f"project_id not in HTML"
    assert "ready" in captured["subject"].lower()
    print("  ✓ HTML contains project_id")


async def test_video_ready_html_includes_platform_links():
    """Platform URLs appear as links, 'master' excluded."""
    captured = {}

    async def fake_to_thread(fn, to_email, subject, html_body):
        captured["html"] = html_body

    with patch("services.integrations.email_notifier.asyncio.to_thread", side_effect=fake_to_thread):
        await send_video_ready(
            to_email="test@example.com",
            project_id="proj-1",
            video_urls={
                "instagram_reels": "https://cdn.example.com/ig.mp4",
                "tiktok": "https://cdn.example.com/tt.mp4",
                "master": "https://cdn.example.com/master.mp4",
            },
            thumbnail_url=None,
        )

    html = captured["html"]
    assert "https://cdn.example.com/ig.mp4" in html, "instagram URL missing"
    assert "https://cdn.example.com/tt.mp4" in html, "tiktok URL missing"
    assert "https://cdn.example.com/master.mp4" not in html, "'master' URL should be excluded"
    assert "Instagram Reels" in html, "Platform name not formatted"
    print("  ✓ platform links present, 'master' excluded")


async def test_video_ready_html_with_thumbnail():
    """thumbnail_url provided → <img> tag in HTML."""
    captured = {}

    async def fake_to_thread(fn, to_email, subject, html_body):
        captured["html"] = html_body

    with patch("services.integrations.email_notifier.asyncio.to_thread", side_effect=fake_to_thread):
        await send_video_ready(
            to_email="test@example.com",
            project_id="proj-1",
            video_urls={"instagram_reels": "https://example.com/v.mp4"},
            thumbnail_url="https://example.com/thumb.jpg",
        )

    assert "<img" in captured["html"], "Expected <img> tag"
    assert "https://example.com/thumb.jpg" in captured["html"]
    print("  ✓ thumbnail_url → <img> tag in HTML")


async def test_video_ready_html_without_thumbnail():
    """thumbnail_url=None → no <img> tag."""
    captured = {}

    async def fake_to_thread(fn, to_email, subject, html_body):
        captured["html"] = html_body

    with patch("services.integrations.email_notifier.asyncio.to_thread", side_effect=fake_to_thread):
        await send_video_ready(
            to_email="test@example.com",
            project_id="proj-1",
            video_urls={"instagram_reels": "https://example.com/v.mp4"},
            thumbnail_url=None,
        )

    assert "<img" not in captured["html"], "No <img> expected when thumbnail_url is None"
    print("  ✓ no thumbnail → no <img> tag")


# ── send_generation_failed — HTML construction ───────────────────────────────

async def test_failed_html_contains_error_message():
    """Error string appears in HTML body."""
    captured = {}

    async def fake_to_thread(fn, to_email, subject, html_body):
        captured["html"] = html_body
        captured["subject"] = subject

    with patch("services.integrations.email_notifier.asyncio.to_thread", side_effect=fake_to_thread):
        await send_generation_failed(
            to_email="test@example.com",
            project_id="proj-fail-1",
            error="GPU out of memory during scene 3",
        )

    assert "GPU out of memory during scene 3" in captured["html"]
    assert "proj-fail-1" in captured["html"]
    assert "failed" in captured["subject"].lower()
    print("  ✓ error message and project_id in HTML")


async def test_failed_html_truncates_long_error():
    """Error > 200 chars → truncated in HTML."""
    captured = {}
    long_error = "x" * 300

    async def fake_to_thread(fn, to_email, subject, html_body):
        captured["html"] = html_body

    with patch("services.integrations.email_notifier.asyncio.to_thread", side_effect=fake_to_thread):
        await send_generation_failed(
            to_email="test@example.com",
            project_id="proj-1",
            error=long_error,
        )

    # Full 300-char string should NOT be in HTML; only first 200
    assert long_error not in captured["html"], "Full 300-char error should be truncated"
    assert "x" * 200 in captured["html"], "First 200 chars should be present"
    print("  ✓ long error truncated to 200 chars")


async def test_failed_html_handles_empty_error():
    """Empty error string → 'Unknown error' in HTML."""
    captured = {}

    async def fake_to_thread(fn, to_email, subject, html_body):
        captured["html"] = html_body

    with patch("services.integrations.email_notifier.asyncio.to_thread", side_effect=fake_to_thread):
        await send_generation_failed(
            to_email="test@example.com",
            project_id="proj-1",
            error="",
        )

    assert "Unknown error" in captured["html"], f"Expected 'Unknown error' for empty error string"
    print("  ✓ empty error → 'Unknown error'")


# ── Runner ────────────────────────────────────────────────────────────────────

async def main() -> None:
    sync_tests = [
        test_sendgrid_available_when_installed,
        test_sendgrid_not_available_when_missing,
        test_send_skips_when_no_api_key,
        test_send_skips_when_sendgrid_not_installed,
        test_send_calls_sendgrid_when_configured,
    ]
    async_tests = [
        test_video_ready_html_contains_project_id,
        test_video_ready_html_includes_platform_links,
        test_video_ready_html_with_thumbnail,
        test_video_ready_html_without_thumbnail,
        test_failed_html_contains_error_message,
        test_failed_html_truncates_long_error,
        test_failed_html_handles_empty_error,
    ]

    passed = failed = 0

    print("\n── _sendgrid_available + _send_email_sync (guards) ──")
    for fn in sync_tests:
        print(f"[{fn.__name__}]")
        try:
            fn()
            passed += 1
        except Exception as exc:
            print(f"  ✗ FAILED: {exc}")
            failed += 1

    print("\n── send_video_ready (HTML construction) ──")
    for fn in async_tests[:4]:
        print(f"[{fn.__name__}]")
        try:
            await fn()
            passed += 1
        except Exception as exc:
            print(f"  ✗ FAILED: {exc}")
            failed += 1

    print("\n── send_generation_failed (HTML construction) ──")
    for fn in async_tests[4:]:
        print(f"[{fn.__name__}]")
        try:
            await fn()
            passed += 1
        except Exception as exc:
            print(f"  ✗ FAILED: {exc}")
            failed += 1

    print(f"\n{'─'*44}")
    print(f"  {passed} passed  |  {failed} failed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    asyncio.run(main())
