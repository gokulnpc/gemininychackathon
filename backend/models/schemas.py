from __future__ import annotations

from enum import Enum
from typing import Optional
from uuid import UUID, uuid4

from datetime import datetime

from pydantic import BaseModel, Field


# ── Enums ─────────────────────────────────────────────────────────────────────


class Platform(str, Enum):
    instagram_reels = "instagram_reels"
    youtube_shorts = "youtube_shorts"
    tiktok = "tiktok"


class VideoStyle(str, Enum):
    modern_energetic = "modern_energetic"
    corporate = "corporate"
    fun = "fun"
    dramatic = "dramatic"
    minimal = "minimal"


class TransitionType(str, Enum):
    smooth_fade = "smooth_fade"
    quick_cut = "quick_cut"
    slide_left = "slide_left"
    zoom_in = "zoom_in"


class VideoFormat(str, Enum):
    storytelling = "storytelling"
    what_if = "what_if"
    five_things = "five_things"
    random_fact = "random_fact"
    custom = "custom"


class ArtStyle(str, Enum):
    # Original styles
    comic = "comic"
    creepy_comic = "creepy_comic"
    painting = "painting"
    ghibli = "ghibli"
    polaroid = "polaroid"
    disney = "disney"
    realism = "realism"
    # Gallery styles (from style picker UI)
    monochrome = "monochrome"
    colour_block = "colour_block"
    runway = "runway"
    risograph = "risograph"
    technicolour = "technicolour"
    gothic_clay = "gothic_clay"
    dynamite = "dynamite"
    salon = "salon"
    sketch = "sketch"
    cinematic = "cinematic"
    steampunk = "steampunk"
    sunrise = "sunrise"


class MusicPreset(str, Enum):
    happy_rhythm = "happy_rhythm"
    quiet_before_storm = "quiet_before_storm"
    peaceful_vibes = "peaceful_vibes"
    brilliant_symphony = "brilliant_symphony"
    breathing_shadows = "breathing_shadows"
    lyria = "lyria"   # AI-generated music via Vertex AI Lyria
    none = "none"


class VideoDurationRange(str, Enum):
    short = "15-30"
    medium = "30-40"
    long = "60+"


class CaptionStyleEnum(str, Enum):
    bold_stroke = "bold_stroke"      # 1-2 words, ALL CAPS, white bold black outline
    red_highlight = "red_highlight"  # 1-2 words, white on red background
    sleek = "sleek"                  # 6-7 words, thin outline, bottom
    karaoke = "karaoke"             # word-by-word gold highlight
    majestic = "majestic"           # 4-5 words, large centered, gold shadow
    beast = "beast"                  # 1 word at a time, maximum impact
    elegant = "elegant"              # 5-6 words, italic, thin outline
    clarity = "clarity"              # 6-7 words, lowercase, soft gray, minimal


# ── User character role (optional — preset flow image personalisation) ────────


class UserCharacterRole(str, Enum):
    main_character = "main_character"   # User IS the protagonist — appears in every scene
    side_character = "side_character"   # User appears as a supporting character
    audience       = "audience"         # User visible as bystander / crowd member


# ── Script source (drives the generate-script flow) ───────────────────────────


class ScriptSource(str, Enum):
    voice  = "voice"   # Flow 1: audio → Gemini transcription → agent
    text   = "text"    # Flow 2: plain text → agent
    preset = "preset"  # Flow 3: preset niche + topic → reddit context → agent


# ── Preset keys ───────────────────────────────────────────────────────────────


class PresetKey(str, Enum):
    scary_stories      = "scary_stories"
    history            = "history"
    true_crime         = "true_crime"
    stoic_motivation   = "stoic_motivation"
    marketing_business = "marketing_business"
    tech_innovation    = "tech_innovation"


# ── Script generation ─────────────────────────────────────────────────────────


class GenerateScriptRequest(BaseModel):
    """Unified generate-script request for all three flows."""

    source: ScriptSource = Field(..., description="Input mode: voice | text | preset")

    # Flow 1 — voice
    audio_base64:  Optional[str] = Field(default=None, description="Base64 audio (required when source=voice)")
    audio_format:  str           = Field(default="webm", description="Audio format: webm, wav, mp3, m4a")

    # Flow 2 — text
    transcript: Optional[str] = Field(default=None, description="Raw text (required when source=text)")

    # Flow 3 — preset
    preset:     Optional[PresetKey] = Field(default=None, description="Preset key (required when source=preset)")
    topic_hint: Optional[str]       = Field(default=None, description="Specific angle within the preset")

    # Common video config (user fills these manually in all 3 flows)
    target_platforms: list[Platform]   = Field(default=[Platform.instagram_reels])
    style:            VideoStyle       = Field(default=VideoStyle.modern_energetic)
    video_duration:   int              = Field(default=30, description="Target seconds: 15, 30, or 60")
    caption_style:    CaptionStyleEnum = Field(default=CaptionStyleEnum.bold_stroke)
    art_style:        ArtStyle         = Field(default=ArtStyle.realism)
    background_music: MusicPreset      = Field(default=MusicPreset.none)
    voice_id:         str              = Field(default="Aoede")
    video_format:     VideoFormat      = Field(default=VideoFormat.storytelling)
    brand_voice:      Optional[str]    = Field(default=None)
    cta_preference:   Optional[str]    = Field(default=None)

    # Optional — user-selected plot direction from generate-plot-options
    plot_summary: Optional[str] = Field(default=None, description="Brief story direction chosen by the user")

    # Optional — character role when user uploads a reference photo
    user_character_role: Optional[str] = Field(
        default=None,
        description="Role of the user in the video (main_character, side_character, audience). "
                    "Injected as a character context hint for the script agent.",
    )

    # Optional — load an existing saved series config (overrides the manual fields above)
    series_id: Optional[str] = Field(default=None, description="Saved series config ID from /api/v1/series")


class QueueScriptRequest(BaseModel):
    """Request body for POST /api/v1/projects/{id}/queue-script.

    All config is saved to Firestore; the worker loads it by project_id.
    Raw audio (audio_base64) is offloaded to GCS before the task is enqueued.
    """
    # Source
    source: ScriptSource
    audio_base64:  Optional[str]      = Field(default=None, description="Base64 audio (voice flow only)")
    audio_format:  str                = Field(default="webm")
    transcript:    Optional[str]      = Field(default=None)
    preset:        Optional[PresetKey] = Field(default=None)
    topic_hint:    Optional[str]      = Field(default=None)

    # Plot + character context
    plot_summary:        Optional[str] = Field(default=None)
    user_character_role: Optional[str] = Field(default=None)

    # Video config (stored in Firestore, used when video gen is approved)
    target_platforms:      list[Platform]    = Field(default=[Platform.instagram_reels])
    voice_id:              str               = Field(default="Aoede")
    art_style_override:    Optional[str]     = Field(default=None)
    music_preset_override: Optional[str]     = Field(default=None)
    caption_style:         str               = Field(default="bold_stroke")
    video_duration:        int               = Field(default=30)

    # Optional personalization
    user_reference_image_b64: Optional[str] = Field(default=None)
    series_name:              Optional[str] = Field(default=None)


class ScriptEditRequest(BaseModel):
    """Request body for PUT /api/v1/projects/{id}/script — save user edits to the generated script."""
    script: dict  # Full ScriptGenerationResponse-shaped dict


class TextOverlay(BaseModel):
    text: str
    position: str = "bottom_center"
    animation: str = "fade_in"
    emphasis_words: list[str] = []


class Scene(BaseModel):
    scene_id: int
    duration_seconds: int = Field(ge=1, le=30)
    visual_prompt: Optional[str] = None
    voiceover_text: str = ""
    text_overlay: Optional[TextOverlay] = None
    emotion: str = "neutral"
    transition_to_next: Optional[str] = None


class Hook(BaseModel):
    text: str
    duration: int = 3


class CTA(BaseModel):
    text: str
    type: str = "verbal_and_visual"


class SocialCopy(BaseModel):
    caption: str = ""
    hashtags: list[str] = []
    title: Optional[str] = None
    description: Optional[str] = None
    tags: list[str] = []


class ScriptGenerationResponse(BaseModel):
    project_id: UUID = Field(default_factory=uuid4)
    metadata: dict
    hook: Hook
    scenes: list[Scene]
    cta: CTA
    social_copy: dict[str, SocialCopy] = {}
    voiceover_full_script: str


# ── Video generation ──────────────────────────────────────────────────────────


class GenerateVideoRequest(BaseModel):
    """Phase 2: generate video from a user-confirmed script.

    Pass the ScriptGenerationResponse from /generate-script back here.
    Runs: Veo 3 video clips → captions → FFmpeg compose → S3 upload.
    """
    script: ScriptGenerationResponse = Field(..., description="The confirmed script from /generate-script")
    target_platforms: list[Platform] = Field(default=[Platform.instagram_reels])
    caption_style: CaptionStyleEnum  = Field(default=CaptionStyleEnum.bold_stroke)
    video_duration: int              = Field(default=30)

    # Series config (voice, music, art style) — load from saved series or supply directly
    series_id:             Optional[str] = Field(default=None)
    voice_id:              Optional[str] = Field(default=None)
    art_style_override:    Optional[str] = Field(default=None, description="ArtStyle enum value")
    music_preset_override: Optional[str] = Field(default=None, description="MusicPreset enum value")

    # Optional user photo personalisation (preset flow)
    user_reference_image_b64: Optional[str] = Field(
        default=None,
        description="Base64-encoded JPEG/PNG of the user's photo. Used as a visual reference when generating scene images.",
    )
    user_character_role: Optional[UserCharacterRole] = Field(
        default=None,
        description="Role of the user in the video: main_character (protagonist in every scene), side_character (supporting), or audience (bystander/crowd).",
    )

    # Notification — email sent when generation completes
    user_email: Optional[str] = Field(
        default=None,
        description="Email address to notify when video generation completes.",
    )


# ── Pipeline plumbing ─────────────────────────────────────────────────────────


class PipelineStageStatus(BaseModel):
    stage: str
    status: str  # "pending" | "running" | "completed" | "failed"
    detail: Optional[str] = None


class PipelineResponse(BaseModel):
    project_id: UUID = Field(default_factory=uuid4)
    status: str = "completed"
    stages: list[PipelineStageStatus] = []
    video_urls: dict[str, str] = Field(
        default_factory=dict,
        description="Platform → S3 URL mapping for final videos",
    )
    script: Optional[ScriptGenerationResponse] = None
    thumbnail_url: Optional[str] = None
    visual_qa_report: Optional[list[dict]] = None
    error: Optional[str] = None


# ── Publishing ────────────────────────────────────────────────────────────────


class PublishPlatform(str, Enum):
    instagram = "instagram"
    youtube = "youtube"
    tiktok = "tiktok"


class PublishRequest(BaseModel):
    platforms: list[PublishPlatform] = Field(..., min_length=1)
    schedule: Optional[datetime] = Field(
        default=None,
        description="ISO datetime to schedule the post. None = publish immediately.",
    )
    social_copy: Optional[dict[str, SocialCopy]] = Field(
        default=None,
        description="Override social copy per platform. Uses script defaults if omitted.",
    )


class PlatformPostResult(BaseModel):
    platform: PublishPlatform
    status: str  # "published" | "scheduled" | "failed"
    post_url: Optional[str] = None
    screenshot_url: Optional[str] = None
    error: Optional[str] = None


class PublishResponse(BaseModel):
    project_id: UUID
    status: str  # "completed" | "partial" | "failed"
    posts: list[PlatformPostResult] = []
    completed_at: Optional[datetime] = None


# ── Series / wizard config ────────────────────────────────────────────────────


class ToneOption(BaseModel):
    id: str          # matches gemini_audio detected_tone values
    name: str
    description: str  # explains the script style this tone produces


class SeriesConfig(BaseModel):
    series_name: str
    video_format: VideoFormat = VideoFormat.storytelling
    niche: Optional[str] = None
    language: str = "en-US"
    voice_id: str = "Aoede"
    background_music: MusicPreset = MusicPreset.none
    music_volume: float = Field(default=0.15, ge=0.0, le=1.0)
    art_style: ArtStyle = ArtStyle.realism
    caption_style: CaptionStyleEnum = CaptionStyleEnum.bold_stroke
    video_duration: VideoDurationRange = VideoDurationRange.medium


class SeriesCreateResponse(BaseModel):
    series_id: str
    config: SeriesConfig
    config_url: Optional[str] = None


class SeriesListItem(BaseModel):
    series_id: str
    series_name: str
    video_format: str
    niche: Optional[str] = None
    art_style: str
    caption_style: str
    background_music: str
    voice_id: str
    video_duration: str


class SeriesListResponse(BaseModel):
    series: list[SeriesListItem]
    total: int


# ── Dashboard / project list ──────────────────────────────────────────────────


class ProjectMetadata(BaseModel):
    project_id: str
    created_at: str                        # ISO-8601
    status: str                            # "queued" | "in_progress" | "completed" | "failed"
    series_id: Optional[str] = None
    series_name: Optional[str] = None
    hook: Optional[str] = None
    scenes_count: int = 0
    voiceover_duration: Optional[float] = None
    platforms: list[str] = []
    video_urls: dict[str, str] = {}
    error: Optional[str] = None
    # Recompose fields (present on projects generated after recompose support was added)
    voiceover_full_script: Optional[str] = None
    caption_style: Optional[str] = None
    background_music: Optional[str] = None
    video_duration: Optional[int] = None
    thumbnail_url: Optional[str] = None
    # Async job tracking
    current_stage: Optional[str] = None
    progress_pct: Optional[int] = None
    queued_at: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    user_email: Optional[str] = None


class JobStatusResponse(BaseModel):
    """Lightweight job status response for polling during async generation."""
    project_id: str
    status: str                   # queued | in_progress | completed | failed
    current_stage: Optional[str] = None
    progress_pct: Optional[int] = None
    stages: list[PipelineStageStatus] = []
    queued_at: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    video_urls: dict[str, str] = {}
    thumbnail_url: Optional[str] = None
    error: Optional[str] = None


class ProjectListResponse(BaseModel):
    projects: list[ProjectMetadata]
    total: int


# ── Creative Director — Interleaved Multimodal Output ────────────────────────


class CreativeMode(str, Enum):
    storybook      = "storybook"       # alternating story text + inline illustrations
    marketing      = "marketing"       # headline + hero image + body copy + CTA visual
    educational    = "educational"     # narration sections + concept/diagram images
    social_content = "social_content"  # caption + post image + hashtag cloud


class InterleavedBlock(BaseModel):
    """One unit of interleaved output — either a text block or a generated image."""
    type: str                    # "text" | "image"
    content: str                 # text string OR base64-encoded image data
    mime_type: Optional[str] = None  # e.g. "image/png" — only present for image blocks


class CreativeDirectorRequest(BaseModel):
    brief: str = Field(
        ...,
        description="Creative brief — topic, target audience, tone, and goals",
    )
    mode: CreativeMode = Field(
        default=CreativeMode.social_content,
        description="Creative output mode: storybook | marketing | educational | social_content",
    )
    art_style: Optional[str] = Field(
        default=None,
        description=(
            "Art style applied consistently to all generated images. "
            "Accepts any ArtStyle enum value (e.g. 'cinematic', 'ghibli', 'realism')."
        ),
    )
    include_narration: bool = Field(
        default=False,
        description="Generate a Gemini TTS audio narration of all text blocks (returns base64 WAV)",
    )
    voice_id: str = Field(
        default="Aoede",
        description="Gemini TTS voice name for narration (e.g. Aoede, Charon, Fenrir, Kore, Puck)",
    )


class CreativePackageResponse(BaseModel):
    package_id: UUID = Field(default_factory=uuid4)
    mode: CreativeMode
    brief: str
    blocks: list[InterleavedBlock]
    total_images: int = 0
    total_text_blocks: int = 0
    narration_audio_b64: Optional[str] = Field(
        default=None,
        description="Base64-encoded WAV narration of all text blocks (only present when include_narration=true)",
    )


# ── Recompose — change caption/music without re-running TTS or image gen ──────


class RecomposeRequest(BaseModel):
    """Recompose a completed project with a new caption style and/or background music.

    Skips TTS, image generation, and FFmpeg animation — starts from the preserved
    with_audio.mp4 (scenes + voiceover, no captions, no music).
    Requires that generate-video was run at least once for this project.
    """
    caption_style: CaptionStyleEnum = Field(
        ...,
        description="New caption style to burn into the video",
    )
    background_music: MusicPreset = Field(
        default=MusicPreset.none,
        description="New background music preset. 'none' removes music entirely.",
    )
    target_platforms: list[Platform] = Field(
        default=[Platform.instagram_reels],
        description="Platforms to export. Defaults to instagram_reels.",
    )
    music_volume: float = Field(
        default=0.15,
        ge=0.0,
        le=1.0,
        description="Background music relative volume (0.0–1.0). Only used when background_music != none.",
    )


class RecomposeResponse(BaseModel):
    project_id: UUID
    status: str                              # "completed" | "failed"
    stages: list[PipelineStageStatus] = []
    video_urls: dict[str, str] = Field(default_factory=dict)
    caption_style: str = ""
    background_music: str = ""
    error: Optional[str] = None


# ── User Assets ───────────────────────────────────────────────────────────────


class AssetCategory(str, Enum):
    images = "images"
    music = "music"
    voice_memos = "voice_memos"


class AssetMetadata(BaseModel):
    id: str
    filename: str
    content_type: str
    uploaded_at: str   # ISO-8601
    gcs_key: str
    size_bytes: int


# ── Edit Agent (natural-language recompose) ────────────────────────────────────


class EditAgentRequest(BaseModel):
    """Natural-language instruction for the AI video edit agent."""
    instruction: str = Field(
        ...,
        description="Natural-language edit request, e.g. 'make the captions more aggressive and add dark music'",
    )
