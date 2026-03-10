from __future__ import annotations

import asyncio
import base64
import io
from types import SimpleNamespace

import pytest
from PIL import Image

from services.gemini.image import (
    GeminiImageProviderError,
    GeminiImageResponseError,
    _extract_image,
    _save_temp_image,
    _style_reference_image,
    _style_suffix,
    describe_reference_subject,
    generate_character_sheet,
    generate_image,
    generate_thumbnail,
)


def _image_bytes(fmt: str = "PNG") -> bytes:
    image = Image.new("RGB", (4, 4), color="red")
    buf = io.BytesIO()
    image.save(buf, format=fmt)
    return buf.getvalue()


def _dummy_image(color: str = "blue") -> Image.Image:
    return Image.new("RGB", (8, 8), color=color)


class _PartWithImage:
    def __init__(self, image: Image.Image):
        self._image = image

    def as_image(self) -> Image.Image:
        return self._image


class _InlinePart:
    def __init__(self, data):
        self.inline_data = SimpleNamespace(data=data)


class _BadPart:
    def as_image(self):
        raise ValueError("boom")


@pytest.fixture()
def sample_image_path(tmp_path):
    path = tmp_path / "sample.png"
    _dummy_image().save(path, format="PNG")
    return str(path)


@pytest.fixture()
def style_ref(monkeypatch):
    monkeypatch.setattr("services.gemini.image._style_reference_image", lambda _style: _dummy_image("green"))


@pytest.mark.unit
def test_style_suffix_known_and_fallback():
    assert "anamorphic widescreen cinema" in _style_suffix("cinematic")
    assert _style_suffix("unknown-style") == (
        "vertical 9:16 portrait, cinematic dramatic lighting, ultra-detailed, top quality"
    )


@pytest.mark.unit
def test_style_reference_image_loads_from_directory(tmp_path, monkeypatch):
    style_dir = tmp_path / "styles"
    style_dir.mkdir()
    image_path = style_dir / "cinematic.png"
    _dummy_image().save(image_path, format="PNG")
    monkeypatch.setattr("services.gemini.image._STYLES_DIR", str(style_dir))

    image = _style_reference_image("cinematic")

    assert image is not None
    assert image.mode == "RGB"


@pytest.mark.unit
def test_style_reference_image_returns_none_when_unreadable(tmp_path, monkeypatch):
    style_dir = tmp_path / "styles"
    style_dir.mkdir()
    bad_file = style_dir / "cinematic.png"
    bad_file.write_text("not-an-image", encoding="utf-8")
    monkeypatch.setattr("services.gemini.image._STYLES_DIR", str(style_dir))

    assert _style_reference_image("cinematic") is None


@pytest.mark.unit
def test_extract_image_uses_as_image():
    response = SimpleNamespace(parts=[_PartWithImage(_dummy_image())])

    extracted = _extract_image(response)

    assert extracted is not None
    assert extracted.size == (8, 8)


@pytest.mark.unit
def test_extract_image_uses_inline_bytes():
    response = SimpleNamespace(parts=[_InlinePart(_image_bytes())])

    extracted = _extract_image(response)

    assert extracted is not None
    assert extracted.mode == "RGB"


@pytest.mark.unit
def test_extract_image_uses_inline_base64():
    response = SimpleNamespace(parts=[_InlinePart(base64.b64encode(_image_bytes()).decode("ascii"))])

    extracted = _extract_image(response)

    assert extracted is not None
    assert extracted.mode == "RGB"


@pytest.mark.unit
def test_extract_image_returns_none_for_malformed_parts():
    response = SimpleNamespace(parts=[_BadPart(), _InlinePart("bad-base64")])

    assert _extract_image(response) is None


@pytest.mark.unit
def test_extract_image_handles_missing_parts():
    assert _extract_image(SimpleNamespace()) is None


@pytest.mark.unit
def test_save_temp_image_writes_expected_format(tmp_path, monkeypatch):
    monkeypatch.setattr("services.gemini.image.tempfile.mkstemp", lambda prefix, suffix: (1, str(tmp_path / f"{prefix}out{suffix}")))
    monkeypatch.setattr("services.gemini.image.os.close", lambda _fd: None)

    path = _save_temp_image(_dummy_image(), prefix="voicevid_", suffix=".jpg", output_format="JPEG", save_kwargs={"quality": 80})

    assert path.endswith(".jpg")
    with Image.open(path) as image:
        assert image.format == "JPEG"


@pytest.mark.unit
def test_describe_reference_subject_empty_or_missing_returns_empty():
    assert asyncio.run(describe_reference_subject("")) == ""
    assert asyncio.run(describe_reference_subject("/tmp/does-not-exist-image.png")) == ""


@pytest.mark.unit
def test_describe_reference_subject_returns_stripped_text(sample_image_path):
    async def text_provider(prompt: str, image: Image.Image) -> str:
        assert "Describe the person in this photo" in prompt
        assert image.mode == "RGB"
        return "  A person in a blue jacket.  "

    result = asyncio.run(describe_reference_subject(sample_image_path, text_provider=text_provider))

    assert result == "A person in a blue jacket."


@pytest.mark.unit
def test_describe_reference_subject_returns_empty_on_provider_failure(sample_image_path):
    async def text_provider(_prompt: str, _image: Image.Image) -> str:
        raise RuntimeError("provider down")

    assert asyncio.run(describe_reference_subject(sample_image_path, text_provider=text_provider)) == ""


@pytest.mark.unit
def test_generate_image_fresh_generation_branch(style_ref):
    seen_contents: list[list[object]] = []

    async def image_provider(contents: list[object]) -> Image.Image:
        seen_contents.append(contents)
        return _dummy_image()

    path = asyncio.run(generate_image("A cinematic skyline", art_style="cinematic", image_provider=image_provider))

    assert len(seen_contents) == 1
    assert "A cinematic skyline." in seen_contents[0][0]
    assert "Apply the exact visual style shown in the style reference image" in seen_contents[0][0]
    assert len(seen_contents[0]) == 2
    assert path.endswith(".png")


@pytest.mark.unit
def test_generate_image_scene_evolution_branch(sample_image_path, style_ref):
    seen_contents: list[list[object]] = []

    async def image_provider(contents: list[object]) -> Image.Image:
        seen_contents.append(contents)
        return _dummy_image()

    asyncio.run(
        generate_image(
            "Hero runs forward",
            art_style="cinematic",
            previous_image_path=sample_image_path,
            user_reference_path=sample_image_path,
            user_character_role="side_character",
            image_provider=image_provider,
        )
    )

    assert len(seen_contents) == 1
    assert "Transform this image into a new 2-second scene" in seen_contents[0][0]
    assert len(seen_contents[0]) == 4


@pytest.mark.unit
def test_generate_image_consistent_scene_branch(sample_image_path, style_ref):
    char_ref_path = sample_image_path.replace("sample.png", "character.png")
    _dummy_image("purple").save(char_ref_path, format="PNG")
    seen_contents: list[list[object]] = []

    async def image_provider(contents: list[object]) -> Image.Image:
        seen_contents.append(contents)
        return _dummy_image()

    asyncio.run(
        generate_image(
            "The hero enters a new room",
            art_style="cinematic",
            previous_image_path=sample_image_path,
            character_reference_path=char_ref_path,
            user_reference_path=sample_image_path,
            user_character_role="main_character",
            image_provider=image_provider,
        )
    )

    assert len(seen_contents) == 1
    assert "Create a new 2-second scene image continuing this visual story" in seen_contents[0][0]
    assert len(seen_contents[0]) == 4


@pytest.mark.unit
def test_generate_image_retries_once_and_uses_fallback(style_ref):
    seen_contents: list[list[object]] = []

    async def image_provider(contents: list[object]) -> Image.Image:
        seen_contents.append(contents)
        if len(seen_contents) == 1:
            raise GeminiImageProviderError("primary failed")
        return _dummy_image()

    path = asyncio.run(generate_image("An intense scene", art_style="cinematic", image_provider=image_provider))

    assert len(seen_contents) == 2
    assert seen_contents[1][0].startswith("Cinematic portrait scene:")
    assert path.endswith(".png")


@pytest.mark.unit
def test_generate_image_raises_typed_error_when_all_attempts_fail(style_ref):
    async def image_provider(_contents: list[object]) -> Image.Image:
        raise GeminiImageResponseError("no image")

    with pytest.raises(GeminiImageResponseError, match="no image"):
        asyncio.run(generate_image("A failed scene", art_style="cinematic", image_provider=image_provider))


@pytest.mark.unit
def test_generate_character_sheet_builds_expected_flow(sample_image_path, style_ref):
    seen_contents: list[list[object]] = []

    async def image_provider(contents: list[object]) -> Image.Image:
        seen_contents.append(contents)
        if len(seen_contents) == 1:
            raise GeminiImageProviderError("retry")
        return _dummy_image()

    path = asyncio.run(
        generate_character_sheet(
            "Tall explorer with a red coat",
            art_style="cinematic",
            user_reference_path=sample_image_path,
            image_provider=image_provider,
        )
    )

    assert len(seen_contents) == 2
    assert "Full-body character reference sheet" in seen_contents[0][0]
    assert seen_contents[1][0].startswith("Character reference sheet, neutral pose")
    assert path.endswith(".png")


@pytest.mark.unit
def test_generate_thumbnail_builds_expected_flow(style_ref):
    seen_contents: list[list[object]] = []

    async def image_provider(contents: list[object]) -> Image.Image:
        seen_contents.append(contents)
        if len(seen_contents) == 1:
            raise GeminiImageProviderError("retry")
        return _dummy_image()

    path = asyncio.run(
        generate_thumbnail(
            "This changed everything",
            "A shocked person under dramatic lighting",
            "A confident presenter",
            art_style="cinematic",
            image_provider=image_provider,
        )
    )

    assert len(seen_contents) == 2
    assert "Create a visually striking social media video thumbnail." in seen_contents[0][0]
    assert seen_contents[1][0].startswith("Scroll-stopping video thumbnail:")
    assert path.endswith(".jpg")


@pytest.mark.unit
def test_generate_image_validates_prompt():
    with pytest.raises(ValueError, match="prompt"):
        asyncio.run(generate_image("   ", image_provider=lambda _contents: _dummy_image()))
