"""Recompose service — regenerate captions and/or background music.

Starts from the preserved with_audio.mp4 artifact (scenes + voiceover,
no captions, no music) uploaded during the original generate-video run.
Skips TTS, Gemini image generation, and FFmpeg animation entirely.

GCS layout expected:
  projects/{project_id}/master/with_audio.mp4   ← source (created by pipeline_runner)
  projects/{project_id}/master/composed.mp4      ← overwritten with new composition
  projects/{project_id}/{platform}/final.mp4     ← overwritten per platform
"""

from __future__ import annotations

import logging
import os
import tempfile
from uuid import UUID

from models.schemas import Platform, PipelineStageStatus
from services.media import captions, ffmpeg
from services.storage import gcs

logger = logging.getLogger(__name__)

_MUSIC_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "assets", "music")
)


async def recompose_video(
    project_id: UUID,
    voiceover_full_script: str,
    video_duration: int,
    caption_style: str,
    background_music: str,
    target_platforms: list[Platform],
    music_volume: float = 0.15,
) -> tuple[list[PipelineStageStatus], dict[str, str]]:
    """Recompose a video from its preserved with_audio.mp4 artifact.

    Stages run (all fast — no Gemini calls, no TTS):
      1. download_source   — fetch with_audio.mp4 from GCS/local
      2. captions          — regenerate caption asset with new style (pure Python)
      3. burn_captions     — FFmpeg subtitle burn
      4. background_music  — FFmpeg audio mix (skipped if background_music="none")
      5. export_upload     — platform resize + GCS upload

    Args:
        project_id:            UUID of the existing completed project.
        voiceover_full_script: Full voiceover text (from metadata) for SRT timing.
        video_duration:        Video length in seconds (from metadata).
        caption_style:         CaptionStyleEnum value string.
        background_music:      MusicPreset value string ("none" skips music).
        target_platforms:      List of Platform enums to export.
        music_volume:          Relative music volume (0.0–1.0).

    Returns:
        (stages, video_urls) — same shape as run_pipeline_stages.

    Raises:
        FileNotFoundError: if with_audio.mp4 is not found.
        RuntimeError: on FFmpeg failure.
    """
    stages: list[PipelineStageStatus] = []
    work_dir = tempfile.mkdtemp(prefix=f"voicevid_rc_{project_id}_")

    # ── Stage 1: Download with_audio.mp4 ────────────────────────────────────

    stages.append(PipelineStageStatus(
        stage="download_source",
        status="running",
        detail="Fetching preserved with_audio.mp4 from storage",
    ))

    with_audio_key = f"projects/{project_id}/master/with_audio.mp4"

    if not await gcs.key_exists(with_audio_key):
        stages[-1].status = "failed"
        stages[-1].detail = f"with_audio.mp4 not found ({with_audio_key})"
        raise FileNotFoundError(
            f"Recompose source not found: {with_audio_key}. "
            "This project was created before recompose support was added — "
            "re-run generate-video once to enable recompose."
        )

    local_with_audio = os.path.join(work_dir, "with_audio.mp4")
    await gcs.download_file(with_audio_key, local_with_audio)

    stages[-1].status = "completed"
    stages[-1].detail = "Downloaded with_audio.mp4"

    # ── Stage 2: Regenerate caption asset with new caption style ──────────────

    stages.append(PipelineStageStatus(
        stage="captions",
        status="running",
        detail=f"Generating {caption_style} captions",
    ))

    word_timestamps = captions.generate_word_timestamps_from_script(
        voiceover_text=voiceover_full_script,
        total_duration=float(video_duration),
    )
    caption_artifact = captions.generate_caption_asset(
        word_timestamps=word_timestamps,
        style=caption_style,
        output_path=os.path.join(work_dir, "captions"),
    )

    stages[-1].status = "completed"
    stages[-1].detail = (
        f"Generated {caption_artifact.style_effective} captions "
        f"({caption_artifact.render_mode}, {len(word_timestamps)} words)"
    )

    # ── Stage 3: Burn captions ────────────────────────────────────────────────

    stages.append(PipelineStageStatus(
        stage="burn_captions",
        status="running",
        detail=f"Burning {caption_style} captions",
    ))

    captioned_path = os.path.join(work_dir, "captioned.mp4")
    await ffmpeg.add_captions(local_with_audio, caption_artifact.path, caption_style, captioned_path)

    stages[-1].status = "completed"
    stages[-1].detail = f"Burned {caption_style} captions"

    # ── Stage 4: Mix background music (optional) ──────────────────────────────

    composed_path = captioned_path

    if background_music and background_music != "none":
        stages.append(PipelineStageStatus(
            stage="background_music",
            status="running",
            detail=f"Mixing music: {background_music} (vol={music_volume})",
        ))

        music_file: str | None = None
        lyria_tmp: str | None = None

        if background_music == "lyria":
            from config import get_settings
            _cfg = get_settings()
            if _cfg.google_cloud_project:
                try:
                    from services.media import lyria as lyria_svc
                    lyria_tmp = await lyria_svc.generate_music(
                        music_preset="lyria",
                        project_id=_cfg.google_cloud_project,
                        location=_cfg.vertex_ai_location,
                    )
                    music_file = lyria_tmp
                except Exception as _lyr_exc:
                    logger.warning("Lyria failed in recompose — skipping music: %s", _lyr_exc)
            else:
                logger.warning("Lyria selected but GOOGLE_CLOUD_PROJECT not set — skipping music")
        else:
            static_path = os.path.join(_MUSIC_DIR, f"{background_music}.mp3")
            if os.path.exists(static_path):
                music_file = static_path
            else:
                logger.warning("Music preset file not found: %s — skipping", static_path)

        if music_file:
            music_out = os.path.join(work_dir, "composed_music.mp4")
            composed_path = await ffmpeg.mix_background_music(
                video_path=captioned_path,
                music_path=music_file,
                music_volume=music_volume,
                output_path=music_out,
            )
            stages[-1].status = "completed"
            stages[-1].detail = f"Mixed {'lyria AI' if lyria_tmp else background_music} at vol={music_volume}"
            if lyria_tmp:
                try:
                    os.unlink(lyria_tmp)
                except OSError:
                    pass
        else:
            stages[-1].status = "failed"
            stages[-1].detail = "Music source not available — video produced without music"

    # ── Stage 5: Platform export + upload ─────────────────────────────────────

    stages.append(PipelineStageStatus(
        stage="export_upload",
        status="running",
        detail=f"Exporting {len(target_platforms)} platform(s)",
    ))

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

    master_url = await gcs.upload_file(
        composed_path,
        f"projects/{project_id}/master/composed.mp4",
    )
    video_urls["master"] = master_url

    stages[-1].status = "completed"
    stages[-1].detail = f"Uploaded {len(video_urls)} versions"

    return stages, video_urls
