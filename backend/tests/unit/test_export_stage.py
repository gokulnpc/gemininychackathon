from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest

from models.schemas import PipelineStageStatus
from services.pipeline.stages import export


@pytest.mark.unit
def test_audio_upload_target_for_wav():
    filename, content_type = export._audio_upload_target("/tmp/voiceover.wav")
    assert filename == "voiceover.wav"
    assert content_type == "audio/wav"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_export_stage_uploads_images_and_wav_voiceover(tmp_path, monkeypatch):
    composed_path = tmp_path / "composed.mp4"
    with_audio_path = tmp_path / "with_audio.mp4"
    clip_path = tmp_path / "scene_1.mp4"
    image_path = tmp_path / "scene_1.png"
    voiceover_path = tmp_path / "voiceover.wav"

    for path in [composed_path, with_audio_path, clip_path, image_path, voiceover_path]:
        path.write_bytes(b"data")

    uploaded: list[tuple[str, str, str]] = []

    async def _fake_upload(local_path: str, gcs_key: str, content_type: str = "video/mp4") -> str:
        uploaded.append((local_path, gcs_key, content_type))
        return f"https://example.test/{gcs_key}"

    async def _fake_export_for_platform(video_path: str, platform: str, output_path: str) -> str:
        assert video_path == str(composed_path)
        out = tmp_path / f"{platform}.mp4"
        out.write_bytes(b"platform")
        return str(out)

    monkeypatch.setattr(export.gcs, "upload_file", _fake_upload)
    monkeypatch.setattr(export.ffmpeg, "export_for_platform", _fake_export_for_platform)

    stages: list[PipelineStageStatus] = []
    result = await export.run_export_stage(
        stages=stages,
        composed_path=str(composed_path),
        target_platforms=[SimpleNamespace(value="instagram_reels")],
        project_id=uuid4(),
        work_dir=str(tmp_path),
        with_audio_dest=str(with_audio_path),
        chunk_clips=[str(clip_path)],
        reviewed_image_paths=[str(image_path)],
        voiceover_path=str(voiceover_path),
        voiceover_duration_seconds=7.4,
    )

    assert len(result.scene_image_gcs_urls) == 1
    assert "/scene_images/scene_1.png" in result.scene_image_gcs_urls[0]
    assert result.voiceover_gcs_url.endswith("/master/voiceover.wav")
    assert result.artifact_manifest["editable_assets"]["voiceover_duration"] == 7.4

    upload_map = {gcs_key: content_type for _, gcs_key, content_type in uploaded}
    voiceover_key = next(key for key in upload_map if key.endswith("master/voiceover.wav"))
    image_key = next(key for key in upload_map if "/scene_images/" in key)
    assert upload_map[voiceover_key] == "audio/wav"
    assert upload_map[image_key] == "image/png"
    assert stages[-1].status == "completed"
