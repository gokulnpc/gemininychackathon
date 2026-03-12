"use client";

import { forwardRef, useImperativeHandle } from "react";
import { useTimelineContext } from "@twick/timeline";
import { useLivePlayerContext } from "@twick/live-player";

import type { EditorBridgeHandle } from "@/components/editor/types";

export const EditorBridge = forwardRef<EditorBridgeHandle>((_, ref) => {
  const { editor, selectedItem, selectedIds, timelineAction } = useTimelineContext();
  const livePlayer = useLivePlayerContext();

  useImperativeHandle(ref, () => ({
    getProject: () => editor.getProject(),
    loadProject: (json) => editor.loadProject(json),
    getEditorContext: () => {
      const selectionIds = Array.from(selectedIds ?? []);
      const selectedItemId =
        selectedItem && typeof (selectedItem as { getId?: () => string }).getId === "function"
          ? (selectedItem as { getId: () => string }).getId()
          : null;
      const selectedItemType =
        selectedItem && typeof (selectedItem as { getType?: () => string }).getType === "function"
          ? (selectedItem as { getType: () => string }).getType()
          : null;

      const elementIds = selectionIds.filter((id) => id.startsWith("e-"));
      const trackIds = selectionIds.filter((id) => id.startsWith("t-"));

      if (selectedItemId?.startsWith("e-") && !elementIds.includes(selectedItemId)) {
        elementIds.push(selectedItemId);
      }
      if (selectedItemId?.startsWith("t-") && !trackIds.includes(selectedItemId)) {
        trackIds.push(selectedItemId);
      }

      return {
        mode: typeof timelineAction?.type === "string" && timelineAction.type ? timelineAction.type : null,
        active_panel: "timeline",
        playhead_seconds: typeof livePlayer?.currentTime === "number" ? livePlayer.currentTime : null,
        viewport_scale: null,
        selected_element_ids: elementIds,
        selected_track_ids: trackIds,
        selected_element_types: selectedItemType ? [selectedItemType] : [],
      };
    },
  }), [editor, livePlayer, selectedIds, selectedItem, timelineAction]);

  return null;
});

EditorBridge.displayName = "EditorBridge";
