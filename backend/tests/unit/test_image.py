"""Tests for services/gemini/image.py

Run:  cd backend && pytest tests/pytest/unit/test_image.py -v
Cov:  cd backend && pytest tests/pytest/unit/test_image.py --cov=services.gemini.image --cov-report=term-missing
"""
from __future__ import annotations

import base64
import io
import os
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from PIL import Image

from services.gemini.image import (
    GeminiImageProviderError,
    GeminiImageResponseError,
    GeminiImageServiceError,
    ImageGenerationRequest,
    CharacterSheetRequest,
    ThumbnailRequest,
    _FALLBACK_SUFFIX,
    _STYLE_SUFFIXES,
    _build_character_sheet_plan,
    _build_character_sheet_prompt,
    _build_consistent_scene_prompt,
    _build_scene_evolution_prompt,
    _build_scene_generation_plan,
    _build_scene_generation_prompt,
    _build_thumbnail_plan,
    _build_thumbnail_prompt,
    _extract_image,
    _fallback_scene_prompt,
    _normalize_art_style,
    _require_text,
    _save_temp_image,
    _style_reference_image,
    _style_suffix,
    _style_transfer_instruction,
    _thumbnail_fallback_prompt,
    _user_role_instruction,
    describe_reference_subject,
    generate_character_sheet,
    generate_image,
    generate_thumbnail,
)


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def rgb_image():
    """A minimal 10x10 RGB PIL Image for testing."""
    return Image.new("RGB", (10, 10), color=(128, 64, 32))


@pytest.fixture()
def rgb_image_file(tmp_dir, rgb_image):
    """Persist a minimal RGB image to a temp file and return its path."""
    path = os.path.join(tmp_dir, "test_ref.jpg")
    rgb_image.save(path, "JPEG")
    return path


@pytest.fixture()
def second_rgb_image_file(tmp_dir):
    """A second distinct temp image file (character reference)."""
    img = Image.new("RGB", (8, 8), color=(0, 128, 255))
    path = os.path.join(tmp_dir, "char_ref.png")
    img.save(path, "PNG")
    return path


def _sync_image_provider(image: Image.Image):
    """Synchronous ImageProvider that always returns the given image."""
    def provider(contents):
        return image
    return provider


def _async_image_provider(image: Image.Image):
    """Coroutine-based ImageProvider that always returns the given image."""
    async def provider(contents):
        return image
    return provider


def _failing_image_provider(exc: Exception):
    """ImageProvider that always raises the given exception."""
    def provider(contents):
        raise exc
    return provider


def _counting_image_provider(image: Image.Image, fail_count: int, exc: Exception):
    """ImageProvider that raises exc for the first fail_count calls then returns image."""
    state = {"n": 0}

    def provider(contents):
        state["n"] += 1
        if state["n"] <= fail_count:
            raise exc
        return image

    return provider


def _capturing_image_provider(image: Image.Image, captured: list):
    """ImageProvider that records every contents list and returns image."""
    def provider(contents):
        captured.append(list(contents))
        return image
    return provider


def _sync_text_provider(text: str):
    """Synchronous TextProvider that always returns the given text."""
    def provider(prompt, image):
        return text
    return provider


def _async_text_provider(text: str):
    """Coroutine-based TextProvider that always returns the given text."""
    async def provider(prompt, image):
        return text
    return provider


def _failing_text_provider(exc: Exception):
    """TextProvider that always raises the given exception."""
    def provider(prompt, image):
        raise exc
    return provider


def _make_inline_part(data) -> object:
    """Build a fake response part with inline_data."""
    return SimpleNamespace(inline_data=SimpleNamespace(data=data))


def _make_as_image_part(image: Image.Image) -> object:
    """Build a fake response part whose as_image() method returns the image."""
    class _Part:
        def as_image(self):
            return image

    return _Part()


def _make_bad_as_image_part() -> object:
    """Build a fake response part whose as_image() raises."""
    class _Part:
        def as_image(self):
            raise ValueError("broken")

    return _Part()


def _image_bytes(fmt: str = "PNG") -> bytes:
    """Encode a tiny PIL image to bytes in the given format."""
    img = Image.new("RGB", (4, 4), color="red")
    buf = io.BytesIO()
    img.save(buf, format=fmt)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# A. Pure sync helpers — _normalize_art_style
# ---------------------------------------------------------------------------


class TestNormalizeArtStyle:
    """Tests for _normalize_art_style."""

    @pytest.mark.unit
    @pytest.mark.parametrize("raw,expected", [
        ("", ""),
        ("   ", ""),
        ("\t\n", ""),
        ("cinematic", "cinematic"),
        ("Cinematic", "cinematic"),
        ("MONOCHROME", "monochrome"),
        ("oil_painting", "oil_painting"),
        ("  Surreal  ", "surreal"),
    ])
    def test_normalises_to_lowercase_stripped(self, raw, expected):
        """Input is lowercased and stripped of surrounding whitespace."""
        assert _normalize_art_style(raw) == expected


# ---------------------------------------------------------------------------
# A. Pure sync helpers — _require_text
# ---------------------------------------------------------------------------


class TestRequireText:
    """Tests for _require_text."""

    @pytest.mark.unit
    @pytest.mark.parametrize("bad_input", ["", "   ", "\t", "\n  \t"])
    def test_empty_or_whitespace_raises(self, bad_input):
        """Empty or whitespace-only input raises ValueError mentioning the field."""
        with pytest.raises(ValueError, match=r"must not be empty"):
            _require_text(bad_input, "my_field")

    @pytest.mark.unit
    def test_field_name_appears_in_error(self):
        """ValueError message contains the exact field name passed in."""
        with pytest.raises(ValueError, match=r"prompt"):
            _require_text("", "prompt")

    @pytest.mark.unit
    def test_valid_text_returned_stripped(self):
        """Valid text with surrounding spaces is returned stripped."""
        assert _require_text("  hello world  ", "field") == "hello world"

    @pytest.mark.unit
    def test_already_clean_text_returned_as_is(self):
        """Text with no surrounding spaces is returned unchanged."""
        assert _require_text("hello", "field") == "hello"


# ---------------------------------------------------------------------------
# A. Pure sync helpers — _style_suffix
# ---------------------------------------------------------------------------


class TestStyleSuffix:
    """Tests for _style_suffix."""

    @pytest.mark.unit
    @pytest.mark.parametrize("style", list(_STYLE_SUFFIXES.keys()))
    def test_known_style_returns_registered_suffix(self, style):
        """Every registered style key resolves to its non-empty suffix."""
        result = _style_suffix(style)
        assert result == _STYLE_SUFFIXES[style]
        assert len(result) > 0

    @pytest.mark.unit
    def test_unknown_style_returns_fallback(self):
        """Unrecognised art style key returns the global fallback suffix."""
        assert _style_suffix("totally_unknown_xyz") == _FALLBACK_SUFFIX

    @pytest.mark.unit
    def test_empty_string_returns_fallback(self):
        """Empty string input returns the global fallback suffix."""
        assert _style_suffix("") == _FALLBACK_SUFFIX

    @pytest.mark.unit
    def test_uppercase_resolves_via_normalisation(self):
        """Uppercase key is normalised and resolves to the correct suffix."""
        assert _style_suffix("CINEMATIC") == _STYLE_SUFFIXES["cinematic"]

    @pytest.mark.unit
    def test_cinematic_contains_anamorphic(self):
        """Cinematic suffix contains expected descriptor."""
        assert "anamorphic" in _style_suffix("cinematic")


# ---------------------------------------------------------------------------
# A. Pure sync helpers — _user_role_instruction
# ---------------------------------------------------------------------------


class TestUserRoleInstruction:
    """Tests for _user_role_instruction."""

    @pytest.mark.unit
    def test_main_character_contains_critical_and_protagonist(self):
        """main_character role produces a CRITICAL instruction about the protagonist."""
        result = _user_role_instruction("main_character")
        assert "CRITICAL" in result
        assert "protagonist" in result

    @pytest.mark.unit
    def test_side_character_mentions_supporting(self):
        """side_character role produces instruction about a supporting character."""
        result = _user_role_instruction("side_character")
        assert "supporting character" in result

    @pytest.mark.unit
    def test_audience_mentions_background(self):
        """audience role produces instruction placing the user in the background."""
        result = _user_role_instruction("audience")
        assert "background" in result

    @pytest.mark.unit
    @pytest.mark.parametrize("role", [None, "", "spectator", "villain"])
    def test_unrecognised_or_none_returns_empty(self, role):
        """None or any unrecognised role returns an empty string."""
        assert _user_role_instruction(role) == ""


# ---------------------------------------------------------------------------
# A. Pure sync helpers — _style_transfer_instruction
# ---------------------------------------------------------------------------


class TestStyleTransferInstruction:
    """Tests for _style_transfer_instruction."""

    @pytest.mark.unit
    def test_with_style_ref_starts_with_apply(self, rgb_image):
        """When a style reference image is provided instruction starts with 'Apply'."""
        result = _style_transfer_instruction(rgb_image, "cinematic")
        assert result.startswith("Apply the exact visual style")

    @pytest.mark.unit
    def test_without_style_ref_starts_with_style_colon(self):
        """When no style reference image is provided instruction starts with 'Style:'."""
        result = _style_transfer_instruction(None, "cinematic")
        assert result.startswith("Style:")

    @pytest.mark.unit
    def test_style_suffix_embedded_in_both_variants(self, rgb_image):
        """The art-style suffix appears in the instruction regardless of ref image."""
        suffix = _style_suffix("monochrome")
        assert suffix in _style_transfer_instruction(rgb_image, "monochrome")
        assert suffix in _style_transfer_instruction(None, "monochrome")


# ---------------------------------------------------------------------------
# A. Pure sync helpers — prompt builders
# ---------------------------------------------------------------------------


class TestFallbackScenePrompt:
    """Tests for _fallback_scene_prompt."""

    @pytest.mark.unit
    def test_contains_prompt_text_and_9_16(self):
        """Fallback prompt contains the scene description and 9:16 format."""
        result = _fallback_scene_prompt("warrior in a storm", "cinematic")
        assert "warrior in a storm" in result
        assert "9:16" in result

    @pytest.mark.unit
    def test_contains_style_suffix(self):
        """Fallback prompt embeds the art-style suffix."""
        result = _fallback_scene_prompt("sky", "monochrome")
        assert _style_suffix("monochrome") in result


class TestThumbnailFallbackPrompt:
    """Tests for _thumbnail_fallback_prompt."""

    @pytest.mark.unit
    def test_contains_hook_and_9_16(self):
        """Thumbnail fallback prompt contains the hook text and 9:16 format."""
        result = _thumbnail_fallback_prompt("You won't believe this!", "surreal")
        assert "You won't believe this!" in result
        assert "9:16" in result


class TestBuildSceneGenerationPrompt:
    """Tests for _build_scene_generation_prompt."""

    @pytest.mark.unit
    def test_contains_prompt_and_9_16(self):
        """Generated scene prompt contains the scene description and 9:16 marker."""
        result = _build_scene_generation_prompt("hero runs", "Style: cinematic.", "")
        assert "hero runs" in result
        assert "9:16" in result

    @pytest.mark.unit
    def test_no_text_or_watermarks_disclaimer(self):
        """Scene prompt explicitly forbids text and watermarks."""
        result = _build_scene_generation_prompt("x", "Style: x.", "")
        assert "No text or watermarks" in result


class TestBuildSceneEvolutionPrompt:
    """Tests for _build_scene_evolution_prompt."""

    @pytest.mark.unit
    def test_starts_with_transform_and_contains_prompt(self):
        """Evolution prompt opens with 'Transform' and embeds the scene text."""
        result = _build_scene_evolution_prompt("battle scene", "Style: cinematic.", "")
        assert "Transform" in result
        assert "battle scene" in result

    @pytest.mark.unit
    def test_contains_character_consistency_rule(self):
        """Evolution prompt includes a CHARACTER consistency rule."""
        result = _build_scene_evolution_prompt("x", "Style: x.", "")
        assert "CHARACTER" in result


class TestBuildConsistentScenePrompt:
    """Tests for _build_consistent_scene_prompt."""

    @pytest.mark.unit
    def test_contains_identical_and_prompt(self):
        """Consistent scene prompt uses IDENTICAL and embeds the scene text."""
        result = _build_consistent_scene_prompt("forest clearing", "Style: x.", "")
        assert "IDENTICAL" in result
        assert "forest clearing" in result


class TestBuildThumbnailPrompt:
    """Tests for _build_thumbnail_prompt."""

    @pytest.mark.unit
    def test_with_character_description_embedded(self):
        """When character_description is given it appears in the prompt."""
        result = _build_thumbnail_prompt("Go viral!", "sunset beach", "brave hero", "cinematic")
        assert "brave hero" in result
        assert "Go viral!" in result
        assert "sunset beach" in result

    @pytest.mark.unit
    def test_without_character_description_no_character_clause(self):
        """When character_description is None no 'Character:' clause appears."""
        result = _build_thumbnail_prompt("Go viral!", "sunset beach", None, "cinematic")
        assert "Character:" not in result

    @pytest.mark.unit
    def test_contains_9_16(self):
        """Thumbnail prompt requires vertical 9:16 portrait format."""
        result = _build_thumbnail_prompt("Hook", "Scene", None, "cinematic")
        assert "9:16" in result

    @pytest.mark.unit
    def test_no_text_or_watermarks_disclaimer(self):
        """Thumbnail prompt forbids text and watermarks."""
        result = _build_thumbnail_prompt("Hook", "Scene", None, "cinematic")
        assert "No text or watermarks" in result


class TestBuildCharacterSheetPrompt:
    """Tests for _build_character_sheet_prompt."""

    @pytest.mark.unit
    def test_with_user_reference_includes_user_clause(self):
        """When has_user_reference=True the user reference photo clause appears."""
        result = _build_character_sheet_prompt("tall knight", "cinematic", has_user_reference=True)
        assert "user reference photo" in result
        assert "tall knight" in result

    @pytest.mark.unit
    def test_without_user_reference_excludes_user_clause(self):
        """When has_user_reference=False no user reference clause is included."""
        result = _build_character_sheet_prompt("tall knight", "cinematic", has_user_reference=False)
        assert "user reference photo" not in result

    @pytest.mark.unit
    def test_contains_9_16_and_no_text(self):
        """Character sheet prompt specifies 9:16 and forbids text/watermarks."""
        result = _build_character_sheet_prompt("hero", "cinematic", has_user_reference=False)
        assert "9:16" in result
        assert "No text" in result


# ---------------------------------------------------------------------------
# B. Plan builders
# ---------------------------------------------------------------------------


class TestBuildSceneGenerationPlan:
    """Tests for _build_scene_generation_plan."""

    @pytest.mark.unit
    @pytest.mark.parametrize("bad_prompt", ["", "   "])
    def test_empty_prompt_raises_value_error(self, bad_prompt):
        """Empty or whitespace prompt raises ValueError naming the 'prompt' field."""
        with pytest.raises(ValueError, match=r"prompt"):
            _build_scene_generation_plan(ImageGenerationRequest(prompt=bad_prompt))

    @pytest.mark.unit
    def test_mode_generation_without_refs(self):
        """Without previous_image_path or character_reference_path mode is 'generation'."""
        plan = _build_scene_generation_plan(ImageGenerationRequest(prompt="a knight"))
        assert plan.mode == "generation"

    @pytest.mark.unit
    def test_mode_scene_evolution_with_previous_only(self, rgb_image_file):
        """With only a previous_image_path the mode is 'scene-evolution'."""
        plan = _build_scene_generation_plan(
            ImageGenerationRequest(prompt="a knight", previous_image_path=rgb_image_file)
        )
        assert plan.mode == "scene-evolution"

    @pytest.mark.unit
    def test_mode_consistent_scene_with_distinct_char_ref(self, rgb_image_file, second_rgb_image_file):
        """With previous_image_path and a different character_reference_path mode is 'consistent-scene'."""
        plan = _build_scene_generation_plan(
            ImageGenerationRequest(
                prompt="hero attacks",
                previous_image_path=rgb_image_file,
                character_reference_path=second_rgb_image_file,
            )
        )
        assert plan.mode == "consistent-scene"

    @pytest.mark.unit
    def test_art_style_normalised_to_lowercase(self):
        """Art style stored in the plan is always lowercase."""
        plan = _build_scene_generation_plan(
            ImageGenerationRequest(prompt="scene", art_style="MONOCHROME")
        )
        assert plan.art_style == "monochrome"

    @pytest.mark.unit
    def test_output_format_is_png(self):
        """Scene generation plan uses PNG output format and .png suffix."""
        plan = _build_scene_generation_plan(ImageGenerationRequest(prompt="scene"))
        assert plan.output_format == "PNG"
        assert plan.output_suffix == ".png"
        assert "voicevid_gemini_" in plan.output_prefix

    @pytest.mark.unit
    def test_fallback_contents_non_empty(self):
        """Fallback contents list always contains at least one item."""
        plan = _build_scene_generation_plan(ImageGenerationRequest(prompt="scene"))
        assert len(plan.fallback_contents) >= 1

    @pytest.mark.unit
    def test_primary_contents_starts_with_string(self):
        """Primary contents list starts with the text prompt string."""
        plan = _build_scene_generation_plan(ImageGenerationRequest(prompt="epic battle"))
        assert isinstance(plan.primary_contents[0], str)
        assert "epic battle" in plan.primary_contents[0]

    @pytest.mark.unit
    def test_log_target_truncated_to_80(self):
        """log_target is truncated to at most 80 characters."""
        long_prompt = "x" * 200
        plan = _build_scene_generation_plan(ImageGenerationRequest(prompt=long_prompt))
        assert len(plan.log_target) <= 80


class TestBuildCharacterSheetPlan:
    """Tests for _build_character_sheet_plan."""

    @pytest.mark.unit
    @pytest.mark.parametrize("bad_desc", ["", "   "])
    def test_empty_description_raises_value_error(self, bad_desc):
        """Empty character_description raises ValueError naming the field."""
        with pytest.raises(ValueError, match=r"character_description"):
            _build_character_sheet_plan(CharacterSheetRequest(character_description=bad_desc))

    @pytest.mark.unit
    def test_mode_is_character_sheet(self):
        """Plan mode is always 'character-sheet'."""
        plan = _build_character_sheet_plan(
            CharacterSheetRequest(character_description="a wizard")
        )
        assert plan.mode == "character-sheet"

    @pytest.mark.unit
    def test_output_format_png_and_prefix(self):
        """Character sheet plan uses PNG format and the charsheet prefix."""
        plan = _build_character_sheet_plan(
            CharacterSheetRequest(character_description="a wizard")
        )
        assert plan.output_format == "PNG"
        assert plan.output_suffix == ".png"
        assert "voicevid_charsheet_" in plan.output_prefix

    @pytest.mark.unit
    def test_fallback_contents_starts_with_string(self):
        """Fallback contents first element is a string prompt."""
        plan = _build_character_sheet_plan(
            CharacterSheetRequest(character_description="hero")
        )
        assert isinstance(plan.fallback_contents[0], str)


class TestBuildThumbnailPlan:
    """Tests for _build_thumbnail_plan."""

    @pytest.mark.unit
    @pytest.mark.parametrize("hook,scene", [
        ("", "valid scene"),
        ("valid hook", ""),
        ("   ", "valid scene"),
        ("valid hook", "   "),
    ])
    def test_empty_required_fields_raise(self, hook, scene):
        """Empty hook_text or scene_visual_prompt raises ValueError."""
        with pytest.raises(ValueError, match=r"must not be empty"):
            _build_thumbnail_plan(
                ThumbnailRequest(
                    hook_text=hook, scene_visual_prompt=scene, character_description=None
                )
            )

    @pytest.mark.unit
    def test_mode_is_thumbnail(self):
        """Plan mode is always 'thumbnail'."""
        plan = _build_thumbnail_plan(
            ThumbnailRequest(
                hook_text="Watch this!", scene_visual_prompt="epic battle", character_description=None
            )
        )
        assert plan.mode == "thumbnail"

    @pytest.mark.unit
    def test_output_format_jpeg_quality_92(self):
        """Thumbnail plan uses JPEG format, .jpg suffix, and quality=92."""
        plan = _build_thumbnail_plan(
            ThumbnailRequest(
                hook_text="Hook!", scene_visual_prompt="Scene", character_description=None
            )
        )
        assert plan.output_format == "JPEG"
        assert plan.output_suffix == ".jpg"
        assert plan.save_kwargs.get("quality") == 92
        assert "voicevid_thumb_" in plan.output_prefix


# ---------------------------------------------------------------------------
# C. _extract_image
# ---------------------------------------------------------------------------


class TestExtractImage:
    """Tests for _extract_image."""

    @pytest.mark.unit
    def test_as_image_method_returns_rgb(self, rgb_image):
        """Part with a callable as_image() returning an image yields an RGB image."""
        response = SimpleNamespace(parts=[_make_as_image_part(rgb_image)])
        result = _extract_image(response)
        assert isinstance(result, Image.Image)
        assert result.mode == "RGB"

    @pytest.mark.unit
    def test_inline_data_raw_bytes_yields_rgb(self, rgb_image):
        """Part with raw PNG bytes in inline_data is decoded into an RGB image."""
        buf = io.BytesIO()
        rgb_image.save(buf, "PNG")
        response = SimpleNamespace(parts=[_make_inline_part(buf.getvalue())])
        result = _extract_image(response)
        assert isinstance(result, Image.Image)
        assert result.mode == "RGB"

    @pytest.mark.unit
    def test_inline_data_base64_string_yields_rgb(self, rgb_image):
        """Part with base64-encoded string inline_data is decoded into an RGB image."""
        buf = io.BytesIO()
        rgb_image.save(buf, "PNG")
        encoded = base64.b64encode(buf.getvalue()).decode("ascii")
        response = SimpleNamespace(parts=[_make_inline_part(encoded)])
        result = _extract_image(response)
        assert isinstance(result, Image.Image)
        assert result.mode == "RGB"

    @pytest.mark.unit
    def test_empty_parts_returns_none(self):
        """Response with an empty parts list returns None."""
        assert _extract_image(SimpleNamespace(parts=[])) is None

    @pytest.mark.unit
    def test_none_parts_returns_none(self):
        """Response where the parts attribute is None returns None."""
        assert _extract_image(SimpleNamespace(parts=None)) is None

    @pytest.mark.unit
    def test_missing_parts_attribute_returns_none(self):
        """Response with no parts attribute at all returns None."""
        assert _extract_image(SimpleNamespace()) is None

    @pytest.mark.unit
    def test_broken_inline_data_bytes_returns_none(self):
        """Part with invalid image bytes in inline_data returns None without raising."""
        response = SimpleNamespace(parts=[_make_inline_part(b"not-an-image")])
        assert _extract_image(response) is None

    @pytest.mark.unit
    def test_broken_as_image_falls_through_to_inline(self, rgb_image):
        """When as_image() raises, the code falls through to check inline_data."""
        buf = io.BytesIO()
        rgb_image.save(buf, "PNG")
        bad_part = _make_bad_as_image_part()
        good_part = _make_inline_part(buf.getvalue())
        response = SimpleNamespace(parts=[bad_part, good_part])
        result = _extract_image(response)
        assert result is not None

    @pytest.mark.unit
    def test_as_image_returning_none_falls_through(self, rgb_image):
        """When as_image() returns None the code tries inline_data next."""
        buf = io.BytesIO()
        rgb_image.save(buf, "PNG")

        class _NoneImagePart:
            def as_image(self):
                return None

        good_part = _make_inline_part(buf.getvalue())
        response = SimpleNamespace(parts=[_NoneImagePart(), good_part])
        result = _extract_image(response)
        assert result is not None

    @pytest.mark.unit
    def test_image_converted_to_rgb(self):
        """Extracted image is always converted to RGB mode."""
        rgba_img = Image.new("RGBA", (4, 4), color=(0, 0, 0, 128))
        response = SimpleNamespace(parts=[_make_as_image_part(rgba_img)])
        result = _extract_image(response)
        assert result.mode == "RGB"


# ---------------------------------------------------------------------------
# D. _style_reference_image
# ---------------------------------------------------------------------------


class TestStyleReferenceImage:
    """Tests for _style_reference_image."""

    @pytest.mark.unit
    def test_loads_png_from_styles_dir(self, tmp_dir, monkeypatch, rgb_image):
        """When a .png file exists for the style key it is loaded as RGB."""
        monkeypatch.setattr("services.gemini.image._STYLES_DIR", tmp_dir)
        path = os.path.join(tmp_dir, "cinematic.png")
        rgb_image.save(path, "PNG")
        result = _style_reference_image("cinematic")
        assert result is not None
        assert result.mode == "RGB"

    @pytest.mark.unit
    def test_returns_none_when_no_file(self, tmp_dir, monkeypatch):
        """When no style file exists None is returned."""
        monkeypatch.setattr("services.gemini.image._STYLES_DIR", tmp_dir)
        assert _style_reference_image("cinematic") is None

    @pytest.mark.unit
    def test_returns_none_when_file_is_corrupt(self, tmp_dir, monkeypatch):
        """When the style file is not a valid image None is returned."""
        monkeypatch.setattr("services.gemini.image._STYLES_DIR", tmp_dir)
        bad_path = os.path.join(tmp_dir, "cinematic.png")
        with open(bad_path, "w") as f:
            f.write("not-an-image")
        assert _style_reference_image("cinematic") is None


# ---------------------------------------------------------------------------
# D. _save_temp_image
# ---------------------------------------------------------------------------


class TestSaveTempImage:
    """Tests for _save_temp_image."""

    @pytest.mark.unit
    def test_creates_file_with_correct_prefix_and_suffix(self, rgb_image):
        """Saved file exists and its basename matches the requested prefix and suffix."""
        path = _save_temp_image(
            rgb_image,
            prefix="test_prefix_",
            suffix=".png",
            output_format="PNG",
        )
        try:
            assert os.path.exists(path)
            basename = os.path.basename(path)
            assert basename.startswith("test_prefix_")
            assert basename.endswith(".png")
        finally:
            if os.path.exists(path):
                os.remove(path)

    @pytest.mark.unit
    def test_jpeg_save_with_quality_is_readable(self, rgb_image):
        """JPEG saved with quality kwarg produces a file that PIL can open as JPEG."""
        path = _save_temp_image(
            rgb_image,
            prefix="test_jpg_",
            suffix=".jpg",
            output_format="JPEG",
            save_kwargs={"quality": 85},
        )
        try:
            assert os.path.exists(path)
            with Image.open(path) as img:
                assert img.format == "JPEG"
        finally:
            if os.path.exists(path):
                os.remove(path)

    @pytest.mark.unit
    def test_saved_file_has_correct_dimensions(self, rgb_image):
        """The persisted file can be reopened and has the original dimensions."""
        path = _save_temp_image(
            rgb_image,
            prefix="dims_",
            suffix=".png",
            output_format="PNG",
        )
        try:
            with Image.open(path) as img:
                assert img.size == (10, 10)
        finally:
            if os.path.exists(path):
                os.remove(path)


# ---------------------------------------------------------------------------
# E. Async public API — generate_image
# ---------------------------------------------------------------------------


class TestGenerateImage:
    """Tests for generate_image."""

    @pytest.mark.unit
    @pytest.mark.parametrize("bad_prompt", ["", "   "])
    async def test_empty_prompt_raises_value_error(self, bad_prompt):
        """Empty or whitespace-only prompt raises ValueError before calling any provider."""
        with pytest.raises(ValueError, match=r"prompt"):
            await generate_image(bad_prompt)

    @pytest.mark.unit
    async def test_happy_path_returns_png_file(self, rgb_image):
        """Valid prompt with a sync provider returns an existing .png path."""
        path = await generate_image("A dragon", image_provider=_sync_image_provider(rgb_image))
        try:
            assert isinstance(path, str)
            assert path.endswith(".png")
            assert os.path.exists(path)
        finally:
            if os.path.exists(path):
                os.remove(path)

    @pytest.mark.unit
    async def test_async_provider_is_awaited(self, rgb_image):
        """Coroutine-based image_provider is awaited and file is created."""
        path = await generate_image("A dragon", image_provider=_async_image_provider(rgb_image))
        try:
            assert path.endswith(".png")
            assert os.path.exists(path)
        finally:
            if os.path.exists(path):
                os.remove(path)

    @pytest.mark.unit
    async def test_fallback_used_when_primary_fails(self, rgb_image):
        """When primary provider raises GeminiImageProviderError fallback returns a path."""
        provider = _counting_image_provider(
            rgb_image, fail_count=1, exc=GeminiImageProviderError("primary boom")
        )
        path = await generate_image("A dragon", image_provider=provider)
        try:
            assert os.path.exists(path)
        finally:
            if os.path.exists(path):
                os.remove(path)

    @pytest.mark.unit
    async def test_both_attempts_fail_reraises_last_error(self):
        """When both primary and fallback fail the last GeminiImageServiceError is raised."""
        provider = _failing_image_provider(GeminiImageProviderError("always fails"))
        with pytest.raises(GeminiImageProviderError, match=r"always fails"):
            await generate_image("A dragon", image_provider=provider)

    @pytest.mark.unit
    async def test_generic_exception_wrapped_and_reraised(self):
        """An unexpected non-service exception from the provider is wrapped and re-raised."""
        provider = _failing_image_provider(RuntimeError("unexpected"))
        with pytest.raises((GeminiImageProviderError, GeminiImageServiceError)):
            await generate_image("A dragon", image_provider=provider)

    @pytest.mark.unit
    async def test_fallback_content_starts_with_cinematic_portrait(self, rgb_image):
        """When primary fails the fallback prompt starts with 'Cinematic portrait scene:'."""
        captured: list = []

        async def provider(contents):
            captured.append(list(contents))
            if len(captured) == 1:
                raise GeminiImageProviderError("primary failed")
            return rgb_image

        path = await generate_image("An intense scene", image_provider=provider)
        try:
            assert len(captured) == 2
            assert captured[1][0].startswith("Cinematic portrait scene:")
        finally:
            if os.path.exists(path):
                os.remove(path)

    @pytest.mark.unit
    async def test_generation_mode_primary_contents(self, rgb_image, monkeypatch):
        """Fresh generation primary prompt contains the scene description."""
        monkeypatch.setattr(
            "services.gemini.image._style_reference_image", lambda _: None
        )
        captured: list = []
        path = await generate_image(
            "A cinematic skyline",
            art_style="cinematic",
            image_provider=_capturing_image_provider(rgb_image, captured),
        )
        try:
            assert len(captured) == 1
            assert "A cinematic skyline" in captured[0][0]
        finally:
            if os.path.exists(path):
                os.remove(path)

    @pytest.mark.unit
    async def test_scene_evolution_mode_with_previous(self, rgb_image, rgb_image_file, monkeypatch):
        """With a previous_image_path the prompt contains 'Transform this image'."""
        monkeypatch.setattr(
            "services.gemini.image._style_reference_image", lambda _: None
        )
        captured: list = []
        path = await generate_image(
            "Hero runs forward",
            previous_image_path=rgb_image_file,
            image_provider=_capturing_image_provider(rgb_image, captured),
        )
        try:
            assert "Transform this image into a new 2-second scene" in captured[0][0]
        finally:
            if os.path.exists(path):
                os.remove(path)

    @pytest.mark.unit
    async def test_consistent_scene_mode_with_distinct_refs(
        self, rgb_image, rgb_image_file, second_rgb_image_file, monkeypatch
    ):
        """With previous + distinct character ref the prompt contains 'visual story'."""
        monkeypatch.setattr(
            "services.gemini.image._style_reference_image", lambda _: None
        )
        captured: list = []
        path = await generate_image(
            "The hero enters a new room",
            previous_image_path=rgb_image_file,
            character_reference_path=second_rgb_image_file,
            image_provider=_capturing_image_provider(rgb_image, captured),
        )
        try:
            assert "Create a new 2-second scene image continuing this visual story" in captured[0][0]
        finally:
            if os.path.exists(path):
                os.remove(path)

    @pytest.mark.unit
    @pytest.mark.parametrize("art_style", ["cinematic", "monochrome", "surreal", "oil_painting"])
    async def test_registered_art_styles_accepted(self, rgb_image, art_style):
        """Every registered art style is accepted by generate_image without error."""
        path = await generate_image(
            "Scene", art_style=art_style, image_provider=_sync_image_provider(rgb_image)
        )
        try:
            assert os.path.exists(path)
        finally:
            if os.path.exists(path):
                os.remove(path)

    @pytest.mark.unit
    async def test_unknown_art_style_uses_fallback_suffix(self, rgb_image):
        """An unknown art style uses _FALLBACK_SUFFIX without raising."""
        path = await generate_image(
            "Scene", art_style="unknown_xyz", image_provider=_sync_image_provider(rgb_image)
        )
        try:
            assert os.path.exists(path)
        finally:
            if os.path.exists(path):
                os.remove(path)


# ---------------------------------------------------------------------------
# E. Async public API — generate_character_sheet
# ---------------------------------------------------------------------------


class TestGenerateCharacterSheet:
    """Tests for generate_character_sheet."""

    @pytest.mark.unit
    @pytest.mark.parametrize("bad_desc", ["", "   "])
    async def test_empty_description_raises(self, bad_desc):
        """Empty or whitespace character_description raises ValueError."""
        with pytest.raises(ValueError, match=r"character_description"):
            await generate_character_sheet(bad_desc)

    @pytest.mark.unit
    async def test_happy_path_returns_png_file(self, rgb_image):
        """Valid description returns an existing .png temp file path."""
        path = await generate_character_sheet(
            "A tall wizard", image_provider=_sync_image_provider(rgb_image)
        )
        try:
            assert isinstance(path, str)
            assert path.endswith(".png")
            assert os.path.exists(path)
        finally:
            if os.path.exists(path):
                os.remove(path)

    @pytest.mark.unit
    async def test_fallback_used_when_primary_fails(self, rgb_image):
        """When primary attempt fails fallback is used and a valid path is returned."""
        provider = _counting_image_provider(
            rgb_image, fail_count=1, exc=GeminiImageProviderError("sheet fail")
        )
        path = await generate_character_sheet("warrior", image_provider=provider)
        try:
            assert os.path.exists(path)
        finally:
            if os.path.exists(path):
                os.remove(path)

    @pytest.mark.unit
    async def test_both_fail_reraises(self):
        """When both primary and fallback fail the error propagates."""
        provider = _failing_image_provider(GeminiImageProviderError("always fails"))
        with pytest.raises(GeminiImageProviderError):
            await generate_character_sheet("warrior", image_provider=provider)

    @pytest.mark.unit
    async def test_with_user_reference_path(self, rgb_image, rgb_image_file):
        """Providing a valid user_reference_path is accepted and returns a path."""
        path = await generate_character_sheet(
            "A wizard",
            user_reference_path=rgb_image_file,
            image_provider=_sync_image_provider(rgb_image),
        )
        try:
            assert os.path.exists(path)
        finally:
            if os.path.exists(path):
                os.remove(path)

    @pytest.mark.unit
    async def test_primary_prompt_contains_full_body(self, rgb_image, monkeypatch):
        """Primary prompt starts with 'Full-body character reference sheet'."""
        monkeypatch.setattr(
            "services.gemini.image._style_reference_image", lambda _: None
        )
        captured: list = []
        path = await generate_character_sheet(
            "Tall explorer with a red coat",
            image_provider=_capturing_image_provider(rgb_image, captured),
        )
        try:
            assert "Full-body character reference sheet" in captured[0][0]
        finally:
            if os.path.exists(path):
                os.remove(path)

    @pytest.mark.unit
    async def test_fallback_prompt_starts_correctly(self, rgb_image, monkeypatch):
        """Fallback prompt starts with 'Character reference sheet, neutral pose'."""
        monkeypatch.setattr(
            "services.gemini.image._style_reference_image", lambda _: None
        )
        captured: list = []
        provider = _counting_image_provider(
            rgb_image,
            fail_count=1,
            exc=GeminiImageProviderError("retry"),
        )

        # We need a capturing + counting hybrid
        calls: list = []

        async def hybrid_provider(contents):
            calls.append(list(contents))
            if len(calls) == 1:
                raise GeminiImageProviderError("retry")
            return rgb_image

        path = await generate_character_sheet(
            "Tall explorer",
            image_provider=hybrid_provider,
        )
        try:
            assert calls[1][0].startswith("Character reference sheet, neutral pose")
        finally:
            if os.path.exists(path):
                os.remove(path)


# ---------------------------------------------------------------------------
# E. Async public API — generate_thumbnail
# ---------------------------------------------------------------------------


class TestGenerateThumbnail:
    """Tests for generate_thumbnail."""

    @pytest.mark.unit
    @pytest.mark.parametrize("hook,scene", [
        ("", "valid scene"),
        ("valid hook", ""),
        ("   ", "valid scene"),
        ("valid hook", "   "),
    ])
    async def test_empty_required_fields_raise(self, hook, scene):
        """Empty hook_text or scene_visual_prompt raises ValueError."""
        with pytest.raises(ValueError, match=r"must not be empty"):
            await generate_thumbnail(hook, scene, None)

    @pytest.mark.unit
    async def test_happy_path_returns_jpg_file(self, rgb_image):
        """Valid inputs return an existing .jpg temp file path."""
        path = await generate_thumbnail(
            "You won't believe this!",
            "sunset beach",
            None,
            image_provider=_sync_image_provider(rgb_image),
        )
        try:
            assert isinstance(path, str)
            assert path.endswith(".jpg")
            assert os.path.exists(path)
        finally:
            if os.path.exists(path):
                os.remove(path)

    @pytest.mark.unit
    async def test_with_character_description(self, rgb_image):
        """Thumbnail generation with a character description succeeds."""
        path = await generate_thumbnail(
            "Epic battle!",
            "castle courtyard",
            "brave knight",
            image_provider=_sync_image_provider(rgb_image),
        )
        try:
            assert os.path.exists(path)
        finally:
            if os.path.exists(path):
                os.remove(path)

    @pytest.mark.unit
    async def test_fallback_used_when_primary_fails(self, rgb_image):
        """When primary attempt raises the fallback is used."""
        provider = _counting_image_provider(
            rgb_image, fail_count=1, exc=GeminiImageProviderError("thumb fail")
        )
        path = await generate_thumbnail(
            "Hook", "Scene", None, image_provider=provider
        )
        try:
            assert os.path.exists(path)
        finally:
            if os.path.exists(path):
                os.remove(path)

    @pytest.mark.unit
    async def test_both_fail_reraises(self):
        """When both primary and fallback fail the error propagates."""
        provider = _failing_image_provider(GeminiImageProviderError("thumb fail"))
        with pytest.raises(GeminiImageProviderError):
            await generate_thumbnail("Hook", "Scene", None, image_provider=provider)

    @pytest.mark.unit
    async def test_primary_prompt_contains_thumbnail_marker(self, rgb_image, monkeypatch):
        """Primary prompt starts with the thumbnail creation instruction."""
        monkeypatch.setattr(
            "services.gemini.image._style_reference_image", lambda _: None
        )
        captured: list = []
        path = await generate_thumbnail(
            "This changed everything",
            "A shocked person under dramatic lighting",
            "A confident presenter",
            image_provider=_capturing_image_provider(rgb_image, captured),
        )
        try:
            assert "Create a visually striking social media video thumbnail." in captured[0][0]
        finally:
            if os.path.exists(path):
                os.remove(path)

    @pytest.mark.unit
    async def test_fallback_prompt_starts_with_scroll_stopping(self, rgb_image, monkeypatch):
        """Fallback prompt starts with 'Scroll-stopping video thumbnail:'."""
        monkeypatch.setattr(
            "services.gemini.image._style_reference_image", lambda _: None
        )
        calls: list = []

        async def hybrid_provider(contents):
            calls.append(list(contents))
            if len(calls) == 1:
                raise GeminiImageProviderError("retry")
            return rgb_image

        path = await generate_thumbnail(
            "This changed everything",
            "Shocked crowd",
            None,
            image_provider=hybrid_provider,
        )
        try:
            assert calls[1][0].startswith("Scroll-stopping video thumbnail:")
        finally:
            if os.path.exists(path):
                os.remove(path)


# ---------------------------------------------------------------------------
# E. Async public API — describe_reference_subject
# ---------------------------------------------------------------------------


class TestDescribeReferenceSubject:
    """Tests for describe_reference_subject."""

    @pytest.mark.unit
    @pytest.mark.parametrize("bad_path", ["", None])
    async def test_empty_or_none_path_returns_empty_string(self, bad_path):
        """Empty string or None image path immediately returns an empty string."""
        result = await describe_reference_subject(bad_path)
        assert result == ""

    @pytest.mark.unit
    async def test_nonexistent_path_returns_empty_string(self):
        """A path that does not exist on disk returns an empty string."""
        result = await describe_reference_subject("/nonexistent/totally/fake/img.jpg")
        assert result == ""

    @pytest.mark.unit
    async def test_valid_image_calls_provider_and_returns_text(self, rgb_image_file):
        """Valid image file path calls the text_provider and returns its output."""
        provider = _sync_text_provider("A woman in her 30s, casual attire.")
        result = await describe_reference_subject(rgb_image_file, text_provider=provider)
        assert result == "A woman in her 30s, casual attire."

    @pytest.mark.unit
    async def test_provider_output_is_stripped(self, rgb_image_file):
        """Leading and trailing whitespace in the provider response is stripped."""
        provider = _sync_text_provider("  A man in his 40s.  ")
        result = await describe_reference_subject(rgb_image_file, text_provider=provider)
        assert result == "A man in his 40s."

    @pytest.mark.unit
    async def test_provider_raises_returns_empty_string(self, rgb_image_file):
        """When the text_provider raises any exception an empty string is returned."""
        provider = _failing_text_provider(RuntimeError("vision unavailable"))
        result = await describe_reference_subject(rgb_image_file, text_provider=provider)
        assert result == ""

    @pytest.mark.unit
    async def test_async_text_provider_is_awaited(self, rgb_image_file):
        """Coroutine-based text_provider is awaited and its result returned."""
        result = await describe_reference_subject(
            rgb_image_file, text_provider=_async_text_provider("Async description.")
        )
        assert result == "Async description."

    @pytest.mark.unit
    async def test_prompt_contains_describe_the_person(self, rgb_image_file):
        """The prompt passed to the text_provider asks to describe the person in the photo."""
        received_prompt: list = []

        def capturing_provider(prompt, image):
            received_prompt.append(prompt)
            return "A person."

        await describe_reference_subject(rgb_image_file, text_provider=capturing_provider)
        assert "Describe the person in this photo" in received_prompt[0]

    @pytest.mark.unit
    async def test_image_passed_to_provider_is_rgb(self, rgb_image_file):
        """The PIL image passed to the text_provider has mode RGB."""
        received_image: list = []

        def capturing_provider(prompt, image):
            received_image.append(image)
            return "Description."

        await describe_reference_subject(rgb_image_file, text_provider=capturing_provider)
        assert received_image[0].mode == "RGB"


# ---------------------------------------------------------------------------
# Integration test stubs — run manually with: pytest -m api
# Require: GEMINI_API_KEY, GCP ADC (gcloud auth application-default login)
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.api
@pytest.mark.skip(reason="Requires live GEMINI_API_KEY — run manually")
async def test_generate_image_real_api():
    """Live Gemini image generation call — validates end-to-end PNG creation."""
    pass


@pytest.mark.integration
@pytest.mark.api
@pytest.mark.skip(reason="Requires live GEMINI_API_KEY — run manually")
async def test_generate_character_sheet_real_api():
    """Live Gemini character sheet generation — validates full pipeline."""
    pass


@pytest.mark.integration
@pytest.mark.api
@pytest.mark.skip(reason="Requires live GEMINI_API_KEY — run manually")
async def test_generate_thumbnail_real_api():
    """Live Gemini thumbnail generation — validates JPEG output."""
    pass


@pytest.mark.integration
@pytest.mark.api
@pytest.mark.skip(reason="Requires live GEMINI_API_KEY — run manually")
async def test_describe_reference_subject_real_api():
    """Live Gemini vision call — validates subject description from a real photo."""
    pass
