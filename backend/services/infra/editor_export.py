from __future__ import annotations

import asyncio
import copy
import json
import logging
import tempfile
from pathlib import Path
from typing import Any

import httpx

from config import get_settings
from services.storage import gcs

logger = logging.getLogger(__name__)

ABSOLUTE_SRC_PREFIXES = ("http://", "https://", "data:", "blob:")
GS_MEDIA_SRC_PREFIX = "gs://"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _resolve_gs_media_src(src: str) -> str | None:
    if not src.startswith(GS_MEDIA_SRC_PREFIX):
        return None

    path = src[len(GS_MEDIA_SRC_PREFIX):]
    if "/" not in path:
        return None

    bucket, key = path.split("/", 1)
    if not bucket or not key:
        return None

    return f"https://storage.googleapis.com/{bucket}/{key}"


def normalize_render_media_src(src: str) -> str:
    settings = get_settings()

    if not src:
        return src

    if src.startswith(ABSOLUTE_SRC_PREFIXES):
        return src

    if src.startswith(GS_MEDIA_SRC_PREFIX):
        return _resolve_gs_media_src(src) or src

    if src.startswith("/assets/") or src.startswith("/outputs/"):
        return f"{settings.api_public_base_url.rstrip('/')}{src}"

    if src.startswith("/"):
        return f"{settings.frontend_public_base_url.rstrip('/')}{src}"

    return src


def normalize_project_json_for_render(project_json: dict[str, Any]) -> dict[str, Any]:
    normalized = copy.deepcopy(project_json)

    for track in normalized.get("tracks", []) or []:
        for element in track.get("elements", []) or []:
            props = element.get("props")
            if not isinstance(props, dict):
                continue
            src = props.get("src")
            if isinstance(src, str):
                props["src"] = normalize_render_media_src(src)

    return normalized


def build_editor_export_state(existing: dict[str, Any] | None = None, **updates: Any) -> dict[str, Any]:
    state = {
        "export_id": None,
        "status": "idle",
        "current_stage": None,
        "progress_pct": None,
        "queued_at": None,
        "started_at": None,
        "completed_at": None,
        "download_url": None,
        "thumbnail_url": None,
        "error": None,
    }

    if isinstance(existing, dict):
        state.update(existing)

    state.update(updates)
    return state


def get_editor_export_gcs_key(project_id: str, export_id: str) -> str:
    return f"projects/{project_id}/editor_exports/{export_id}/master.mp4"


def _timeline_worker_cli_path() -> Path:
    return _repo_root() / "timeline-render-worker" / "cli.mjs"


def _fetch_render_service_id_token(audience: str) -> str:
    from google.auth.transport.requests import Request
    from google.oauth2 import id_token

    return id_token.fetch_id_token(Request(), audience)


async def render_timeline_to_file(project_json: dict[str, Any], output_path: str) -> str:
    normalized_project_json = normalize_project_json_for_render(project_json)
    settings = get_settings()

    if settings.timeline_render_worker_url:
        token = await asyncio.to_thread(
            _fetch_render_service_id_token,
            settings.timeline_render_worker_url.rstrip("/"),
        )
        async with httpx.AsyncClient(timeout=None) as client:
            response = await client.post(
                f"{settings.timeline_render_worker_url.rstrip('/')}/render",
                json={"projectJson": normalized_project_json},
                headers={"Authorization": f"Bearer {token}"},
            )
        if response.status_code >= 400:
            detail = response.text.strip() or response.reason_phrase
            raise RuntimeError(f"Timeline render worker failed: {response.status_code} {detail}")

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_bytes(response.content)
        return output_path

    worker_cli = _timeline_worker_cli_path()
    if not worker_cli.exists():
        raise RuntimeError(f"Timeline render CLI not found at {worker_cli}")

    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as input_file:
        json.dump(normalized_project_json, input_file)
        input_json_path = input_file.name

    try:
        process = await asyncio.create_subprocess_exec(
            "node",
            str(worker_cli),
            input_json_path,
            output_path,
            cwd=str(_repo_root()),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        if process.returncode != 0:
            stdout_text = stdout.decode().strip()
            stderr_text = stderr.decode().strip()
            details = "\n".join(part for part in (stdout_text, stderr_text) if part)
            raise RuntimeError(details or f"Timeline render CLI exited with code {process.returncode}")

        return output_path
    finally:
        try:
            Path(input_json_path).unlink(missing_ok=True)
        except OSError:
            logger.warning("Failed to remove temp timeline input %s", input_json_path)


async def upload_rendered_export(local_path: str, project_id: str, export_id: str) -> str:
    return await gcs.upload_file(
        local_path=local_path,
        gcs_key=get_editor_export_gcs_key(project_id, export_id),
        content_type="video/mp4",
    )
