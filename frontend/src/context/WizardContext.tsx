"use client";

import React, {
  createContext,
  useContext,
  useReducer,
  type ReactNode,
} from "react";
import type { WizardState, WizardAction } from "@/types";

const initialState: WizardState = {
  currentStep: 1,
  totalSteps: 8,
  isProcessing: false,

  // Step 1: Message
  messageTab: "speech",
  selectedFormat: null,
  messageText: "",
  selectedPreset: null,

  // Step 2: Language & Voice
  language: "English",
  selectedVoice: null,

  // Step 3: Music
  selectedMusic: null,

  // Step 4: Art Style
  selectedArtStyle: null,

  // Step 5: Caption
  selectedCaption: null,

  // Step 6: Effects
  effects: {
    shakeEffect: false,
    filmGrain: false,
    animatedStock: false,
  },

  // Step 7: Video Details
  seriesName: "",
  videoDuration: "",
  publishTime: "",

  // Preset flow
  presetConfig: null,
  pipelineProjectId: null,
  pipelineVideoUrls: {},

  // Speech / Text two-phase flow
  audioBase64: null,
  audioFormat: "webm",
  generatedScript: null,
  scriptProjectId: null,
  showScriptReview: false,
};

function wizardReducer(state: WizardState, action: WizardAction): WizardState {
  switch (action.type) {
    case "SET_STEP":
      return { ...state, currentStep: action.payload };
    case "NEXT_STEP":
      return {
        ...state,
        currentStep: Math.min(state.currentStep + 1, state.totalSteps),
      };
    case "PREV_STEP":
      return { ...state, currentStep: Math.max(state.currentStep - 1, 1) };
    case "SET_PROCESSING":
      return { ...state, isProcessing: action.payload };
    case "SET_MESSAGE_TAB":
      return { ...state, messageTab: action.payload };
    case "SET_SELECTED_FORMAT":
      return { ...state, selectedFormat: action.payload };
    case "SET_MESSAGE_TEXT":
      return { ...state, messageText: action.payload };
    case "SET_SELECTED_PRESET":
      return { ...state, selectedPreset: action.payload };
    case "SET_LANGUAGE":
      return { ...state, language: action.payload };
    case "SET_SELECTED_VOICE":
      return { ...state, selectedVoice: action.payload };
    case "SET_SELECTED_MUSIC":
      return { ...state, selectedMusic: action.payload };
    case "SET_SELECTED_ART_STYLE":
      return { ...state, selectedArtStyle: action.payload };
    case "SET_SELECTED_CAPTION":
      return { ...state, selectedCaption: action.payload };
    case "SET_EFFECT":
      return {
        ...state,
        effects: {
          ...state.effects,
          [action.payload.effect]: action.payload.value,
        },
      };
    case "SET_SERIES_NAME":
      return { ...state, seriesName: action.payload };
    case "SET_VIDEO_DURATION":
      return { ...state, videoDuration: action.payload };
    case "SET_PUBLISH_TIME":
      return { ...state, publishTime: action.payload };
    case "SET_PRESET_CONFIG":
      return { ...state, presetConfig: action.payload };
    case "SET_PIPELINE_RESULT":
      return {
        ...state,
        pipelineProjectId: action.payload.projectId,
        pipelineVideoUrls: action.payload.videoUrls,
      };
    case "SET_AUDIO_BASE64":
      return { ...state, audioBase64: action.payload };
    case "SET_AUDIO_FORMAT":
      return { ...state, audioFormat: action.payload };
    case "SET_GENERATED_SCRIPT":
      return { ...state, generatedScript: action.payload };
    case "SET_SCRIPT_PROJECT_ID":
      return { ...state, scriptProjectId: action.payload };
    case "SET_SHOW_SCRIPT_REVIEW":
      return { ...state, showScriptReview: action.payload };
    case "RESET_WIZARD":
      return initialState;
    default:
      return state;
  }
}

interface WizardContextType {
  state: WizardState;
  dispatch: React.Dispatch<WizardAction>;
}

const WizardContext = createContext<WizardContextType | undefined>(undefined);

export function WizardProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(wizardReducer, initialState);

  return (
    <WizardContext.Provider value={{ state, dispatch }}>
      {children}
    </WizardContext.Provider>
  );
}

export function useWizard() {
  const context = useContext(WizardContext);
  if (context === undefined) {
    throw new Error("useWizard must be used within a WizardProvider");
  }
  return context;
}
