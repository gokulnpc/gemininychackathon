from __future__ import annotations

import asyncio
import logging
import os
import shutil
import tempfile
import uuid
from pathlib import Path

from services.media.captions import resolve_caption_style

logger = logging.getLogger(__name__)

FPS = 25
FFMPEG_TIMEOUT_SECONDS = 600
FFPROBE_TIMEOUT_SECONDS = 30

EMOTION_TO_EFFECT: dict[str, str] = {
    "confident": "zoom_in_right",
    "energetic": "slide_right",
    "excited": "zoom_in_right",
    "dramatic": "shaky",
    "mysterious": "slide_left",
    "tense": "shaky",
    "scared": "shaky",
    "horror": "shaky",
    "suspense": "slide_left",
    "calm": "zoom_out",
    "neutral": "zoom_in_left",
    "happy": "slide_right",
    "uplifting": "slide_right",
    "sad": "zoom_out",
    "reflective": "zoom_out",
    "apprehension": "slide_left",
    "unease": "slide_left",
    "dread": "shaky",
    "terror": "shaky",
    "anxiety": "shaky",
    "paranoia": "slide_left",
    "alarm": "shaky",
    "desperation": "shaky",
    "hopelessness": "zoom_out",
    "shock": "shaky",
    "revelation": "zoom_in_right",
    "haunting": "slide_left",
    "isolation": "zoom_out",
    "curiosity": "zoom_in_left",
}


PLATFORM_PRESETS = {
    "instagram_reels": {
        "width": 1080,
        "height": 1920,
        "video_bitrate": "8M",
        "audio_bitrate": "128k",
        "fps": 30,
        "max_duration": 90,
    },
    "youtube_shorts": {
        "width": 1080,
        "height": 1920,
        "video_bitrate": "10M",
        "audio_bitrate": "192k",
        "fps": 30,
        "max_duration": 60,
    },
    "tiktok": {
        "width": 1080,
        "height": 1920,
        "video_bitrate": "6M",
        "audio_bitrate": "128k",
        "fps": 30,
        "max_duration": 180,
    },
}


_XFADE_TRANSITIONS: dict[str, str] = {
    "fade": "fade",
    "dissolve": "dissolve",
    "zoom": "zoominout",
    "slide": "slideleft",
    "wipe": "wipeleft",
}


class FFmpegError(RuntimeError):
    """Raised when an ffmpeg subprocess fails."""


class FFmpegTimeoutError(FFmpegError):
    """Raised when ffmpeg exceeds the configured timeout."""


class FFprobeError(RuntimeError):
    """Raised when ffprobe fails or returns invalid output."""


class MediaValidationError(ValueError):
    """Raised when media inputs are invalid before invoking ffmpeg."""


def emotion_to_effect(emotion: str) -> str:
    return EMOTION_TO_EFFECT.get(emotion.lower(), "dolly_in")


def _validate_existing_file(file_path: str, field_name: str) -> None:
    if not file_path:
        raise MediaValidationError(f"{field_name} must not be empty")
    if not os.path.exists(file_path):
        raise MediaValidationError(f"{field_name} does not exist: {file_path}")


def _validate_positive_number(value: float, field_name: str) -> None:
    if value <= 0:
        raise MediaValidationError(f"{field_name} must be > 0, got {value}")


def _validate_scene_videos(scene_videos: list[str]) -> None:
    if not scene_videos:
        raise MediaValidationError("scene_videos must contain at least one clip")
    for clip in scene_videos:
        _validate_existing_file(clip, "scene_video")


def _normalize_music_volume(music_volume: float) -> float:
    return max(0.0, min(1.0, float(music_volume)))


def _generate_temp_output(prefix: str, suffix: str) -> str:
    return os.path.join(tempfile.gettempdir(), f"{prefix}{uuid.uuid4().hex[:8]}{suffix}")


def _escape_srt_path(path: str) -> str:
    return path.replace("\\", "\\\\").replace("'", "\\'").replace(":", "\\:")


def _concat_file_entry(path: str) -> str:
    escaped = path.replace("'", "'\\''")
    return f"file '{escaped}'\n"


async def _run_subprocess(
    binary: str,
    args: list[str],
    description: str,
    *,
    timeout: int,
    error_cls: type[RuntimeError],
) -> tuple[str, str]:
    # ffmpeg supports -nostdin to prevent it from consuming stdin; ffprobe does not
    extra_flags = ["-hide_banner", "-nostdin"] if binary == "ffmpeg" else ["-hide_banner"]
    cmd = [binary, *extra_flags, *args]
    logger.info("%s [%s]: %s", binary, description, " ".join(cmd))
    try:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError as exc:
        raise error_cls(f"{binary} binary not found while running {description}") from exc

    try:
        stdout_bytes, stderr_bytes = await asyncio.wait_for(process.communicate(), timeout=timeout)
    except asyncio.TimeoutError as exc:
        process.kill()
        await process.communicate()
        if error_cls is FFmpegError:
            raise FFmpegTimeoutError(f"{binary} {description} timed out after {timeout}s") from exc
        raise error_cls(f"{binary} {description} timed out after {timeout}s") from exc

    stdout = stdout_bytes.decode(errors="replace")
    stderr = stderr_bytes.decode(errors="replace")

    if process.returncode != 0:
        detail = stderr.strip() or stdout.strip() or f"exit code {process.returncode}"
        logger.error("%s failed [%s]: %s", binary, description, detail)
        raise error_cls(f"{binary} {description} failed: {detail[:500]}")

    return stdout, stderr


async def _run_ffmpeg(cmd: list[str], description: str) -> str:
    stdout, _ = await _run_subprocess(
        "ffmpeg",
        cmd,
        description,
        timeout=FFMPEG_TIMEOUT_SECONDS,
        error_cls=FFmpegError,
    )
    return stdout


async def _run_ffprobe(cmd: list[str], description: str) -> str:
    stdout, _ = await _run_subprocess(
        "ffprobe",
        cmd,
        description,
        timeout=FFPROBE_TIMEOUT_SECONDS,
        error_cls=FFprobeError,
    )
    return stdout


async def _get_duration(file_path: str) -> float:
    _validate_existing_file(file_path, "file_path")
    stdout = await _run_ffprobe(
        [
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            file_path,
        ],
        f"probe duration for {Path(file_path).name}",
    )
    try:
        duration = float(stdout.strip())
    except ValueError as exc:
        raise FFprobeError(f"Invalid ffprobe duration output for {file_path}: {stdout!r}") from exc
    if duration <= 0:
        raise FFprobeError(f"Non-positive duration for {file_path}: {duration}")
    return duration


async def _has_audio_stream(file_path: str) -> bool:
    _validate_existing_file(file_path, "file_path")
    stdout = await _run_ffprobe(
        [
            "-v",
            "error",
            "-select_streams",
            "a",
            "-show_entries",
            "stream=codec_type",
            "-of",
            "csv=p=0",
            file_path,
        ],
        f"probe audio stream for {Path(file_path).name}",
    )
    return bool(stdout.strip())


async def animate_image(
    image_path: str,
    effect: str = "dolly_in",
    duration: int = 5,
    width: int = 576,
    height: int = 1024,
    output_path: str | None = None,
) -> str:
    _validate_existing_file(image_path, "image_path")
    _validate_positive_number(duration, "duration")
    _validate_positive_number(width, "width")
    _validate_positive_number(height, "height")

    if output_path is None:
        output_path = _generate_temp_output("voicevid_anim_", ".mp4")

    zoompan_filter = _build_zoompan(effect, duration, width, height)
    await _run_ffmpeg(
        [
            "-y",
            "-loop",
            "1",
            "-i",
            image_path,
            "-vf",
            zoompan_filter,
            "-t",
            str(duration),
            "-r",
            str(FPS),
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-preset",
            "fast",
            output_path,
        ],
        f"animate image ({effect}, {duration}s)",
    )
    logger.info("Animated image -> %s (%s, %ss)", output_path, effect, duration)
    return output_path


def _build_zoompan(effect: str, duration: float, width: int, height: int) -> str:
    frames = max(1, int(duration * FPS))
    pz = 1.3
    size = f"s={width}x{height}:d={frames}"
    cy = "ih/2-(ih/zoom/2)"

    if effect == "zoom_out":
        rate = round(0.5 / frames, 6)
        z = f"if(eq(on,0),1.5,max(1.0,zoom-{rate}))"
        cx = "iw/2-(iw/zoom/2)"
        return f"zoompan=z='{z}':x='{cx}':y='{cy}':{size}"
    if effect == "zoom_in_left":
        rate = round(0.5 / frames, 6)
        z = f"min(zoom+{rate},1.5)"
        return f"zoompan=z='{z}':x='0':y='{cy}':{size}"
    if effect == "zoom_in_right":
        rate = round(0.5 / frames, 6)
        z = f"min(zoom+{rate},1.5)"
        x = "iw-iw/zoom"
        return f"zoompan=z='{z}':x='{x}':y='{cy}':{size}"
    if effect == "slide_right":
        step = round(width * (1 - 1 / pz) / frames, 4)
        x = f"min(iw*(1-1/{pz}),x+{step})"
        return f"zoompan=z='{pz}':x='{x}':y='{cy}':{size}"
    if effect == "slide_left":
        step = round(width * (1 - 1 / pz) / frames, 4)
        x = f"if(eq(on,0),iw*(1-1/{pz}),max(0,x-{step}))"
        return f"zoompan=z='{pz}':x='{x}':y='{cy}':{size}"
    if effect == "shaky":
        rate = round(0.2 / frames, 6)
        z = f"min(zoom+{rate},1.2)"
        x = "iw/2-(iw/zoom/2)+8*sin(on*0.5)"
        y = "ih/2-(ih/zoom/2)+6*sin(on*0.37+1.0)"
        return f"zoompan=z='{z}':x='{x}':y='{y}':{size}"

    rate = round(0.5 / frames, 6)
    cx = "iw/2-(iw/zoom/2)"
    return f"zoompan=z='min(zoom+{rate},1.5)':x='{cx}':y='{cy}':{size}"


async def _copy_video(video_path: str, output_path: str, description: str) -> str:
    await _run_ffmpeg(["-y", "-i", video_path, "-c", "copy", output_path], description)
    return output_path


async def _build_xfade_concat(
    scene_videos: list[str],
    transitions: list[str | None],
    work_dir: str,
    output_path: str,
    xfade_duration: float = 0.3,
) -> str:
    _validate_scene_videos(scene_videos)
    _validate_positive_number(xfade_duration, "xfade_duration")

    if len(scene_videos) == 1:
        return await _copy_video(scene_videos[0], output_path, "copy single scene")

    has_xfade = any(t for t in transitions if t and t in _XFADE_TRANSITIONS)
    if not has_xfade:
        concat_list = os.path.join(work_dir, "concat.txt")
        with open(concat_list, "w", encoding="utf-8") as handle:
            for video in scene_videos:
                handle.write(_concat_file_entry(video))
        await _run_ffmpeg(
            ["-y", "-f", "concat", "-safe", "0", "-i", concat_list, "-c", "copy", output_path],
            "concatenate scenes (hard cut)",
        )
        return output_path

    re_encoded: list[str] = []
    for i, clip in enumerate(scene_videos):
        out = os.path.join(work_dir, f"xf_clip_{i}.mp4")
        await _run_ffmpeg(
            [
                "-y",
                "-i",
                clip,
                "-vf",
                "fps=25,format=yuv420p,scale=576:1024:force_original_aspect_ratio=decrease,pad=576:1024:(ow-iw)/2:(oh-ih)/2",
                "-c:v",
                "libx264",
                "-preset",
                "fast",
                "-crf",
                "20",
                "-an",
                out,
            ],
            f"re-encode clip {i} for xfade",
        )
        re_encoded.append(out)

    durations = [await _get_duration(path) for path in re_encoded]
    for duration in durations:
        if duration <= xfade_duration:
            raise MediaValidationError(
                f"All clips used with xfade must be longer than {xfade_duration}s; got {duration:.3f}s"
            )

    inputs: list[str] = []
    for clip in re_encoded:
        inputs += ["-i", clip]

    filter_parts: list[str] = []
    last_label = "[0:v]"
    offset = durations[0]
    current_timeline_duration = durations[0]

    for i in range(1, len(re_encoded)):
        transition_name = transitions[i - 1] if i - 1 < len(transitions) else None
        xfade = _XFADE_TRANSITIONS.get(transition_name or "", "dissolve")
        xfade_offset = offset - xfade_duration
        if xfade_offset < 0 or xfade_offset >= current_timeline_duration:
            raise MediaValidationError(
                f"Invalid xfade offset {xfade_offset:.4f}s for clip {i}; durations={durations}"
            )
        out_label = f"[xf{i}]" if i < len(re_encoded) - 1 else "[vout]"
        filter_parts.append(
            f"{last_label}[{i}:v]xfade=transition={xfade}:duration={xfade_duration}:offset={xfade_offset:.4f}{out_label}"
        )
        last_label = out_label
        offset += durations[i] - xfade_duration
        current_timeline_duration += durations[i] - xfade_duration

    await _run_ffmpeg(
        ["-y", *inputs, "-filter_complex", ";".join(filter_parts), "-map", "[vout]", "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-an", output_path],
        "concatenate scenes with xfade transitions",
    )
    return output_path


async def compose_video(
    scene_videos: list[str],
    voiceover_path: str | None = None,
    srt_path: str | None = None,
    caption_style: str = "clean",
    output_path: str | None = None,
    save_intermediate_to: str | None = None,
    scene_transitions: list[str | None] | None = None,
) -> str:
    _validate_scene_videos(scene_videos)
    if voiceover_path:
        _validate_existing_file(voiceover_path, "voiceover_path")
    if srt_path:
        _validate_existing_file(srt_path, "srt_path")

    if output_path is None:
        output_path = _generate_temp_output("voicevid_composed_", ".mp4")

    work_dir = tempfile.mkdtemp(prefix="voicevid_compose_")
    try:
        concat_output = os.path.join(work_dir, "concat.mp4")
        await _build_xfade_concat(
            scene_videos=scene_videos,
            transitions=scene_transitions or [],
            work_dir=work_dir,
            output_path=concat_output,
        )
        current_video = concat_output

        if voiceover_path:
            vo_duration = await _get_duration(voiceover_path)
            extended = os.path.join(work_dir, "extended.mp4")
            current_video = await extend_video_to_duration(current_video, vo_duration, extended)

            audio_mixed = os.path.join(work_dir, "with_audio.mp4")
            await _run_ffmpeg(
                [
                    "-y",
                    "-i",
                    current_video,
                    "-i",
                    voiceover_path,
                    "-c:v",
                    "copy",
                    "-c:a",
                    "aac",
                    "-b:a",
                    "192k",
                    "-map",
                    "0:v:0",
                    "-map",
                    "1:a:0",
                    audio_mixed,
                ],
                "mix voiceover",
            )
            current_video = audio_mixed

        if save_intermediate_to:
            shutil.copy2(current_video, save_intermediate_to)
            logger.info("Saved intermediate with_audio -> %s", save_intermediate_to)

        if srt_path:
            current_video = await add_captions(current_video, srt_path, caption_style, output_path)
        else:
            await _copy_video(current_video, output_path, "copy to output")

        logger.info("Composed video ready: %s", output_path)
        return output_path
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


async def add_captions(
    video_path: str,
    subtitle_path: str,
    style: str = "clean",
    output_path: str | None = None,
) -> str:
    _validate_existing_file(video_path, "video_path")
    _validate_existing_file(subtitle_path, "subtitle_path")
    if output_path is None:
        output_path = _generate_temp_output("voicevid_captioned_", ".mp4")

    subtitle_filter = _build_subtitles_filter(subtitle_path, style)

    await _run_ffmpeg(
        [
            "-y",
            "-i",
            video_path,
            "-vf",
            subtitle_filter,
            "-c:a",
            "copy",
            "-c:v",
            "libx264",
            "-preset",
            "fast",
            "-crf",
            "18",
            output_path,
        ],
        f"burn captions ({style})",
    )
    return output_path


def _build_subtitles_filter(subtitle_path: str, style: str) -> str:
    escaped_path = _escape_srt_path(subtitle_path)
    if Path(subtitle_path).suffix.lower() == ".ass":
        return f"subtitles='{escaped_path}'"
    return f"subtitles='{escaped_path}':{_get_caption_style_options(style)}"


def _get_caption_style_options(style: str) -> str:
    _, style_def = resolve_caption_style(style)
    return style_def.get(
        "ffmpeg_force_style",
        "force_style='FontName=Arial,FontSize=14,Bold=0,"
        "PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,"
        "Outline=2,Shadow=1,Alignment=2,MarginV=30'",
    )


async def extend_video_to_duration(
    video_path: str,
    target_duration: float,
    output_path: str | None = None,
) -> str:
    _validate_existing_file(video_path, "video_path")
    _validate_positive_number(target_duration, "target_duration")
    if output_path is None:
        output_path = _generate_temp_output("voicevid_extended_", ".mp4")

    clip_duration = await _get_duration(video_path)
    if clip_duration >= target_duration:
        return await _copy_video(video_path, output_path, "copy (no extension needed)")

    await _run_ffmpeg(
        [
            "-y",
            "-stream_loop",
            "-1",
            "-i",
            video_path,
            "-t",
            str(target_duration),
            "-c:v",
            "libx264",
            "-preset",
            "fast",
            "-crf",
            "20",
            "-an",
            output_path,
        ],
        f"extend video {clip_duration:.1f}s -> {target_duration:.1f}s",
    )
    logger.info("Extended video from %.1fs to %.1fs: %s", clip_duration, target_duration, output_path)
    return output_path


async def mix_background_music(
    video_path: str,
    music_path: str,
    music_volume: float = 0.15,
    output_path: str | None = None,
) -> str:
    _validate_existing_file(video_path, "video_path")
    _validate_existing_file(music_path, "music_path")
    if output_path is None:
        output_path = _generate_temp_output("voicevid_music_", ".mp4")

    vol = _normalize_music_volume(music_volume)
    has_audio = await _has_audio_stream(video_path)

    if has_audio:
        filter_complex = (
            f"[1:a]volume={vol}[bg];"
            "[0:a][bg]amix=inputs=2:duration=first:dropout_transition=2[aout]"
        )
    else:
        video_duration = await _get_duration(video_path)
        filter_complex = f"[1:a]volume={vol},atrim=duration={video_duration}[aout]"

    await _run_ffmpeg(
        [
            "-y",
            "-i",
            video_path,
            "-stream_loop",
            "-1",
            "-i",
            music_path,
            "-filter_complex",
            filter_complex,
            "-map",
            "0:v:0",
            "-map",
            "[aout]",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            output_path,
        ],
        f"mix background music (vol={vol})",
    )
    logger.info("Mixed background music into: %s", output_path)
    return output_path


async def export_for_platform(
    video_path: str,
    platform: str,
    output_path: str | None = None,
) -> str:
    _validate_existing_file(video_path, "video_path")
    preset = PLATFORM_PRESETS.get(platform)
    if preset is None:
        raise MediaValidationError(
            f"Unknown platform: {platform}. Use one of: {list(PLATFORM_PRESETS.keys())}"
        )
    if output_path is None:
        output_path = _generate_temp_output(f"voicevid_{platform}_", ".mp4")

    w, h = preset["width"], preset["height"]
    await _run_ffmpeg(
        [
            "-y",
            "-i",
            video_path,
            "-vf",
            f"scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2",
            "-c:v",
            "libx264",
            "-preset",
            "fast",
            "-b:v",
            preset["video_bitrate"],
            "-r",
            str(preset["fps"]),
            "-c:a",
            "aac",
            "-b:a",
            preset["audio_bitrate"],
            "-movflags",
            "+faststart",
            "-t",
            str(preset["max_duration"]),
            output_path,
        ],
        f"export for {platform}",
    )
    logger.info("Exported %s version: %s", platform, output_path)
    return output_path
