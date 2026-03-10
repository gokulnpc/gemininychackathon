"""Unit tests for services/media/lyria.py — pure functions + mocked API paths.

No real API calls made. Safe to run without GCP credentials.

Usage:
    cd backend && .venv/bin/python tests/unit/test_lyria.py
"""

from __future__ import annotations

import asyncio
import os
import sys
from unittest.mock import AsyncMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from services.media.lyria import (
    _FALLBACK_PROMPT,
    _PRESET_PROMPTS,
    _STYLE_PROMPTS,
    _build_lyria_prompt,
    generate_music,
)

_FAKE_WAV = b"RIFF\x00\x00\x00\x00WAVEfmt "


# ── _build_lyria_prompt (pure) ────────────────────────────────────────────────

def test_prompt_known_style():
    result = _build_lyria_prompt("dramatic", None)
    assert result == _STYLE_PROMPTS["dramatic"], f"got: {result}"
    print("  ✓ known style → style prompt")


def test_prompt_style_case_insensitive():
    result = _build_lyria_prompt("DRAMATIC", None)
    assert result == _STYLE_PROMPTS["dramatic"], f"got: {result}"
    print("  ✓ style lookup is case-insensitive")


def test_prompt_unknown_style_with_niche():
    result = _build_lyria_prompt("unknown_style", "fitness")
    assert "fitness" in result, f"got: {result}"
    print("  ✓ unknown style + niche → niche-based prompt")


def test_prompt_no_style_no_niche():
    result = _build_lyria_prompt(None, None)
    assert result == _FALLBACK_PROMPT, f"got: {result}"
    print("  ✓ no style, no niche → fallback prompt")


def test_prompt_no_style_with_niche():
    result = _build_lyria_prompt(None, "cooking")
    assert "cooking" in result, f"got: {result}"
    print("  ✓ no style + niche → niche prompt")


def test_all_style_keys_are_strings():
    for key, val in _STYLE_PROMPTS.items():
        assert isinstance(key, str) and isinstance(val, str)
    print(f"  ✓ all {len(_STYLE_PROMPTS)} style prompts are valid strings")


def test_all_preset_keys_are_strings():
    for key, val in _PRESET_PROMPTS.items():
        assert isinstance(key, str) and isinstance(val, str)
    print(f"  ✓ all {len(_PRESET_PROMPTS)} preset prompts are valid strings")


# ── generate_music (mocked) ───────────────────────────────────────────────────

async def test_generate_music_named_preset():
    with patch("services.media.lyria.asyncio.to_thread", new=AsyncMock(return_value=_FAKE_WAV)):
        path = await generate_music(music_preset="happy_rhythm", project_id="test-project")
    assert os.path.exists(path)
    with open(path, "rb") as f:
        assert f.read() == _FAKE_WAV
    os.unlink(path)
    print("  ✓ named preset → WAV file written")


async def test_generate_music_lyria_preset_uses_style():
    captured = {}

    async def fake_to_thread(fn, prompt, *args):
        captured["prompt"] = prompt
        return _FAKE_WAV

    with patch("services.media.lyria.asyncio.to_thread", side_effect=fake_to_thread):
        path = await generate_music(music_preset="lyria", project_id="test-project", style="dramatic")
    assert captured["prompt"] == _STYLE_PROMPTS["dramatic"], f"wrong prompt: {captured['prompt']}"
    os.path.exists(path) and os.unlink(path)
    print("  ✓ lyria preset + known style → style prompt passed to Lyria")


async def test_generate_music_lyria_preset_unknown_style():
    captured = {}

    async def fake_to_thread(fn, prompt, *args):
        captured["prompt"] = prompt
        return _FAKE_WAV

    with patch("services.media.lyria.asyncio.to_thread", side_effect=fake_to_thread):
        path = await generate_music(music_preset="lyria", project_id="test-project",
                                    style="unknown_xyz", niche="travel")
    assert "travel" in captured["prompt"], f"niche missing: {captured['prompt']}"
    os.path.exists(path) and os.unlink(path)
    print("  ✓ lyria preset + unknown style + niche → niche prompt")


async def test_generate_music_recitation_retry():
    call_count = 0

    async def fake_to_thread(fn, prompt, *args):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RuntimeError("Content generation blocked due to recitation policy")
        return _FAKE_WAV

    with patch("services.media.lyria.asyncio.to_thread", side_effect=fake_to_thread):
        path = await generate_music(music_preset="lyria", project_id="test-project", style="dramatic")
    assert call_count == 2, f"expected 2 calls, got {call_count}"
    os.path.exists(path) and os.unlink(path)
    print("  ✓ recitation error → retried once with fallback prompt")


async def test_generate_music_non_recitation_error_raises():
    async def fake_to_thread(fn, *args):
        raise RuntimeError("Network timeout")

    with patch("services.media.lyria.asyncio.to_thread", side_effect=fake_to_thread):
        try:
            await generate_music(music_preset="happy_rhythm", project_id="test-project")
            assert False, "Expected RuntimeError"
        except RuntimeError as e:
            assert "Network timeout" in str(e)
    print("  ✓ non-recitation error propagates")


async def test_generate_music_unknown_preset_uses_fallback():
    captured = {}

    async def fake_to_thread(fn, prompt, *args):
        captured["prompt"] = prompt
        return _FAKE_WAV

    with patch("services.media.lyria.asyncio.to_thread", side_effect=fake_to_thread):
        path = await generate_music(music_preset="nonexistent_preset", project_id="test-project")
    assert captured["prompt"] == _FALLBACK_PROMPT, f"got: {captured['prompt']}"
    os.path.exists(path) and os.unlink(path)
    print("  ✓ unknown preset → fallback prompt")


# ── Runner ────────────────────────────────────────────────────────────────────

async def main() -> None:
    sync_tests = [
        test_prompt_known_style,
        test_prompt_style_case_insensitive,
        test_prompt_unknown_style_with_niche,
        test_prompt_no_style_no_niche,
        test_prompt_no_style_with_niche,
        test_all_style_keys_are_strings,
        test_all_preset_keys_are_strings,
    ]
    async_tests = [
        test_generate_music_named_preset,
        test_generate_music_lyria_preset_uses_style,
        test_generate_music_lyria_preset_unknown_style,
        test_generate_music_recitation_retry,
        test_generate_music_non_recitation_error_raises,
        test_generate_music_unknown_preset_uses_fallback,
    ]

    passed = failed = 0

    print("\n── _build_lyria_prompt (pure) ──")
    for fn in sync_tests:
        print(f"[{fn.__name__}]")
        try:
            fn()
            passed += 1
        except Exception as exc:
            print(f"  ✗ FAILED: {exc}")
            failed += 1

    print("\n── generate_music (mocked) ──")
    for fn in async_tests:
        print(f"[{fn.__name__}]")
        try:
            await fn()
            passed += 1
        except Exception as exc:
            print(f"  ✗ FAILED: {exc}")
            failed += 1

    print(f"\n{'─'*44}")
    print(f"  {passed} passed  |  {failed} failed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    asyncio.run(main())
