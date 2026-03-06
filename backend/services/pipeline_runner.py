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
    user_reference_path: str | None = None,
    user_character_role: str | None = None,
) -> tuple[list[PipelineStageStatus], dict[str, str], ScriptGenerationResponse | None, str | None, list[dict]]:
    """Run pipeline stages 2–7: script → video → voiceover → captions → compose → upload.

    Returns (stages, video_urls, script, thumbnail_url, visual_qa_report).
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
        user_reference_path=user_reference_path,
        user_character_role=user_character_role,
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
    user_reference_path: str | None = None,
    user_character_role: str | None = None,
) -> tuple[list[PipelineStageStatus], dict[str, str], ScriptGenerationResponse | None, str | None, list[dict]]:
    """Inner function containing the actual pipeline stage logic."""
    qa_report: list[dict] = []

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

    if voiceover_path:
        try:
            from services import stt as stt_svc
            word_timestamps = await stt_svc.extract_word_timestamps(voiceover_path)
        except Exception as _stt_exc:
            logger.warning("STT word timestamps failed — falling back to estimated: %s", _stt_exc)
            word_timestamps = captions.generate_word_timestamps_from_script(
                voiceover_text=script.voiceover_full_script,
                total_duration=resolved_duration,
            )
    else:
        word_timestamps = captions.generate_word_timestamps_from_script(
            voiceover_text=script.voiceover_full_script,
            total_duration=resolved_duration,
        )

    # ── Stage 4: Image Generation — one Gemini image per scene ──────────────
    stages.append(PipelineStageStatus(
        stage="video_generation",
        status="running",
        detail=f"Method: Gemini image generation ({art_style} style)",
    ))

    from services import gemini_image as gemini_image_svc

    char_desc = script.metadata.get("character_description", "")

    # ── Phase A: Generate a dedicated character sheet for stable reference ────
    # A purpose-built neutral-pose character image anchors all scene generations,
    # preventing the compounding drift that occurs when Scene 1's environment
    # contaminates the character reference.
    character_ref_path: str | None = None
    char_sheet_path: str | None = None  # tracked separately for cleanup

    if user_reference_path and user_character_role == "main_character":
        # User photo is the character anchor — no sheet needed
        character_ref_path = user_reference_path
    elif char_desc:
        try:
            char_sheet_path = await gemini_image_svc.generate_character_sheet(
                character_description=char_desc,
                art_style=art_style,
            )
            character_ref_path = char_sheet_path
            logger.info("Character sheet generated → %s", character_ref_path)
        except Exception as _cs_exc:
            logger.warning("Character sheet failed — will use scene 1 as anchor: %s", _cs_exc)

    # ── Phase B: Generate all scene images (kept alive for VQD review) ───────
    all_image_paths: list[str] = []
    prev_image_path: str | None = None

    for scene_idx, scene in enumerate(script.scenes):
        # Enrich prompt with character description for scenes after the first
        prompt = scene.visual_prompt or ""
        if char_desc and scene_idx > 0:
            prompt = f"{prompt}. Maintain consistent character: {char_desc}"

        img_path = await gemini_image_svc.generate_image(
            prompt=prompt,
            art_style=art_style,
            previous_image_path=prev_image_path,
            character_reference_path=character_ref_path,
            user_reference_path=user_reference_path,
            user_character_role=user_character_role,
        )

        # Fallback: if character sheet failed, use scene 1 as anchor
        if scene_idx == 0 and character_ref_path is None:
            character_ref_path = img_path

        prev_image_path = img_path
        all_image_paths.append(img_path)
        logger.info("Scene %d/%d generated → %s", scene_idx + 1, len(script.scenes), img_path)

    stages[-1].status = "completed"
    stages[-1].detail = (
        f"{len(all_image_paths)} images generated "
        f"({len(script.scenes)} scenes, {art_style} style)"
    )

    # ── Stage 4c: Visual Quality Director — review and fix low-quality images ─
    qa_report: list[dict] = []
    stages.append(PipelineStageStatus(
        stage="visual_qa",
        status="running",
        detail="Visual Quality Director: reviewing scene images",
    ))
    try:
        from services import visual_quality_director
        reviewed_image_paths, qa_report = await visual_quality_director.review_and_fix_scenes(
            scene_images=all_image_paths,
            scenes=script.scenes,
            character_description=char_desc,
            art_style=art_style,
            user_reference_path=user_reference_path,
            character_ref_path=character_ref_path,
        )
        improved = sum(1 for r in qa_report if r.get("regenerated"))
        stages[-1].status = "completed"
        stages[-1].detail = (
            f"VQD reviewed {len(qa_report)} scenes; {improved} improved"
        )
    except Exception as _vqd_exc:
        logger.warning("VQD failed (non-fatal, using original images): %s", _vqd_exc)
        reviewed_image_paths = all_image_paths
        stages[-1].status = "failed"
        stages[-1].detail = str(_vqd_exc)

    # ── Phase C: Animate reviewed images → video clips ────────────────────────
    # Use scene.emotion for camera effect and scene.duration_seconds for timing
    chunk_clips: list[str] = []
    scene_transitions: list[str | None] = []

    for scene_idx, (img_path, scene) in enumerate(zip(reviewed_image_paths, script.scenes)):
        effect = ffmpeg.emotion_to_effect(scene.emotion)
        clip_duration = getattr(scene, "duration_seconds", 2) or 2

        clip_path = os.path.join(work_dir, f"scene_{scene_idx + 1}.mp4")
        ffmpeg.animate_image(
            image_path=img_path,
            effect=effect,
            duration=clip_duration,
            output_path=clip_path,
        )
        chunk_clips.append(clip_path)
        scene_transitions.append(getattr(scene, "transition_to_next", None))
        logger.info(
            "Scene %d/%d: emotion=%s → effect=%s, duration=%ds → %s",
            scene_idx + 1, len(script.scenes), scene.emotion, effect, clip_duration, clip_path,
        )

    # Clean up all generated images (originals + any VQD replacements)
    all_paths_to_clean = set(all_image_paths) | set(reviewed_image_paths)
    for img_path in all_paths_to_clean:
        if img_path == user_reference_path:
            continue  # never delete the user's original photo
        try:
            os.unlink(img_path)
        except OSError:
            pass
    if char_sheet_path:
        try:
            os.unlink(char_sheet_path)
        except OSError:
            pass

    # ── Stage 4b: Thumbnail Generation ───────────────────────────────────────
    thumbnail_url: str | None = None
    stages.append(PipelineStageStatus(
        stage="thumbnail",
        status="running",
        detail="Generating catchy thumbnail with Gemini",
    ))
    try:
        hook_text = script.hook.text if script.hook else script.voiceover_full_script[:120]
        scene_visual = script.scenes[0].visual_prompt if script.scenes else hook_text
        thumb_path = await gemini_image_svc.generate_thumbnail(
            hook_text=hook_text,
            scene_visual_prompt=scene_visual,
            character_description=char_desc or None,
            art_style=art_style,
        )
        thumbnail_url = await gcs.upload_file(
            local_path=thumb_path,
            gcs_key=f"projects/{project_id}/thumbnail.jpg",
            content_type="image/jpeg",
        )
        try:
            os.unlink(thumb_path)
        except OSError:
            pass
        stages[-1].status = "completed"
        stages[-1].detail = f"Thumbnail uploaded → {thumbnail_url}"
    except Exception as _thumb_exc:
        logger.warning("Thumbnail generation failed (non-fatal): %s", _thumb_exc)
        stages[-1].status = "failed"
        stages[-1].detail = str(_thumb_exc)

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

    # Upload with_audio.mp4 so the recompose endpoint can regenerate captions/music
    if os.path.exists(with_audio_dest):
        await gcs.upload_file(
            with_audio_dest,
            f"projects/{project_id}/master/with_audio.mp4",
            content_type="video/mp4",
        )

    stages[-1].status = "completed"
    stages[-1].detail = f"Uploaded {len(video_urls)} versions to GCS"

    return stages, video_urls, script, thumbnail_url, qa_report
