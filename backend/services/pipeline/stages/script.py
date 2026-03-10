"""Stage 2: Script generation via Gemini agent."""

from __future__ import annotations

import logging

from models.schemas import PipelineStageStatus, ScriptGenerationResponse
from services.gemini.agent import generate_script_with_agent

logger = logging.getLogger(__name__)


async def run_script_stage(
    stages: list[PipelineStageStatus],
    pre_generated_script: ScriptGenerationResponse | None,
    transcript: str,
    target_platforms: list,
    style: str,
    video_duration: int,
    brand_voice: str | None,
    cta_preference: str | None,
    niche: str | None,
    art_style: str,
    video_format: str,
    subject_description: str | None = None,
) -> ScriptGenerationResponse:
    if pre_generated_script is not None:
        script = pre_generated_script
        stages.append(PipelineStageStatus(
            stage="script_generation",
            status="completed",
            detail=f"Using pre-confirmed script: {len(script.scenes)} scenes",
        ))
        return script

    stages.append(PipelineStageStatus(
        stage="script_generation",
        status="running",
        detail="Claude agent: search_trending_hooks → analyze_brand_voice → draft → validate",
    ))

    script_data = await generate_script_with_agent(
        transcript=transcript,
        target_platforms=[p.value for p in target_platforms],
        style=style,
        video_duration=video_duration,
        brand_voice=brand_voice,
        cta_preference=cta_preference,
        niche=niche,
        art_style=art_style,
        video_format=video_format,
        subject_description=subject_description,
    )

    script = ScriptGenerationResponse(**script_data)
    quality_score = script.metadata.get("agent_quality_score", "n/a")
    stages[-1].status = "completed"
    stages[-1].detail = f"{len(script.scenes)} scenes planned, quality={quality_score}/100"

    return script
