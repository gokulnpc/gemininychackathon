"use client";

import { useState } from "react";
import type { EditorLeftPanelKey } from "@/components/editor/types";

interface EditorShellState {
  activeLeftPanel: EditorLeftPanelKey;
  setActiveLeftPanel: (panel: EditorLeftPanelKey) => void;
}

export function useEditorShellState(initialPanel: EditorLeftPanelKey = "media"): EditorShellState {
  const [activeLeftPanel, setActiveLeftPanel] = useState<EditorLeftPanelKey>(initialPanel);

  return {
    activeLeftPanel,
    setActiveLeftPanel,
  };
}
