"""Stage 7: Platform export and GCS upload."""

from __future__ import annotations

import logging
import mimetypes
import os
from dataclasses import dataclass, field
from collections.abc import Awaitable, Callable
from uuid import UUID

from models.schemas import PipelineStageStatus
from services.media import ffmpeg
from services.storage import gcs

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ExportStageResult:
    video_urls: dict[str, str]
    scene_video_gcs_urls: list[str]
    scene_image_gcs_urls: list[str]
    voiceover_gcs_url: str | None
    artifact_manifest: dict = field(default_factory=dict)


def _audio_upload_target(voiceover_path: str) -> tuple[str, str]:
    ext = os.path.splitext(voiceover_path)[1].lower() or ".wav"
    if ext == ".wav":
        return "voiceover.wav", "audio/wav"
    if ext == ".mp3":
        return "voiceover.mp3", "audio/mpeg"
    mime_type = mimetypes.guess_type(f"placeholder{ext}")[0] or "application/octet-stream"
    return f"voiceover{ext}", mime_type


async def run_export_stage(
    stages: list[PipelineStageStatus],
    composed_path: str,
    target_platforms: list,
    project_id: UUID,
    work_dir: str,
    with_audio_dest: str,
    chunk_clips: list[str],
    reviewed_image_paths: list[str],
    voiceover_path: str | None,
    voiceover_duration_seconds: float | None,
    on_progress: Callable[[str, str, int], Awaitable[None]] | None = None,
) -> ExportStageResult:
    """Export per-platform videos and upload everything to GCS.

    Returns uploaded render/editable asset URLs plus a persisted manifest payload.
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
        platform_path = await ffmpeg.export_for_platform(
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
    scene_video_gcs_urls: list[str] = []
    for idx, clip_path in enumerate(chunk_clips):
        if os.path.exists(clip_path):
            try:
                scene_url = await gcs.upload_file(
                    clip_path,
                    f"projects/{project_id}/scenes/scene_{idx + 1}.mp4",
                    content_type="video/mp4",
                )
                scene_video_gcs_urls.append(scene_url)
            except Exception as _clip_exc:
                logger.warning("Failed to upload scene clip %d: %s", idx + 1, _clip_exc)

    # Editable still images (canonical Twick scene assets)
    scene_image_gcs_urls: list[str] = []
    for idx, image_path in enumerate(reviewed_image_paths):
        if os.path.exists(image_path):
            try:
                ext = os.path.splitext(image_path)[1].lower() or ".png"
                mime_type = mimetypes.guess_type(f"scene{ext}")[0] or "image/png"
                image_url = await gcs.upload_file(
                    image_path,
                    f"projects/{project_id}/scene_images/scene_{idx + 1}{ext}",
                    content_type=mime_type,
                )
                scene_image_gcs_urls.append(image_url)
            except Exception as _img_exc:
                logger.warning("Failed to upload scene image %d: %s", idx + 1, _img_exc)

    # Voiceover audio (used by Twick editor)
    voiceover_gcs_url: str | None = None
    if voiceover_path and os.path.exists(voiceover_path):
        try:
            filename, content_type = _audio_upload_target(voiceover_path)
            voiceover_gcs_url = await gcs.upload_file(
                voiceover_path,
                f"projects/{project_id}/master/{filename}",
                content_type=content_type,
            )
        except Exception as _vo_exc:
            logger.warning("Failed to upload voiceover: %s", _vo_exc)

    stages[-1].status = "completed"
    stages[-1].detail = f"Uploaded {len(video_urls)} versions to GCS"

    artifact_manifest = {
        "render_artifacts": {
            "composed_video_url": master_url,
            "platform_video_urls": video_urls,
            "scene_video_urls": scene_video_gcs_urls,
        },
        "editable_assets": {
            "scene_image_urls": scene_image_gcs_urls,
            "voiceover_url": voiceover_gcs_url,
            "voiceover_duration": voiceover_duration_seconds,
        },
    }

    return ExportStageResult(
        video_urls=video_urls,
        scene_video_gcs_urls=scene_video_gcs_urls,
        scene_image_gcs_urls=scene_image_gcs_urls,
        voiceover_gcs_url=voiceover_gcs_url,
        artifact_manifest=artifact_manifest,
    )
