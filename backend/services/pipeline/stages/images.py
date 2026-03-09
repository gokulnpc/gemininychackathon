"""Stage 4: Image generation (character sheet + scene images) and animation."""

from __future__ import annotations

import logging
import os
from collections.abc import Awaitable, Callable

from models.schemas import PipelineStageStatus, ScriptGenerationResponse
from services.media import ffmpeg

logger = logging.getLogger(__name__)


async def run_image_generation_stage(
    stages: list[PipelineStageStatus],
    script: ScriptGenerationResponse,
    art_style: str,
    user_reference_path: str | None,
    user_character_role: str | None,
    on_progress: Callable[[str, str, int], Awaitable[None]] | None = None,
) -> tuple[list[str], str | None, str | None]:
    """Generate character sheet and all scene images.

    Returns (all_image_paths, character_ref_path, char_sheet_path).
    """
    if on_progress:
        try:
            await on_progress("video_generation", "Creating scene images", 25)
        except Exception as _e:
            logger.debug("Progress callback error: %s", _e)

    stages.append(PipelineStageStatus(
        stage="video_generation",
        status="running",
        detail=f"Method: Gemini image generation ({art_style} style)",
    ))

    from services.gemini import image as gemini_image_svc

    char_desc = script.metadata.get("character_description", "")
    character_ref_path: str | None = None
    char_sheet_path: str | None = None

    # Phase A: Generate character sheet for stable reference across scenes
    if user_reference_path and user_character_role == "main_character":
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

    # Phase B: Generate scene images
    all_image_paths: list[str] = []
    prev_image_path: str | None = None
    n_scenes = len(script.scenes)

    for scene_idx, scene in enumerate(script.scenes):
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

        if scene_idx == 0 and character_ref_path is None:
            character_ref_path = img_path

        prev_image_path = img_path
        all_image_paths.append(img_path)
        logger.info("Scene %d/%d generated → %s", scene_idx + 1, n_scenes, img_path)

        if on_progress:
            try:
                await on_progress(
                    "video_generation",
                    f"Creating scene image ({scene_idx + 1}/{n_scenes})",
                    25 + int(40 * (scene_idx + 1) / n_scenes),
                )
            except Exception as _e:
                logger.debug("Progress callback error: %s", _e)

    stages[-1].status = "completed"
    stages[-1].detail = (
        f"{len(all_image_paths)} images generated "
        f"({n_scenes} scenes, {art_style} style)"
    )

    return all_image_paths, character_ref_path, char_sheet_path


def animate_scenes(
    reviewed_image_paths: list[str],
    script: ScriptGenerationResponse,
    work_dir: str,
) -> tuple[list[str], list[str | None]]:
    """Animate reviewed scene images into video clips.

    Returns (chunk_clips, scene_transitions).
    """
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

    return chunk_clips, scene_transitions


def cleanup_images(
    all_image_paths: list[str],
    reviewed_image_paths: list[str],
    user_reference_path: str | None,
    char_sheet_path: str | None,
) -> None:
    """Delete generated images after animation; never deletes the user's original photo."""
    all_paths = set(all_image_paths) | set(reviewed_image_paths)
    for img_path in all_paths:
        if img_path == user_reference_path:
            continue
        try:
            os.unlink(img_path)
        except OSError:
            pass

    if char_sheet_path:
        try:
            os.unlink(char_sheet_path)
        except OSError:
            pass
