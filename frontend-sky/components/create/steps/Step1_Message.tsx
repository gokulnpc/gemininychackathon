"use client";

import { useRef, useState, useEffect } from "react";
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
  Trash2,
  FileText,
  Mic,
  Search,
  Square,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useWizard } from "@/context/WizardContext";
import { presets } from "@/data/staticData";
import { motion, AnimatePresence } from "framer-motion";
import { AudioVisualizer } from "@/components/AudioVisualizer";
import { Play, RotateCcw, Pause } from "lucide-react";
import apiClient from "@/lib/apiClient";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";

interface AssetItem {
  id: string;
  filename: string;
  content_type: string;
  uploaded_at: string;
  size_bytes?: number;
}

function formatAssetBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

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
  const [isPlaying, setIsPlaying] = useState(false);
  const [playbackProgress, setPlaybackProgress] = useState(0);
  const [audioDuration, setAudioDuration] = useState(0);

  const fileInputRef = useRef<HTMLInputElement>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioPlayerRef = useRef<HTMLAudioElement | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  
  // My Assets — voice memos dialog
  const [voiceDialogOpen, setVoiceDialogOpen] = useState(false);
  const [voiceSearch, setVoiceSearch] = useState('');
  const [voiceAssets, setVoiceAssets] = useState<AssetItem[]>([]);
  const [voiceAssetUrls, setVoiceAssetUrls] = useState<Record<string, string>>({});
  const [voiceAssetsFetched, setVoiceAssetsFetched] = useState(false);
  const [voiceAssetsLoading, setVoiceAssetsLoading] = useState(false);
  const [voicePreviewingId, setVoicePreviewingId] = useState<string | null>(null);
  const [voicePlayingId, setVoicePlayingId] = useState<string | null>(null);
  const voiceAssetAudioRef = useRef<HTMLAudioElement | null>(null);

  // WebSocket and Audio processing refs
  const wsRef = useRef<WebSocket | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const processorRef = useRef<ScriptProcessorNode | null>(null);

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

  // ── Voice memo assets ───────────────────────────────────────────────────────

  useEffect(() => {
    if (!voiceDialogOpen || voiceAssetsFetched) return;
    setVoiceAssetsLoading(true);
    apiClient
      .get('/api/v1/assets?category=voice_memos')
      .then((r) => {
        const list: AssetItem[] = r.data.assets ?? [];
        setVoiceAssets(list);
        setVoiceAssetsFetched(true);
        return list;
      })
      .then((list) => {
        if (!list.length) return;
        Promise.all(
          list.map((a) =>
            apiClient
              .get(`/api/v1/assets/${a.id}/url?category=voice_memos`)
              .then((r) => [a.id, r.data.url] as [string, string])
              .catch(() => [a.id, ''] as [string, string])
          )
        ).then((entries) => setVoiceAssetUrls(Object.fromEntries(entries)));
      })
      .catch(() => { setVoiceAssets([]); setVoiceAssetsFetched(true); })
      .finally(() => setVoiceAssetsLoading(false));
  }, [voiceDialogOpen, voiceAssetsFetched]);

  const filteredVoiceAssets = voiceAssets.filter((a) =>
    a.filename.toLowerCase().includes(voiceSearch.toLowerCase())
  );

  const handleVoiceAssetPreview = async (e: React.MouseEvent, asset: AssetItem) => {
    e.stopPropagation();
    if (voicePlayingId === asset.id) {
      voiceAssetAudioRef.current?.pause();
      voiceAssetAudioRef.current = null;
      setVoicePlayingId(null);
      return;
    }
    voiceAssetAudioRef.current?.pause();
    voiceAssetAudioRef.current = null;
    setVoicePlayingId(null);
    const url = voiceAssetUrls[asset.id];
    if (!url) return;
    setVoicePreviewingId(asset.id);
    try {
      const audio = new Audio(url);
      audio.onended = () => { setVoicePlayingId(null); voiceAssetAudioRef.current = null; };
      await audio.play();
      voiceAssetAudioRef.current = audio;
      setVoicePlayingId(asset.id);
    } catch {
      console.error('Voice asset preview failed');
    } finally {
      setVoicePreviewingId(null);
    }
  };

  const handleVoiceAssetSelect = async (asset: AssetItem) => {
    const url = voiceAssetUrls[asset.id];
    if (!url) return;
    voiceAssetAudioRef.current?.pause();
    voiceAssetAudioRef.current = null;
    setVoicePlayingId(null);

    try {
      const blob = await fetch(url).then((r) => r.blob());
      const ext = asset.filename.split('.').pop()?.toLowerCase() ?? 'mp3';
      setAudioUrl(URL.createObjectURL(blob));
      setUploadedFileName(asset.filename);
      const reader = new FileReader();
      reader.onloadend = () => {
        const b64 = (reader.result as string).split(',')[1];
        dispatch({ type: 'SET_AUDIO_BASE64', payload: b64 });
        dispatch({ type: 'SET_AUDIO_FORMAT', payload: ext });
        setAudioReady(true);
        setVoiceDialogOpen(false);
        setVoiceSearch('');
        runTranscribe(b64, ext);
      };
      reader.readAsDataURL(blob);
    } catch {
      console.error('Failed to load voice asset');
    }
  };

  // ── Transcription ──────────────────────────────────────────────────────────

  const runTranscribe = async (b64: string, format: string) => {
    setTranscribing(true);
    setTranscript(null);
    try {
      const data = await apiClient.post("/api/v1/transcribe", {
        audio_base64: b64,
        audio_format: format,
        language: "en",
      }).then(r => r.data);
      setTranscript(data.transcript ?? null);
      if (data.transcript) {
        dispatch({ type: "SET_MESSAGE_TEXT", payload: data.transcript });
      }
    } catch {
      // fallback strictly if it errors out
      setTranscript("Transcription failed or no speech detected.");
    } finally {
      setTranscribing(false);
    }
  };

  const togglePlayback = () => {
    if (!audioPlayerRef.current) return;
    if (isPlaying) {
      audioPlayerRef.current.pause();
    } else {
      audioPlayerRef.current.play();
    }
    setIsPlaying(!isPlaying);
  };

  const handleTimeUpdate = () => {
    if (!audioPlayerRef.current) return;
    setPlaybackProgress(audioPlayerRef.current.currentTime);
  };

  const handleLoadedMetadata = () => {
    if (!audioPlayerRef.current) return;
    setAudioDuration(audioPlayerRef.current.duration);
  };

  const handleEnded = () => {
    setIsPlaying(false);
    setPlaybackProgress(0);
  };

  const resetRecording = () => {
    setAudioReady(false);
    setAudioUrl(null);
    setTranscript(null);
    setUploadedFileName(null);
  };

  const formatTime = (time: number) => {
    if (!isFinite(time)) return "0:00";
    const minutes = Math.floor(time / 60);
    const seconds = Math.floor(time % 60);
    return `${minutes}:${seconds.toString().padStart(2, '0')}`;
  };

  // ── Highlight logic ────────────────────────────────────────────────────────
  // Rough estimation of word highlighting based on playback progress.
  const renderHighlightedText = (text: string | null, currentTime: number, duration: number) => {
    if (!text || duration === 0) return null;
    const words = text.split(" ");
    const wordDuration = duration / words.length;
    
    return words.map((word, index) => {
      const isHighlighted = currentTime >= index * wordDuration && currentTime < (index + 1) * wordDuration;
      const isPast = currentTime > (index + 1) * wordDuration;
      
      return (
        <span
          key={index}
          className={cn(
            "transition-colors duration-200",
            isHighlighted ? "bg-[#9A7A76] rounded px-0.5 text-white" : "",
            isPast ? "text-white" : "text-white/60"
          )}
        >
          {word}{" "}
        </span>
      );
    });
  };

  // ── Audio recording ────────────────────────────────────────────────────────

  const startRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;

      // Ensure 16kHz sample rate for Gemini live streaming
      const audioContext = new (window.AudioContext || (window as any).webkitAudioContext)({ sampleRate: 16000 });
      audioContextRef.current = audioContext;

      // In parallel, record the file locally for playback using MediaRecorder
      const recorder = new MediaRecorder(stream, { mimeType: "audio/webm" });
      chunksRef.current = [];
      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data);
      };
      recorder.onstop = () => {
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
        };
        reader.readAsDataURL(blob);
      };
      mediaRecorderRef.current = recorder;
      recorder.start();

      const source = audioContext.createMediaStreamSource(stream);
      // 4096 frames = ~250ms chunks at 16kHz
      const processor = audioContext.createScriptProcessor(4096, 1, 1);
      processorRef.current = processor;

      // Connect WebSocket
      const wsUrl = `${API.replace(/^http/, "ws")}/api/v1/transcribe/ws`;
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onmessage = (event) => {
        const msg = JSON.parse(event.data);
        if (msg.type === "transcript_chunk") {
          setTranscribing(true); // just to show it's working
          setTranscript(msg.text);
        } else if (msg.type === "complete") {
          setTranscript(msg.transcript);
          if (msg.transcript) {
            dispatch({ type: "SET_MESSAGE_TEXT", payload: msg.transcript });
          }
          setTranscribing(false);
          setAudioReady(true);
        } else if (msg.type === "error") {
          console.error("Transcription WS error:", msg.message);
          setTranscript("Error during live transcription.");
          setTranscribing(false);
        }
      };

      ws.onopen = () => {
        setIsRecording(true);
        setAudioReady(false);
        setTranscript(null);
        setTranscribing(true); // Actively listening

        processor.onaudioprocess = (e) => {
          if (ws.readyState !== WebSocket.OPEN) return;
          const inputData = e.inputBuffer.getChannelData(0);
          
          // Convert Float32 to Int16 and send as raw binary (same as live-voice protocol)
          const pcmData = new Int16Array(inputData.length);
          for (let i = 0; i < inputData.length; i++) {
             const s = Math.max(-1, Math.min(1, inputData[i]));
             pcmData[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
          }
          ws.send(pcmData.buffer);
        };

        source.connect(processor);
        processor.connect(audioContext.destination);
      };

    } catch (err) {
      console.error(err);
      alert("Microphone access denied. Please allow microphone access and try again.");
    }
  };

  const stopRecording = () => {
    setIsRecording(false);
    
    // Stop local MediaRecorder so it saves the audioUrl
    mediaRecorderRef.current?.stop();
    
    // Stop audio tracks
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop());
    }
    
    // Disconnect live audio WS nodes
    if (processorRef.current && audioContextRef.current) {
      processorRef.current.disconnect();
      audioContextRef.current.close();
    }
    
    // Tell socket we're done sending audio so Gemini can finalize
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: "done" }));
    }
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
  const [ocrFileSize, setOcrFileSize] = useState<number | null>(null);
  const [ocrProgress, setOcrProgress] = useState(0);

  const formatFileSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes}B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)}KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)}MB`;
  };

  const handleTextFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    e.target.value = "";

    if (file.type === "application/pdf" || file.name.toLowerCase().endsWith(".pdf")) {
      // PDF → Mistral Document AI OCR
      setOcrFileName(file.name);
      setOcrFileSize(file.size);
      setOcrLoading(true);
      setOcrProgress(10);
      const reader = new FileReader();
      reader.onloadend = async () => {
        try {
          setOcrProgress(30);
          const b64 = (reader.result as string).split(",")[1];
          const data = await apiClient.post("/api/v1/ocr-pdf", { pdf_base64: b64 }).then(r => r.data);
          setOcrProgress(80);
          dispatch({ type: "SET_MESSAGE_TEXT", payload: data.text ?? "" });
          setOcrProgress(100);
        } catch {
          setOcrFileName(null);
          setOcrFileSize(null);
          setOcrProgress(0);
        } finally {
          setOcrLoading(false);
        }
      };
      reader.readAsDataURL(file);
    } else {
      // Plain text / markdown / rtf — read directly
      setOcrFileName(file.name);
      setOcrFileSize(file.size);
      setOcrProgress(100);
      setOcrLoading(false);
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

  const removeUploadedFile = () => {
    setOcrFileName(null);
    setOcrFileSize(null);
    setOcrProgress(0);
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
                      <motion.div
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        transition={{ delay: 0.5 }}
                        className="text-white/70 text-sm mt-6 font-medium text-center flex flex-col items-center"
                      >
                        Listening…
                        {transcript && (
                          <div className="mt-4 p-4 rounded-xl bg-black/20 text-white/90 text-left max-w-lg w-full">
                            {transcript}
                          </div>
                        )}
                      </motion.div>
                    </motion.div>
                  ) : audioReady ? (
                    <motion.div
                      key="ready"
                      initial={{ opacity: 0, scale: 0.9 }}
                      animate={{ opacity: 1, scale: 1 }}
                      exit={{ opacity: 0, scale: 0.9 }}
                      className="w-full text-left bg-[#404040] rounded-[24px] p-8 relative flex flex-col justify-between"
                      style={{ minHeight: "260px" }}
                    >
                      {audioUrl && (
                        <audio
                          ref={audioPlayerRef}
                          src={audioUrl}
                          onTimeUpdate={handleTimeUpdate}
                          onLoadedMetadata={handleLoadedMetadata}
                          onEnded={handleEnded}
                          className="hidden"
                        />
                      )}

                      {transcribing ? (
                        <div className="flex-1 flex items-center justify-center">
                          <span className="text-sm font-medium text-white/50">
                            Transcribing...
                          </span>
                        </div>
                      ) : (
                        <>
                          <div className="flex-1 mb-8 text-base text-white/80 leading-relaxed font-light">
                            {transcript ? (
                              <span className="text-white bg-[#9A7A76] rounded px-0.5">{transcript}</span>
                            ) : "No transcript available."}
                          </div>

                          <div className="flex items-center justify-between">
                            <div className="flex items-center gap-4">
                              <button
                                onClick={togglePlayback}
                                className="w-12 h-12 rounded-full border border-white/30 flex items-center justify-center bg-transparent hover:bg-white/5 transition-colors"
                              >
                                {isPlaying ? (
                                  <Pause className="w-5 h-5 text-white" />
                                ) : (
                                  <Play className="w-5 h-5 text-white ml-1" />
                                )}
                              </button>
                              <span className="text-sm text-white/50 font-medium">
                                {formatTime(playbackProgress)} / {formatTime(audioDuration)}
                              </span>
                            </div>

                            <div className="flex items-center gap-4">
                              <Button
                                variant="outline"
                                onClick={resetRecording}
                                className="rounded-full px-6 py-5 bg-[#3B3B3B] text-white border-white/20 hover:bg-white/20 hover:border-white/40"
                              >
                                Restart Recording
                              </Button>
                              <span className="text-sm text-white/40">or</span>
                              <Button
                                variant="outline"
                                onClick={() => fileInputRef.current?.click()}
                                className="rounded-full px-6 py-5 bg-[#3B3B3B] text-white border-white/20 hover:bg-white/20 hover:border-white/40 flex items-center"
                              >
                                <Upload className="w-4 h-4 mr-2 text-white/70" />
                                Upload Audio
                              </Button>
                            </div>
                          </div>
                        </>
                      )}
                    </motion.div>
                    // Intentionally replaced by playback wrapper component
                    // (Audio player replaced above)
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
                  {!audioReady && (
                    isRecording ? (
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
                          Start Recording
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
                        <span className="text-white/40 text-sm">or</span>
                        <Button
                          variant="outline"
                          className="rounded-full px-6 py-5 bg-white/10 text-white border-white/30 hover:bg-white/20"
                          onClick={() => setVoiceDialogOpen(true)}
                        >
                          <Mic className="w-4 h-4 mr-2" />
                          My Assets
                        </Button>
                      </>
                    )
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
              Type or upload your idea
            </h3>
            <div className="space-y-4">
              {/* Textarea card with upload button inside */}
              <div className="rounded-2xl border border-white/20 bg-white/10 overflow-hidden">
                <textarea
                  value={state.messageText}
                  onChange={(e) =>
                    dispatch({
                      type: "SET_MESSAGE_TEXT",
                      payload: e.target.value,
                    })
                  }
                  placeholder="E.g, a video showcasing the marketing campaign for a vegan-friendly skincare product"
                  className="w-full min-h-[140px] p-5 pb-2 bg-transparent text-white placeholder:text-white/30 resize-none focus:outline-none transition-all duration-200 text-[15px] leading-relaxed"
                />
                <div className="flex justify-end px-5 pb-4">
                  <input
                    type="file"
                    accept=".txt,.md,.rtf,.pdf"
                    className="hidden"
                    ref={textFileInputRef}
                    onChange={handleTextFileUpload}
                  />
                  <button
                    disabled={ocrLoading}
                    onClick={() => textFileInputRef.current?.click()}
                    className="flex items-center gap-2 text-white/70 text-sm font-medium px-4 py-2 rounded-full border border-white/20 hover:bg-white/10 hover:border-white/30 transition-all disabled:opacity-50"
                  >
                    <Upload className="w-4 h-4" />
                    {ocrFileName ? "Reupload Message" : "Upload Message"}
                  </button>
                </div>
              </div>

              {/* File upload indicator */}
              <AnimatePresence>
                {ocrFileName && (
                  <motion.div
                    initial={{ opacity: 0, y: -8 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -8 }}
                    transition={{ duration: 0.2 }}
                    className="rounded-2xl border border-white/20 bg-white/10 px-5 py-4"
                  >
                    <div className="flex items-center gap-4">
                      {/* File icon */}
                      <div className="w-10 h-10 rounded-lg bg-[#e84c1e]/15 flex items-center justify-center shrink-0">
                        <FileText className="w-5 h-5 text-[#e84c1e]" />
                      </div>

                      {/* File info + progress */}
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium text-white truncate">
                          {ocrFileName}
                        </p>
                        <p className="text-xs text-white/40 mt-0.5">
                          {ocrFileSize ? formatFileSize(ocrFileSize) : ""}{ocrFileSize ? " - " : ""}
                          {ocrLoading
                            ? `${ocrProgress}% uploaded`
                            : "100% uploaded"}
                        </p>
                        {ocrLoading && (
                          <div className="mt-2 h-1 w-full bg-white/10 rounded-full overflow-hidden">
                            <motion.div
                              className="h-full bg-[#5a9ab5] rounded-full"
                              initial={{ width: 0 }}
                              animate={{ width: `${ocrProgress}%` }}
                              transition={{ duration: 0.3 }}
                            />
                          </div>
                        )}
                      </div>

                      {/* Status + delete */}
                      <div className="flex items-center gap-3 shrink-0">
                        {ocrLoading ? (
                          <Loader2 className="w-5 h-5 text-[#5a9ab5] animate-spin" />
                        ) : (
                          <CheckCircle2 className="w-5 h-5 text-emerald-400" />
                        )}
                        <button
                          onClick={removeUploadedFile}
                          className="text-white/30 hover:text-white/60 transition-colors"
                        >
                          <Trash2 className="w-5 h-5" />
                        </button>
                      </div>
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>

              {/* Ideas for you */}
              <div className="rounded-2xl border border-white/20 bg-white/10 p-5">
                <h4 className="text-sm font-semibold text-white mb-4">
                  Ideas for you
                </h4>
                <div className="space-y-1">
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
                      className={cn(
                        "w-full flex items-center gap-3 text-left px-4 py-3 rounded-xl transition-all duration-200",
                        state.messageText === idea
                          ? "bg-[#1C1C1E] text-white"
                          : "text-white/50 hover:bg-white/5 hover:text-white/80"
                      )}
                    >
                      <Sparkles className="w-4 h-4 text-[#5a9ab5] shrink-0" />
                      <span className="text-sm leading-relaxed">
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
            className="flex gap-6"
          >
            {/* Left Column: Preset List */}
            <div className="w-1/2 flex flex-col gap-3">
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
                      ? "border-transparent bg-[#1C1C1E]"
                      : "border-white/10 bg-transparent hover:border-white/30 hover:bg-white/5"
                  )}
                >
                  <h4 className="text-sm font-medium text-white mb-1">
                    {preset.title}
                  </h4>
                  <p className="text-sm text-white/50">{preset.description}</p>
                </motion.button>
              ))}
            </div>

            {/* Right Column: Image Preview */}
            <div className="w-1/2 rounded-2xl overflow-hidden relative">
              {presets.find((p) => p.id === (state.selectedPreset || presets[0].id))?.image && (
                <img
                  src={presets.find((p) => p.id === (state.selectedPreset || presets[0].id))?.image}
                  alt="Preset Preview"
                  className="absolute inset-0 w-full h-full object-cover"
                />
              )}
            </div>
          </motion.div>
        </TabsContent>

      </Tabs>

      {/* Voice Memos — My Assets Dialog */}
      <Dialog
        open={voiceDialogOpen}
        onOpenChange={(open) => {
          setVoiceDialogOpen(open);
          if (!open) {
            setVoiceSearch('');
            voiceAssetAudioRef.current?.pause();
            voiceAssetAudioRef.current = null;
            setVoicePlayingId(null);
          }
        }}
      >
        <DialogContent className="max-w-xl bg-[#2B2B2B] border-white/10 text-white">
          <DialogHeader>
            <DialogTitle className="text-white">Select from My Assets</DialogTitle>
          </DialogHeader>

          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-white/40" />
            <Input
              placeholder="Search by filename…"
              value={voiceSearch}
              onChange={(e) => setVoiceSearch(e.target.value)}
              className="pl-9 bg-[#333333] border-white/10 text-white placeholder:text-white/40 focus-visible:ring-[#5a9ab5]"
            />
          </div>

          <div className="overflow-y-auto max-h-96 space-y-2 pr-1 mt-1">
            {voiceAssetsLoading ? (
              <div className="flex items-center justify-center py-16">
                <Loader2 className="w-6 h-6 animate-spin text-[#5a9ab5]" />
              </div>
            ) : filteredVoiceAssets.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-16 gap-3">
                <Mic className="w-10 h-10 text-white/20" />
                <p className="text-sm text-white/40 text-center">
                  {voiceAssets.length === 0
                    ? 'No voice memos in My Assets yet.'
                    : 'No files match your search.'}
                </p>
              </div>
            ) : (
              filteredVoiceAssets.map((asset) => {
                const isPlaying = voicePlayingId === asset.id;
                const isPreviewing = voicePreviewingId === asset.id;
                return (
                  <button
                    key={asset.id}
                    onClick={() => handleVoiceAssetSelect(asset)}
                    className="w-full flex items-center gap-3 p-3 rounded-xl border border-white/10 bg-[#333333] hover:border-[#5a9ab5]/40 hover:bg-white/10 transition-all duration-200 text-left"
                  >
                    <div className="w-9 h-9 rounded-lg bg-[#5a9ab5]/20 flex items-center justify-center shrink-0">
                      <Mic className="w-4 h-4 text-[#5a9ab5]" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium text-white truncate">{asset.filename}</p>
                      {asset.size_bytes != null && (
                        <p className="text-xs text-white/40">{formatAssetBytes(asset.size_bytes)}</p>
                      )}
                    </div>
                    <div
                      onClick={(e) => handleVoiceAssetPreview(e, asset)}
                      className={cn(
                        'w-8 h-8 rounded-full flex items-center justify-center shrink-0 transition-colors',
                        isPlaying
                          ? 'bg-[#5a9ab5] text-white'
                          : 'bg-white/10 border border-white/20 hover:bg-white/20 text-white/60'
                      )}
                    >
                      {isPreviewing ? (
                        <Loader2 className="w-3.5 h-3.5 animate-spin" />
                      ) : isPlaying ? (
                        <Square className="w-3 h-3 fill-current" />
                      ) : (
                        <Play className="w-3.5 h-3.5 ml-0.5" />
                      )}
                    </div>
                  </button>
                );
              })
            )}
          </div>
        </DialogContent>
      </Dialog>
    </motion.div>
  );
}
