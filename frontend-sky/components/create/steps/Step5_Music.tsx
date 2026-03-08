"use client";

import { useState, useRef, useCallback } from 'react';
import { Play, Square, Music, Upload } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useWizard } from '@/context/WizardContext';
import { musicTracks } from '@/data/staticData';
import { motion } from 'framer-motion';

export function Step5_Music() {
  const { state, dispatch } = useWizard();
  const [activeTab, setActiveTab] = useState<'preset' | 'custom'>('preset');
  const [playingTrackId, setPlayingTrackId] = useState<string | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);

  const handleMusicSelect = (musicId: string) => {
    dispatch({ type: 'SET_SELECTED_MUSIC', payload: musicId });
  };

  const handlePlayToggle = useCallback((e: React.MouseEvent, trackId: string, audioFile: string) => {
    e.stopPropagation();

    if (playingTrackId === trackId) {
      // Stop current track
      audioRef.current?.pause();
      audioRef.current = null;
      setPlayingTrackId(null);
    } else {
      // Stop previous track if playing
      audioRef.current?.pause();

      // Play new track
      const audio = new Audio(audioFile);
      audio.onended = () => {
        setPlayingTrackId(null);
        audioRef.current = null;
      };
      audio.play();
      audioRef.current = audio;
      setPlayingTrackId(trackId);
    }
  }, [playingTrackId]);

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

      {/* Music List */}
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
                        track.id === "happy-rhythm" ? "rgba(235, 169, 161, 0.5)" :
                        track.id === "quiet-before-storm" ? "rgba(163, 228, 250, 0.5)" :
                        track.id === "peaceful-vibes" ? "rgba(245, 219, 233, 0.5)" :
                        track.id === "brilliant-symphony" ? "rgba(113, 143, 168, 0.5)" :
                        track.id === "breathing-shadows" ? "rgba(191, 191, 186, 0.5)" :
                        "rgba(255, 255, 255, 0.1)"
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

      {activeTab === 'custom' && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="bg-white/20 rounded-2xl border border-white/20 p-10 text-center"
        >
          <div className="w-16 h-16 rounded-full bg-[#5a9ab5]/20 flex items-center justify-center mx-auto mb-4">
            <Upload className="w-7 h-7 text-[#5a9ab5]" />
          </div>
          <p className="text-white/50 text-sm mb-6">
            Upload your own background music
          </p>
          <button className="px-6 py-3 rounded-full border border-white/20 text-sm font-medium text-white hover:bg-white/10 transition-colors">
            Choose File
          </button>
        </motion.div>
      )}
    </motion.div>
  );
}
