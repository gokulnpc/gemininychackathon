"use client";

import { useCallback, useMemo } from "react";
import { Check } from "lucide-react";
import {
  EffectElement,
  type ProjectJSON,
  TRACK_TYPES,
  TIMELINE_ELEMENT_TYPE,
  useTimelineContext,
} from "@twick/timeline";

import { EFFECT_OPTIONS, EFFECTS, type EffectKey } from "@/lib/twick-effects";
import { cn } from "@/lib/utils";

import { EffectStylePreview } from "./effect-style-preview";

type TimelineTrackJson = NonNullable<ProjectJSON["tracks"]>[number];
type TimelineElementJson = TimelineTrackJson["elements"][number];

interface TimelineElementRecord {
  track: TimelineTrackJson;
  element: TimelineElementJson;
}

interface EffectsPanelProps {
  agentLoading: boolean;
}

const EFFECT_STYLE_TRACK_NAME = "Effect Styles";

const STYLE_EFFECT_PRIORITY: EffectKey[] = [
  "sepia",
  "vignette",
  "pixelate",
  "warp",
  "glitch",
  "rgbShift",
  "halftone",
  "hueShift",
  "waveDistort",
  "tvScanlines",
  "hdr",
  "retro70s",
  "bubbleSparkles",
  "heartSparkles",
];

const STYLE_EFFECT_PRIORITY_MAP = new Map(
  STYLE_EFFECT_PRIORITY.map((key, index) => [key, index]),
);

const STYLE_EFFECT_OPTIONS = [...EFFECT_OPTIONS].sort((left, right) => {
  const leftPriority =
    STYLE_EFFECT_PRIORITY_MAP.get(left.key) ?? STYLE_EFFECT_PRIORITY.length + 1;
  const rightPriority =
    STYLE_EFFECT_PRIORITY_MAP.get(right.key) ?? STYLE_EFFECT_PRIORITY.length + 1;

  if (leftPriority !== rightPriority) {
    return leftPriority - rightPriority;
  }

  return left.label.localeCompare(right.label);
});

const isKnownEffectKey = (value: unknown): value is EffectKey =>
  typeof value === "string" &&
  Object.prototype.hasOwnProperty.call(EFFECTS, value);

const findElementRecordById = (
  projectJson: ProjectJSON | null,
  elementId: string | null,
): TimelineElementRecord | null => {
  if (!projectJson || !elementId) {
    return null;
  }

  for (const track of projectJson.tracks ?? []) {
    for (const element of track.elements ?? []) {
      if (element.id === elementId) {
        return { track, element };
      }
    }
  }

  return null;
};

const isStyleMediaElementType = (type: string | undefined): boolean =>
  type === TIMELINE_ELEMENT_TYPE.IMAGE || type === TIMELINE_ELEMENT_TYPE.VIDEO;

const isStyleEligibleType = (type: string | undefined): boolean =>
  isStyleMediaElementType(type) || type === TIMELINE_ELEMENT_TYPE.EFFECT;

const getEffectKeyFromProps = (props: unknown): EffectKey | null => {
  if (!props || typeof props !== "object") {
    return null;
  }

  const effectKey = (props as { effectKey?: unknown }).effectKey;
  return isKnownEffectKey(effectKey) ? effectKey : null;
};

const getLinkedStyleEffectRecord = (
  projectJson: ProjectJSON | null,
  selectedRecord: TimelineElementRecord | null,
): TimelineElementRecord | null => {
  if (!projectJson || !selectedRecord) {
    return null;
  }

  if (!isStyleMediaElementType(selectedRecord.element.type)) {
    return null;
  }

  const effectTrack = (projectJson.tracks ?? []).find(
    (track) =>
      track.name === EFFECT_STYLE_TRACK_NAME &&
      (track.type ?? TRACK_TYPES.ELEMENT) === TRACK_TYPES.ELEMENT,
  );

  if (!effectTrack) {
    return null;
  }

  const matchingEffect = (effectTrack.elements ?? []).find(
    (element) =>
      element.type === TIMELINE_ELEMENT_TYPE.EFFECT &&
      element.s === selectedRecord.element.s &&
      element.e === selectedRecord.element.e,
  );

  return matchingEffect ? { track: effectTrack, element: matchingEffect } : null;
};

export function EffectsPanel({ agentLoading }: EffectsPanelProps) {
  const {
    editor,
    present,
    selectedItem,
    selectedIds,
    setSelectedItem,
    setSelection,
  } = useTimelineContext();

  const selectedElementId = useMemo(
    () => (selectedIds.size === 1 ? Array.from(selectedIds)[0] : null),
    [selectedIds],
  );
  const selectedElementRecord = useMemo(
    () => findElementRecordById(present, selectedElementId),
    [present, selectedElementId],
  );
  const selectedType =
    selectedElementRecord?.element.type ??
    (selectedItem &&
    typeof selectedItem === "object" &&
    "getType" in selectedItem
      ? (selectedItem as { getType?: () => string }).getType?.() ?? ""
      : "");

  const linkedStyleEffectRecord = useMemo(
    () => getLinkedStyleEffectRecord(present, selectedElementRecord),
    [present, selectedElementRecord],
  );
  const activeStyleEffectRecord =
    selectedType === TIMELINE_ELEMENT_TYPE.EFFECT
      ? selectedElementRecord
      : linkedStyleEffectRecord;
  const selectedStyleEffectKey = getEffectKeyFromProps(
    activeStyleEffectRecord?.element.props,
  );
  const canApplyStyleEffect =
    selectedIds.size === 1 && isStyleEligibleType(selectedType);
  const canRemoveStyleEffect = Boolean(activeStyleEffectRecord);

  const styleHint = useMemo(() => {
    if (selectedIds.size === 0) {
      return "Select one image, video, or effect clip to apply a style effect.";
    }
    if (selectedIds.size > 1) {
      return "Select one clip at a time to apply or remove a style effect.";
    }
    if (selectedType === TIMELINE_ELEMENT_TYPE.EFFECT || isStyleMediaElementType(selectedType)) {
      return null;
    }
    return "Style effects are only available for image and video clips.";
  }, [selectedIds.size, selectedType]);

  const handleApplyStyleEffect = useCallback(
    async (effect: (typeof STYLE_EFFECT_OPTIONS)[number]) => {
      if (agentLoading || !selectedElementRecord || !canApplyStyleEffect) {
        return;
      }

      try {
        if (selectedType === TIMELINE_ELEMENT_TYPE.EFFECT) {
          const existingProps =
            selectedElementRecord.element.props &&
            typeof selectedElementRecord.element.props === "object"
              ? { ...selectedElementRecord.element.props }
              : {};

          editor.updateElements([
            {
              elementId: selectedElementRecord.element.id,
              updates: {
                name: effect.label,
                props: {
                  ...existingProps,
                  effectKey: effect.key,
                  intensity: 1,
                },
              },
            },
          ]);
          return;
        }

        if (!isStyleMediaElementType(selectedType)) {
          return;
        }

        if (linkedStyleEffectRecord) {
          const existingProps =
            linkedStyleEffectRecord.element.props &&
            typeof linkedStyleEffectRecord.element.props === "object"
              ? { ...linkedStyleEffectRecord.element.props }
              : {};

          editor.updateElements([
            {
              elementId: linkedStyleEffectRecord.element.id,
              updates: {
                name: effect.label,
                props: {
                  ...existingProps,
                  effectKey: effect.key,
                  intensity: 1,
                },
              },
            },
          ]);
          return;
        }

        const effectTrack =
          editor.getTrackByName(EFFECT_STYLE_TRACK_NAME) ??
          editor.addTrack(EFFECT_STYLE_TRACK_NAME, TRACK_TYPES.ELEMENT);

        const effectElement = new EffectElement(effect.key, { intensity: 1 })
          .setName(effect.label)
          .setStart(selectedElementRecord.element.s)
          .setEnd(selectedElementRecord.element.e);

        const added = await editor.addElementToTrack(effectTrack, effectElement);

        if (added) {
          setSelectedItem(effectElement);
          setSelection(new Set([effectElement.getId()]));
        }
      } catch (error) {
        console.error("[EffectsPanel] Failed to apply style effect:", error);
      }
    },
    [
      agentLoading,
      canApplyStyleEffect,
      editor,
      linkedStyleEffectRecord,
      selectedElementRecord,
      selectedType,
      setSelectedItem,
      setSelection,
    ],
  );

  const handleRemoveStyleEffect = useCallback(() => {
    if (!activeStyleEffectRecord) {
      return;
    }

    try {
      editor.removeElements([activeStyleEffectRecord.element.id]);

      if (selectedType === TIMELINE_ELEMENT_TYPE.EFFECT) {
        setSelectedItem(null);
        setSelection(new Set<string>());
      }
    } catch (error) {
      console.error("[EffectsPanel] Failed to remove style effect:", error);
    }
  }, [
    activeStyleEffectRecord,
    editor,
    selectedType,
    setSelectedItem,
    setSelection,
  ]);

  return (
    <div className="space-y-3">
      {styleHint ? (
        <div className="rounded-xl border border-dashed border-editor-border bg-editor-card/60 px-3 py-3 text-center text-xs text-editor-text-muted">
          {styleHint}
        </div>
      ) : null}

      <div className="grid grid-cols-2 gap-2">
        {STYLE_EFFECT_OPTIONS.map((effect) => {
          const isSelected = effect.key === selectedStyleEffectKey;
          return (
            <button
              key={effect.key}
              type="button"
              onClick={() => void handleApplyStyleEffect(effect)}
              disabled={agentLoading || !canApplyStyleEffect}
              title={effect.description}
              className={cn(
                "group relative overflow-hidden rounded-xl border transition-all disabled:opacity-40",
                isSelected
                  ? "border-primary/50 ring-1 ring-primary/30"
                  : "border-editor-border hover:border-primary/40 hover:ring-1 hover:ring-primary/20",
              )}
            >
              <div className="relative aspect-[5/4] w-full overflow-hidden rounded-xl">
                <EffectStylePreview effectKey={effect.key} />
                <div className="absolute inset-0 bg-gradient-to-t from-black/85 via-black/15 to-transparent" />
                {isSelected ? (
                  <div className="absolute right-1.5 top-1.5 flex h-5 w-5 items-center justify-center rounded-full bg-primary shadow-md">
                    <Check className="h-3 w-3 text-primary-foreground" />
                  </div>
                ) : null}
                <div className="absolute inset-x-0 bottom-0 px-3 pb-4 pt-8">
                  <p className="text-center text-sm font-semibold leading-tight text-white drop-shadow-[0_2px_12px_rgba(0,0,0,0.75)]">
                    {effect.label}
                  </p>
                </div>
              </div>
            </button>
          );
        })}
      </div>

      {canRemoveStyleEffect ? (
        <button
          type="button"
          onClick={handleRemoveStyleEffect}
          className="w-full rounded-xl border border-dashed border-editor-border px-3 py-2.5 text-center text-xs text-editor-text-muted transition hover:border-red-400/40 hover:text-red-400"
        >
          Remove style effect
        </button>
      ) : null}
    </div>
  );
}
