"""Pipeline orchestrator — coordinates all stages end-to-end."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
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


@dataclass
class PipelineArtifacts:
    voiceover: voiceover.VoiceoverStageResult | None = None
    caption_asset: captions.CaptionsStageResult | None = None
    reviewed_image_paths: list[str] = field(default_factory=list)
    scene_motion_effects: list[str | None] = field(default_factory=list)
    scene_transitions: list[str | None] = field(default_factory=list)
    chunk_clips: list[str] = field(default_factory=list)
    video_urls: dict[str, str] = field(default_factory=dict)
    scene_video_gcs_urls: list[str] = field(default_factory=list)
    scene_image_gcs_urls: list[str] = field(default_factory=list)
    voiceover_gcs_url: str | None = None
    artifact_manifest: dict = field(default_factory=dict)


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
    artifacts = PipelineArtifacts()

    # Stage 1.5: Infer subject context from reference image (non-blocking)
    subject_description: str | None = None
    if user_reference_path:
        from services.gemini.image import describe_reference_subject
        subject_description = await describe_reference_subject(user_reference_path) or None

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
        subject_description=subject_description,
    )

    # Stage 3: TTS voiceover + STT word timestamps
    artifacts.voiceover = await voiceover.run_voiceover_stage(
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
    artifacts.reviewed_image_paths = reviewed_image_paths
    artifacts.chunk_clips, artifacts.scene_transitions = await images.animate_scenes(
        reviewed_image_paths=artifacts.reviewed_image_paths,
        script=generated_script,
        work_dir=work_dir,
    )
    from services.media import ffmpeg as ffmpeg_svc
    artifacts.scene_motion_effects = [
        ffmpeg_svc.emotion_to_effect(getattr(scene, "emotion", None))
        for scene in generated_script.scenes
    ]

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
    artifacts.caption_asset = await captions.run_captions_stage(
        stages=stages,
        word_timestamps=artifacts.voiceover.word_timestamps,
        caption_style=settings["caption_style"],
        work_dir=work_dir,
        on_progress=on_progress,
    )

    # Stage 6: Video composition + music
    with_audio_dest = os.path.join(work_dir, "with_audio.mp4")
    composed_path = await composition.run_composition_stage(
        stages=stages,
        chunk_clips=artifacts.chunk_clips,
        voiceover_path=artifacts.voiceover.voiceover_path,
        caption_asset_path=artifacts.caption_asset.path,
        caption_style=settings["caption_style"],
        scene_transitions=artifacts.scene_transitions,
        music_preset=settings["music_preset"],
        music_volume=settings["music_volume"],
        style=style,
        niche=settings["niche"],
        work_dir=work_dir,
        on_progress=on_progress,
    )

    # Stage 7: Platform export + GCS upload
    export_result = await export.run_export_stage(
        stages=stages,
        composed_path=composed_path,
        target_platforms=target_platforms,
        project_id=project_id,
        work_dir=work_dir,
        with_audio_dest=with_audio_dest,
        chunk_clips=artifacts.chunk_clips,
        reviewed_image_paths=artifacts.reviewed_image_paths,
        voiceover_path=artifacts.voiceover.voiceover_path,
        voiceover_duration_seconds=artifacts.voiceover.actual_duration,
        on_progress=on_progress,
    )
    artifacts.video_urls = export_result.video_urls
    artifacts.scene_video_gcs_urls = export_result.scene_video_gcs_urls
    artifacts.scene_image_gcs_urls = export_result.scene_image_gcs_urls
    artifacts.voiceover_gcs_url = export_result.voiceover_gcs_url
    artifacts.artifact_manifest = export_result.artifact_manifest

    # Timeline JSON
    try:
        project_json = await timeline.run_timeline_stage(
            project_id=project_id,
            script=generated_script,
            scene_gcs_urls=artifacts.scene_video_gcs_urls,
            scene_image_gcs_urls=artifacts.scene_image_gcs_urls,
            voiceover_gcs_url=artifacts.voiceover_gcs_url,
            voiceover_duration_seconds=artifacts.voiceover.actual_duration,
            word_timestamps=artifacts.voiceover.word_timestamps,
            caption_timing_source=artifacts.voiceover.timing_source,
            caption_style=settings["caption_style"],
            caption_render_mode=artifacts.caption_asset.render_mode,
            caption_style_effective=artifacts.caption_asset.style_effective,
            caption_degraded=artifacts.caption_asset.degraded,
            music_preset=settings["music_preset"],
            music_volume=settings["music_volume"],
            scene_motion_effects=artifacts.scene_motion_effects,
            scene_transitions=artifacts.scene_transitions,
            artifact_manifest={
                **artifacts.artifact_manifest,
                "caption_assets": {
                    "path": artifacts.caption_asset.path,
                    "format": artifacts.caption_asset.format,
                    "render_mode": artifacts.caption_asset.render_mode,
                    "style_requested": artifacts.caption_asset.style_requested,
                    "style_effective": artifacts.caption_asset.style_effective,
                    "degraded": artifacts.caption_asset.degraded,
                },
            },
        )
    finally:
        images.cleanup_images(
            all_image_paths=all_image_paths,
            reviewed_image_paths=artifacts.reviewed_image_paths,
            user_reference_path=user_reference_path,
            char_sheet_path=char_sheet_path,
        )

    return stages, artifacts.video_urls, generated_script, thumbnail_url, qa_report, project_json
