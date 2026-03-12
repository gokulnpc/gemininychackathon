"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Bold, Italic, Plus } from "lucide-react";
import { VideoEditor as StudioVideoEditor } from "@twick/studio";
import {
  type ProjectJSON,
  type TextProps,
  TextElement,
  useTimelineContext,
} from "@twick/timeline";

import type { TextInsertConfig } from "@/components/editor/types";
import { cn } from "@/lib/utils";

const TEXT_PRESETS = [
  {
    label: "Hook Title",
    title: "DREAD MORNINGS NO MORE",
    subtitle: "Centered opener for the first beat",
    variant: "hook" as const,
  },
  {
    label: "Lower Third",
    title: "Your Story Starts Here",
    subtitle: "Small anchored text card",
    variant: "lower-third" as const,
  },
  {
    label: "Callout",
    title: "Watch this moment",
    subtitle: "Short emphasis overlay",
    variant: "callout" as const,
  },
] as const;

const DEFAULT_TEXT_FONT = "Poppins";
const DEFAULT_TEXT_COLOR = "#ffffff";
const DEFAULT_STROKE_COLOR = "#4d4d4d";
const DEFAULT_BACKGROUND_COLOR = "#000000";
const DEFAULT_BACKGROUND_OPACITY = 0.45;
const DEFAULT_SHADOW_PROPS = {
  shadowColor: "#000000",
  shadowOffset: [0, 4] as [number, number],
  shadowBlur: 12,
  shadowOpacity: 0.35,
};

const TEXT_FONT_OPTIONS = Array.from(
  new Set(
    Object.values(
      (
        StudioVideoEditor as unknown as {
          AVAILABLE_TEXT_FONTS?: Record<string, string>;
        }
      ).AVAILABLE_TEXT_FONTS ?? {
        POPPINS: DEFAULT_TEXT_FONT,
      },
    ),
  ),
);

interface SelectedTextOverlay {
  id: string;
  name: string;
  props: TextProps;
  trackId: string;
}

const getSelectedItemType = (selectedItem: unknown): string | null => {
  if (!selectedItem || typeof selectedItem !== "object") return null;
  if (
    "getType" in selectedItem &&
    typeof (selectedItem as { getType?: () => unknown }).getType === "function"
  ) {
    const type = (selectedItem as { getType: () => unknown }).getType();
    return typeof type === "string" ? type : null;
  }
  return null;
};

const isValidHexColor = (value: string): boolean =>
  /^#?[0-9a-f]{6}$/i.test(value.trim());

const normalizeHexColor = (value: string): string | null => {
  const trimmed = value.trim();
  if (!trimmed) return null;
  const nextValue = trimmed.startsWith("#") ? trimmed : `#${trimmed}`;
  return isValidHexColor(nextValue) ? nextValue.toLowerCase() : null;
};

const resolveEditorColor = (value: unknown, fallback: string): string =>
  typeof value === "string" && isValidHexColor(value)
    ? value.toLowerCase()
    : fallback;

const findTextElementById = (
  projectJson: ProjectJSON | null,
  elementId: string,
): SelectedTextOverlay | null => {
  const tracks = projectJson?.tracks ?? [];
  for (const track of tracks) {
    for (const element of track.elements ?? []) {
      if (element.id !== elementId || element.type !== "text") continue;
      const props =
        typeof element.props === "object" && element.props
          ? { ...(element.props as TextProps) }
          : { text: "" };
      return {
        id: element.id,
        name: typeof element.name === "string" ? element.name : "Text Overlay",
        props,
        trackId: track.id,
      };
    }
  }
  return null;
};

interface TextColorFieldProps {
  label: string;
  color: string;
  draft: string;
  disabled?: boolean;
  onColorChange: (nextColor: string) => void;
  onDraftChange: (nextValue: string) => void;
  onDraftBlur: () => void;
}

function TextColorField({
  label,
  color,
  draft,
  disabled = false,
  onColorChange,
  onDraftChange,
  onDraftBlur,
}: TextColorFieldProps) {
  return (
    <div className="space-y-2">
      <div className="text-xs font-medium text-editor-text-muted">{label}</div>
      <div className="flex items-center gap-2">
        <input
          type="color"
          value={color}
          disabled={disabled}
          onChange={(event) => onColorChange(event.target.value)}
          className="h-11 w-14 rounded-xl border border-editor-border bg-editor-control p-1 disabled:cursor-not-allowed disabled:opacity-40"
        />
        <input
          type="text"
          value={draft}
          disabled={disabled}
          onChange={(event) => onDraftChange(event.target.value)}
          onBlur={onDraftBlur}
          className="w-full rounded-xl border border-editor-border bg-editor-control px-3 py-2.5 text-sm text-foreground placeholder:text-muted-foreground focus:border-primary/50 focus:outline-none focus:ring-1 focus:ring-primary/30 disabled:cursor-not-allowed disabled:opacity-40"
          placeholder="#ffffff"
        />
      </div>
    </div>
  );
}

interface TextPanelProps {
  onInsertText: (
    config: TextInsertConfig,
  ) => void | Promise<TextElement | null> | TextElement | null;
}

export function TextPanel({ onInsertText }: TextPanelProps) {
  const {
    present,
    editor,
    selectedItem,
    selectedIds,
    setSelectedItem,
    setSelection,
  } = useTimelineContext();
  const [draftText, setDraftText] = useState("");
  const [textColorDraft, setTextColorDraft] = useState(DEFAULT_TEXT_COLOR);
  const [strokeColorDraft, setStrokeColorDraft] =
    useState(DEFAULT_STROKE_COLOR);
  const [backgroundColorDraft, setBackgroundColorDraft] = useState(
    DEFAULT_BACKGROUND_COLOR,
  );

  const selectedType = getSelectedItemType(selectedItem);
  const selectedTextElement = useMemo(() => {
    if (selectedIds.size !== 1) return null;
    const [selectedId] = Array.from(selectedIds);
    return findTextElementById(present, selectedId);
  }, [present, selectedIds]);

  const selectedProps = selectedTextElement?.props ?? { text: "" };
  const selectedFontFamily =
    typeof selectedProps.fontFamily === "string" &&
    selectedProps.fontFamily.trim()
      ? selectedProps.fontFamily
      : DEFAULT_TEXT_FONT;
  const fontOptions = useMemo(() => {
    if (!selectedFontFamily || TEXT_FONT_OPTIONS.includes(selectedFontFamily))
      return TEXT_FONT_OPTIONS;
    return [selectedFontFamily, ...TEXT_FONT_OPTIONS];
  }, [selectedFontFamily]);
  const fontSize =
    typeof selectedProps.fontSize === "number" ? selectedProps.fontSize : 48;
  const fillColor = resolveEditorColor(selectedProps.fill, DEFAULT_TEXT_COLOR);
  const strokeColor = resolveEditorColor(
    selectedProps.stroke,
    DEFAULT_STROKE_COLOR,
  );
  const backgroundColor = resolveEditorColor(
    selectedProps.backgroundColor,
    DEFAULT_BACKGROUND_COLOR,
  );
  const strokeWidth =
    typeof selectedProps.lineWidth === "number"
      ? selectedProps.lineWidth
      : typeof selectedProps.strokeWidth === "number"
        ? selectedProps.strokeWidth
        : 0;
  const isBold =
    typeof selectedProps.fontWeight === "number"
      ? selectedProps.fontWeight >= 700
      : false;
  const isItalic = selectedProps.fontStyle === "italic";
  const hasShadow =
    typeof selectedProps.shadowColor === "string" ||
    typeof selectedProps.shadowBlur === "number" ||
    typeof selectedProps.shadowOpacity === "number" ||
    Array.isArray(selectedProps.shadowOffset);
  const hasBackground = typeof selectedProps.backgroundColor === "string";

  useEffect(() => {
    setTextColorDraft(fillColor);
    setStrokeColorDraft(strokeColor);
    setBackgroundColorDraft(backgroundColor);
  }, [backgroundColor, fillColor, selectedTextElement?.id, strokeColor]);

  const updateSelectedTextProps = useCallback(
    (patch: Partial<TextProps>, keysToRemove: Array<keyof TextProps> = []) => {
      if (!selectedTextElement) return;
      const nextProps: TextProps = { ...selectedTextElement.props, ...patch };
      const mutableNextProps = nextProps as TextProps & {
        [key: string]: unknown;
      };
      for (const key of keysToRemove) {
        delete mutableNextProps[key];
      }
      editor.updateElements([
        { elementId: selectedTextElement.id, updates: { props: nextProps } },
      ]);
    },
    [editor, selectedTextElement],
  );

  const handleInsertText = useCallback(
    async (config: TextInsertConfig) => {
      const inserted = await onInsertText(config);
      if (!inserted) return false;
      setSelectedItem(inserted);
      setSelection(new Set([inserted.getId()]));
      return true;
    },
    [onInsertText, setSelectedItem, setSelection],
  );

  const handleAddText = useCallback(async () => {
    const didInsert = await handleInsertText({
      text: draftText,
      variant: "freeform",
    });
    if (didInsert) {
      setDraftText("");
    }
  }, [draftText, handleInsertText]);

  const propertiesHint = useMemo(() => {
    if (selectedIds.size === 0) {
      return "Select a text overlay on the canvas or timeline to edit it here.";
    }
    if (selectedIds.size > 1) {
      return "Select one text overlay at a time to edit its properties.";
    }
    if (selectedType === "caption") {
      return "Captions stay in the Caption tab. Select a manual text overlay to edit it here.";
    }
    return "Only manual text overlays are editable in this panel.";
  }, [selectedIds.size, selectedType]);

  return (
    <div className="space-y-4">
      <div className="rounded-2xl border border-editor-border bg-editor-card p-4">
        <div className="flex items-center justify-between gap-3">
          <div>
            <p className="text-sm font-semibold text-foreground">Add Text</p>
            <p className="mt-1 text-xs text-editor-text-muted">
              Create manual overlays without using the agent.
            </p>
          </div>
          <div className="rounded-full border border-editor-border bg-editor-control px-2 py-1 text-[10px] uppercase tracking-[0.18em] text-editor-text-dim">
            Manual
          </div>
        </div>
        <textarea
          rows={3}
          value={draftText}
          onChange={(event) => setDraftText(event.target.value)}
          placeholder="Sample text"
          className="mt-4 w-full rounded-2xl border border-editor-border bg-editor-control px-3 py-3 text-sm text-foreground placeholder:text-muted-foreground focus:border-primary/50 focus:outline-none focus:ring-1 focus:ring-primary/30"
        />
        <button
          type="button"
          onClick={() => void handleAddText()}
          className="mt-3 flex w-full items-center justify-center gap-2 rounded-xl bg-primary px-3 py-2.5 text-sm font-semibold text-primary-foreground transition hover:bg-primary/90"
        >
          <Plus className="h-4 w-4" />
          Add to timeline
        </button>
      </div>

      <div className="rounded-2xl border border-editor-border bg-editor-card p-4">
        <div className="flex items-center justify-between gap-3">
          <div>
            <p className="text-sm font-semibold text-foreground">
              Text Properties
            </p>
            <p className="mt-1 text-xs text-editor-text-muted">
              {selectedTextElement
                ? selectedTextElement.name
                : "Select a text overlay to edit it here"}
            </p>
          </div>
          {selectedTextElement ? (
            <div className="rounded-full border border-primary/30 bg-primary/10 px-2 py-1 text-[10px] uppercase tracking-[0.16em] text-primary">
              Active
            </div>
          ) : null}
        </div>

        {!selectedTextElement ? (
          <div className="mt-4 rounded-xl border border-dashed border-editor-border bg-editor-control/50 px-3 py-4 text-center text-xs text-editor-text-muted">
            {propertiesHint}
          </div>
        ) : (
          <div className="mt-4 space-y-4">
            <div className="space-y-2">
              <div className="text-xs font-medium text-editor-text-muted">
                Text
              </div>
              <textarea
                rows={3}
                value={selectedProps.text ?? ""}
                onChange={(event) =>
                  updateSelectedTextProps({ text: event.target.value })
                }
                className="w-full rounded-2xl border border-editor-border bg-editor-control px-3 py-3 text-sm text-foreground placeholder:text-muted-foreground focus:border-primary/50 focus:outline-none focus:ring-1 focus:ring-primary/30"
                placeholder="Enter text"
              />
            </div>

            <div className="space-y-2">
              <div className="flex items-center justify-between gap-3 text-xs font-medium text-editor-text-muted">
                <span>Font Size</span>
                <span>{fontSize}px</span>
              </div>
              <input
                type="range"
                min={16}
                max={160}
                step={1}
                value={fontSize}
                onChange={(event) =>
                  updateSelectedTextProps({
                    fontSize: Number(event.target.value),
                  })
                }
                className="w-full accent-primary"
              />
            </div>

            <div className="space-y-2">
              <div className="text-xs font-medium text-editor-text-muted">
                Font
              </div>
              <div className="flex items-center gap-2">
                <select
                  value={selectedFontFamily}
                  onChange={(event) =>
                    updateSelectedTextProps({ fontFamily: event.target.value })
                  }
                  className="flex-1 rounded-xl border border-editor-border bg-editor-control px-3 py-2.5 text-sm text-foreground focus:border-primary/50 focus:outline-none focus:ring-1 focus:ring-primary/30"
                >
                  {fontOptions.map((font) => (
                    <option key={font} value={font}>
                      {font}
                    </option>
                  ))}
                </select>
                <button
                  type="button"
                  onClick={() =>
                    updateSelectedTextProps({ fontWeight: isBold ? 400 : 700 })
                  }
                  className={cn(
                    "flex h-11 w-11 items-center justify-center rounded-xl border transition",
                    isBold
                      ? "border-primary/45 bg-primary/15 text-primary"
                      : "border-editor-border bg-editor-control text-foreground hover:border-primary/35 hover:bg-editor-control-hover",
                  )}
                  title="Bold"
                >
                  <Bold className="h-4 w-4" />
                </button>
                <button
                  type="button"
                  onClick={() =>
                    updateSelectedTextProps({
                      fontStyle: isItalic ? "normal" : "italic",
                    })
                  }
                  className={cn(
                    "flex h-11 w-11 items-center justify-center rounded-xl border transition",
                    isItalic
                      ? "border-primary/45 bg-primary/15 text-primary"
                      : "border-editor-border bg-editor-control text-foreground hover:border-primary/35 hover:bg-editor-control-hover",
                  )}
                  title="Italic"
                >
                  <Italic className="h-4 w-4" />
                </button>
              </div>
            </div>

            <div className="space-y-3">
              <p className="text-xs font-semibold uppercase tracking-[0.18em] text-editor-text-dim">
                Colors
              </p>
              <TextColorField
                label="Text Color"
                color={fillColor}
                draft={textColorDraft}
                onColorChange={(nextColor) => {
                  setTextColorDraft(nextColor);
                  updateSelectedTextProps({ fill: nextColor });
                }}
                onDraftChange={(nextValue) => {
                  setTextColorDraft(nextValue);
                  const normalized = normalizeHexColor(nextValue);
                  if (normalized) updateSelectedTextProps({ fill: normalized });
                }}
                onDraftBlur={() => setTextColorDraft(fillColor)}
              />
              <TextColorField
                label="Stroke Color"
                color={strokeColor}
                draft={strokeColorDraft}
                onColorChange={(nextColor) => {
                  setStrokeColorDraft(nextColor);
                  updateSelectedTextProps({ stroke: nextColor });
                }}
                onDraftChange={(nextValue) => {
                  setStrokeColorDraft(nextValue);
                  const normalized = normalizeHexColor(nextValue);
                  if (normalized)
                    updateSelectedTextProps({ stroke: normalized });
                }}
                onDraftBlur={() => setStrokeColorDraft(strokeColor)}
              />
            </div>

            <label className="flex items-center gap-3 rounded-xl border border-editor-border bg-editor-control px-3 py-3 text-sm text-foreground">
              <input
                type="checkbox"
                checked={hasShadow}
                onChange={(event) => {
                  if (event.target.checked) {
                    updateSelectedTextProps(DEFAULT_SHADOW_PROPS);
                    return;
                  }
                  updateSelectedTextProps({}, [
                    "shadowColor",
                    "shadowOffset",
                    "shadowBlur",
                    "shadowOpacity",
                  ]);
                }}
                className="h-4 w-4 rounded border-editor-border accent-primary"
              />
              Apply Shadow
            </label>

            <div className="space-y-2">
              <div className="flex items-center justify-between gap-3 text-xs font-medium text-editor-text-muted">
                <span>Stroke Width</span>
                <span>{strokeWidth}</span>
              </div>
              <input
                type="range"
                min={0}
                max={24}
                step={1}
                value={strokeWidth}
                onChange={(event) => {
                  const nextWidth = Number(event.target.value);
                  updateSelectedTextProps({
                    lineWidth: nextWidth,
                    strokeWidth: nextWidth,
                  });
                }}
                className="w-full accent-primary"
              />
            </div>

            <label className="flex items-center gap-3 rounded-xl border border-editor-border bg-editor-control px-3 py-3 text-sm text-foreground">
              <input
                type="checkbox"
                checked={hasBackground}
                onChange={(event) => {
                  if (event.target.checked) {
                    updateSelectedTextProps({
                      backgroundColor:
                        normalizeHexColor(backgroundColorDraft) ??
                        backgroundColor,
                      backgroundOpacity:
                        typeof selectedProps.backgroundOpacity === "number"
                          ? selectedProps.backgroundOpacity
                          : DEFAULT_BACKGROUND_OPACITY,
                    });
                    return;
                  }
                  updateSelectedTextProps({}, [
                    "backgroundColor",
                    "backgroundOpacity",
                  ]);
                }}
                className="h-4 w-4 rounded border-editor-border accent-primary"
              />
              Apply Background
            </label>

            <TextColorField
              label="Background Color"
              color={backgroundColor}
              draft={backgroundColorDraft}
              disabled={!hasBackground}
              onColorChange={(nextColor) => {
                setBackgroundColorDraft(nextColor);
                updateSelectedTextProps({
                  backgroundColor: nextColor,
                  backgroundOpacity:
                    typeof selectedProps.backgroundOpacity === "number"
                      ? selectedProps.backgroundOpacity
                      : DEFAULT_BACKGROUND_OPACITY,
                });
              }}
              onDraftChange={(nextValue) => {
                setBackgroundColorDraft(nextValue);
                const normalized = normalizeHexColor(nextValue);
                if (normalized && hasBackground) {
                  updateSelectedTextProps({
                    backgroundColor: normalized,
                    backgroundOpacity:
                      typeof selectedProps.backgroundOpacity === "number"
                        ? selectedProps.backgroundOpacity
                        : DEFAULT_BACKGROUND_OPACITY,
                  });
                }
              }}
              onDraftBlur={() => setBackgroundColorDraft(backgroundColor)}
            />
          </div>
        )}
      </div>
    </div>
  );
}
