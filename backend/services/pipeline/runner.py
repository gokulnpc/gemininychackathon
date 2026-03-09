"""Pipeline orchestrator — coordinates all stages end-to-end."""

from __future__ import annotations

import logging
import os
from collections.abc import Awaitable, Callable
from uuid import UUID

from models.schemas import (
    PipelineStageStatus,
    ScriptGenerationResponse,
    SeriesConfig,
)
from services.pipeline.config import resolve_series_settings
from services.pipeline.stages import (
    captions,
    composition,
    export,
    images,
    script,
    thumbnail,
    timeline,
    visual_qa,
    voiceover,
)

logger = logging.getLogger(__name__)


async def run_pipeline_stages(
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
    pre_generated_script: ScriptGenerationResponse | None = None,
    user_reference_path: str | None = None,
    user_character_role: str | None = None,
    on_progress: Callable[[str, str, int], Awaitable[None]] | None = None,
) -> tuple[list[PipelineStageStatus], dict[str, str], ScriptGenerationResponse | None, str | None, list[dict], dict]:
    """Run pipeline stages 2–7: script → video → voiceover → captions → compose → upload.

    Returns (stages, video_urls, script, thumbnail_url, visual_qa_report, project_json).
    Raises on unrecoverable errors — caller should catch and mark stage as failed.
    """
    settings = resolve_series_settings(series, video_duration, caption_style_override)

    stages: list[PipelineStageStatus] = []

    # Stage 2: Script generation
    generated_script = await script.run_script_stage(
        stages=stages,
        pre_generated_script=pre_generated_script,
        transcript=transcript,
        target_platforms=target_platforms,
        style=style,
        video_duration=settings["resolved_duration"],
        brand_voice=brand_voice,
        cta_preference=cta_preference,
        niche=settings["niche"],
        art_style=settings["art_style"],
        video_format=settings["video_format"],
    )

    # Stage 3: TTS voiceover + STT word timestamps
    voiceover_path, word_timestamps = await voiceover.run_voiceover_stage(
        stages=stages,
        script=generated_script,
        voice_id=settings["voice_id"],
        resolved_duration=settings["resolved_duration"],
        on_progress=on_progress,
    )

    # Stage 4: Image generation (character sheet + all scene images)
    all_image_paths, character_ref_path, char_sheet_path = await images.run_image_generation_stage(
        stages=stages,
        script=generated_script,
        art_style=settings["art_style"],
        user_reference_path=user_reference_path,
        user_character_role=user_character_role,
        on_progress=on_progress,
    )

    char_desc = generated_script.metadata.get("character_description", "")

    # Stage 4c: Visual Quality Director
    reviewed_image_paths, qa_report = await visual_qa.run_visual_qa_stage(
        stages=stages,
        all_image_paths=all_image_paths,
        script=generated_script,
        char_desc=char_desc,
        art_style=settings["art_style"],
        user_reference_path=user_reference_path,
        character_ref_path=character_ref_path,
        on_progress=on_progress,
    )

    # Animate reviewed images → video clips, then clean up images
    chunk_clips, scene_transitions = images.animate_scenes(
        reviewed_image_paths=reviewed_image_paths,
        script=generated_script,
        work_dir=work_dir,
    )
    images.cleanup_images(
        all_image_paths=all_image_paths,
        reviewed_image_paths=reviewed_image_paths,
        user_reference_path=user_reference_path,
        char_sheet_path=char_sheet_path,
    )

    # Stage 4b: Thumbnail
    thumbnail_url = await thumbnail.run_thumbnail_stage(
        stages=stages,
        script=generated_script,
        char_desc=char_desc,
        art_style=settings["art_style"],
        project_id=project_id,
        on_progress=on_progress,
    )

    # Stage 5: Captions
    srt_path = await captions.run_captions_stage(
        stages=stages,
        word_timestamps=word_timestamps,
        caption_style=settings["caption_style"],
        work_dir=work_dir,
        on_progress=on_progress,
    )

    # Stage 6: Video composition + music
    with_audio_dest = os.path.join(work_dir, "with_audio.mp4")
    composed_path = await composition.run_composition_stage(
        stages=stages,
        chunk_clips=chunk_clips,
        voiceover_path=voiceover_path,
        srt_path=srt_path,
        caption_style=settings["caption_style"],
        scene_transitions=scene_transitions,
        music_preset=settings["music_preset"],
        music_volume=settings["music_volume"],
        style=style,
        niche=settings["niche"],
        work_dir=work_dir,
        on_progress=on_progress,
    )

    # Stage 7: Platform export + GCS upload
    video_urls, scene_gcs_urls, voiceover_gcs_url = await export.run_export_stage(
        stages=stages,
        composed_path=composed_path,
        target_platforms=target_platforms,
        project_id=project_id,
        work_dir=work_dir,
        with_audio_dest=with_audio_dest,
        chunk_clips=chunk_clips,
        voiceover_path=voiceover_path,
        on_progress=on_progress,
    )

    # Timeline JSON
    project_json = await timeline.run_timeline_stage(
        project_id=project_id,
        script=generated_script,
        scene_gcs_urls=scene_gcs_urls,
        voiceover_gcs_url=voiceover_gcs_url,
        word_timestamps=word_timestamps,
        caption_style=settings["caption_style"],
        music_preset=settings["music_preset"],
        music_volume=settings["music_volume"],
    )

    return stages, video_urls, generated_script, thumbnail_url, qa_report, project_json
