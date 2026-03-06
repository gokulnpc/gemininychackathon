"use client";

import { useRef, useState } from "react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import {
  Upload,
  Volume2,
  Type,
  LayoutGrid,
  CheckCircle2,
  Loader2,
  Sparkles,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useWizard } from "@/context/WizardContext";
import { presets } from "@/data/staticData";
import { motion, AnimatePresence } from "framer-motion";
import { AudioVisualizer } from "@/components/AudioVisualizer";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export function Step1_Message() {
  const { state, dispatch } = useWizard();
  const [activeTab, setActiveTab] = useState<"speech" | "text" | "preset">(
    state.messageTab
  );
  const [isRecording, setIsRecording] = useState(false);
  const [audioReady, setAudioReady] = useState(false);
  const [uploadedFileName, setUploadedFileName] = useState<string | null>(null);
  const [transcribing, setTranscribing] = useState(false);
  const [transcript, setTranscript] = useState<string | null>(null);

  const [audioUrl, setAudioUrl] = useState<string | null>(null);

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleTabChange = (value: string) => {
    setActiveTab(value as "speech" | "text" | "preset");
    dispatch({
      type: "SET_MESSAGE_TAB",
      payload: value as "speech" | "text" | "preset",
    });
  };

  const handlePresetSelect = (presetId: string) => {
    dispatch({ type: "SET_SELECTED_PRESET", payload: presetId });
  };

  // ── Transcription ──────────────────────────────────────────────────────────

  const runTranscribe = async (b64: string, format: string) => {
    setTranscribing(true);
    setTranscript(null);
    try {
      const res = await fetch(`${API}/api/v1/transcribe`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          audio_base64: b64,
          audio_format: format,
          language: "en",
        }),
      });
      if (!res.ok) throw new Error("Transcription failed");
      const data = await res.json();
      setTranscript(data.transcript ?? null);
    } catch {
      // transcript is optional — silently skip on failure
    } finally {
      setTranscribing(false);
    }
  };

  // ── Audio recording ────────────────────────────────────────────────────────

  const startRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(stream, { mimeType: "audio/webm" });
      chunksRef.current = [];
      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data);
      };
      recorder.onstop = () => {
        stream.getTracks().forEach((t) => t.stop());
        const blob = new Blob(chunksRef.current, { type: "audio/webm" });
        setAudioUrl((prev) => {
          if (prev) URL.revokeObjectURL(prev);
          return URL.createObjectURL(blob);
        });
        const reader = new FileReader();
        reader.onloadend = () => {
          const b64 = (reader.result as string).split(",")[1];
          dispatch({ type: "SET_AUDIO_BASE64", payload: b64 });
          dispatch({ type: "SET_AUDIO_FORMAT", payload: "webm" });
          setAudioReady(true);
          setUploadedFileName(null);
          runTranscribe(b64, "webm");
        };
        reader.readAsDataURL(blob);
      };
      mediaRecorderRef.current = recorder;
      recorder.start();
      setIsRecording(true);
      setAudioReady(false);
      setTranscript(null);
    } catch {
      alert(
        "Microphone access denied. Please allow microphone access and try again."
      );
    }
  };

  const stopRecording = () => {
    mediaRecorderRef.current?.stop();
    setIsRecording(false);
  };

  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploadedFileName(file.name);
    setAudioUrl((prev) => {
      if (prev) URL.revokeObjectURL(prev);
      return URL.createObjectURL(file);
    });
    const ext = file.name.split(".").pop()?.toLowerCase() ?? "mp3";
    const reader = new FileReader();
    reader.onloadend = () => {
      const b64 = (reader.result as string).split(",")[1];
      dispatch({ type: "SET_AUDIO_BASE64", payload: b64 });
      dispatch({ type: "SET_AUDIO_FORMAT", payload: ext });
      setAudioReady(true);
      runTranscribe(b64, ext);
    };
    reader.readAsDataURL(file);
    // reset so the same file can be re-selected
    e.target.value = "";
  };

  const textFileInputRef = useRef<HTMLInputElement>(null);
  const [ocrLoading, setOcrLoading] = useState(false);
  const [ocrFileName, setOcrFileName] = useState<string | null>(null);

  const handleTextFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    e.target.value = "";

    if (file.type === "application/pdf" || file.name.toLowerCase().endsWith(".pdf")) {
      // PDF → Mistral Document AI OCR
      setOcrFileName(file.name);
      setOcrLoading(true);
      const reader = new FileReader();
      reader.onloadend = async () => {
        try {
          const b64 = (reader.result as string).split(",")[1];
          const res = await fetch(`${API}/api/v1/ocr-pdf`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ pdf_base64: b64 }),
          });
          if (!res.ok) throw new Error("OCR request failed");
          const data = await res.json();
          dispatch({ type: "SET_MESSAGE_TEXT", payload: data.text ?? "" });
        } catch {
          setOcrFileName(null);
        } finally {
          setOcrLoading(false);
        }
      };
      reader.readAsDataURL(file);
    } else {
      // Plain text / markdown / rtf — read directly
      setOcrFileName(null);
      const reader = new FileReader();
      reader.onload = (event) => {
        const text = event.target?.result;
        if (typeof text === "string") {
          dispatch({ type: "SET_MESSAGE_TEXT", payload: text });
        }
      };
      reader.readAsText(file);
    }
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -20 }}
      transition={{ duration: 0.3 }}
    >
      <Tabs
        value={activeTab}
        onValueChange={handleTabChange}
        className="w-full"
      >
        <TabsList className="bg-transparent w-full justify-start rounded-none h-auto p-0 mb-8 gap-3">
          <TabsTrigger
            value="speech"
            className={cn(
              "rounded-xl px-5 py-3 text-sm font-medium transition-all duration-200 border",
              activeTab === "speech"
                ? "bg-[#5a9ab5]! text-white! border-[#5a9ab5] shadow-md data-[state=active]:bg-[#5a9ab5]! data-[state=active]:text-white! [&_svg]:text-white!"
                : "bg-white/10! text-white! border-white/20 hover:bg-white/20! hover:border-white/30 data-[state=active]:bg-[#5a9ab5]! data-[state=active]:text-white!"
            )}
          >
            <Volume2 className="w-4 h-4 mr-2" />
            Speech to Video
          </TabsTrigger>
          <TabsTrigger
            value="text"
            className={cn(
              "rounded-xl px-5 py-3 text-sm font-medium transition-all duration-200 border",
              activeTab === "text"
                ? "bg-[#5a9ab5]! text-white! border-[#5a9ab5] shadow-md data-[state=active]:bg-[#5a9ab5]! data-[state=active]:text-white! [&_svg]:text-white!"
                : "bg-white/10! text-white! border-white/20 hover:bg-white/20! hover:border-white/30 data-[state=active]:bg-[#5a9ab5]! data-[state=active]:text-white!"
            )}
          >
            <Type className="w-4 h-4 mr-2" />
            Text to Video
          </TabsTrigger>
          <TabsTrigger
            value="preset"
            className={cn(
              "rounded-xl px-5 py-3 text-sm font-medium transition-all duration-200 border",
              activeTab === "preset"
                ? "bg-[#5a9ab5]! text-white! border-[#5a9ab5] shadow-md data-[state=active]:bg-[#5a9ab5]! data-[state=active]:text-white! [&_svg]:text-white!"
                : "bg-white/10! text-white! border-white/20 hover:bg-white/20! hover:border-white/30 data-[state=active]:bg-[#5a9ab5]! data-[state=active]:text-white!"
            )}
          >
            <LayoutGrid className="w-4 h-4 mr-2" />
            Preset
          </TabsTrigger>
        </TabsList>

        {/* ── Speech tab ── */}
        <TabsContent value="speech" className="mt-0">
          <motion.div
            key="speech"
            initial={{ opacity: 0, x: -20 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.2 }}
          >
            {/* Record / Upload */}
            <div>
              <h3 className="text-base font-semibold text-white mb-4">
                Record your message
              </h3>
              <div className="bg-white/20 rounded-2xl border border-white/20 p-10 text-center relative overflow-hidden min-h-[260px] flex flex-col justify-center">
                <AnimatePresence mode="wait">
                  {isRecording ? (
                    <motion.div
                      key="recording"
                      initial={{ opacity: 0, scale: 0.9 }}
                      animate={{ opacity: 1, scale: 1 }}
                      exit={{ opacity: 0, scale: 0.9 }}
                      className="mb-8"
                    >
                      <AudioVisualizer />
                      <motion.p
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        transition={{ delay: 0.5 }}
                        className="text-white/70 text-sm mt-6 font-medium"
                      >
                        Listening…
                      </motion.p>
                    </motion.div>
                  ) : audioReady ? (
                    <motion.div
                      key="ready"
                      initial={{ opacity: 0, scale: 0.9 }}
                      animate={{ opacity: 1, scale: 1 }}
                      exit={{ opacity: 0, scale: 0.9 }}
                      className="mb-6 w-full"
                    >
                      <CheckCircle2 className="w-12 h-12 text-[#90D6F8] mx-auto mb-3" />
                      <p className="text-sm font-medium text-white">
                        {uploadedFileName
                          ? `Uploaded: ${uploadedFileName}`
                          : "Recording saved!"}
                      </p>

                      {/* Audio playback */}
                      {audioUrl && (
                        <div className="mt-4 px-2">
                          <audio
                            key={audioUrl}
                            src={audioUrl}
                            controls
                            className="w-full h-10 rounded-lg"
                          />
                        </div>
                      )}

                      {transcribing ? (
                        <div className="flex items-center justify-center gap-2 mt-3">
                          <Loader2 className="w-4 h-4 animate-spin text-[#5a9ab5]" />
                          <span className="text-xs text-white/50">
                            Transcribing…
                          </span>
                        </div>
                      ) : transcript ? (
                        <div className="mt-4 p-4 bg-white/10 rounded-xl text-left max-h-32 overflow-y-auto">
                          <p className="text-xs font-semibold text-[#5a9ab5] mb-1 uppercase tracking-wide">
                            Transcript
                          </p>
                          <p className="text-sm text-white leading-relaxed">
                            {transcript}
                          </p>
                        </div>
                      ) : (
                        <p className="text-xs text-white/40 mt-1">
                          Audio ready — continue through the wizard to generate
                          your script
                        </p>
                      )}
                    </motion.div>
                  ) : (
                    <motion.div
                      key="start"
                      initial={{ opacity: 0, scale: 0.9 }}
                      animate={{ opacity: 1, scale: 1 }}
                      exit={{ opacity: 0, scale: 0.9 }}
                    >
                      <motion.div
                        whileHover={{ scale: 1.05 }}
                        whileTap={{ scale: 0.95 }}
                        className="w-20 h-20 mx-auto mb-4 cursor-pointer"
                        onClick={startRecording}
                      >
                        <img
                          src="/Mic_Button_Sky.png"
                          alt="Record"
                          className="w-full h-full object-contain"
                        />
                      </motion.div>
                      <p className="text-white/70 text-sm mb-6">
                        Speak naturally about your product, idea, or story.
                      </p>
                    </motion.div>
                  )}
                </AnimatePresence>

                {/* Hidden file input */}
                <input
                  ref={fileInputRef}
                  type="file"
                  accept="audio/*"
                  className="hidden"
                  onChange={handleFileUpload}
                />

                <div className="flex items-center justify-center gap-4">
                  {isRecording ? (
                    <Button
                      variant="outline"
                      className="rounded-full px-6 py-5 bg-white/10 text-white border-white/30 hover:bg-white/20 transition-colors duration-300"
                      onClick={stopRecording}
                    >
                      <div className="w-3 h-3 bg-white rounded-sm mr-2 animate-pulse" />
                      Stop Recording
                    </Button>
                  ) : (
                    <>
                      <Button
                        variant="outline"
                        className="rounded-full px-6 py-5 bg-white/10 text-white border-white/30 hover:bg-white/20"
                        onClick={startRecording}
                      >
                        {audioReady ? "Re-record" : "Start Recording"}
                      </Button>
                      <span className="text-white/40 text-sm">or</span>
                      <Button
                        variant="outline"
                        className="rounded-full px-6 py-5 bg-white/10 text-white border-white/30 hover:bg-white/20"
                        onClick={() => fileInputRef.current?.click()}
                      >
                        <Upload className="w-4 h-4 mr-2" />
                        Upload Audio
                      </Button>
                    </>
                  )}
                </div>
              </div>
            </div>
          </motion.div>
        </TabsContent>

        {/* ── Text tab ── */}
        <TabsContent value="text" className="mt-0">
          <motion.div
            key="text"
            initial={{ opacity: 0, x: -20 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.2 }}
          >
            <h3 className="text-base font-semibold text-white mb-4">
              Type your idea
            </h3>
            <div className="space-y-4">
              <textarea
                value={state.messageText}
                onChange={(e) =>
                  dispatch({
                    type: "SET_MESSAGE_TEXT",
                    payload: e.target.value,
                  })
                }
                placeholder="E.g, a video showcasing the marketing campaign for a vegan-friendly skincare product"
                className="w-full min-h-[120px] p-5 rounded-2xl border border-white/20 bg-white/20 text-white placeholder:text-white/30 resize-none focus:outline-none focus:ring-2 focus:ring-[#5a9ab5]/30 focus:border-[#5a9ab5] transition-all duration-200"
              />

              <div className="flex items-center justify-end gap-3">
                {ocrLoading && (
                  <span className="flex items-center gap-2 text-xs text-white/50">
                    <Loader2 className="w-3 h-3 animate-spin" />
                    Extracting text from PDF…
                  </span>
                )}
                {ocrFileName && !ocrLoading && (
                  <span className="flex items-center gap-1.5 text-xs text-[#5a9ab5]">
                    <CheckCircle2 className="w-3 h-3" />
                    {ocrFileName}
                  </span>
                )}
                <input
                  type="file"
                  accept=".txt,.md,.rtf,.pdf"
                  className="hidden"
                  ref={textFileInputRef}
                  onChange={handleTextFileUpload}
                />
                <Button
                  variant="outline"
                  size="sm"
                  disabled={ocrLoading}
                  onClick={() => textFileInputRef.current?.click()}
                  className="bg-transparent text-white border-white/20 hover:bg-white/10 disabled:opacity-50"
                >
                  <Upload className="w-4 h-4 mr-2" />
                  Upload your Message
                </Button>
              </div>

              <div className="bg-white/20 rounded-2xl border border-white/20 p-5">
                <h4 className="text-sm font-medium text-white/60 mb-3">
                  Ideas for you
                </h4>
                <div className="space-y-3">
                  {[
                    "Close-up ASMR-style film of hands refilling a ceramic skincare jar from a glass pouch.",
                    "A poetic environmental brand film.",
                    "A slow cinematic commercial for a vegan probiotic skincare brand.",
                  ].map((idea, i) => (
                    <button
                      key={i}
                      onClick={() =>
                        dispatch({ type: "SET_MESSAGE_TEXT", payload: idea })
                      }
                      className="w-full flex items-start gap-3 text-left group hover:bg-white/10 p-2 rounded-lg transition-colors"
                    >
                      <Sparkles className="w-4 h-4 text-[#5a9ab5] mt-0.5 shrink-0" />
                      <span className="text-sm text-white/70 group-hover:text-white transition-colors">
                        {idea}
                      </span>
                    </button>
                  ))}
                </div>
              </div>
            </div>
          </motion.div>
        </TabsContent>

        {/* ── Preset tab ── */}
        <TabsContent value="preset" className="mt-0">
          <motion.div
            key="preset"
            initial={{ opacity: 0, x: -20 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.2 }}
            className="space-y-3"
          >
            {presets.map((preset, index) => (
              <motion.button
                key={preset.id}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: index * 0.05 }}
                onClick={() => handlePresetSelect(preset.id)}
                className={cn(
                  "w-full text-left p-5 rounded-2xl border transition-all duration-200",
                  state.selectedPreset === preset.id
                    ? "border-[#5a9ab5] bg-[#5a9ab5]/20"
                    : "border-white/20 bg-white/20 hover:border-[#5a9ab5]/50 hover:bg-white/25"
                )}
              >
                <h4 className="text-sm font-medium text-white mb-1">
                  {preset.title}
                </h4>
                <p className="text-sm text-white/50">{preset.description}</p>
              </motion.button>
            ))}
          </motion.div>
        </TabsContent>
      </Tabs>
    </motion.div>
  );
}
