import asyncio
import logging
import os
import shlex
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

FPS = 25  # output framerate for animated image clips

# Maps scene emotion → zoompan camera effect
# Four effects available: shaky | zoom_in_left | zoom_in_right | slide_left | slide_right | zoom_out
EMOTION_TO_EFFECT: dict[str, str] = {
    "confident":  "zoom_in_right",
    "energetic":  "slide_right",
    "excited":    "zoom_in_right",
    "dramatic":   "shaky",
    "mysterious": "slide_left",
    "tense":      "shaky",
    "scared":     "shaky",
    "horror":     "shaky",
    "suspense":   "slide_left",
    "calm":       "zoom_out",
    "neutral":    "zoom_in_left",
    "happy":      "slide_right",
    "uplifting":  "slide_right",
    "sad":        "zoom_out",
    "reflective": "zoom_out",
}


def emotion_to_effect(emotion: str) -> str:
    """Map a scene emotion string to a zoompan camera effect name."""
    return EMOTION_TO_EFFECT.get(emotion.lower(), "dolly_in")


def animate_image(
    image_path: str,
    effect: str = "dolly_in",
    duration: int = 5,
    width: int = 576,
    height: int = 1024,
    output_path: str | None = None,
) -> str:
    """Animate a still image with a cinematic camera move using FFmpeg zoompan.

    Args:
        image_path: Path to the source PNG/JPEG image (from Nova Canvas).
        effect: Camera move — dolly_in, dolly_out, crash_zoom,
                pan_left, pan_right, crane_up, crane_down.
        duration: Clip duration in seconds.
        width: Output width in pixels (default 576, must match Nova Canvas output).
        height: Output height in pixels (default 1024, must match Nova Canvas output).
        output_path: Where to write the output MP4. Defaults to /tmp.

    Returns:
        Path to the animated video clip.
    """
    if output_path is None:
        output_path = f"/tmp/voicevid_anim_{os.getpid()}.mp4"

    zoompan_filter = _build_zoompan(effect, duration, width, height)

    _run_ffmpeg(
        [
            "ffmpeg", "-y",
            "-loop", "1",
            "-i", image_path,
            "-vf", zoompan_filter,
            "-t", str(duration),
            "-r", str(FPS),
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-preset", "fast",
            output_path,
        ],
        f"animate image ({effect}, {duration}s)",
    )

    logger.info("Animated image → %s (%s, %ds)", output_path, effect, duration)
    return output_path


def _build_zoompan(effect: str, duration: float, width: int, height: int) -> str:
    """Build the FFmpeg -vf zoompan filter string for a given camera move.

    Effects:
      shaky        — handheld shake with slight zoom in
      zoom_in_left — slow zoom into the left side of the frame
      zoom_in_right— slow zoom into the right side of the frame
      slide_left   — slow slide from right → left  (viewport pans left)
      slide_right  — slow slide from left → right  (viewport pans right)
      zoom_out     — slow zoom out from 1.5× → 1.0×, centered
    """
    frames = max(1, int(duration * FPS))
    pz = 1.3                              # zoom level used for slide effects
    size = f"s={width}x{height}:d={frames}"
    cy = "ih/2-(ih/zoom/2)"               # keep centered vertically

    if effect == "zoom_out":
        # Start at 1.5×, drift back to 1.0×, stay centered
        rate = round(0.5 / frames, 6)
        z = f"if(eq(on,0),1.5,max(1.0,zoom-{rate}))"
        cx = "iw/2-(iw/zoom/2)"
        return f"zoompan=z='{z}':x='{cx}':y='{cy}':{size}"

    elif effect == "zoom_in_left":
        # Slow zoom 1.0→1.5×, x stays at 0 so focus drifts to the left portion
        rate = round(0.5 / frames, 6)
        z = f"min(zoom+{rate},1.5)"
        return f"zoompan=z='{z}':x='0':y='{cy}':{size}"

    elif effect == "zoom_in_right":
        # Slow zoom 1.0→1.5×, x tracks the right edge so focus drifts right
        rate = round(0.5 / frames, 6)
        z = f"min(zoom+{rate},1.5)"
        x = "iw-iw/zoom"                 # rightmost valid x = iw*(1-1/zoom)
        return f"zoompan=z='{z}':x='{x}':y='{cy}':{size}"

    elif effect == "slide_right":
        # Fixed zoom pz, viewport slides left→right across the full travel distance
        step = round(width * (1 - 1 / pz) / frames, 4)
        x = f"min(iw*(1-1/{pz}),x+{step})"
        return f"zoompan=z='{pz}':x='{x}':y='{cy}':{size}"

    elif effect == "slide_left":
        # Fixed zoom pz, viewport slides right→left; initialize x to max on frame 0
        step = round(width * (1 - 1 / pz) / frames, 4)
        x = f"if(eq(on,0),iw*(1-1/{pz}),max(0,x-{step}))"
        return f"zoompan=z='{pz}':x='{x}':y='{cy}':{size}"

    elif effect == "shaky":
        # Slight zoom in 1.0→1.2× with sinusoidal handheld shake on x and y.
        # Uses `on` (frame index 0…d-1) for stable, predictable oscillation.
        rate = round(0.2 / frames, 6)
        z = f"min(zoom+{rate},1.2)"
        x = f"iw/2-(iw/zoom/2)+8*sin(on*0.5)"     # ~2 Hz horizontal shake
        y = f"ih/2-(ih/zoom/2)+6*sin(on*0.37+1.0)" # ~1.5 Hz vertical shake
        return f"zoompan=z='{z}':x='{x}':y='{y}':{size}"

    else:
        # Default: slow zoom in centered
        rate = round(0.5 / frames, 6)
        cx = "iw/2-(iw/zoom/2)"
        return f"zoompan=z='min(zoom+{rate},1.5)':x='{cx}':y='{cy}':{size}"


# Platform export presets: (width, height, video_bitrate, audio_bitrate)
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


def _run_ffmpeg(cmd: list[str], description: str) -> str:
    """Run an FFmpeg command via subprocess and return stdout."""
    logger.info("FFmpeg [%s]: %s", description, " ".join(shlex.quote(c) for c in cmd))
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=600,  # 10 min max
    )
    if result.returncode != 0:
        logger.error("FFmpeg failed [%s]: %s", description, result.stderr)
        raise RuntimeError(f"FFmpeg {description} failed: {result.stderr[:500]}")
    return result.stdout


def _get_duration(file_path: str) -> float:
    """Get media duration in seconds using ffprobe."""
    cmd = [
        "ffprobe", "-v", "quiet",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        file_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    return float(result.stdout.strip())


async def compose_video(
    scene_videos: list[str],
    voiceover_path: str | None = None,
    srt_path: str | None = None,
    caption_style: str = "clean",
    output_path: str | None = None,
) -> str:
    """Compose a final video from scene clips, voiceover, and captions.

    Args:
        scene_videos: Ordered list of file paths to scene video clips.
        voiceover_path: Path to the voiceover audio file (.wav/.mp3).
        srt_path: Path to the .srt caption file.
        caption_style: Style hint for caption rendering ("hormozi", "clean", "karaoke").
        output_path: Where to write the final video. Defaults to /tmp.

    Returns:
        Path to the composed video file.
    """
    if output_path is None:
        output_path = f"/tmp/voicevid_composed_{os.getpid()}.mp4"

    work_dir = f"/tmp/voicevid_work_{os.getpid()}"
    os.makedirs(work_dir, exist_ok=True)

    # Step 1: Concatenate scene videos
    concat_list_path = os.path.join(work_dir, "concat.txt")
    with open(concat_list_path, "w") as f:
        for video_path in scene_videos:
            f.write(f"file {shlex.quote(video_path)}\n")

    concat_output = os.path.join(work_dir, "concat.mp4")
    _run_ffmpeg(
        [
            "ffmpeg", "-y", "-f", "concat", "-safe", "0",
            "-i", concat_list_path,
            "-c", "copy",
            concat_output,
        ],
        "concatenate scenes",
    )

    current_video = concat_output

    # Step 2: Mix in voiceover audio
    if voiceover_path and os.path.exists(voiceover_path):
        audio_mixed = os.path.join(work_dir, "with_audio.mp4")
        _run_ffmpeg(
            [
                "ffmpeg", "-y",
                "-i", current_video,
                "-i", voiceover_path,
                "-c:v", "copy",
                "-c:a", "aac", "-b:a", "192k",
                "-map", "0:v:0", "-map", "1:a:0",
                "-shortest",
                audio_mixed,
            ],
            "mix voiceover",
        )
        current_video = audio_mixed

    # Step 3: Burn in captions
    if srt_path and os.path.exists(srt_path):
        current_video = add_captions(current_video, srt_path, caption_style, output_path)
    else:
        # Just copy to output
        _run_ffmpeg(
            ["ffmpeg", "-y", "-i", current_video, "-c", "copy", output_path],
            "copy to output",
        )

    logger.info("Composed video ready: %s", output_path)
    return output_path


def add_captions(
    video_path: str,
    srt_path: str,
    style: str = "clean",
    output_path: str | None = None,
) -> str:
    """Burn captions into a video using FFmpeg subtitles filter.

    Args:
        video_path: Path to the input video.
        srt_path: Path to the .srt file.
        style: Visual style for the captions.
        output_path: Where to write the output. Defaults to /tmp.

    Returns:
        Path to the captioned video.
    """
    if output_path is None:
        output_path = f"/tmp/voicevid_captioned_{os.getpid()}.mp4"

    style_options = _get_caption_style_options(style)

    # Escape special characters in path for FFmpeg filter
    escaped_srt = srt_path.replace("'", "'\\''").replace(":", "\\:")

    _run_ffmpeg(
        [
            "ffmpeg", "-y",
            "-i", video_path,
            "-vf", f"subtitles='{escaped_srt}':{style_options}",
            "-c:a", "copy",
            "-c:v", "libx264", "-preset", "fast", "-crf", "18",
            output_path,
        ],
        f"burn captions ({style})",
    )

    return output_path


def _get_caption_style_options(style: str) -> str:
    """Return FFmpeg subtitle filter force_style options for each caption style."""
    # Bold Stroke — white bold text, heavy black outline, upper-center
    if style in ("bold_stroke", "hormozi"):
        return (
            "force_style='FontName=Arial Black,FontSize=20,Bold=1,"
            "PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,"
            "Outline=3,Shadow=0,Alignment=10,MarginV=60'"
        )
    # Red Highlight — white text on red background box
    elif style == "red_highlight":
        return (
            "force_style='FontName=Arial Black,FontSize=18,Bold=1,"
            "PrimaryColour=&H00FFFFFF,BackColour=&H000000FF,"
            "BorderStyle=4,Outline=0,Shadow=0,Alignment=10,MarginV=60'"
        )
    # Sleek — clean thin subtitle at bottom
    elif style in ("sleek", "clean"):
        return (
            "force_style='FontName=Arial,FontSize=14,Bold=0,"
            "PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,"
            "Outline=2,Shadow=1,Alignment=2,MarginV=30'"
        )
    # Karaoke — word highlight, bottom
    elif style == "karaoke":
        return (
            "force_style='FontName=Arial,FontSize=16,Bold=1,"
            "PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,"
            "Outline=2,Shadow=1,Alignment=2,MarginV=40'"
        )
    # Majestic — centered, gold shadow
    elif style == "majestic":
        return (
            "force_style='FontName=Georgia,FontSize=22,Bold=1,Italic=0,"
            "PrimaryColour=&H00FFFFFF,OutlineColour=&H001C86EE,"
            "Outline=2,Shadow=2,Alignment=2,MarginV=50'"
        )
    # Beast — impact, single words, all caps, heavy stroke
    elif style == "beast":
        return (
            "force_style='FontName=Impact,FontSize=26,Bold=1,"
            "PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,"
            "Outline=4,Shadow=0,Alignment=10,MarginV=80'"
        )
    # Elegant — refined italic, thin outline, bottom
    elif style == "elegant":
        return (
            "force_style='FontName=Georgia,FontSize=16,Bold=0,Italic=1,"
            "PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,"
            "Outline=1,Shadow=1,Alignment=2,MarginV=35'"
        )
    else:
        return (
            "force_style='FontName=Arial,FontSize=14,Bold=0,"
            "PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,"
            "Outline=2,Shadow=1,Alignment=2,MarginV=30'"
        )


def extend_video_to_duration(
    video_path: str,
    target_duration: float,
    output_path: str | None = None,
) -> str:
    """Loop a video clip until it reaches at least target_duration seconds.

    Uses FFmpeg's -stream_loop to seamlessly repeat the clip. Useful when
    a generated clip is shorter than the voiceover.

    Args:
        video_path: Path to the source video clip.
        target_duration: Desired output duration in seconds.
        output_path: Where to write the output. Defaults to /tmp.

    Returns:
        Path to the extended video file.
    """
    if output_path is None:
        output_path = f"/tmp/voicevid_extended_{os.getpid()}.mp4"

    clip_duration = _get_duration(video_path)
    if clip_duration >= target_duration:
        # Already long enough — just copy
        _run_ffmpeg(
            ["ffmpeg", "-y", "-i", video_path, "-c", "copy", output_path],
            "copy (no extension needed)",
        )
        return output_path

    # -stream_loop -1 loops indefinitely; -t trims to exact target duration
    _run_ffmpeg(
        [
            "ffmpeg", "-y",
            "-stream_loop", "-1",
            "-i", video_path,
            "-t", str(target_duration),
            "-c:v", "libx264", "-preset", "fast", "-crf", "20",
            "-an",  # strip audio (video-only clip; voiceover added separately)
            output_path,
        ],
        f"extend video {clip_duration:.1f}s → {target_duration:.1f}s",
    )
    logger.info("Extended video from %.1fs to %.1fs: %s", clip_duration, target_duration, output_path)
    return output_path


def mix_background_music(
    video_path: str,
    music_path: str,
    music_volume: float = 0.15,
    output_path: str | None = None,
) -> str:
    """Mix a background music track under the existing audio in a video.

    Uses FFmpeg amix to blend the music at a reduced volume behind the voiceover.
    The output duration matches the video (music loops if shorter, cuts if longer).

    Args:
        video_path: Path to video with voiceover audio already mixed in.
        music_path: Path to the background music file (MP3/WAV).
        music_volume: Relative volume for the music track (0.0–1.0). Default 0.15.
        output_path: Where to write the output. Defaults to /tmp.

    Returns:
        Path to the video with background music mixed in.
    """
    if output_path is None:
        output_path = f"/tmp/voicevid_music_{os.getpid()}.mp4"

    vol = max(0.0, min(1.0, music_volume))

    # Probe whether the video has an audio stream
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a",
         "-show_entries", "stream=codec_type", "-of", "csv=p=0", video_path],
        capture_output=True, text=True,
    )
    has_audio = bool(probe.stdout.strip())

    if has_audio:
        # Mix music behind existing voiceover
        filter_complex = (
            f"[1:a]volume={vol}[bg];"
            f"[0:a][bg]amix=inputs=2:duration=first:dropout_transition=2[aout]"
        )
        audio_map = "[aout]"
    else:
        # No voiceover — use music as the only audio track, trimmed to video length
        filter_complex = f"[1:a]volume={vol},atrim=duration={_get_duration(video_path)}[aout]"
        audio_map = "[aout]"

    _run_ffmpeg(
        [
            "ffmpeg", "-y",
            "-i", video_path,
            "-stream_loop", "-1", "-i", music_path,
            "-filter_complex", filter_complex,
            "-map", "0:v:0",
            "-map", audio_map,
            "-c:v", "copy",
            "-c:a", "aac", "-b:a", "192k",
            output_path,
        ],
        f"mix background music (vol={vol})",
    )

    logger.info("Mixed background music into: %s", output_path)
    return output_path


def export_for_platform(
    video_path: str,
    platform: str,
    output_path: str | None = None,
) -> str:
    """Re-encode a video optimized for a specific social media platform.

    Applies platform-specific resolution, bitrate, and codec settings.

    Args:
        video_path: Path to the source video.
        platform: One of "instagram_reels", "youtube_shorts", "tiktok".
        output_path: Where to write the output. Defaults to /tmp.

    Returns:
        Path to the platform-optimized video.
    """
    preset = PLATFORM_PRESETS.get(platform)
    if preset is None:
        raise ValueError(f"Unknown platform: {platform}. Use one of: {list(PLATFORM_PRESETS.keys())}")

    if output_path is None:
        output_path = f"/tmp/voicevid_{platform}_{os.getpid()}.mp4"

    w, h = preset["width"], preset["height"]

    _run_ffmpeg(
        [
            "ffmpeg", "-y",
            "-i", video_path,
            "-vf", f"scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2",
            "-c:v", "libx264", "-preset", "fast",
            "-b:v", preset["video_bitrate"],
            "-r", str(preset["fps"]),
            "-c:a", "aac", "-b:a", preset["audio_bitrate"],
            "-movflags", "+faststart",
            "-t", str(preset["max_duration"]),
            output_path,
        ],
        f"export for {platform}",
    )

    logger.info("Exported %s version: %s", platform, output_path)
    return output_path
