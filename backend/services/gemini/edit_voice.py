"""Compatibility facade for Scout's voice/text edit helpers."""

from __future__ import annotations

from .editing.commands import (
    _build_proposal_from_commands,
    _build_proposal_from_pending_edits,
    _looks_like_media_url,
    _normalize_editor_media_url,
    _queue_pending_edits,
    _resolve_gs_media_url,
)
from .editing.constants import _LIVE_MODEL, _TEXT_MODEL
from .editing.context import _summarize_editor_context
from .editing.env import settings_env
from .editing.preview import _generate_quick_preview, _invoke_quick_preview, _quick_preview_prompt
from .editing.projector import _apply_live_edits, _patch_project_json, _project_commands
from .editing.voice_runtime import _build_voice_config, _dispatch_voice_tool, run_edit_voice_agent
from .editing.text_runtime import run_edit_text_agent

__all__ = [
    "_LIVE_MODEL",
    "_TEXT_MODEL",
    "_apply_live_edits",
    "_build_proposal_from_commands",
    "_build_proposal_from_pending_edits",
    "_build_voice_config",
    "_dispatch_voice_tool",
    "_generate_quick_preview",
    "_invoke_quick_preview",
    "_looks_like_media_url",
    "_normalize_editor_media_url",
    "_patch_project_json",
    "_project_commands",
    "_queue_pending_edits",
    "_quick_preview_prompt",
    "_resolve_gs_media_url",
    "_summarize_editor_context",
    "run_edit_text_agent",
    "run_edit_voice_agent",
    "settings_env",
]
