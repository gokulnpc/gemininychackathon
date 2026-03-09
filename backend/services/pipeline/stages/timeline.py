"""Timeline JSON build and GCS upload."""

from __future__ import annotations

import json
import logging
import os
import tempfile
from uuid import UUID

from models.schemas import ScriptGenerationResponse
from services.storage import gcs

logger = logging.getLogger(__name__)


async def run_timeline_stage(
    project_id: UUID,
    script: ScriptGenerationResponse,
    scene_gcs_urls: list[str],
    voiceover_gcs_url: str | None,
    word_timestamps: list,
    caption_style: str,
    music_preset: str,
    music_volume: float,
) -> dict:
    """Build Twick-compatible timeline JSON and upload to GCS.

    Returns project_json dict (empty dict on failure).
    """
    try:
        from services.content.timeline_builder import build_project_timeline

        project_timeline = build_project_timeline(
            project_id=project_id,
            script=script,
            scene_gcs_urls=scene_gcs_urls,
            voiceover_gcs_url=voiceover_gcs_url,
            word_timestamps=word_timestamps,
            caption_style=caption_style,
            music_preset=music_preset,
            music_volume=music_volume,
        )
        project_json = project_timeline.model_dump()

        _json_fd, _json_path = tempfile.mkstemp(suffix=".json", prefix="voicevid_timeline_")
        try:
            with os.fdopen(_json_fd, "w") as _f:
                _f.write(json.dumps(project_json))
            await gcs.upload_file(
                _json_path,
                f"projects/{project_id}/project.json",
                content_type="application/json",
            )
        finally:
            try:
                os.unlink(_json_path)
            except OSError:
                pass

        logger.info("Timeline JSON built and uploaded for project %s", project_id)
        return project_json
    except Exception as _tl_exc:
        logger.warning("Timeline JSON build failed (non-fatal): %s", _tl_exc)
        return {}
