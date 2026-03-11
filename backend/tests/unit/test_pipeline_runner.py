from __future__ import annotations

from uuid import uuid4

import pytest

from models.schemas import CTA, Hook, Scene, ScriptGenerationResponse, SeriesConfig, VideoDurationRange
from services.pipeline.runner import run_pipeline_stages
from services.pipeline.stages.captions import CaptionsStageResult
from services.pipeline.stages.export import ExportStageResult
from services.pipeline.stages.voiceover import VoiceoverStageResult


@pytest.mark.unit
@pytest.mark.asyncio
async def test_runner_passes_image_canonical_assets_to_timeline(monkeypatch, tmp_path):
    script_response = ScriptGenerationResponse(
        metadata={"character_description": "A detective"},
        hook=Hook(text="Hook", duration=2),
        scenes=[
            Scene(scene_id=1, duration_seconds=4, voiceover_text="One", visual_prompt="Scene one", emotion="calm"),
            Scene(scene_id=2, duration_seconds=6, voiceover_text="Two", visual_prompt="Scene two", emotion="exciting"),
        ],
        cta=CTA(text="CTA"),
        voiceover_full_script="One Two",
    )

    series = SeriesConfig(
        series_name="Test",
        niche="mystery",
        art_style="cinematic",
        caption_style="bold_stroke",
        background_music="none",
        voice_id="Aoede",
        video_duration=VideoDurationRange.medium,
        video_format="storytelling",
    )

    timeline_calls: list[dict] = []
    cleanup_calls: list[dict] = []

    async def _script_stage(**kwargs):
        return script_response

    async def _voiceover_stage(**kwargs):
        return VoiceoverStageResult(
            voiceover_path="/tmp/voice.wav",
            word_timestamps=[{"word": "One", "start": 0.0, "end": 0.5}],
            timing_source="stt",
            actual_duration=8.2,
        )

    async def _image_stage(**kwargs):
        return ["/tmp/all1.png", "/tmp/all2.png"], "/tmp/ref.png", "/tmp/sheet.png"

    async def _visual_qa_stage(**kwargs):
        return ["/tmp/reviewed1.png", "/tmp/reviewed2.png"], [{"ok": True}]

    async def _animate_scenes(**kwargs):
        return ["/tmp/scene1.mp4", "/tmp/scene2.mp4"], ["fade", None]

    async def _thumbnail_stage(**kwargs):
        return "https://example.test/thumb.png"

    async def _captions_stage(**kwargs):
        return CaptionsStageResult(
            path=str(tmp_path / "captions.ass"),
            format="ass",
            render_mode="advanced_ass",
            style_requested="bold_stroke",
            style_effective="karaoke",
            degraded=False,
        )

    async def _composition_stage(**kwargs):
        return str(tmp_path / "composed.mp4")

    async def _export_stage(**kwargs):
        return ExportStageResult(
            video_urls={"master": "https://example.test/master.mp4"},
            scene_video_gcs_urls=["https://example.test/scenes/scene_1.mp4", "https://example.test/scenes/scene_2.mp4"],
            scene_image_gcs_urls=["https://example.test/scene_images/scene_1.png", "https://example.test/scene_images/scene_2.png"],
            voiceover_gcs_url="https://example.test/master/voiceover.wav",
            artifact_manifest={"editable_assets": {}},
        )

    async def _timeline_stage(**kwargs):
        timeline_calls.append(kwargs)
        return {"metadata": {"timeline_build_mode": "image_canonical"}}

    def _cleanup_images(**kwargs):
        cleanup_calls.append(kwargs)

    monkeypatch.setattr("services.pipeline.runner.script.run_script_stage", _script_stage)
    monkeypatch.setattr("services.pipeline.runner.voiceover.run_voiceover_stage", _voiceover_stage)
    monkeypatch.setattr("services.pipeline.runner.images.run_image_generation_stage", _image_stage)
    monkeypatch.setattr("services.pipeline.runner.visual_qa.run_visual_qa_stage", _visual_qa_stage)
    monkeypatch.setattr("services.pipeline.runner.images.animate_scenes", _animate_scenes)
    monkeypatch.setattr("services.pipeline.runner.thumbnail.run_thumbnail_stage", _thumbnail_stage)
    monkeypatch.setattr("services.pipeline.runner.captions.run_captions_stage", _captions_stage)
    monkeypatch.setattr("services.pipeline.runner.composition.run_composition_stage", _composition_stage)
    monkeypatch.setattr("services.pipeline.runner.export.run_export_stage", _export_stage)
    monkeypatch.setattr("services.pipeline.runner.timeline.run_timeline_stage", _timeline_stage)
    monkeypatch.setattr("services.pipeline.runner.images.cleanup_images", _cleanup_images)
    monkeypatch.setattr("services.media.ffmpeg.emotion_to_effect", lambda emotion: f"effect:{emotion}")

    _, video_urls, _, _, _, project_json = await run_pipeline_stages(
        project_id=uuid4(),
        transcript="One Two",
        series=series,
        series_id=None,
        target_platforms=[],
        style="modern_energetic",
        video_duration=30,
        caption_style_override="bold_stroke",
        brand_voice=None,
        cta_preference=None,
        work_dir=str(tmp_path),
        pre_generated_script=script_response,
    )

    assert video_urls["master"] == "https://example.test/master.mp4"
    assert project_json["metadata"]["timeline_build_mode"] == "image_canonical"
    assert timeline_calls[0]["scene_image_gcs_urls"][0].endswith("scene_1.png")
    assert timeline_calls[0]["voiceover_duration_seconds"] == 8.2
    assert timeline_calls[0]["caption_timing_source"] == "stt"
    assert timeline_calls[0]["caption_render_mode"] == "advanced_ass"
    assert timeline_calls[0]["caption_style_effective"] == "karaoke"
    assert timeline_calls[0]["artifact_manifest"]["caption_assets"]["format"] == "ass"
    assert timeline_calls[0]["scene_motion_effects"] == ["effect:calm", "effect:exciting"]
    assert cleanup_calls, "expected cleanup_images to run after timeline build"
