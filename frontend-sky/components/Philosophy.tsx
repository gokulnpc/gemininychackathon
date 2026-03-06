"use client";

import React from "react";
import TextReveal from "./TextReveal";

export default function Philosophy() {
  return (
    <section className="px-6 py-20 md:px-12 md:py-32 max-w-[1800px] mx-auto border-t border-gray-300">
      <div className="flex flex-col md:flex-row justify-between items-start mb-12 md:mb-20 text-xl md:text-2xl font-normal leading-snug">
        <div className="max-w-md">
          <TextReveal as="p">We operate on a simple philosophy:</TextReveal>
          <TextReveal as="p">Creating content should be easy</TextReveal>
        </div>
      </div>

      <TextReveal
        as="h2"
        className="text-3xl md:text-5xl lg:text-[4.2rem] leading-[1.1] tracking-tight font-normal max-w-6xl"
      >
        Our AI scans what&apos;s already resonating — Reddit threads, trending topics,
        viral formats — then crafts video content perfectly tuned to your channel
        and audience. You stay ahead without ever running out of ideas.
      </TextReveal>
    </section>
  );
}
