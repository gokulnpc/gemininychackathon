"""
backend/tests/conftest.py

Shared pytest fixtures for the Story Factory backend test suite.

Coexists with the custom-runner tests in tests/unit/ and tests/integration/ —
pytest is configured to only collect from tests/pytest/ (see backend/pytest.ini),
so the standalone scripts are never touched.

Usage in generated tests:
    def test_something(mocker, mock_gemini_client, sample_words):
        ...
"""
from __future__ import annotations

import base64
import io
import os
import sys
import tempfile
import wave
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

# ---------------------------------------------------------------------------
# Make "backend/" the import root so "from services.x import y" works in tests
# ---------------------------------------------------------------------------
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ===========================================================================
# Settings fixtures
# ===========================================================================

@pytest.fixture()
def test_settings():
    """Pydantic-Settings-compatible SimpleNamespace with safe test values.

    No real credentials — all keys are placeholders that prevent accidental
    network calls while allowing service code to run.
    """
    return SimpleNamespace(
        # GCP / Storage
        gcs_bucket="test-bucket",
        google_cloud_project="test-project",
        # Gemini
        gemini_api_key="fake-api-key-for-testing",
        vertex_ai_location="us-central1",
        use_vertex_ai=False,
        # Email
        sendgrid_api_key="",
        notification_from_email="noreply@test.example.com",
        # Document AI
        document_ai_processor_id="",
        document_ai_location="us",
        # App
        app_name="TestApp",
        debug=True,
        # Worker / Cloud Tasks
        worker_url="",
        cloud_tasks_queue="test-queue",
        cloud_tasks_location="us-central1",
        # Social
        instagram_access_token="",
        instagram_user_id="",
        tiktok_access_token="",
        youtube_client_secrets_file="",
        youtube_token_file="/tmp/test_youtube_token.json",
    )


@pytest.fixture()
def patch_settings(test_settings, monkeypatch):
    """Monkeypatches config.get_settings() to return test_settings.

    Also clears the lru_cache before and after so the patched version
    is used by all service imports during the test.

    Use this fixture in any test that indirectly calls get_settings() via
    a service module (most service tests need this).
    """
    import config
    config.get_settings.cache_clear()
    monkeypatch.setattr(config, "get_settings", lambda: test_settings)
    yield test_settings
    config.get_settings.cache_clear()


# ===========================================================================
# Gemini API mock factories
# ===========================================================================

@pytest.fixture()
def mock_gemini_response():
    """Factory: returns a callable that builds a mock Gemini text response.

    Example:
        def test_foo(mocker, mock_gemini_response):
            mocker.patch("services.gemini.reasoning.call_with_retry",
                         new_callable=AsyncMock,
                         return_value=mock_gemini_response('{"score": 82}'))
    """
    def _factory(text: str = "{}") -> MagicMock:
        resp = MagicMock()
        resp.text = text
        return resp
    return _factory


@pytest.fixture()
def mock_gemini_tts_response():
    """Factory: returns a callable that builds a mock Gemini TTS response.

    The response contains one candidate with inline_data (raw PCM bytes).

    Example:
        resp = mock_gemini_tts_response(b"\\x00" * 48000)
    """
    def _factory(pcm_bytes: bytes = b"\x00" * 48000) -> MagicMock:
        blob = MagicMock()
        blob.data = pcm_bytes

        part = MagicMock()
        part.inline_data = blob

        content = MagicMock()
        content.parts = [part]

        candidate = MagicMock()
        candidate.content = content

        response = MagicMock()
        response.candidates = [candidate]
        return response
    return _factory


@pytest.fixture()
def mock_gemini_client(mock_gemini_response):
    """Factory: returns a callable that builds a fully mocked genai.Client.

    The client's generate_content returns a text response by default.

    Example:
        client = mock_gemini_client('{"result": "ok"}')
        mocker.patch("services.gemini.client.get_client", return_value=client)
    """
    def _factory(response_text: str = '{"result": "ok"}') -> MagicMock:
        client = MagicMock()
        client.models.generate_content.return_value = mock_gemini_response(response_text)
        return client
    return _factory


# ===========================================================================
# GCS fixtures
# ===========================================================================

@pytest.fixture()
def gcs_settings():
    """SimpleNamespace that matches what services/storage/gcs.py reads."""
    return SimpleNamespace(
        gcs_bucket="test-bucket",
        google_cloud_project="test-project",
    )


@pytest.fixture()
def mock_gcs_available_true(monkeypatch):
    """Makes _gcs_available() return True (GCS cloud path active)."""
    import services.storage.gcs as gcs_mod
    monkeypatch.setattr(gcs_mod, "_gcs_available", lambda: True)


@pytest.fixture()
def mock_gcs_available_false(monkeypatch):
    """Makes _gcs_available() return False (local filesystem fallback)."""
    import services.storage.gcs as gcs_mod
    monkeypatch.setattr(gcs_mod, "_gcs_available", lambda: False)


# ===========================================================================
# Firestore fixtures
# ===========================================================================

@pytest.fixture()
def mock_firestore_available_true(monkeypatch):
    """Makes _firestore_available() return True."""
    import services.storage.firestore_db as fdb
    monkeypatch.setattr(fdb, "_firestore_available", lambda: True)


@pytest.fixture()
def mock_firestore_available_false(monkeypatch):
    """Makes _firestore_available() return False (GCS fallback)."""
    import services.storage.firestore_db as fdb
    monkeypatch.setattr(fdb, "_firestore_available", lambda: False)


# ===========================================================================
# Sample test data
# ===========================================================================

@pytest.fixture()
def sample_words():
    """Standard word-timestamp list used in caption and STT tests."""
    return [
        {"word": "Hello", "start": 0.0,  "end": 0.5},
        {"word": "world", "start": 0.5,  "end": 1.0},
        {"word": "this",  "start": 1.0,  "end": 1.4},
        {"word": "is",    "start": 1.4,  "end": 1.6},
        {"word": "a",     "start": 1.6,  "end": 1.7},
        {"word": "test",  "start": 1.7,  "end": 2.0},
        {"word": "of",    "start": 2.2,  "end": 2.4},
        {"word": "captions", "start": 2.4, "end": 3.0},
    ]


@pytest.fixture()
def sample_words_with_silence():
    """Word list containing a >0.7s silence gap — triggers cue flush."""
    return [
        {"word": "Before", "start": 0.0, "end": 0.5},
        {"word": "pause",  "start": 0.5, "end": 1.0},
        # 1.5s silence gap
        {"word": "After",  "start": 2.5, "end": 3.0},
        {"word": "gap",    "start": 3.0, "end": 3.5},
    ]


@pytest.fixture()
def sample_script():
    """Minimal script dict matching ScriptGenerationResponse shape."""
    return {
        "hook": {"text": "Did you know this one thing?", "type": "mystery"},
        "scenes": [
            {
                "scene_id": 1,
                "duration_seconds": 5,
                "voiceover_text": "The giraffe walked slowly.",
                "visual_prompt": "A giraffe in a golden savanna",
                "emotion": "calm",
            },
            {
                "scene_id": 2,
                "duration_seconds": 5,
                "voiceover_text": "And then it ran.",
                "visual_prompt": "A giraffe running at sunset",
                "emotion": "exciting",
            },
        ],
        "cta": "Follow for more wildlife facts",
        "social_copy": "Mind-blowing giraffe facts #wildlife",
        "metadata": {"agent_quality_score": 82, "hook_type": "mystery"},
    }


@pytest.fixture()
def sample_project_metadata():
    """Minimal project metadata dict for Firestore/GCS tests."""
    return {
        "project_id": "test-proj-001",
        "status": "done",
        "created_at": "2025-01-01T00:00:00Z",
        "video_urls": {
            "instagram_reels": "https://storage.googleapis.com/test-bucket/projects/001/video.mp4"
        },
    }


@pytest.fixture()
def valid_audio_b64():
    """Small valid base64-encoded audio payload (100 zero bytes).

    Suitable for passing input-validation checks that require non-empty audio.
    Not a real audio file — use tmp_wav_file for tests that actually parse audio.
    """
    return base64.b64encode(b"\x00" * 100).decode()


@pytest.fixture()
def valid_json_transcription():
    """JSON string matching the transcribe_with_tone response shape."""
    return '{"transcript": "hello world", "detected_tone": "excited", "language": "en-US"}'


@pytest.fixture()
def tmp_wav_file():
    """Creates a real minimal WAV file (1s silence at 24kHz) in /tmp.

    Yields the file path. File is deleted after the test.

    Example:
        def test_audio_processing(tmp_wav_file):
            result = process_audio(tmp_wav_file)
    """
    pcm = b"\x00" * 48000  # 1s of silence: 24000 frames × 2 bytes/frame

    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(24000)
        wf.writeframes(pcm)
    wav_bytes = buf.getvalue()

    with tempfile.NamedTemporaryFile(
        suffix=".wav", delete=False, prefix="test_story_"
    ) as f:
        f.write(wav_bytes)
        path = f.name

    yield path

    if os.path.exists(path):
        os.unlink(path)


@pytest.fixture()
def tmp_dir():
    """Creates a temporary directory. Yields path. Removes all contents after test."""
    with tempfile.TemporaryDirectory(prefix="test_story_") as d:
        yield d
