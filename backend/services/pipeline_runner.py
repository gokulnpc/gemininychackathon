"""Shared pipeline execution logic for VoiceVid.

Both endpoints use this:
  POST /api/v1/projects/{id}/process       — Option A (manual form)
  POST /api/v1/projects/{id}/smart-process — Option B (voice idea → Nemotron auto-config)
"""

from __future__ import annotations

import logging
import os
from uuid import UUID

from models.schemas import (
    PipelineStageStatus,
    ScriptGenerationResponse,
    SeriesConfig,
)
from services import captions, ffmpeg, gcs, veo_video
from services.gemini_agent import generate_script_with_agent

logger = logging.getLogger(__name__)

# Duration range string → integer seconds
DURATION_MAP = {
    "15-30": 25,
    "30-40": 35,
    "60+": 60,
}


async def run_pipeline_stages(
    project_id: UUID,
    transcript: str,
    series: SeriesConfig | None,
    series_id: str | None,
    target_platforms: list,           # list[Platform]
    style: str,
    video_duration: int,
    caption_style_override: str,
    brand_voice: str | None,
    cta_preference: str | None,
    work_dir: str,
    pre_generated_script: ScriptGenerationResponse | None = None,
) -> tuple[list[PipelineStageStatus], dict[str, str], ScriptGenerationResponse | None]:
    """Run pipeline stages 2–7: script → video → voiceover → captions → compose → upload.

    Returns (stages, video_urls, script).
    Raises on unrecoverable errors — caller should catch and mark stage as failed.
    """
    stages: list[PipelineStageStatus] = []

    # ── Resolve effective settings from series (series overrides request defaults) ──
    voice_id = series.voice_id if series else "21m00Tcm4TlvDq8ikWAM"
    language = series.language if series else "en-US"
    art_style = series.art_style.value if series else "realism"
    video_format = series.video_format.value if series else "storytelling"
    niche = series.niche if series else None
    caption_style = series.caption_style.value if series else caption_style_override
    music_preset = series.background_music.value if series else "none"
    music_volume = series.music_volume if series else 0.15
    resolved_duration = (
        DURATION_MAP.get(series.video_duration.value, video_duration)
        if series else video_duration
    )

    return await _run_stages(
        stages=stages,
        project_id=project_id,
        transcript=transcript,
        series=series,
        series_id=series_id,
        target_platforms=target_platforms,
        style=style,
        video_duration=video_duration,
        caption_style_override=caption_style_override,
        brand_voice=brand_voice,
        cta_preference=cta_preference,
        work_dir=work_dir,
        voice_id=voice_id,
        language=language,
        art_style=art_style,
        video_format=video_format,
        niche=niche,
        caption_style=caption_style,
        music_preset=music_preset,
        music_volume=music_volume,
        resolved_duration=resolved_duration,
        pre_generated_script=pre_generated_script,
    )


async def _run_stages(
    stages: list[PipelineStageStatus],
    project_id: UUID,
    transcript: str,
    series: SeriesConfig | None,
    series_id: str | None,
    target_platforms: list,
    style: str,
    video_duration: int,
    caption_style_override: str,
    brand_voice: str | None,
    cta_preference: str | None,
    work_dir: str,
    voice_id: str,
    language: str,
    art_style: str,
    video_format: str,
    niche: str | None,
    caption_style: str,
    music_preset: str,
    music_volume: float,
    resolved_duration: int,
    pre_generated_script: ScriptGenerationResponse | None = None,
) -> tuple[list[PipelineStageStatus], dict[str, str], ScriptGenerationResponse | None]:
    """Inner function containing the actual pipeline stage logic."""

    # ── Stage 2: Claude Agent Script Generation ───────────────────────────────
    if pre_generated_script is not None:
        # User already reviewed and confirmed this script — skip generation
        script = pre_generated_script
        stages.append(PipelineStageStatus(
            stage="script_generation",
            status="completed",
            detail=f"Using pre-confirmed script: {len(script.scenes)} scenes",
        ))
        quality_score = script.metadata.get("agent_quality_score", "n/a")
    else:
        stages.append(PipelineStageStatus(
            stage="script_generation",
            status="running",
            detail="Claude agent: search_trending_hooks → analyze_brand_voice → draft → validate",
        ))

        script_data = await generate_script_with_agent(
            transcript=transcript,
            target_platforms=[p.value for p in target_platforms],
            style=style,
            video_duration=resolved_duration,
            brand_voice=brand_voice,
            cta_preference=cta_preference,
            niche=niche,
            art_style=art_style,
            video_format=video_format,
        )

        script = ScriptGenerationResponse(**script_data)
        quality_score = script.metadata.get("agent_quality_score", "n/a")
        stages[-1].status = "completed"
        stages[-1].detail = f"{len(script.scenes)} scenes planned, quality={quality_score}/100"

    voiceover_path = None
    word_timestamps = captions.generate_word_timestamps_from_script(
        voiceover_text=script.voiceover_full_script,
        total_duration=resolved_duration,
    )

    # ── Stage 4: Video Generation — one Veo 3 clip per scene ─────────────────
    stages.append(PipelineStageStatus(
        stage="video_generation",
        status="running",
        detail="Method: Veo 3 on Vertex AI (one video clip per scene)",
    ))

    SHOT_VARIATIONS = [
        "wide establishing shot",
        "close-up detail shot",
        "medium shot from a different angle",
        "low angle dramatic perspective",
        "overhead bird's eye view",
        "shallow depth of field foreground focus",
    ]

    chunk_clips: list[str] = []

    for scene_idx, scene in enumerate(script.scenes):
        shot = SHOT_VARIATIONS[scene_idx % len(SHOT_VARIATIONS)]
        prompt = f"{scene.visual_prompt or ''}, {shot}"
        clip_duration = max(5, min(8, scene.duration_seconds))

        clip_path = os.path.join(work_dir, f"scene_{scene_idx + 1}.mp4")
        tmp = await veo_video.generate_video_clip(
            prompt=prompt,
            duration_seconds=clip_duration,
        )
        import shutil
        shutil.move(tmp, clip_path)
        chunk_clips.append(clip_path)
        logger.info("Scene %d/%d clip → %s", scene_idx + 1, len(script.scenes), clip_path)

    stages[-1].status = "completed"
    stages[-1].detail = (
        f"{len(chunk_clips)} Veo 3 clips generated "
        f"({len(script.scenes)} scenes) via Vertex AI"
    )

    # ── Stage 5: Caption Generation ──────────────────────────────────────────
    stages.append(PipelineStageStatus(stage="captions", status="running"))

    srt_path = captions.generate_srt(
        word_timestamps=word_timestamps,
        style=caption_style,
        output_path=os.path.join(work_dir, "captions.srt"),
    )

    stages[-1].status = "completed"
    stages[-1].detail = f"Generated {caption_style} captions"

    # ── Stage 6: Video Composition ───────────────────────────────────────────
    stages.append(PipelineStageStatus(stage="composition", status="running"))

    composed_path = await ffmpeg.compose_video(
        scene_videos=chunk_clips,
        voiceover_path=voiceover_path,
        srt_path=srt_path,
        caption_style=caption_style,
        output_path=os.path.join(work_dir, "composed.mp4"),
    )

    if music_preset != "none":
        music_file = os.path.join(
            os.path.dirname(__file__), "..", "assets", "music", f"{music_preset}.mp3"
        )
        if os.path.exists(music_file):
            music_out = os.path.join(work_dir, "composed_music.mp4")
            composed_path = ffmpeg.mix_background_music(
                video_path=composed_path,
                music_path=music_file,
                music_volume=music_volume,
                output_path=music_out,
            )
            stages[-1].detail = f"Composition + background music ({music_preset})"
        else:
            logger.warning("Music preset file not found: %s — skipping music", music_file)

    stages[-1].status = "completed"

    # ── Stage 7: Platform Export & S3 Upload ─────────────────────────────────
    stages.append(PipelineStageStatus(stage="export_upload", status="running"))

    video_urls: dict[str, str] = {}
    for platform in target_platforms:
        platform_path = ffmpeg.export_for_platform(
            video_path=composed_path,
            platform=platform.value,
            output_path=os.path.join(work_dir, f"final_{platform.value}.mp4"),
        )
        s3_key = f"projects/{project_id}/{platform.value}/final.mp4"
        url = await gcs.upload_file(
            local_path=platform_path,
            s3_key=s3_key,
            content_type="video/mp4",
        )
        video_urls[platform.value] = url

    master_key = f"projects/{project_id}/master/composed.mp4"
    master_url = await gcs.upload_file(composed_path, master_key)
    video_urls["master"] = master_url

    stages[-1].status = "completed"
    stages[-1].detail = f"Uploaded {len(video_urls)} versions to GCS"

    return stages, video_urls, script
