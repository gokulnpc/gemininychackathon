"use client";

import React from "react";
import Link from "next/link";
import { ArrowUpRight } from "lucide-react";
import TextReveal from "./TextReveal";

const images = [
  "https://hoirqrkdgbmvpwutwuwj.supabase.co/storage/v1/object/public/assets/assets/5bab247f-35d9-400d-a82b-fd87cfe913d2_1600w.webp",
  "https://images.unsplash.com/photo-1529626455594-4ff0802cfb7e?q=80&w=800&auto=format&fit=crop",
  "https://images.unsplash.com/photo-1522071820081-009f0129c71c?q=80&w=800&auto=format&fit=crop",
  "https://hoirqrkdgbmvpwutwuwj.supabase.co/storage/v1/object/public/assets/assets/4734259a-bad7-422f-981e-ce01e79184f2_1600w.jpg",
  "https://hoirqrkdgbmvpwutwuwj.supabase.co/storage/v1/object/public/assets/assets/917d6f93-fb36-439a-8c48-884b67b35381_1600w.jpg",
];

export default function Carousel() {
  return (
    <section className="pt-20 pb-40 overflow-hidden relative">
      <div className="px-6 md:px-12 mb-10">
        <h2 className="text-6xl md:text-[8rem] lg:text-[10rem] leading-none tracking-tighter font-normal">
          <TextReveal>Start Creating</TextReveal>
        </h2>
      </div>

      {/* Horizontal Scroll */}
      <div className="flex gap-4 overflow-x-auto px-6 md:px-12 no-scrollbar pb-10">
        {images.map((src, idx) => (
          <div
            key={idx}
            className="flex-none w-[300px] md:w-[450px] aspect-[4/3] bg-gray-200"
          >
            <img
              src={src}
              alt={`Carousel item ${idx + 1}`}
              className="w-full h-full object-cover"
            />
          </div>
        ))}
      </div>

      <div className="flex flex-col items-center justify-center mt-20 text-center">
        <div className="flex items-center gap-1 mb-2 text-sm">
          <TextReveal as="span">Built for creators, marketers & brands</TextReveal>
          <ArrowUpRight size={12} />
        </div>
        <Link
          href="/create"
          className="text-4xl md:text-6xl lg:text-7xl font-normal tracking-tight leading-tight border-b-2 border-transparent hover:border-black transition-colors duration-300 pb-1"
        >
          <TextReveal>Try Content Factory free</TextReveal>
        </Link>
      </div>
    </section>
  );
}
