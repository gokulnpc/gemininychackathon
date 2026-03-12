"use client";

import type { ProjectJSON } from "@twick/timeline";

export type EditorLeftPanelKey = "media" | "video" | "text" | "caption" | "audio" | "effects";

export type TextInsertVariant = "freeform" | "hook" | "lower-third" | "callout";

export interface TextInsertConfig {
  text: string;
  variant?: TextInsertVariant;
}

export interface EditorExport {
  export_id?: string | null;
  status?: "idle" | "queued" | "in_progress" | "completed" | "failed" | string;
  current_stage?: string | null;
  progress_pct?: number | null;
  queued_at?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
  download_url?: string | null;
  thumbnail_url?: string | null;
  error?: string | null;
}

export interface Project {
  project_id: string;
  status: string;
  hook?: string;
  scenes_count?: number;
  video_duration?: number;
  platforms?: string[];
  video_urls?: Record<string, string>;
  thumbnail_url?: string;
  caption_style?: string;
  background_music?: string;
  voiceover_full_script?: string;
  voiceover_duration?: number;
  error?: string;
  project_json?: ProjectJSON | null;
  editor_export?: EditorExport | null;
}

export interface EditorContextSnapshot {
  mode: string | null;
  active_panel: string | null;
  playhead_seconds: number | null;
  viewport_scale: number | null;
  selected_element_ids: string[];
  selected_track_ids: string[];
  selected_element_types: string[];
}

export interface EditorBridgeHandle {
  getProject: () => ProjectJSON;
  loadProject: (json: ProjectJSON) => void;
  getEditorContext: () => EditorContextSnapshot;
}

export type TimelineTrackJson = NonNullable<ProjectJSON["tracks"]>[number];
export type TimelineElementJson = TimelineTrackJson["elements"][number];

export interface MediaTransformRecord {
  canonicalSrc: string;
  editorSrc: string;
  canonicalElementObjectFit: string | null;
  canonicalPropsObjectFit: string | null;
  editorElementObjectFit: string | null;
  editorPropsObjectFit: string | null;
}

export interface SkippedEditorElement {
  element: TimelineElementJson;
  index: number;
}

export interface PlaybackWarning {
  elementId: string;
  trackId: string;
  type: string;
  src: string | null;
  editorSrc: string | null;
  reason: string;
}

export interface MediaSourceReference {
  elementId: string;
  trackId: string;
  type: string;
  canonicalSrc: string;
}

export interface EditorProjectSession {
  editorProjectJson: ProjectJSON;
  canonicalMediaByElementId: Record<string, MediaTransformRecord>;
  skippedElementsByTrackId: Record<string, SkippedEditorElement[]>;
  playbackWarnings: PlaybackWarning[];
  mediaIndexByEditorSrc: Record<string, MediaSourceReference[]>;
}

export type EditCommandKind =
  | "set_caption_style"
  | "set_background_music"
  | "add_text_overlay"
  | "update_selected_text"
  | "move_selected_element"
  | "replace_selected_media"
  | "insert_media_asset"
  | "trim_selected_element"
  | "delete_selected_element"
  | "add_hook_title";

export interface EditCommand {
  kind: EditCommandKind;
  args: Record<string, unknown>;
  element_id?: string | null;
  track_id?: string | null;
}

export interface EditProposal {
  proposal_id: string;
  summary: string;
  commands: EditCommand[];
  confirmation_required: boolean;
  created_at?: string | null;
  /** Client-side state — not from server */
  state: "pending" | "confirmed" | "rejected";
}

export interface AgentMessage {
  id: string;
  role: "user" | "agent";
  text: string;
  actions?: string[];
  isThinking?: boolean;
  isError?: boolean;
  proposal?: EditProposal;
}

export interface Asset {
  id: string;
  filename: string;
  content_type: string;
  uploaded_at: string;
  gcs_key: string;
  size_bytes: number;
}
