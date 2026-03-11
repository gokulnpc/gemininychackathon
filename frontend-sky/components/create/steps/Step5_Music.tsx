"use client";

import { useState, useRef, useCallback, useEffect } from 'react';
import { Play, Square, Music, Upload, FileAudio, Search, Loader2, X } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useWizard } from '@/context/WizardContext';
import { musicTracks } from '@/data/staticData';
import { motion } from 'framer-motion';
import apiClient from '@/lib/apiClient';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';

interface AssetItem {
  id: string;
  filename: string;
  content_type: string;
  uploaded_at: string;
  size_bytes?: number;
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function Step5_Music() {
  const { state, dispatch } = useWizard();
  const [activeTab, setActiveTab] = useState<'preset' | 'custom'>('preset');

  // Preset music playback
  const [playingTrackId, setPlayingTrackId] = useState<string | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);

  // My Assets dialog
  const [assetDialogOpen, setAssetDialogOpen] = useState(false);
  const [assetSearch, setAssetSearch] = useState('');
  const [musicAssets, setMusicAssets] = useState<AssetItem[]>([]);
  const [assetUrls, setAssetUrls] = useState<Record<string, string>>({});
  const [assetsFetched, setAssetsFetched] = useState(false);
  const [assetsLoading, setAssetsLoading] = useState(false);
  const [previewingId, setPreviewingId] = useState<string | null>(null);
  const [playingAssetId, setPlayingAssetId] = useState<string | null>(null);
  const assetAudioRef = useRef<HTMLAudioElement | null>(null);

  // Fetch music assets on first dialog open
  useEffect(() => {
    if (!assetDialogOpen || assetsFetched) return;
    setAssetsLoading(true);
    apiClient
      .get('/api/v1/assets?category=music')
      .then((r) => {
        const list: AssetItem[] = r.data.assets ?? [];
        setMusicAssets(list);
        setAssetsFetched(true);
        return list;
      })
      .then((list) => {
        if (!list.length) return;
        Promise.all(
          list.map((a) =>
            apiClient
              .get(`/api/v1/assets/${a.id}/url?category=music`)
              .then((r) => [a.id, r.data.url] as [string, string])
              .catch(() => [a.id, ''] as [string, string])
          )
        ).then((entries) => setAssetUrls(Object.fromEntries(entries)));
      })
      .catch(() => {
        setMusicAssets([]);
        setAssetsFetched(true);
      })
      .finally(() => setAssetsLoading(false));
  }, [assetDialogOpen, assetsFetched]);

  const filteredAssets = musicAssets.filter((a) =>
    a.filename.toLowerCase().includes(assetSearch.toLowerCase())
  );

  // ── Preset playback ────────────────────────────────────────────────────────
  const handleMusicSelect = (musicId: string) => {
    dispatch({ type: 'SET_SELECTED_MUSIC', payload: musicId });
  };

  const handlePlayToggle = useCallback((e: React.MouseEvent, trackId: string, audioFile: string) => {
    e.stopPropagation();
    if (playingTrackId === trackId) {
      audioRef.current?.pause();
      audioRef.current = null;
      setPlayingTrackId(null);
    } else {
      audioRef.current?.pause();
      const audio = new Audio(audioFile);
      audio.onended = () => { setPlayingTrackId(null); audioRef.current = null; };
      audio.play();
      audioRef.current = audio;
      setPlayingTrackId(trackId);
    }
  }, [playingTrackId]);

  // ── Asset playback ─────────────────────────────────────────────────────────
  const handleAssetPreview = async (e: React.MouseEvent, asset: AssetItem) => {
    e.stopPropagation();
    if (playingAssetId === asset.id) {
      assetAudioRef.current?.pause();
      assetAudioRef.current = null;
      setPlayingAssetId(null);
      return;
    }
    assetAudioRef.current?.pause();
    assetAudioRef.current = null;
    setPlayingAssetId(null);
    const url = assetUrls[asset.id];
    if (!url) return;
    setPreviewingId(asset.id);
    try {
      const audio = new Audio(url);
      audio.onended = () => { setPlayingAssetId(null); assetAudioRef.current = null; };
      await audio.play();
      assetAudioRef.current = audio;
      setPlayingAssetId(asset.id);
    } catch {
      console.error('Asset audio preview failed');
    } finally {
      setPreviewingId(null);
    }
  };

  const handleAssetSelect = (asset: AssetItem) => {
    dispatch({ type: 'SET_CUSTOM_MUSIC_ASSET', payload: { id: asset.id, filename: asset.filename } });
    assetAudioRef.current?.pause();
    assetAudioRef.current = null;
    setPlayingAssetId(null);
    setAssetDialogOpen(false);
    setAssetSearch('');
  };

  const clearCustomMusic = () => {
    dispatch({ type: 'SET_CUSTOM_MUSIC_ASSET', payload: null });
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -20 }}
      transition={{ duration: 0.3 }}
    >
      {/* Tabs */}
      <div className="flex items-center gap-6 mb-6 border-b border-white/10">
        <button
          onClick={() => setActiveTab('preset')}
          className={cn(
            'flex items-center gap-2 pb-3 text-sm font-medium border-b-2 transition-all duration-200',
            activeTab === 'preset'
              ? 'border-[#5a9ab5] text-[#5a9ab5]'
              : 'border-transparent text-white/50 hover:text-white'
          )}
        >
          <Music className="w-4 h-4" />
          Preset music
        </button>
        <button
          onClick={() => setActiveTab('custom')}
          className={cn(
            'flex items-center gap-2 pb-3 text-sm font-medium border-b-2 transition-all duration-200',
            activeTab === 'custom'
              ? 'border-[#5a9ab5] text-[#5a9ab5]'
              : 'border-transparent text-white/50 hover:text-white'
          )}
        >
          <Upload className="w-4 h-4" />
          Custom
        </button>
      </div>

      {/* Preset Music List */}
      {activeTab === 'preset' && (
        <div className="space-y-3">
          {musicTracks.map((track, index) => {
            const isPlaying = playingTrackId === track.id;
            return (
              <motion.button
                key={track.id}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: index * 0.05 }}
                onClick={() => handleMusicSelect(track.id)}
                className={cn(
                  'w-full flex items-center justify-between p-4 rounded-2xl border transition-all duration-200',
                  state.selectedMusic === track.id
                    ? 'border-[#5a9ab5] bg-[#5a9ab5]/20'
                    : 'border-white/20 bg-white/20 hover:border-[#5a9ab5]/40 hover:bg-white/25'
                )}
              >
                <div className="flex items-center gap-4">
                  <div
                    className="w-12 h-12 rounded-xl flex items-center justify-center shrink-0"
                    style={{
                      backgroundColor:
                        track.id === 'happy-rhythm' ? 'rgba(235, 169, 161, 0.5)' :
                        track.id === 'quiet-before-storm' ? 'rgba(163, 228, 250, 0.5)' :
                        track.id === 'peaceful-vibes' ? 'rgba(245, 219, 233, 0.5)' :
                        track.id === 'brilliant-symphony' ? 'rgba(113, 143, 168, 0.5)' :
                        track.id === 'breathing-shadows' ? 'rgba(191, 191, 186, 0.5)' :
                        'rgba(255, 255, 255, 0.1)',
                    }}
                  >
                    <Music className="w-5 h-5 text-white" />
                  </div>
                  <div className="text-left">
                    <h4 className="text-sm font-medium text-white">{track.title}</h4>
                    <p className="text-sm text-white/50 mt-0.5">{track.description}</p>
                  </div>
                </div>
                {track.audioFile ? (
                  <motion.div
                    whileHover={{ scale: 1.1 }}
                    whileTap={{ scale: 0.95 }}
                    onClick={(e) => handlePlayToggle(e, track.id, track.audioFile!)}
                    className={cn(
                      'w-10 h-10 rounded-full flex items-center justify-center transition-colors',
                      isPlaying
                        ? 'bg-[#5a9ab5] text-white'
                        : 'bg-white/10 border border-white/20 hover:bg-white/20 text-white/60'
                    )}
                  >
                    {isPlaying ? (
                      <Square className="w-3.5 h-3.5 fill-current" />
                    ) : (
                      <Play className="w-4 h-4 ml-0.5" />
                    )}
                  </motion.div>
                ) : (
                  <span className="text-xs font-medium text-[#5a9ab5] bg-[#5a9ab5]/20 px-2 py-1 rounded-full border border-[#5a9ab5]/30">
                    ✨ AI
                  </span>
                )}
              </motion.button>
            );
          })}
        </div>
      )}

      {/* Custom Tab */}
      {activeTab === 'custom' && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="bg-white/20 rounded-2xl border border-white/20 p-10 text-center"
        >
          {state.customMusicAssetId ? (
            /* Selected asset display */
            <div className="flex flex-col items-center gap-4">
              <div className="w-16 h-16 rounded-full bg-[#5a9ab5]/20 flex items-center justify-center">
                <FileAudio className="w-7 h-7 text-[#5a9ab5]" />
              </div>
              <div>
                <p className="text-white text-sm font-medium truncate max-w-xs">
                  {state.customMusicFilename}
                </p>
                <p className="text-white/40 text-xs mt-1">Custom track selected</p>
              </div>
              <div className="flex items-center gap-3">
                <button
                  onClick={() => setAssetDialogOpen(true)}
                  className="px-5 py-2 rounded-full border border-white/20 text-sm font-medium text-white hover:bg-white/10 transition-colors"
                >
                  Change
                </button>
                <button
                  onClick={clearCustomMusic}
                  className="px-5 py-2 rounded-full border border-white/10 text-sm font-medium text-white/50 hover:bg-white/10 hover:text-white transition-colors"
                >
                  Clear
                </button>
              </div>
            </div>
          ) : (
            /* Empty state */
            <>
              <div className="w-16 h-16 rounded-full bg-[#5a9ab5]/20 flex items-center justify-center mx-auto mb-4">
                <Upload className="w-7 h-7 text-[#5a9ab5]" />
              </div>
              <p className="text-white/50 text-sm mb-6">
                Upload your own background music or choose from My Assets
              </p>
              <div className="flex items-center justify-center gap-3">
                <button className="px-6 py-3 rounded-full border border-white/20 text-sm font-medium text-white hover:bg-white/10 transition-colors">
                  Choose File
                </button>
                <span className="text-white/20 text-xs">or</span>
                <button
                  onClick={() => setAssetDialogOpen(true)}
                  className="flex items-center gap-2 px-6 py-3 rounded-full border border-white/20 text-sm font-medium text-white hover:bg-white/10 transition-colors"
                >
                  <FileAudio className="w-4 h-4" />
                  My Assets
                </button>
              </div>
            </>
          )}
        </motion.div>
      )}

      {/* My Assets Dialog */}
      <Dialog
        open={assetDialogOpen}
        onOpenChange={(open) => {
          setAssetDialogOpen(open);
          if (!open) {
            setAssetSearch('');
            assetAudioRef.current?.pause();
            assetAudioRef.current = null;
            setPlayingAssetId(null);
          }
        }}
      >
        <DialogContent className="max-w-xl bg-[#2B2B2B] border-white/10 text-white">
          <DialogHeader>
            <DialogTitle className="text-white">Select from My Assets</DialogTitle>
          </DialogHeader>

          {/* Search */}
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-white/40" />
            <Input
              placeholder="Search by filename…"
              value={assetSearch}
              onChange={(e) => setAssetSearch(e.target.value)}
              className="pl-9 bg-[#333333] border-white/10 text-white placeholder:text-white/40 focus-visible:ring-[#5a9ab5]"
            />
          </div>

          {/* List */}
          <div className="overflow-y-auto max-h-96 space-y-2 pr-1 mt-1">
            {assetsLoading ? (
              <div className="flex items-center justify-center py-16">
                <Loader2 className="w-6 h-6 animate-spin text-[#5a9ab5]" />
              </div>
            ) : filteredAssets.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-16 gap-3">
                <FileAudio className="w-10 h-10 text-white/20" />
                <p className="text-sm text-white/40 text-center">
                  {musicAssets.length === 0
                    ? 'No music files in My Assets yet.'
                    : 'No files match your search.'}
                </p>
              </div>
            ) : (
              filteredAssets.map((asset) => {
                const isPlaying = playingAssetId === asset.id;
                const isPreviewing = previewingId === asset.id;
                return (
                  <button
                    key={asset.id}
                    onClick={() => handleAssetSelect(asset)}
                    className={cn(
                      'w-full flex items-center gap-3 p-3 rounded-xl border transition-all duration-200 text-left',
                      state.customMusicAssetId === asset.id
                        ? 'border-[#5a9ab5] bg-[#5a9ab5]/10'
                        : 'border-white/10 bg-[#333333] hover:border-[#5a9ab5]/40 hover:bg-white/10'
                    )}
                  >
                    <div className="w-9 h-9 rounded-lg bg-[#5a9ab5]/20 flex items-center justify-center shrink-0">
                      <FileAudio className="w-4 h-4 text-[#5a9ab5]" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium text-white truncate">{asset.filename}</p>
                      {asset.size_bytes != null && (
                        <p className="text-xs text-white/40">{formatBytes(asset.size_bytes)}</p>
                      )}
                    </div>
                    {/* Play/pause preview */}
                    <div
                      onClick={(e) => handleAssetPreview(e, asset)}
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
                    {state.customMusicAssetId === asset.id && (
                      <X className="w-4 h-4 text-[#5a9ab5] shrink-0" />
                    )}
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
