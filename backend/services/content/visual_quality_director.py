"""Visual Quality Director — Gemini-powered image QA agent.

Reviews each generated scene image against its original visual prompt, art style,
and character description. Images scoring below the quality threshold are regenerated
once with reinforced constraints before video composition begins.

This agent runs between Stage 4 (image generation) and Stage 4c (animation) in the
pipeline so that only approved frames make it into the final video.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os

from models.schemas import Scene

logger = logging.getLogger(__name__)

# Per-image quality threshold (0–10 scale). Images scoring below this overall score
# are regenerated once with a strongly enforced prompt.
QUALITY_THRESHOLD = 5


def _build_review_prompt(
    visual_prompt: str,
    character_description: str,
    art_style: str,
    scene_emotion: str,
) -> str:
    return (
        f"You are a visual quality director reviewing a generated scene image for a short-form social video.\n\n"
        f"Expected visual prompt: {visual_prompt}\n"
        f"Expected character: {character_description or 'N/A'}\n"
        f"Expected art style: {art_style}\n"
        f"Expected emotion/mood: {scene_emotion}\n\n"
        f"Review the provided image and score it on a scale of 0-10 for each dimension:\n"
        f"- style_match: Does the image match the expected art style?\n"
        f"- character_match: Does the character look consistent with the description? (10 if no character)\n"
        f"- composition: Is the composition well-framed, vertical 9:16, visually compelling?\n"
        f"- overall: Overall quality score (0-10)\n\n"
        f"Respond ONLY with a JSON object in this exact format:\n"
        f'{{"style_match": <0-10>, "character_match": <0-10>, "composition": <0-10>, '
        f'"overall": <0-10>, "issue": "<brief description of main issue or empty string>"}}'
    )


def _invoke_review(image_path: str, prompt: str) -> dict:
    """Synchronous Gemini 2.5 Pro vision call for image review."""
    from google.genai import types
    from PIL import Image as PILImage

    from services.gemini.client import get_client

    client = get_client()  # Vertex AI on GCP, API key locally
    img = PILImage.open(image_path).convert("RGB")

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=[prompt, img],
        config=types.GenerateContentConfig(
            temperature=0.1,
            max_output_tokens=1024,
            response_mime_type="application/json",
        ),
    )

    return json.loads(response.text or "{}")


async def review_and_fix_scenes(
    scene_images: list[str],
    scenes: list[Scene],
    character_description: str,
    art_style: str,
    user_reference_path: str | None,
    character_ref_path: str | None,
) -> tuple[list[str], list[dict]]:
    """Review generated scene images and regenerate those below quality threshold.

    For each scene image:
    1. Gemini 2.5 Pro vision call → JSON score { style_match, character_match, composition, overall }
    2. If overall < QUALITY_THRESHOLD: call generate_image() once with reinforced constraints
    3. Return final image paths (may include replacements) + per-scene quality report

    Non-blocking: if review or regeneration fails for a scene, the original is kept.

    Args:
        scene_images:       Ordered list of generated PNG paths (one per scene).
        scenes:             Corresponding Scene objects from the script.
        character_description: Character description from script.metadata.
        art_style:          Art style string (e.g. "cinematic").
        user_reference_path: Optional user reference photo path.
        character_ref_path:  Character sheet or scene-1 anchor path.

    Returns:
        (reviewed_paths, quality_report)
        - reviewed_paths: final image paths (originals or replacements)
        - quality_report: list of dicts with per-scene scores + regenerated flag
    """
    from services.gemini import image as gemini_image_svc

    reviewed_paths: list[str] = list(scene_images)  # copy, we may replace entries
    quality_report: list[dict] = []

    for idx, (img_path, scene) in enumerate(zip(scene_images, scenes)):
        if not os.path.exists(img_path):
            quality_report.append({"scene_idx": idx, "skipped": True, "reason": "image not found"})
            continue

        prompt = _build_review_prompt(
            visual_prompt=scene.visual_prompt or "",
            character_description=character_description,
            art_style=art_style,
            scene_emotion=scene.emotion,
        )

        try:
            scores = await asyncio.to_thread(_invoke_review, img_path, prompt)
        except Exception as exc:
            logger.warning("VQD review failed for scene %d: %s — keeping original", idx + 1, exc)
            quality_report.append({"scene_idx": idx, "error": str(exc), "regenerated": False})
            continue

        overall = scores.get("overall", 10)
        report_entry = {"scene_idx": idx, "regenerated": False, **scores}

        if overall < QUALITY_THRESHOLD:
            issue = scores.get("issue", "")
            logger.info(
                "VQD: scene %d scored %s/10 (%s) — regenerating",
                idx + 1, overall, issue,
            )
            # Build a strongly reinforced prompt for regeneration
            reinforced_prompt = (
                f"{scene.visual_prompt or ''}. "
                f"CRITICAL: Fix these issues: {issue}. "
                f"Art style must match {art_style} precisely. "
                f"Character must match description exactly. "
                f"Vertical 9:16 portrait, high quality."
            )
            try:
                new_img_path = await gemini_image_svc.generate_image(
                    prompt=reinforced_prompt,
                    art_style=art_style,
                    character_reference_path=character_ref_path,
                    user_reference_path=user_reference_path,
                    user_character_role=None,  # don't re-apply role instruction on regen
                )
                reviewed_paths[idx] = new_img_path
                report_entry["regenerated"] = True
                logger.info("VQD: scene %d regenerated → %s", idx + 1, new_img_path)
            except Exception as regen_exc:
                logger.warning(
                    "VQD regeneration failed for scene %d: %s — keeping original",
                    idx + 1, regen_exc,
                )
                report_entry["regen_error"] = str(regen_exc)
        else:
            logger.debug("VQD: scene %d passed (%s/10)", idx + 1, overall)

        quality_report.append(report_entry)

    return reviewed_paths, quality_report
