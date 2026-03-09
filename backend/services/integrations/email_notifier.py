"""SendGrid email notifications for video generation events.

Sends a short HTML email when:
  - Video generation completes successfully (with video URLs + thumbnail)
  - Video generation fails (with error summary and retry prompt)

Requires:
  SENDGRID_API_KEY    — from Secret Manager on Cloud Run
  NOTIFICATION_FROM_EMAIL — sender address (default: noreply@voicevid.app)

Falls back to no-op if SENDGRID_API_KEY is not set (local dev).
"""

from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)


def _sendgrid_available() -> bool:
    try:
        import sendgrid  # noqa: F401
        return True
    except ImportError:
        return False


def _send_email_sync(to_email: str, subject: str, html_body: str) -> None:
    """Synchronous SendGrid send — called via asyncio.to_thread."""
    from config import get_settings
    settings = get_settings()

    if not settings.sendgrid_api_key:
        logger.info("SENDGRID_API_KEY not set — skipping email to %s", to_email)
        return

    if not _sendgrid_available():
        logger.warning("sendgrid package not installed — skipping email. pip install sendgrid")
        return

    from sendgrid import SendGridAPIClient
    from sendgrid.helpers.mail import Mail

    message = Mail(
        from_email=settings.notification_from_email,
        to_emails=to_email,
        subject=subject,
        html_content=html_body,
    )
    client = SendGridAPIClient(settings.sendgrid_api_key)
    response = client.send(message)
    logger.info("Email sent to %s (status=%s)", to_email, response.status_code)


async def send_video_ready(
    to_email: str,
    project_id: str,
    video_urls: dict[str, str],
    thumbnail_url: str | None,
) -> None:
    """Send 'your video is ready' notification email."""
    platform_links = "\n".join(
        f'<li><a href="{url}" style="color:#6C63FF">{platform.replace("_", " ").title()}</a></li>'
        for platform, url in video_urls.items()
        if platform != "master"
    )
    thumb_html = (
        f'<img src="{thumbnail_url}" style="max-width:300px;border-radius:8px;margin:16px 0" /><br/>'
        if thumbnail_url else ""
    )

    html_body = f"""
    <div style="font-family:sans-serif;max-width:600px;margin:0 auto;padding:24px">
      <h2 style="color:#6C63FF">🎬 Your video is ready!</h2>
      <p>Great news — your Content Factory video has finished generating.</p>
      {thumb_html}
      <h3>Download your videos:</h3>
      <ul style="line-height:2">{platform_links}</ul>
      <p style="margin-top:24px">
        <a href="https://voicevid.app/dashboard/{project_id}"
           style="background:#6C63FF;color:white;padding:12px 24px;border-radius:6px;text-decoration:none">
          View in Dashboard
        </a>
      </p>
      <p style="color:#888;font-size:12px;margin-top:32px">
        Project ID: {project_id}<br/>
        Content Factory · Unsubscribe
      </p>
    </div>
    """
    await asyncio.to_thread(_send_email_sync, to_email, "🎬 Your video is ready!", html_body)


async def send_generation_failed(
    to_email: str,
    project_id: str,
    error: str,
) -> None:
    """Send 'video generation failed' notification email."""
    # Truncate error to avoid leaking sensitive details
    safe_error = error[:200] if error else "Unknown error"

    html_body = f"""
    <div style="font-family:sans-serif;max-width:600px;margin:0 auto;padding:24px">
      <h2 style="color:#E53E3E">❌ Video generation failed</h2>
      <p>Unfortunately your video generation did not complete successfully.</p>
      <p style="background:#FFF5F5;border-left:4px solid #E53E3E;padding:12px;border-radius:4px">
        <strong>Error:</strong> {safe_error}
      </p>
      <p>
        <a href="https://voicevid.app/dashboard/{project_id}"
           style="background:#6C63FF;color:white;padding:12px 24px;border-radius:6px;text-decoration:none">
          Retry from Dashboard
        </a>
      </p>
      <p style="color:#888;font-size:12px;margin-top:32px">
        Project ID: {project_id}<br/>
        Content Factory · Unsubscribe
      </p>
    </div>
    """
    await asyncio.to_thread(_send_email_sync, to_email, "❌ Video generation failed", html_body)
