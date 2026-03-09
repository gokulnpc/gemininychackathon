"""Pydantic models for the Twick-compatible editable timeline JSON.

The schema mirrors the twick-project.json format used by the Twick SDK editor,
allowing the frontend to load a pipeline-generated video as a re-editable project.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ElementFrame(BaseModel):
    """Spatial positioning of a media element on the canvas."""

    size: list[int]       # [width, height] in pixels
    x: float = 0.0        # canvas x offset (pixels from center)
    y: float = 0.0        # canvas y offset (pixels from center)
    rotation: float = 0.0


class TimelineElement(BaseModel):
    """A single media element placed on a track."""

    id: str
    trackId: str
    type: str             # "video" | "image" | "audio" | "text" | "caption" | "effect"
    s: float              # start time (seconds)
    e: float              # end time (seconds)
    props: dict = Field(default_factory=dict)
    zIndex: int | None = None
    frame: ElementFrame | None = None
    frameEffects: list = Field(default_factory=list)
    objectFit: str | None = None   # "cover" | "contain" — for video/image
    mediaDuration: float | None = None
    name: str | None = None
    t: str | None = None           # text content for caption elements


class TimelineTrack(BaseModel):
    """A single track containing one or more elements."""

    id: str
    name: str
    type: Literal["element", "caption"]
    props: dict = Field(default_factory=dict)   # caption track: capStyle, font, colors, etc.
    elements: list[TimelineElement] = Field(default_factory=list)


class TimelineProject(BaseModel):
    """Root object representing the full editable project timeline."""

    tracks: list[TimelineTrack]
    version: int = 1
    metadata: dict = Field(default_factory=dict)  # project_id, pipeline_version, created_at
