"""Integration test for services/integrations/email_notifier.py — real SendGrid call.

Sends real emails to gokulnpc@gmail.com via SendGrid.

Requires:
  - SENDGRID_API_KEY in .env
  - sendgrid package installed: pip install sendgrid

Usage:
    cd backend && .venv/bin/python tests/integration/test_email_notifier.py
"""

from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from services.integrations.email_notifier import send_generation_failed, send_video_ready

TO_EMAIL = "gokulnpc@gmail.com"


def _check_settings():
    """Clear settings cache and verify SendGrid config is loaded."""
    from config import get_settings
    get_settings.cache_clear()
    settings = get_settings()
    key_preview = settings.sendgrid_api_key[:10] + "..." if settings.sendgrid_api_key else "(empty)"
    print(f"  sendgrid_api_key : {key_preview}")
    print(f"  from_email       : {settings.notification_from_email}")
    if not settings.sendgrid_api_key:
        print("  ⚠ SKIP: SENDGRID_API_KEY not set")
        return False
    return True


async def test_real_video_ready_email():
    """Real SendGrid call — sends a 'video ready' email to gokulnpc@gmail.com."""
    if not _check_settings():
        return

    print(f"  Sending 'video ready' email to {TO_EMAIL} ...")
    await send_video_ready(
        to_email=TO_EMAIL,
        project_id="integration-test-001",
        video_urls={
            "instagram_reels": "https://example.com/videos/ig-test.mp4",
            "tiktok": "https://example.com/videos/tt-test.mp4",
            "master": "https://example.com/videos/master-test.mp4",
        },
        thumbnail_url="https://picsum.photos/300/200",
    )
    print(f"  ✓ 'Video ready' email sent to {TO_EMAIL}")


async def test_real_generation_failed_email():
    """Real SendGrid call — sends a 'generation failed' email to gokulnpc@gmail.com."""
    if not _check_settings():
        return

    print(f"  Sending 'generation failed' email to {TO_EMAIL} ...")
    await send_generation_failed(
        to_email=TO_EMAIL,
        project_id="integration-test-002",
        error="Integration test error: GPU memory exhausted during scene rendering (test only)",
    )
    print(f"  ✓ 'Generation failed' email sent to {TO_EMAIL}")


async def main() -> None:
    tests = [
        test_real_video_ready_email,
        test_real_generation_failed_email,
    ]
    passed = failed = 0

    for fn in tests:
        print(f"[{fn.__name__}]")
        try:
            await fn()
            passed += 1
        except Exception as exc:
            print(f"  ✗ FAILED: {exc}")
            failed += 1

    print(f"\n{'─'*40}")
    print(f"  {passed} passed  |  {failed} failed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    asyncio.run(main())
