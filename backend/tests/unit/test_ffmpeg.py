from __future__ import annotations

import asyncio
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from services.media import ffmpeg


class _FakeProcess:
    def __init__(self, *, stdout: bytes = b"", stderr: bytes = b"", returncode: int = 0):
        self._stdout = stdout
        self._stderr = stderr
        self.returncode = returncode
        self.killed = False

    async def communicate(self):
        return self._stdout, self._stderr

    def kill(self):
        self.killed = True


@pytest.mark.unit
def test_emotion_to_effect_known_and_default():
    assert ffmpeg.emotion_to_effect("dramatic") == "shaky"
    assert ffmpeg.emotion_to_effect("unknown") == "dolly_in"


@pytest.mark.unit
def test_build_zoompan_known_and_default():
    assert "zoompan=z='min(zoom+" in ffmpeg._build_zoompan("dolly_in", 5, 576, 1024)
    assert "iw-iw/zoom" in ffmpeg._build_zoompan("zoom_in_right", 5, 576, 1024)
    assert "sin(on*0.5)" in ffmpeg._build_zoompan("shaky", 5, 576, 1024)


@pytest.mark.unit
def test_concat_file_entry_escapes_quotes():
    entry = ffmpeg._concat_file_entry("/tmp/it's.mp4")
    assert entry == "file '/tmp/it'\\''s.mp4'\n"


@pytest.mark.unit
def test_escape_srt_path_escapes_specials():
    escaped = ffmpeg._escape_srt_path(r"/tmp/a:b'c.srt")
    assert escaped == r"/tmp/a\:b\'c.srt"


@pytest.mark.unit
def test_normalize_music_volume_clamps():
    assert ffmpeg._normalize_music_volume(-1) == 0.0
    assert ffmpeg._normalize_music_volume(2) == 1.0


@pytest.mark.unit
def test_validate_scene_videos_empty_raises():
    with pytest.raises(ffmpeg.MediaValidationError, match="scene_videos"):
        ffmpeg._validate_scene_videos([])


@pytest.mark.unit
def test_run_subprocess_missing_binary_raises(monkeypatch):
    async def _raise(*_args, **_kwargs):
        raise FileNotFoundError("missing")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _raise)

    with pytest.raises(ffmpeg.FFmpegError, match="binary not found"):
        asyncio.run(
            ffmpeg._run_subprocess(
                "ffmpeg",
                ["-version"],
                "show version",
                timeout=1,
                error_cls=ffmpeg.FFmpegError,
            )
        )


@pytest.mark.unit
def test_run_ffmpeg_non_zero_raises(monkeypatch):
    async def _fake_exec(*_args, **_kwargs):
        return _FakeProcess(stderr=b"boom", returncode=1)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake_exec)

    with pytest.raises(ffmpeg.FFmpegError, match="boom"):
        asyncio.run(ffmpeg._run_ffmpeg(["-version"], "version"))


@pytest.mark.unit
def test_run_ffmpeg_timeout_raises(monkeypatch):
    async def _fake_exec(*_args, **_kwargs):
        return _FakeProcess()

    async def _timeout(*_args, **_kwargs):
        if _args:
            maybe_coro = _args[0]
            close = getattr(maybe_coro, "close", None)
            if callable(close):
                close()
        raise asyncio.TimeoutError

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake_exec)
    monkeypatch.setattr(asyncio, "wait_for", _timeout)

    with pytest.raises(ffmpeg.FFmpegTimeoutError, match="timed out"):
        asyncio.run(ffmpeg._run_ffmpeg(["-version"], "version"))


@pytest.mark.unit
def test_run_ffprobe_success(monkeypatch):
    async def _fake_exec(*_args, **_kwargs):
        return _FakeProcess(stdout=b"1.23\n")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake_exec)

    stdout = asyncio.run(ffmpeg._run_ffprobe(["-v", "error"], "probe"))
    assert stdout == "1.23\n"


@pytest.mark.unit
def test_get_duration_invalid_output_raises(tmp_path, monkeypatch):
    media = tmp_path / "media.mp4"
    media.write_bytes(b"x")

    monkeypatch.setattr(
        ffmpeg,
        "_run_ffprobe",
        AsyncMock(return_value="not-a-duration"),
    )

    with pytest.raises(ffmpeg.FFprobeError, match="Invalid ffprobe duration output"):
        asyncio.run(ffmpeg._get_duration(str(media)))


@pytest.mark.unit
def test_has_audio_stream_uses_probe(tmp_path, monkeypatch):
    media = tmp_path / "media.mp4"
    media.write_bytes(b"x")
    monkeypatch.setattr(ffmpeg, "_run_ffprobe", AsyncMock(return_value="audio\n"))

    assert asyncio.run(ffmpeg._has_audio_stream(str(media))) is True


@pytest.mark.unit
def test_build_xfade_concat_empty_raises(tmp_path):
    with pytest.raises(ffmpeg.MediaValidationError, match="scene_videos"):
        asyncio.run(ffmpeg._build_xfade_concat([], [], str(tmp_path), str(tmp_path / "out.mp4")))


@pytest.mark.unit
def test_build_xfade_concat_single_scene_copies(tmp_path, monkeypatch):
    clip = tmp_path / "scene.mp4"
    clip.write_bytes(b"x")
    copy_mock = AsyncMock(return_value=str(tmp_path / "out.mp4"))
    monkeypatch.setattr(ffmpeg, "_copy_video", copy_mock)

    out = asyncio.run(ffmpeg._build_xfade_concat([str(clip)], [], str(tmp_path), str(tmp_path / "out.mp4")))

    assert out.endswith("out.mp4")
    copy_mock.assert_awaited_once()


@pytest.mark.unit
def test_build_xfade_concat_hard_cut_writes_concat(monkeypatch, tmp_path):
    clip1 = tmp_path / "a.mp4"
    clip2 = tmp_path / "b.mp4"
    clip1.write_bytes(b"a")
    clip2.write_bytes(b"b")
    run_mock = AsyncMock(return_value="")
    monkeypatch.setattr(ffmpeg, "_run_ffmpeg", run_mock)

    asyncio.run(ffmpeg._build_xfade_concat([str(clip1), str(clip2)], [], str(tmp_path), str(tmp_path / "out.mp4")))

    run_mock.assert_awaited_once()
    concat_file = tmp_path / "concat.txt"
    assert concat_file.exists()


@pytest.mark.unit
def test_build_xfade_concat_xfade_path(monkeypatch, tmp_path):
    clip1 = tmp_path / "a.mp4"
    clip2 = tmp_path / "b.mp4"
    clip1.write_bytes(b"a")
    clip2.write_bytes(b"b")
    run_mock = AsyncMock(return_value="")
    duration_mock = AsyncMock(side_effect=[2.0, 2.0])
    monkeypatch.setattr(ffmpeg, "_run_ffmpeg", run_mock)
    monkeypatch.setattr(ffmpeg, "_get_duration", duration_mock)

    asyncio.run(
        ffmpeg._build_xfade_concat(
            [str(clip1), str(clip2)],
            ["fade"],
            str(tmp_path),
            str(tmp_path / "out.mp4"),
        )
    )

    assert run_mock.await_count == 3
    final_cmd = run_mock.await_args_list[-1].args[0]
    assert "-filter_complex" in final_cmd
    assert "xfade=transition=fade" in final_cmd[final_cmd.index("-filter_complex") + 1]


@pytest.mark.unit
def test_build_xfade_concat_short_clip_raises(monkeypatch, tmp_path):
    clip1 = tmp_path / "a.mp4"
    clip2 = tmp_path / "b.mp4"
    clip1.write_bytes(b"a")
    clip2.write_bytes(b"b")
    monkeypatch.setattr(ffmpeg, "_run_ffmpeg", AsyncMock(return_value=""))
    monkeypatch.setattr(ffmpeg, "_get_duration", AsyncMock(side_effect=[0.2, 2.0]))

    with pytest.raises(ffmpeg.MediaValidationError, match="longer than 0.3"):
        asyncio.run(
            ffmpeg._build_xfade_concat(
                [str(clip1), str(clip2)],
                ["fade"],
                str(tmp_path),
                str(tmp_path / "out.mp4"),
            )
        )


@pytest.mark.unit
def test_animate_image_validates_missing_input():
    with pytest.raises(ffmpeg.MediaValidationError, match="image_path"):
        asyncio.run(ffmpeg.animate_image("/tmp/does-not-exist.png"))


@pytest.mark.unit
def test_animate_image_runs_ffmpeg(monkeypatch, tmp_path):
    image = tmp_path / "img.png"
    image.write_bytes(b"x")
    run_mock = AsyncMock(return_value="")
    monkeypatch.setattr(ffmpeg, "_run_ffmpeg", run_mock)

    out = asyncio.run(ffmpeg.animate_image(str(image), output_path=str(tmp_path / "out.mp4")))

    assert out.endswith("out.mp4")
    assert "-vf" in run_mock.await_args.args[0]


@pytest.mark.unit
def test_compose_video_concat_only(monkeypatch, tmp_path):
    clip = tmp_path / "scene.mp4"
    clip.write_bytes(b"x")
    concat_mock = AsyncMock(return_value=str(tmp_path / "concat.mp4"))
    copy_mock = AsyncMock(return_value=str(tmp_path / "out.mp4"))
    monkeypatch.setattr(ffmpeg, "_build_xfade_concat", concat_mock)
    monkeypatch.setattr(ffmpeg, "_copy_video", copy_mock)

    out = asyncio.run(ffmpeg.compose_video([str(clip)], output_path=str(tmp_path / "out.mp4")))

    assert out.endswith("out.mp4")
    concat_mock.assert_awaited_once()
    copy_mock.assert_awaited_once()


@pytest.mark.unit
def test_add_captions_runs_ffmpeg(monkeypatch, tmp_path):
    video = tmp_path / "video.mp4"
    srt = tmp_path / "captions.srt"
    video.write_bytes(b"x")
    srt.write_text("1\n00:00:00,000 --> 00:00:01,000\nhi\n", encoding="utf-8")
    run_mock = AsyncMock(return_value="")
    monkeypatch.setattr(ffmpeg, "_run_ffmpeg", run_mock)

    asyncio.run(ffmpeg.add_captions(str(video), str(srt), output_path=str(tmp_path / "out.mp4")))

    assert "subtitles='" in run_mock.await_args.args[0][run_mock.await_args.args[0].index("-vf") + 1]


@pytest.mark.unit
def test_add_captions_uses_plain_ass_filter(monkeypatch, tmp_path):
    video = tmp_path / "video.mp4"
    ass = tmp_path / "captions.ass"
    video.write_bytes(b"x")
    ass.write_text("[Script Info]\n", encoding="utf-8")
    run_mock = AsyncMock(return_value="")
    monkeypatch.setattr(ffmpeg, "_run_ffmpeg", run_mock)

    asyncio.run(ffmpeg.add_captions(str(video), str(ass), style="karaoke", output_path=str(tmp_path / "out.mp4")))

    filter_value = run_mock.await_args.args[0][run_mock.await_args.args[0].index("-vf") + 1]
    assert filter_value == f"subtitles='{ffmpeg._escape_srt_path(str(ass))}'"


@pytest.mark.unit
def test_extend_video_to_duration_copy_path(monkeypatch, tmp_path):
    video = tmp_path / "video.mp4"
    video.write_bytes(b"x")
    monkeypatch.setattr(ffmpeg, "_get_duration", AsyncMock(return_value=10.0))
    copy_mock = AsyncMock(return_value=str(tmp_path / "out.mp4"))
    monkeypatch.setattr(ffmpeg, "_copy_video", copy_mock)

    asyncio.run(ffmpeg.extend_video_to_duration(str(video), 5.0, str(tmp_path / "out.mp4")))

    copy_mock.assert_awaited_once()


@pytest.mark.unit
def test_mix_background_music_existing_audio(monkeypatch, tmp_path):
    video = tmp_path / "video.mp4"
    music = tmp_path / "music.mp3"
    video.write_bytes(b"x")
    music.write_bytes(b"y")
    monkeypatch.setattr(ffmpeg, "_has_audio_stream", AsyncMock(return_value=True))
    run_mock = AsyncMock(return_value="")
    monkeypatch.setattr(ffmpeg, "_run_ffmpeg", run_mock)

    asyncio.run(ffmpeg.mix_background_music(str(video), str(music), output_path=str(tmp_path / "out.mp4")))

    filter_complex = run_mock.await_args.args[0][run_mock.await_args.args[0].index("-filter_complex") + 1]
    assert "amix=inputs=2" in filter_complex


@pytest.mark.unit
def test_mix_background_music_no_audio(monkeypatch, tmp_path):
    video = tmp_path / "video.mp4"
    music = tmp_path / "music.mp3"
    video.write_bytes(b"x")
    music.write_bytes(b"y")
    monkeypatch.setattr(ffmpeg, "_has_audio_stream", AsyncMock(return_value=False))
    monkeypatch.setattr(ffmpeg, "_get_duration", AsyncMock(return_value=12.5))
    run_mock = AsyncMock(return_value="")
    monkeypatch.setattr(ffmpeg, "_run_ffmpeg", run_mock)

    asyncio.run(ffmpeg.mix_background_music(str(video), str(music), output_path=str(tmp_path / "out.mp4")))

    filter_complex = run_mock.await_args.args[0][run_mock.await_args.args[0].index("-filter_complex") + 1]
    assert "atrim=duration=12.5" in filter_complex


@pytest.mark.unit
def test_export_for_platform_unknown_raises(tmp_path):
    video = tmp_path / "video.mp4"
    video.write_bytes(b"x")
    with pytest.raises(ffmpeg.MediaValidationError, match="Unknown platform"):
        asyncio.run(ffmpeg.export_for_platform(str(video), "unknown"))


@pytest.mark.unit
def test_export_for_platform_runs_ffmpeg(monkeypatch, tmp_path):
    video = tmp_path / "video.mp4"
    video.write_bytes(b"x")
    run_mock = AsyncMock(return_value="")
    monkeypatch.setattr(ffmpeg, "_run_ffmpeg", run_mock)

    out = asyncio.run(ffmpeg.export_for_platform(str(video), "tiktok", str(tmp_path / "out.mp4")))

    assert out.endswith("out.mp4")
    assert "-movflags" in run_mock.await_args.args[0]
