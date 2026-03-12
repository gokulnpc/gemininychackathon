"use client";

import { Captions, Film, Image as ImageIcon, Music4, Sparkles, Type } from "lucide-react";

import type { EditorLeftPanelKey } from "@/components/editor/types";

export const PANEL_CONFIG: Array<{
  key: EditorLeftPanelKey;
  label: string;
  icon: typeof ImageIcon;
  description: string;
}> = [
  { key: "media", label: "Image", icon: ImageIcon, description: "Insert uploaded images fast" },
  { key: "video", label: "Video", icon: Film, description: "Insert uploaded videos fast" },
  { key: "audio", label: "Audio", icon: Music4, description: "Preview and swap soundtrack choices" },
  { key: "text", label: "Text", icon: Type, description: "Add hook titles and overlays" },
  { key: "caption", label: "Caption", icon: Captions, description: "Retheme subtitles and captions" },
  { key: "effects", label: "Effects", icon: Sparkles, description: "Apply light directional edits" },
];
