"""Stage 7: Platform export and GCS upload."""

from __future__ import annotations

import logging
import os
from collections.abc import Awaitable, Callable
from uuid import UUID

from models.schemas import PipelineStageStatus
from services.media import ffmpeg
from services.storage import gcs

logger = logging.getLogger(__name__)


async def run_export_stage(
    stages: list[PipelineStageStatus],
    composed_path: str,
    target_platforms: list,
    project_id: UUID,
    work_dir: str,
    with_audio_dest: str,
    chunk_clips: list[str],
    voiceover_path: str | None,
    on_progress: Callable[[str, str, int], Awaitable[None]] | None = None,
) -> tuple[dict[str, str], list[str], str | None]:
    """Export per-platform videos and upload everything to GCS.

    Returns (video_urls, scene_gcs_urls, voiceover_gcs_url).
    """
    if on_progress:
        try:
            await on_progress("export_upload", "Uploading final video", 95)
        except Exception as _e:
            logger.debug("Progress callback error: %s", _e)

    stages.append(PipelineStageStatus(stage="export_upload", status="running"))

    # Per-platform exports
    video_urls: dict[str, str] = {}
    for platform in target_platforms:
        platform_path = ffmpeg.export_for_platform(
            video_path=composed_path,
            platform=platform.value,
            output_path=os.path.join(work_dir, f"final_{platform.value}.mp4"),
        )
        url = await gcs.upload_file(
            local_path=platform_path,
            gcs_key=f"projects/{project_id}/{platform.value}/final.mp4",
            content_type="video/mp4",
        )
        video_urls[platform.value] = url

    # Master video
    master_url = await gcs.upload_file(
        composed_path,
        f"projects/{project_id}/master/composed.mp4",
    )
    video_urls["master"] = master_url

    # Intermediate with-audio file (used by recompose endpoint)
    if os.path.exists(with_audio_dest):
        await gcs.upload_file(
            with_audio_dest,
            f"projects/{project_id}/master/with_audio.mp4",
            content_type="video/mp4",
        )

    # Individual scene clips (used by Twick editor)
    scene_gcs_urls: list[str] = []
    for idx, clip_path in enumerate(chunk_clips):
        if os.path.exists(clip_path):
            try:
                scene_url = await gcs.upload_file(
                    clip_path,
                    f"projects/{project_id}/scenes/scene_{idx + 1}.mp4",
                    content_type="video/mp4",
                )
                scene_gcs_urls.append(scene_url)
            except Exception as _clip_exc:
                logger.warning("Failed to upload scene clip %d: %s", idx + 1, _clip_exc)

    # Voiceover audio (used by Twick editor)
    voiceover_gcs_url: str | None = None
    if voiceover_path and os.path.exists(voiceover_path):
        try:
            voiceover_gcs_url = await gcs.upload_file(
                voiceover_path,
                f"projects/{project_id}/master/voiceover.mp3",
                content_type="audio/mpeg",
            )
        except Exception as _vo_exc:
            logger.warning("Failed to upload voiceover: %s", _vo_exc)

    stages[-1].status = "completed"
    stages[-1].detail = f"Uploaded {len(video_urls)} versions to GCS"

    return video_urls, scene_gcs_urls, voiceover_gcs_url
