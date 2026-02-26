"use client";

import React from "react";
import TextReveal from "./TextReveal";

export default function DataSection() {
  return (
    <section className="px-6 py-20 md:px-12 md:py-32 max-w-[1800px] mx-auto">
      <div className="flex flex-col md:flex-row justify-between items-start mb-12 md:mb-20 text-xl md:text-2xl font-normal leading-snug">
        <div className="max-w-md">
          <TextReveal as="p">From raw input</TextReveal>
          <TextReveal as="p">to published-ready video.</TextReveal>
        </div>
      </div>

      <TextReveal
        as="h2"
        className="text-3xl md:text-5xl lg:text-[4.2rem] leading-[1.1] tracking-tight font-normal max-w-[90%]"
      >
        Content Factory removes every bottleneck between your idea and your
        audience. Type it, say it, or let the AI find it and our pipeline
        handles scripting, visuals, and editing. What used to take a team and a
        week now takes seconds.
      </TextReveal>
    </section>
  );
}
