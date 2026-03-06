"use client";

import { cn } from '@/lib/utils';
import { useWizard } from '@/context/WizardContext';
import { captionStyles } from '@/data/staticData';
import { motion } from 'framer-motion';

function CaptionPreview({ styleId, preview }: { styleId: string; preview: string }) {
  switch (styleId) {
    case 'bold-stroke':
      return (
        <span
          className="text-2xl font-black uppercase text-white"
          style={{
            WebkitTextStroke: '1.5px black',
            textShadow: '2px 2px 0px rgba(0,0,0,0.8)',
            letterSpacing: '0.05em',
          }}
        >
          {preview}
        </span>
      );

    case 'red-highlight':
      return (
        <span className="text-lg font-bold uppercase text-white">
          <span className="bg-red-600 px-1.5 py-0.5 rounded">{preview.split(' ')[0]}</span>{' '}
          <span>{preview.split(' ').slice(1).join(' ')}</span>
        </span>
      );

    case 'sleek':
      return (
        <span
          className="text-lg font-medium uppercase text-white tracking-widest"
          style={{ fontStyle: 'italic' }}
        >
          {preview}
        </span>
      );

    case 'karaoke':
      return (
        <span className="text-lg font-bold uppercase">
          {preview.split(' ').map((word, i) => (
            <span key={i}>
              {i > 0 && ' '}
              <span className={i === 0 ? 'text-yellow-400' : 'text-white/50'}>{word}</span>
            </span>
          ))}
        </span>
      );

    case 'majestic':
      return (
        <span
          className="text-xl uppercase text-transparent bg-clip-text font-bold"
          style={{
            backgroundImage: 'linear-gradient(180deg, #FFD700 0%, #FFA500 50%, #FFD700 100%)',
            letterSpacing: '0.15em',
            fontFamily: 'Georgia, serif',
          }}
        >
          {preview}
        </span>
      );

    case 'beast':
      return (
        <span
          className="text-2xl font-black uppercase text-white"
          style={{
            textShadow: '0 0 10px rgba(255,0,0,0.7), 0 0 20px rgba(255,0,0,0.4)',
            letterSpacing: '0.1em',
          }}
        >
          {preview}
        </span>
      );

    case 'elegant':
      return (
        <span
          className="text-xl text-white font-light tracking-[0.2em] uppercase"
          style={{ fontFamily: 'Georgia, serif' }}
        >
          {preview}
        </span>
      );

    case 'clarity':
      return (
        <span className="text-lg font-medium lowercase text-gray-300 tracking-wide">
          {preview}
        </span>
      );

    default:
      return <span className="text-lg font-bold text-white">{preview}</span>;
  }
}

export function Step7_Caption() {
  const { state, dispatch } = useWizard();

  const handleCaptionSelect = (captionId: string) => {
    dispatch({ type: 'SET_SELECTED_CAPTION', payload: captionId });
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -20 }}
      transition={{ duration: 0.3 }}
      className="bg-white/20 rounded-2xl border border-white/20 p-6"
    >
      <div className="grid grid-cols-4 gap-4">
        {captionStyles.map((style, index) => (
          <motion.button
            key={style.id}
            initial={{ opacity: 0, scale: 0.9 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ delay: index * 0.03 }}
            onClick={() => handleCaptionSelect(style.id)}
            className="flex flex-col items-center gap-3"
          >
            <div
              className={cn(
                'w-full aspect-[3/2] rounded-xl flex items-center justify-center transition-all duration-200',
                state.selectedCaption === style.id
                  ? 'bg-gray-800 ring-2 ring-[#5a9ab5] ring-offset-2'
                  : 'bg-gray-700 hover:bg-gray-600'
              )}
            >
              <CaptionPreview styleId={style.id} preview={style.preview} />
            </div>
            <span className="text-xs font-medium text-white/60">{style.name}</span>
          </motion.button>
        ))}
      </div>
    </motion.div>
  );
}
