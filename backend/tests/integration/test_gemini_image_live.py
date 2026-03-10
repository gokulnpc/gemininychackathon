from __future__ import annotations

import asyncio
import os

import pytest

from services.gemini.image import describe_reference_subject, generate_thumbnail


SAMPLE_IMAGE = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "input", "gokul.jpeg")
)

HAS_GEMINI_API_KEY = bool(os.getenv("GEMINI_API_KEY"))
HAS_SAMPLE_IMAGE = os.path.exists(SAMPLE_IMAGE)


pytestmark = [
    pytest.mark.integration,
    pytest.mark.api,
    pytest.mark.skipif(
        not HAS_GEMINI_API_KEY or not HAS_SAMPLE_IMAGE,
        reason="Requires GEMINI_API_KEY and backend/input/gokul.jpeg",
    ),
]


def test_describe_reference_subject_live():
    result = asyncio.run(describe_reference_subject(SAMPLE_IMAGE))

    assert result
    assert len(result) > 10


def test_generate_thumbnail_live():
    path = asyncio.run(
        generate_thumbnail(
            hook_text="This discovery changes everything",
            scene_visual_prompt="A dramatic close-up portrait with bold cinematic lighting",
            character_description=None,
            art_style="cinematic",
        )
    )

    assert os.path.exists(path)
    assert path.endswith(".jpg")
