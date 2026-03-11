from __future__ import annotations

import asyncio
import os
import shutil

import pytest
from PIL import Image

from services.media import ffmpeg


HAS_FFMPEG = bool(shutil.which("ffmpeg")) and bool(shutil.which("ffprobe"))

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not HAS_FFMPEG, reason="Requires local ffmpeg and ffprobe"),
]


@pytest.mark.integration
async def test_animate_image_real_ffmpeg(tmp_path):
    image_path = tmp_path / "image.png"
    Image.new("RGB", (576, 1024), color="navy").save(image_path)
    output_path = tmp_path / "animated.mp4"

    result = await ffmpeg.animate_image(str(image_path), duration=1, output_path=str(output_path))

    assert result == str(output_path)
    assert output_path.exists()


@pytest.mark.integration
async def test_add_captions_real_ffmpeg(tmp_path):
    image_path = tmp_path / "image.png"
    Image.new("RGB", (576, 1024), color="black").save(image_path)
    video_path = await ffmpeg.animate_image(str(image_path), duration=1, output_path=str(tmp_path / "base.mp4"))
    srt_path = tmp_path / "captions.srt"
    srt_path.write_text("1\n00:00:00,000 --> 00:00:00,800\nHello\n", encoding="utf-8")
    output_path = tmp_path / "captioned.mp4"

    result = await ffmpeg.add_captions(video_path, str(srt_path), output_path=str(output_path))

    assert result == str(output_path)
    assert output_path.exists()


@pytest.mark.integration
async def test_add_ass_captions_real_ffmpeg(tmp_path):
    image_path = tmp_path / "image.png"
    Image.new("RGB", (576, 1024), color="black").save(image_path)
    video_path = await ffmpeg.animate_image(str(image_path), duration=1, output_path=str(tmp_path / "base_ass.mp4"))
    ass_path = tmp_path / "captions.ass"
    ass_path.write_text(
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        "PlayResX: 576\n"
        "PlayResY: 1024\n\n"
        "[V4+ Styles]\n"
        "Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,"
        "Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding\n"
        "Style: Default,Arial,20,&H00FFFFFF,&H0000D7FF,&H00000000,&H00000000,1,0,0,0,100,100,0,0,1,2,1,2,20,20,40,1\n\n"
        "[Events]\n"
        "Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text\n"
        r"Dialogue: 0,0:00:00.00,0:00:00.80,Default,,0,0,0,,{\kf40}Hello {\kf40}world" "\n",
        encoding="utf-8",
    )
    output_path = tmp_path / "captioned_ass.mp4"

    result = await ffmpeg.add_captions(video_path, str(ass_path), style="karaoke", output_path=str(output_path))

    assert result == str(output_path)
    assert output_path.exists()


@pytest.mark.integration
async def test_export_for_platform_real_ffmpeg(tmp_path):
    image_path = tmp_path / "image.png"
    Image.new("RGB", (576, 1024), color="green").save(image_path)
    video_path = await ffmpeg.animate_image(str(image_path), duration=1, output_path=str(tmp_path / "base.mp4"))
    output_path = tmp_path / "export.mp4"

    result = await ffmpeg.export_for_platform(video_path, "tiktok", str(output_path))

    assert result == str(output_path)
    assert output_path.exists()


@pytest.mark.integration
async def test_build_xfade_concat_real_ffmpeg(tmp_path):
    image_one = tmp_path / "one.png"
    image_two = tmp_path / "two.png"
    Image.new("RGB", (576, 1024), color="red").save(image_one)
    Image.new("RGB", (576, 1024), color="blue").save(image_two)

    clip_one = await ffmpeg.animate_image(str(image_one), duration=1, output_path=str(tmp_path / "one.mp4"))
    clip_two = await ffmpeg.animate_image(str(image_two), duration=1, output_path=str(tmp_path / "two.mp4"))
    output_path = tmp_path / "xfade.mp4"

    result = await ffmpeg._build_xfade_concat(
        [clip_one, clip_two],
        ["fade"],
        str(tmp_path),
        str(output_path),
    )

    assert result == str(output_path)
    assert output_path.exists()
