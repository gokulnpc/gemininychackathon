from __future__ import annotations

from enum import Enum
from typing import Optional
from uuid import UUID, uuid4

from datetime import datetime

from pydantic import BaseModel, Field


# --- Enums ---


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
    comic = "comic"
    creepy_comic = "creepy_comic"
    painting = "painting"
    ghibli = "ghibli"
    polaroid = "polaroid"
    disney = "disney"
    realism = "realism"


class MusicPreset(str, Enum):
    happy_rhythm = "happy_rhythm"
    quiet_before_storm = "quiet_before_storm"
    peaceful_vibes = "peaceful_vibes"
    brilliant_symphony = "brilliant_symphony"
    breathing_shadows = "breathing_shadows"
    none = "none"


class VideoDurationRange(str, Enum):
    short = "15-30"
    medium = "30-40"
    long = "60+"


# --- Transcription ---


class TranscribeRequest(BaseModel):
    audio_base64: str = Field(..., description="Base64-encoded audio data")
    audio_format: str = Field(default="wav", description="Audio format: wav, mp3, m4a, webm, ogg, flac")
    language: str = Field(default="en-US")


class TranscribeResponse(BaseModel):
    transcript: str
    detected_tone: Optional[str] = None
    language: str
    confidence: float


# --- Script Generation ---


class ScriptGenerationRequest(BaseModel):
    transcript: str = Field(..., description="Transcribed text or user-provided text")
    target_platforms: list[Platform] = Field(default=[Platform.instagram_reels])
    style: VideoStyle = Field(default=VideoStyle.modern_energetic)
    video_duration: int = Field(default=30, description="Target duration in seconds: 15, 30, or 60")
    brand_voice: Optional[str] = Field(default=None, description="Brand voice guidelines")
    cta_preference: Optional[str] = Field(default=None, description="Preferred call-to-action")


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


# --- Voiceover ---


class VoiceoverRequest(BaseModel):
    text: str
    voice_id: Optional[str] = None
    language: str = "en-US"


class VoiceoverResponse(BaseModel):
    audio_base64: str
    duration_seconds: float
    word_timestamps: Optional[list[WordTimestamp]] = None


# --- Captions ---


class CaptionStyleEnum(str, Enum):
    bold_stroke = "bold_stroke"      # 1-2 words, ALL CAPS, white bold black outline
    red_highlight = "red_highlight"  # 1-2 words, white on red background
    sleek = "sleek"                  # 6-7 words, thin outline, bottom
    karaoke = "karaoke"             # word-by-word gold highlight
    majestic = "majestic"           # 4-5 words, large centered, gold shadow
    beast = "beast"                  # 1 word at a time, maximum impact
    elegant = "elegant"              # 5-6 words, italic, thin outline
    clarity = "clarity"              # 6-7 words, lowercase, soft gray, minimal


class WordTimestamp(BaseModel):
    word: str
    start: float
    end: float


# --- Full Pipeline ---


class PipelineRequest(BaseModel):
    audio_base64: Optional[str] = Field(default=None, description="Base64-encoded audio (provide this OR transcript)")
    audio_format: str = Field(default="wav")
    transcript: Optional[str] = Field(default=None, description="Text input (provide this OR audio)")
    target_platforms: list[Platform] = Field(default=[Platform.instagram_reels])
    style: VideoStyle = Field(default=VideoStyle.modern_energetic)
    video_duration: int = Field(default=30)
    caption_style: CaptionStyleEnum = Field(default=CaptionStyleEnum.bold_stroke)
    brand_voice: Optional[str] = None
    cta_preference: Optional[str] = None
    series_id: Optional[str] = Field(default=None, description="Series config ID — loads wizard settings from S3")


class PipelineStageStatus(BaseModel):
    stage: str
    status: str  # "pending", "running", "completed", "failed"
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
    error: Optional[str] = None


# --- Publishing (Nova Act) ---


class PublishPlatform(str, Enum):
    instagram = "instagram"
    youtube = "youtube"
    tiktok = "tiktok"


class PublishRequest(BaseModel):
    platforms: list[PublishPlatform] = Field(
        ..., min_length=1, description="Platforms to publish to"
    )
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
    status: str  # "published", "scheduled", "failed"
    post_url: Optional[str] = None
    screenshot_url: Optional[str] = None
    error: Optional[str] = None


class PublishResponse(BaseModel):
    project_id: UUID
    status: str  # "completed", "partial", "failed"
    posts: list[PlatformPostResult] = []
    completed_at: Optional[datetime] = None


# --- Series / Wizard Config ---


class VoiceOption(BaseModel):
    id: str
    name: str
    gender: str
    description: str


class SeriesConfig(BaseModel):
    series_name: str
    video_format: VideoFormat = VideoFormat.storytelling
    niche: Optional[str] = None
    language: str = "en-US"
    voice_id: str = "21m00Tcm4TlvDq8ikWAM"  # ElevenLabs Rachel (default)
    background_music: MusicPreset = MusicPreset.none
    music_volume: float = Field(default=0.15, ge=0.0, le=1.0)
    art_style: ArtStyle = ArtStyle.realism
    caption_style: CaptionStyleEnum = CaptionStyleEnum.bold_stroke
    video_duration: VideoDurationRange = VideoDurationRange.medium


class SeriesCreateResponse(BaseModel):
    series_id: str
    config: SeriesConfig
    config_url: Optional[str] = None


class VoicePreviewResponse(BaseModel):
    voice_id: str
    audio_base64: str
    duration_seconds: float


class VoiceCloneResponse(BaseModel):
    voice_id: str
    name: str
    message: str = "Voice clone created. Pass this voice_id when creating a series."


# --- Dashboard / Project List ---


class ProjectMetadata(BaseModel):
    project_id: str
    created_at: str                        # ISO-8601
    status: str                            # "completed" | "failed"
    series_id: Optional[str] = None
    series_name: Optional[str] = None
    hook: Optional[str] = None
    scenes_count: int = 0
    voiceover_duration: Optional[float] = None
    platforms: list[str] = []
    video_urls: dict[str, str] = {}
    error: Optional[str] = None


class ProjectListResponse(BaseModel):
    projects: list[ProjectMetadata]
    total: int


# --- Smart Process (Option B — voice idea → Nemotron auto-config → pipeline) ---


class SmartProcessRequest(BaseModel):
    audio_base64: Optional[str] = Field(default=None, description="Base64-encoded audio of the creator's idea")
    audio_format: str = Field(default="wav")
    transcript: Optional[str] = Field(default=None, description="Raw idea text (if audio not provided)")
    target_platforms: list[Platform] = Field(
        default=[Platform.instagram_reels],
        description="Hint for Nemotron — it may adjust based on content analysis",
    )
    niche: Optional[str] = Field(
        default=None,
        description="Content niche for Reddit research (horror, finance, fitness, etc.). "
                    "Auto-detected from transcript if not provided.",
    )


class NemotronSeriesConfig(BaseModel):
    """The auto-generated series config returned by Nemotron's multi-agent reasoning."""
    series_name: str
    niche: str
    art_style: str
    caption_style: str
    background_music: str
    music_volume: float
    voice_id: str
    voice_name: str
    video_duration: str
    video_format: str
    target_platforms: list[str]
    reasoning: str
    configured_by: str = "nemotron"
    series_id: Optional[str] = None   # set after auto-creating in S3


class SmartProcessResponse(BaseModel):
    project_id: UUID = Field(default_factory=uuid4)
    status: str = "completed"
    stages: list[PipelineStageStatus] = []
    video_urls: dict[str, str] = Field(default_factory=dict)
    script: Optional[ScriptGenerationResponse] = None
    nemotron_config: Optional[NemotronSeriesConfig] = None
    error: Optional[str] = None


# --- Preset Process (Option C — pick a preset → Nemotron auto-config → pipeline) ---


class PresetKey(str, Enum):
    scary_stories = "scary_stories"
    history = "history"
    true_crime = "true_crime"
    stoic_motivation = "stoic_motivation"
    marketing_business = "marketing_business"
    tech_innovation = "tech_innovation"


class PresetProcessRequest(BaseModel):
    preset: PresetKey = Field(..., description="Built-in content preset to generate a video for")
    target_platforms: list[Platform] = Field(
        default=[Platform.instagram_reels],
        description="Hint for Nemotron — it may adjust based on content analysis",
    )
    topic_hint: Optional[str] = Field(
        default=None,
        description="Optional specific angle or topic within the preset (e.g. 'Fall of the Roman Empire')",
    )
    # Phase-2 override: supply series_id + transcript returned by the /configure endpoint
    # to skip re-running Nemotron and jump straight to the pipeline.
    series_id: Optional[str] = Field(
        default=None,
        description="Pre-built series ID from /presets/{preset}/configure — skips Nemotron",
    )
    transcript: Optional[str] = Field(
        default=None,
        description="Pre-built topic transcript from /presets/{preset}/configure",
    )


class PresetConfigureResponse(BaseModel):
    """Returned by POST /api/v1/presets/{preset}/configure.

    Contains the Nemotron-auto-generated series config so the frontend can
    pre-fill wizard steps (voice, music, art style, caption style) before
    the user confirms and the pipeline is launched.
    """
    series_id: str
    series_name: str
    transcript: str
    # Wizard fields
    voice_id: str
    voice_name: str
    art_style: str
    caption_style: str
    background_music: str
    music_volume: float
    video_duration: str
    video_format: str
    target_platforms: list[str]
    # Nemotron reasoning (nice to show in UI)
    nemotron_reasoning: str
    configured_by: str
    # Stage progress (so UI can show what ran)
    stages: list[PipelineStageStatus] = []


# --- Script-only + Video-from-script (Speech/Text two-phase flow) ---


class GenerateScriptRequest(BaseModel):
    """Phase 1 of the speech/text flow: transcribe + generate script only.

    The returned ScriptGenerationResponse is shown to the user for review.
    They can regenerate as many times as they like before confirming.
    """
    audio_base64: Optional[str] = Field(default=None, description="Base64 audio (speech tab)")
    audio_format: str = Field(default="webm", description="Audio format: webm, wav, mp3, m4a")
    transcript: Optional[str] = Field(default=None, description="Raw text (text tab)")
    target_platforms: list[Platform] = Field(default=[Platform.instagram_reels])
    style: VideoStyle = Field(default=VideoStyle.modern_energetic)
    video_duration: int = Field(default=30, description="Target seconds: 15, 30, or 60")
    brand_voice: Optional[str] = None
    cta_preference: Optional[str] = None
    series_id: Optional[str] = Field(default=None, description="Optional series config to pull niche/format hints")


class GenerateVideoRequest(BaseModel):
    """Phase 2: generate video from a user-confirmed script.

    Pass the ScriptGenerationResponse from Phase 1 back here.
    Runs stages 3-7: voiceover → images → captions → compose → upload.
    """
    script: ScriptGenerationResponse = Field(..., description="The confirmed script from /generate-script")
    target_platforms: list[Platform] = Field(default=[Platform.instagram_reels])
    caption_style: CaptionStyleEnum = Field(default=CaptionStyleEnum.bold_stroke)
    video_duration: int = Field(default=30)
    series_id: Optional[str] = Field(default=None, description="Series config (voice, music, art style)")
    # Per-field overrides when no series_id
    voice_id: Optional[str] = Field(default=None, description="ElevenLabs voice ID override")
    art_style_override: Optional[str] = Field(default=None, description="ArtStyle enum value override")
    music_preset_override: Optional[str] = Field(default=None, description="MusicPreset enum value override")


# --- Series List ---


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
