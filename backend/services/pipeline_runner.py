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
from services import captions, ffmpeg, gcs
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
    voice_id = series.voice_id if series else "Aoede"
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

    # ── Stage 3: TTS Voiceover ───────────────────────────────────────────────
    stages.append(PipelineStageStatus(stage="voiceover", status="running", detail=f"Gemini TTS: voice={voice_id}"))
    voiceover_path: str | None = None
    try:
        from services import gemini_tts
        voiceover_path = await gemini_tts.generate_voiceover(
            text=script.voiceover_full_script,
            voice_name=voice_id,
        )
        stages[-1].status = "completed"
        stages[-1].detail = f"Gemini TTS: voice={voice_id}"
    except Exception as _tts_exc:
        logger.warning("TTS generation failed (video will have no voiceover): %s", _tts_exc)
        stages[-1].status = "failed"
        stages[-1].detail = str(_tts_exc)

    word_timestamps = captions.generate_word_timestamps_from_script(
        voiceover_text=script.voiceover_full_script,
        total_duration=resolved_duration,
    )

    # ── Stage 4: Image Generation — one Gemini image per scene (5s each) ──────
    stages.append(PipelineStageStatus(
        stage="video_generation",
        status="running",
        detail=f"Method: Gemini image generation ({art_style} style, 1 image per 5s)",
    ))

    # Camera move sequence — cinematic variety across scenes
    EFFECT_VARIATIONS = [
        "dolly_in",
        "crane_down",
        "zoom_in_right",
        "dolly_out",
        "zoom_in_left",
        "crane_up",
    ]

    chunk_clips: list[str] = []
    character_ref_path: str | None = None   # first-scene PNG — reused for character consistency
    prev_image_path: str | None = None       # previous-scene PNG — chained for smooth evolution

    from services import gemini_image as gemini_image_svc

    char_desc = script.metadata.get("character_description", "")

    for scene_idx, scene in enumerate(script.scenes):
        effect = EFFECT_VARIATIONS[scene_idx % len(EFFECT_VARIATIONS)]
        clip_duration = max(5, min(8, scene.duration_seconds))

        # Enrich prompt with character description for scenes after the first
        prompt = scene.visual_prompt or ""
        if char_desc and scene_idx > 0:
            prompt = f"{prompt}. Maintain consistent character: {char_desc}"

        # ── Generate image (Gemini image model) ───────────────────────────────
        img_path = await gemini_image_svc.generate_image(
            prompt=prompt,
            art_style=art_style,
            previous_image_path=prev_image_path,
            character_reference_path=character_ref_path,
        )

        # First scene image becomes the character reference for all subsequent scenes
        if scene_idx == 0:
            character_ref_path = img_path

        # ── Animate image → video clip ─────────────────────────────────────────
        clip_path = os.path.join(work_dir, f"scene_{scene_idx + 1}.mp4")
        ffmpeg.animate_image(
            image_path=img_path,
            effect=effect,
            duration=clip_duration,
            output_path=clip_path,
        )

        # Keep image around for next scene chaining, clean up after that
        if prev_image_path and prev_image_path != character_ref_path:
            try:
                os.unlink(prev_image_path)
            except OSError:
                pass
        prev_image_path = img_path

        chunk_clips.append(clip_path)
        logger.info("Scene %d/%d: image → %s, clip → %s", scene_idx + 1, len(script.scenes), img_path, clip_path)

    # Clean up final scene image
    if prev_image_path and prev_image_path != character_ref_path:
        try:
            os.unlink(prev_image_path)
        except OSError:
            pass
    if character_ref_path:
        try:
            os.unlink(character_ref_path)
        except OSError:
            pass

    stages[-1].status = "completed"
    stages[-1].detail = (
        f"{len(chunk_clips)} images generated and animated "
        f"({len(script.scenes)} scenes, {art_style} style)"
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
        gcs_key = f"projects/{project_id}/{platform.value}/final.mp4"
        url = await gcs.upload_file(
            local_path=platform_path,
            gcs_key=gcs_key,
            content_type="video/mp4",
        )
        video_urls[platform.value] = url

    master_key = f"projects/{project_id}/master/composed.mp4"
    master_url = await gcs.upload_file(composed_path, master_key)
    video_urls["master"] = master_url

    stages[-1].status = "completed"
    stages[-1].detail = f"Uploaded {len(video_urls)} versions to GCS"

    return stages, video_urls, script
