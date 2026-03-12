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

export interface AgentMessage {
  id: string;
  role: "user" | "agent";
  text: string;
  actions?: string[];
  isThinking?: boolean;
  isError?: boolean;
}

export interface Asset {
  id: string;
  filename: string;
  content_type: string;
  uploaded_at: string;
  gcs_key: string;
  size_bytes: number;
}
