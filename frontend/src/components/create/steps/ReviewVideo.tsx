"use client";

import { Play, Download, ArrowRight, Sparkles } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { scenes } from '@/data/staticData';
import { motion } from 'framer-motion';
import { cn } from '@/lib/utils';

export function ReviewVideo() {
  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -20 }}
      transition={{ duration: 0.3 }}
      className="flex gap-6"
    >
      {/* Left Column - Video Player & Timeline */}
      <div className="flex-1">
        {/* Status Badge */}
        <div className="mb-4">
          <Badge variant="secondary" className="bg-green-100 text-green-600 hover:bg-green-100 px-3 py-1">
            <span className="w-2 h-2 rounded-full bg-green-500 mr-2" />
            Ready
          </Badge>
        </div>

        {/* Video Player */}
        <div className="relative bg-gradient-to-br from-pink-100 to-purple-100 rounded-2xl aspect-video flex items-center justify-center mb-4">
          <motion.button
            whileHover={{ scale: 1.1 }}
            whileTap={{ scale: 0.95 }}
            className="w-16 h-16 rounded-full bg-white/90 flex items-center justify-center shadow-lg"
          >
            <Play className="w-6 h-6 text-[#1A1A1A] ml-1" />
          </motion.button>
          <div className="absolute bottom-4 left-1/2 -translate-x-1/2 text-sm text-[#6B6B6B]">
            1080p · 9:16 · 60s
          </div>
        </div>

        {/* Progress Bar */}
        <div className="flex items-center gap-4 mb-6">
          <button className="w-8 h-8 rounded-full bg-white border border-[#E8E0DC] flex items-center justify-center hover:bg-gray-50">
            <Play className="w-4 h-4 text-[#6B6B6B] ml-0.5" />
          </button>
          <div className="flex-1 h-1 bg-gray-200 rounded-full overflow-hidden">
            <div className="w-1/3 h-full bg-[#1A1A1A] rounded-full" />
          </div>
          <span className="text-sm text-[#6B6B6B]">0:20 / 1:00</span>
        </div>

        {/* Scene Timeline */}
        <div className="bg-white rounded-2xl border border-[#E8E0DC] p-5">
          <h3 className="text-sm font-semibold text-[#1A1A1A] mb-4">Scene Timeline</h3>
          <div className="space-y-3">
            {scenes.map((scene, index) => (
              <motion.div
                key={scene.id}
                initial={{ opacity: 0, x: -10 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: index * 0.05 }}
                className={cn(
                  'flex items-start gap-3 p-3 rounded-xl transition-all duration-200',
                  index === 0 ? 'bg-gray-100' : 'hover:bg-gray-50'
                )}
              >
                <div
                  className={cn(
                    'w-6 h-6 rounded-full flex items-center justify-center text-xs font-medium flex-shrink-0',
                    index === 0 ? 'bg-[#1A1A1A] text-white' : 'bg-gray-200 text-[#6B6B6B]'
                  )}
                >
                  {scene.id}
                </div>
                <div className="flex-1">
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-medium text-[#1A1A1A]">{scene.title}</span>
                    <span className="text-xs text-[#9B9B9B]">{scene.timestamp}</span>
                  </div>
                  <p className="text-sm text-[#6B6B6B] mt-0.5">{scene.description}</p>
                </div>
              </motion.div>
            ))}
          </div>
        </div>
      </div>

      {/* Right Column - AI Improvements, Settings, Stats */}
      <div className="w-[320px] space-y-4">
        {/* Action Buttons */}
        <div className="flex gap-3">
          <Button
            variant="outline"
            className="flex-1 rounded-full border-[#E8E0DC] hover:bg-[#FDF6F3]"
          >
            <Download className="w-4 h-4 mr-2" />
            Download
          </Button>
          <Button className="flex-1 rounded-full bg-[#1A1A1A] hover:bg-[#1A1A1A]/90 text-white">
            Publish
            <ArrowRight className="w-4 h-4 ml-2" />
          </Button>
        </div>

        {/* AI Improvements */}
        <div className="bg-white rounded-2xl border border-[#E8E0DC] p-5">
          <div className="flex items-center gap-2 mb-4">
            <Sparkles className="w-4 h-4 text-[#B08D9F]" />
            <h3 className="text-sm font-semibold text-[#1A1A1A]">AI Improvements</h3>
          </div>
          <div className="space-y-2">
            {[
              'Make the hook more energetic',
              'Add more emotion to the narration',
              'Shorten to 30 seconds',
              'Change to a professional tone',
            ].map((improvement, index) => (
              <button
                key={index}
                className="w-full text-left p-3 rounded-xl border border-[#E8E0DC] text-sm text-[#1A1A1A] hover:border-[#B08D9F]/30 hover:bg-[#B08D9F]/5 transition-all duration-200"
              >
                {improvement}
              </button>
            ))}
          </div>
        </div>

        {/* Settings */}
        <div className="bg-white rounded-2xl border border-[#E8E0DC] p-5">
          <h3 className="text-sm font-semibold text-[#1A1A1A] mb-4">Settings</h3>
          <div className="space-y-4">
            <div>
              <label className="block text-xs text-[#9B9B9B] mb-2">Format</label>
              <select className="w-full p-3 rounded-xl border border-[#E8E0DC] bg-white text-sm text-[#1A1A1A] focus:outline-none focus:ring-2 focus:ring-[#B08D9F]/20 focus:border-[#B08D9F]">
                <option>Select format</option>
              </select>
            </div>
            <div>
              <label className="block text-xs text-[#9B9B9B] mb-2">Quality</label>
              <select className="w-full p-3 rounded-xl border border-[#E8E0DC] bg-white text-sm text-[#1A1A1A] focus:outline-none focus:ring-2 focus:ring-[#B08D9F]/20 focus:border-[#B08D9F]">
                <option>Select quality</option>
              </select>
            </div>
          </div>
        </div>

        {/* Generation Stats */}
        <div className="bg-white rounded-2xl border border-[#E8E0DC] p-5">
          <h3 className="text-sm font-semibold text-[#1A1A1A] mb-4">Generation Stats</h3>
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-sm text-[#6B6B6B]">Processing Time</span>
              <span className="text-sm font-medium text-[#1A1A1A]">58 seconds</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-sm text-[#6B6B6B]">AI Models Used</span>
              <span className="text-sm font-medium text-[#1A1A1A]">3</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-sm text-[#6B6B6B]">Scenes Generated</span>
              <span className="text-sm font-medium text-[#1A1A1A]">4</span>
            </div>
          </div>
        </div>
      </div>
    </motion.div>
  );
}
