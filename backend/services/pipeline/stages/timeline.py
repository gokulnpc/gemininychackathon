"""Timeline JSON build and GCS upload."""

from __future__ import annotations

import logging
from uuid import UUID

from models.schemas import ScriptGenerationResponse
from services.storage import gcs

logger = logging.getLogger(__name__)


async def run_timeline_stage(
    project_id: UUID,
    script: ScriptGenerationResponse,
    scene_gcs_urls: list[str],
    scene_image_gcs_urls: list[str],
    voiceover_gcs_url: str | None,
    voiceover_duration_seconds: float | None,
    word_timestamps: list,
    caption_timing_source: str,
    caption_style: str,
    music_preset: str,
    music_volume: float,
    scene_motion_effects: list[str | None],
    scene_transitions: list[str | None],
    artifact_manifest: dict | None = None,
    caption_render_mode: str = "",
    caption_style_effective: str = "",
    caption_degraded: bool = False,
) -> dict:
    """Build Twick-compatible timeline JSON and upload to GCS.

    Returns project_json dict. Raises on failure.
    """
    from services.content.timeline_builder import build_project_timeline

    project_timeline = build_project_timeline(
        project_id=project_id,
        script=script,
        scene_gcs_urls=scene_gcs_urls,
        scene_image_gcs_urls=scene_image_gcs_urls,
        voiceover_gcs_url=voiceover_gcs_url,
        voiceover_duration_seconds=voiceover_duration_seconds,
        word_timestamps=word_timestamps,
        caption_timing_source=caption_timing_source,
        caption_style=caption_style,
        music_preset=music_preset,
        music_volume=music_volume,
        scene_motion_effects=scene_motion_effects,
        scene_transitions=scene_transitions,
    )
    project_json = project_timeline.model_dump()

    builder_manifest = project_json.get("metadata", {}).get("artifact_manifest", {})
    merged_manifest = {
        **(artifact_manifest or {}),
        **builder_manifest,
    }
    project_json.setdefault("metadata", {})["artifact_manifest"] = merged_manifest
    project_json["metadata"]["caption_render_mode"] = caption_render_mode or project_json["metadata"].get("caption_render_mode", "")
    project_json["metadata"]["caption_style_effective"] = caption_style_effective or project_json["metadata"].get("caption_style_effective", "")
    project_json["metadata"]["caption_degraded"] = caption_degraded

    await gcs.store_json(project_json, f"projects/{project_id}/project.json")
    await gcs.store_json(merged_manifest, f"projects/{project_id}/artifacts.json")

    logger.info("Timeline JSON built and uploaded for project %s", project_id)
    return project_json
