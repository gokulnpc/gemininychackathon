"""Google Cloud Speech-to-Text — word-level timestamp extraction.

Uses ADC (Application Default Credentials) — no extra config needed on Cloud Run
or locally after `gcloud auth application-default login`.

Production features:
    - File validation (exists, readable, non-empty)
    - Auto-format conversion (m4a/mp3/ogg → WAV via ffmpeg)
    - Long-running recognize for audio > 10 MB
    - Retry with exponential backoff on transient errors
    - Confidence-based word filtering (configurable threshold)
    - Timestamp normalization (sort + overlap fix)

Prerequisite:
    gcloud services enable speech.googleapis.com --project=YOUR_PROJECT_ID
"""

from __future__ import annotations

import asyncio
import logging
import os
import subprocess
import tempfile
import time

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

# GCP sync recognize payload limit (bytes).  Files larger than this use
# long_running_recognize instead.
_SYNC_LIMIT_BYTES = 10 * 1024 * 1024  # 10 MB

# Minimum word confidence to keep (0.0–1.0).  Words below this are dropped.
MIN_WORD_CONFIDENCE = 0.5

# Retry configuration for transient GCP errors.
MAX_RETRIES = 2
RETRY_BASE_DELAY = 1.0  # seconds — doubles each retry

# Audio extensions we can auto-convert to WAV via ffmpeg.
_CONVERTIBLE_EXTS = frozenset({".m4a", ".mp3", ".ogg", ".flac", ".aac", ".opus", ".webm"})


# ── Helpers ───────────────────────────────────────────────────────────────────

def _validate_audio_file(path: str) -> None:
    """Raise clear errors for missing / empty / unreadable audio files."""
    if not os.path.exists(path):
        raise FileNotFoundError(f"Audio file not found: {path}")
    if not os.path.isfile(path):
        raise ValueError(f"Path is not a file: {path}")
    if os.path.getsize(path) == 0:
        raise ValueError(f"Audio file is empty (0 bytes): {path}")


def _ensure_wav(path: str, sample_rate: int = 24000) -> tuple[str, bool]:
    """Return (wav_path, is_temp).  If already .wav, returns as-is.

    For non-WAV formats, converts via ffmpeg to LINEAR16 mono at *sample_rate*.
    The caller must delete the temp WAV if *is_temp* is True.
    """
    ext = os.path.splitext(path)[1].lower()
    if ext == ".wav":
        return path, False

    if ext not in _CONVERTIBLE_EXTS:
        # Let GCP handle it — may fail, but we don't block unknown formats
        logger.warning("Unknown audio extension %s — attempting direct WAV conversion", ext)

    fd, wav_path = tempfile.mkstemp(suffix=".wav", prefix="stt_convert_")
    os.close(fd)

    try:
        subprocess.run(
            [
                "ffmpeg", "-y",
                "-i", path,
                "-ar", str(sample_rate),
                "-ac", "1",
                "-c:a", "pcm_s16le",
                wav_path,
            ],
            check=True,
            capture_output=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        os.unlink(wav_path)
        raise RuntimeError(
            f"Failed to convert {path} to WAV (is ffmpeg installed?): {exc}"
        ) from exc

    logger.info("Converted %s → %s (%d bytes)", path, wav_path, os.path.getsize(wav_path))
    return wav_path, True


def _normalize_timestamps(timestamps: list[dict]) -> list[dict]:
    """Sort by start time and fix overlapping end values.

    If word[i].end > word[i+1].start, clamp word[i].end = word[i+1].start.
    """
    if not timestamps:
        return timestamps

    timestamps.sort(key=lambda w: w["start"])

    for i in range(len(timestamps) - 1):
        if timestamps[i]["end"] > timestamps[i + 1]["start"]:
            timestamps[i]["end"] = timestamps[i + 1]["start"]

    return timestamps


def _is_transient(exc: Exception) -> bool:
    """Check if a GCP error is transient and worth retrying."""
    msg = str(exc).lower()
    transient_codes = ("503", "429", "deadline exceeded", "unavailable", "resource exhausted")
    return any(code in msg for code in transient_codes)


# ── Core STT ──────────────────────────────────────────────────────────────────

def _get_speech_module():
    """Lazy import of google.cloud.speech — mockable for tests."""
    from google.cloud import speech
    return speech


def _invoke_stt(wav_path: str, sample_rate: int = 24000) -> list[dict]:
    """Synchronous STT call — run via asyncio.to_thread.

    Returns list of {"word": str, "start": float, "end": float}.

    Features:
        - Validates input file
        - Auto-converts non-WAV formats
        - Uses long_running_recognize for files > 10 MB
        - Retries on transient GCP errors
        - Filters low-confidence words
        - Normalizes timestamps (sort + overlap fix)
    """
    _validate_audio_file(wav_path)

    # Auto-convert to WAV if needed
    actual_wav, is_temp = _ensure_wav(wav_path, sample_rate)

    try:
        return _recognize_with_retry(actual_wav, sample_rate)
    finally:
        if is_temp:
            os.unlink(actual_wav)


def _recognize_with_retry(wav_path: str, sample_rate: int) -> list[dict]:
    """Call GCP STT with retry logic and post-processing."""
    speech = _get_speech_module()
    client = speech.SpeechClient()

    with open(wav_path, "rb") as f:
        audio_bytes = f.read()

    file_size = len(audio_bytes)
    use_long_running = file_size > _SYNC_LIMIT_BYTES

    audio = speech.RecognitionAudio(content=audio_bytes)
    config = speech.RecognitionConfig(
        encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
        sample_rate_hertz=sample_rate,
        audio_channel_count=1,
        language_code="en-US",
        enable_word_time_offsets=True,
        enable_word_confidence=True,
    )

    last_exc: Exception | None = None

    for attempt in range(MAX_RETRIES + 1):
        try:
            if use_long_running:
                logger.info(
                    "STT: using long_running_recognize (file=%d bytes, attempt=%d)",
                    file_size, attempt + 1,
                )
                operation = client.long_running_recognize(config=config, audio=audio)
                response = operation.result(timeout=300)
            else:
                response = client.recognize(config=config, audio=audio)
            break  # success
        except Exception as exc:
            last_exc = exc
            if attempt < MAX_RETRIES and _is_transient(exc):
                delay = RETRY_BASE_DELAY * (2 ** attempt)
                logger.warning(
                    "STT: transient error (attempt %d/%d), retrying in %.1fs: %s",
                    attempt + 1, MAX_RETRIES + 1, delay, exc,
                )
                time.sleep(delay)
            else:
                raise
    else:
        raise last_exc  # type: ignore[misc]

    # Extract timestamps with confidence filtering
    timestamps: list[dict] = []
    filtered_count = 0

    for result in response.results:
        for word_info in result.alternatives[0].words:
            confidence = getattr(word_info, "confidence", 1.0)
            if confidence < MIN_WORD_CONFIDENCE:
                filtered_count += 1
                continue

            timestamps.append({
                "word":  word_info.word,
                "start": word_info.start_time.total_seconds(),
                "end":   word_info.end_time.total_seconds(),
            })

    if filtered_count:
        logger.info("STT: filtered %d low-confidence words (threshold=%.2f)", filtered_count, MIN_WORD_CONFIDENCE)

    # Normalize: sort + fix overlaps
    timestamps = _normalize_timestamps(timestamps)

    logger.info("STT: extracted %d word timestamps from %s", len(timestamps), wav_path)
    return timestamps


# ── Public async API ──────────────────────────────────────────────────────────

async def extract_word_timestamps(wav_path: str, sample_rate: int = 24000) -> list[dict]:
    """Extract word-level timestamps from an audio file using GCP Speech-to-Text.

    Args:
        wav_path:    Path to an audio file (WAV, M4A, MP3, OGG, etc.).
                     Non-WAV formats are auto-converted via ffmpeg.
        sample_rate: Sample rate in Hz (default 24000 — matches Gemini TTS output).

    Returns:
        List of {"word": str, "start": float, "end": float} dicts,
        sorted by start time with overlaps fixed.

    Raises:
        FileNotFoundError: If the audio file doesn't exist.
        ValueError: If the audio file is empty.
        RuntimeError: If format conversion fails.
        Exception: Propagates GCP errors after retry exhaustion.
    """
    return await asyncio.to_thread(_invoke_stt, wav_path, sample_rate)
