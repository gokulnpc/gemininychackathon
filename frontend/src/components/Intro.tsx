"use client";

import React from "react";
import TextReveal from "./TextReveal";

export default function Intro() {
  return (
    <section className="px-6 py-20 md:px-12 md:py-32 max-w-[1800px] mx-auto">
      <div className="flex flex-col md:flex-row justify-between items-start mb-12 md:mb-20 text-xl md:text-2xl font-normal leading-snug">
        <div className="max-w-md">
          <TextReveal as="p">AI-powered content engine.</TextReveal>
          <TextReveal as="p">Three input methods. Infinite output.</TextReveal>
        </div>
        <div className="mt-4 md:mt-0">
          <TextReveal as="p">Text | Voice | Themes</TextReveal>
        </div>
      </div>

      <TextReveal
        as="h2"
        className="text-3xl md:text-5xl lg:text-[4.2rem] leading-[1.1] tracking-tight font-normal max-w-6xl"
      >
        Drop a voice memo, scribble a text, or pick a theme. Our AI agent turns
        it into a ready-to-post video instantly. Creating killer content has
        never been this effortless!
      </TextReveal>
    </section>
  );
}
