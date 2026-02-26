"use client";

import { useState, useRef, useCallback } from 'react';
import { Play, Square, Music, Upload } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useWizard } from '@/context/WizardContext';
import { musicTracks } from '@/data/staticData';
import { motion } from 'framer-motion';

export function Step3_Music() {
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
      <div className="flex items-center gap-6 mb-6 border-b border-[#E8E0DC]">
        <button
          onClick={() => setActiveTab('preset')}
          className={cn(
            'flex items-center gap-2 pb-3 text-sm font-medium border-b-2 transition-all duration-200',
            activeTab === 'preset'
              ? 'border-[#B08D9F] text-[#B08D9F]'
              : 'border-transparent text-[#6B6B6B] hover:text-[#1A1A1A]'
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
              ? 'border-[#B08D9F] text-[#B08D9F]'
              : 'border-transparent text-[#6B6B6B] hover:text-[#1A1A1A]'
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
                    ? 'border-[#B08D9F] bg-[#B08D9F]/5'
                    : 'border-[#E8E0DC] bg-white hover:border-[#B08D9F]/30'
                )}
              >
                <div className="flex items-center gap-4">
                  <div
                    className="w-12 h-12 rounded-xl flex items-center justify-center flex-shrink-0"
                    style={{ backgroundColor: `${track.iconColor}30` }}
                  >
                    <Music className="w-5 h-5" style={{ color: track.iconColor }} />
                  </div>
                  <div className="text-left">
                    <h4 className="text-sm font-medium text-[#1A1A1A]">{track.title}</h4>
                    <p className="text-sm text-[#6B6B6B] mt-0.5">{track.description}</p>
                  </div>
                </div>
                <motion.div
                  whileHover={{ scale: 1.1 }}
                  whileTap={{ scale: 0.95 }}
                  onClick={(e) => handlePlayToggle(e, track.id, track.audioFile)}
                  className={cn(
                    'w-10 h-10 rounded-full flex items-center justify-center transition-colors',
                    isPlaying
                      ? 'bg-[#B08D9F] text-white'
                      : 'bg-white border border-[#E8E0DC] hover:bg-gray-50 text-[#6B6B6B]'
                  )}
                >
                  {isPlaying ? (
                    <Square className="w-3.5 h-3.5 fill-current" />
                  ) : (
                    <Play className="w-4 h-4 ml-0.5" />
                  )}
                </motion.div>
              </motion.button>
            );
          })}
        </div>
      )}

      {activeTab === 'custom' && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="bg-white rounded-2xl border border-[#E8E0DC] p-10 text-center"
        >
          <div className="w-16 h-16 rounded-full bg-[#B08D9F]/10 flex items-center justify-center mx-auto mb-4">
            <Upload className="w-7 h-7 text-[#B08D9F]" />
          </div>
          <p className="text-[#6B6B6B] text-sm mb-6">
            Upload your own background music
          </p>
          <button className="px-6 py-3 rounded-full border border-[#E8E0DC] text-sm font-medium hover:bg-[#FDF6F3] transition-colors">
            Choose File
          </button>
        </motion.div>
      )}
    </motion.div>
  );
}
