"use client";

import React from "react";
import Link from "next/link";
import { MoveRight } from "lucide-react";
import TextReveal from "./TextReveal";

const items = [
  {
    title: "VOICE → VIDEO",
    desc: "Record your idea. We handle the rest.",
    pill: "🎙 Voice Memo",
    img: "https://hoirqrkdgbmvpwutwuwj.supabase.co/storage/v1/object/public/assets/assets/4734259a-bad7-422f-981e-ce01e79184f2_1600w.jpg",
    alt: "Voice Memo",
  },
  {
    title: "TEXT → STORY",
    desc: "Paste your draft. AI shapes the narrative.",
    pill: "✏️ Text Input",
    img: "https://hoirqrkdgbmvpwutwuwj.supabase.co/storage/v1/object/public/assets/assets/917d6f93-fb36-439a-8c48-884b67b35381_1600w.jpg",
    alt: "Text Input",
  },
  {
    title: "TRENDS → CONTENT",
    desc: "We crawl Reddit's hottest threads for you.",
    pill: "🔥 Pick a Theme",
    img: "https://images.unsplash.com/photo-1533473359331-0135ef1b58bf?q=80&w=1200&auto=format&fit=crop",
    alt: "Pick a Theme",
  },
];

export default function Portfolio() {
  return (
    <section className="px-6 md:px-12 pb-32 max-w-[1800px] mx-auto">
      <div className="flex justify-between items-end mb-8 text-xl">
        <TextReveal as="span" className="font-normal">
          Transforming any idea into viral video content.
        </TextReveal>
        <Link
          href="#"
          className="flex items-center gap-2 font-normal hover:underline"
        >
          <span>See the work</span>
          <MoveRight size={20} />
        </Link>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-1">
        {items.map((item, idx) => (
          <div
            key={idx}
            className="relative group aspect-[4/5] md:aspect-auto md:h-[600px] overflow-hidden bg-gray-200"
          >
            <img
              src={item.img}
              alt={item.alt}
              className="w-full h-full object-cover transition-transform duration-700 group-hover:scale-105"
            />
            <div className="absolute inset-0 flex flex-col justify-end p-8 text-white">
              <div
                className="text-white/70 mb-3 w-fit px-3 py-1 rounded-full text-sm backdrop-blur-md"
                style={{ background: "rgba(255, 255, 255, 0.1)" }}
              >
                {item.pill}
              </div>
              <TextReveal
                as="span"
                className="font-display text-2xl font-semibold tracking-wide"
              >
                {item.title}
              </TextReveal>
              <p className="text-sm text-white/60 mt-1">{item.desc}</p>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
