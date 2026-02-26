export interface GeneratedScriptScene {
  scene_id: number;
  duration_seconds: number;
  voiceover_text: string;
  visual_prompt?: string | null;
  emotion: string;
  transition_to_next?: string | null;
  text_overlay?: unknown;
}

export interface GeneratedScript {
  project_id: string;
  metadata: Record<string, unknown>;
  hook: { text: string; duration: number };
  scenes: GeneratedScriptScene[];
  cta: { text: string; type: string };
  social_copy: Record<string, unknown>;
  voiceover_full_script: string;
}

export interface PresetConfigureResponse {
  series_id: string;
  series_name: string;
  transcript: string;
  voice_id: string;
  voice_name: string;
  art_style: string;
  caption_style: string;
  background_music: string;
  music_volume: number;
  video_duration: string;
  video_format: string;
  target_platforms: string[];
  nemotron_reasoning: string;
  configured_by: string;
  stages: Array<{ stage: string; status: string; detail?: string | null }>;
}

export interface VoiceData {
  id: string;
  name: string;
  gender: "Male" | "Female" | "Me";
  description: string;
  avatarColor: string;
}

export interface MusicData {
  id: string;
  title: string;
  description: string;
  iconColor: string;
  audioFile: string;
}

export interface ArtStyle {
  id: string;
  name: string;
  description: string;
}

export interface CaptionStyle {
  id: string;
  name: string;
  preview: string;
}

export interface EffectData {
  id: string;
  name: string;
  description: string;
  tag?: "NEW" | "PREMIUM";
}

export interface Scene {
  id: number;
  title: string;
  description: string;
  timestamp: string;
}

export interface ProcessStep {
  id: number;
  title: string;
  description: string;
  model?: string;
}

export interface WizardState {
  currentStep: number;
  totalSteps: number;
  isProcessing: boolean;

  // Step 1: Message
  messageTab: "speech" | "text" | "preset";
  selectedFormat: string | null;
  messageText: string;
  selectedPreset: string | null;

  // Step 2: Language & Voice
  language: string;
  selectedVoice: string | null;

  // Step 3: Music
  selectedMusic: string | null;

  // Step 4: Art Style
  selectedArtStyle: string | null;

  // Step 5: Caption
  selectedCaption: string | null;

  // Step 6: Effects
  effects: {
    shakeEffect: boolean;
    filmGrain: boolean;
    animatedStock: boolean;
  };

  // Step 7: Video Details
  seriesName: string;
  videoDuration: string;
  publishTime: string;

  // Preset flow
  presetConfig: PresetConfigureResponse | null;
  pipelineProjectId: string | null;
  pipelineVideoUrls: Record<string, string>;

  // Speech / Text two-phase flow
  audioBase64: string | null;
  audioFormat: string;
  generatedScript: GeneratedScript | null;
  scriptProjectId: string | null;
  showScriptReview: boolean;
}

export type WizardAction =
  | { type: "SET_STEP"; payload: number }
  | { type: "NEXT_STEP" }
  | { type: "PREV_STEP" }
  | { type: "SET_PROCESSING"; payload: boolean }
  | { type: "SET_MESSAGE_TAB"; payload: "speech" | "text" | "preset" }
  | { type: "SET_SELECTED_FORMAT"; payload: string | null }
  | { type: "SET_MESSAGE_TEXT"; payload: string }
  | { type: "SET_SELECTED_PRESET"; payload: string | null }
  | { type: "SET_LANGUAGE"; payload: string }
  | { type: "SET_SELECTED_VOICE"; payload: string | null }
  | { type: "SET_SELECTED_MUSIC"; payload: string | null }
  | { type: "SET_SELECTED_ART_STYLE"; payload: string | null }
  | { type: "SET_SELECTED_CAPTION"; payload: string | null }
  | {
      type: "SET_EFFECT";
      payload: { effect: keyof WizardState["effects"]; value: boolean };
    }
  | { type: "SET_SERIES_NAME"; payload: string }
  | { type: "SET_VIDEO_DURATION"; payload: string }
  | { type: "SET_PUBLISH_TIME"; payload: string }
  | { type: "SET_PRESET_CONFIG"; payload: PresetConfigureResponse | null }
  | { type: "SET_PIPELINE_RESULT"; payload: { projectId: string; videoUrls: Record<string, string> } }
  | { type: "SET_AUDIO_BASE64"; payload: string | null }
  | { type: "SET_AUDIO_FORMAT"; payload: string }
  | { type: "SET_GENERATED_SCRIPT"; payload: GeneratedScript | null }
  | { type: "SET_SCRIPT_PROJECT_ID"; payload: string | null }
  | { type: "SET_SHOW_SCRIPT_REVIEW"; payload: boolean }
  | { type: "RESET_WIZARD" };
