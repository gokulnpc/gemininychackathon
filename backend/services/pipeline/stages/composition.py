"""Stage 6: Video composition and optional background music mixing."""

from __future__ import annotations

import logging
import os
from collections.abc import Awaitable, Callable

from models.schemas import PipelineStageStatus
from services.media import ffmpeg

logger = logging.getLogger(__name__)


async def run_composition_stage(
    stages: list[PipelineStageStatus],
    chunk_clips: list[str],
    voiceover_path: str | None,
    srt_path: str,
    caption_style: str,
    scene_transitions: list[str | None],
    music_preset: str,
    music_volume: float,
    style: str,
    niche: str | None,
    work_dir: str,
    on_progress: Callable[[str, str, int], Awaitable[None]] | None = None,
) -> str:
    """Compose video clips, audio, captions, and music. Returns final video path."""
    if on_progress:
        try:
            await on_progress("composition", "Composing video", 85)
        except Exception as _e:
            logger.debug("Progress callback error: %s", _e)

    stages.append(PipelineStageStatus(stage="composition", status="running"))

    with_audio_dest = os.path.join(work_dir, "with_audio.mp4")
    composed_path = await ffmpeg.compose_video(
        scene_videos=chunk_clips,
        voiceover_path=voiceover_path,
        srt_path=srt_path,
        caption_style=caption_style,
        output_path=os.path.join(work_dir, "composed.mp4"),
        save_intermediate_to=with_audio_dest,
        scene_transitions=scene_transitions,
    )

    if music_preset != "none":
        composed_path = await _mix_music(
            stages=stages,
            composed_path=composed_path,
            music_preset=music_preset,
            music_volume=music_volume,
            style=style,
            niche=niche,
            work_dir=work_dir,
        )

    stages[-1].status = "completed"
    return composed_path


async def _mix_music(
    stages: list[PipelineStageStatus],
    composed_path: str,
    music_preset: str,
    music_volume: float,
    style: str,
    niche: str | None,
    work_dir: str,
) -> str:
    from config import get_settings
    _cfg = get_settings()
    music_file: str | None = None
    lyria_tmp: str | None = None

    if music_preset == "lyria":
        if _cfg.google_cloud_project:
            try:
                from services.media import lyria as lyria_svc
                lyria_tmp = await lyria_svc.generate_music(
                    music_preset="lyria",
                    project_id=_cfg.google_cloud_project,
                    location=_cfg.vertex_ai_location,
                    style=style,
                    niche=niche,
                )
                music_file = lyria_tmp
            except Exception as _lyr_exc:
                logger.warning("Lyria failed — skipping music: %s", _lyr_exc)
        else:
            logger.warning("Lyria selected but GOOGLE_CLOUD_PROJECT not set — skipping music")
    else:
        static_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "..", "assets", "music", f"{music_preset}.mp3"
        )
        if os.path.exists(static_path):
            music_file = static_path
        else:
            logger.warning("Static music preset not found: %s — skipping music", static_path)

    if music_file:
        music_out = os.path.join(work_dir, "composed_music.mp4")
        composed_path = await ffmpeg.mix_background_music(
            video_path=composed_path,
            music_path=music_file,
            music_volume=music_volume,
            output_path=music_out,
        )
        stages[-1].detail = f"Composition + background music ({'lyria' if lyria_tmp else music_preset})"
        if lyria_tmp:
            try:
                os.unlink(lyria_tmp)
            except OSError:
                pass

    return composed_path
