"use client";

import React from "react";

export default function Orb() {
  return (
    <section className="h-[80vh] w-full flex items-center justify-center relative overflow-hidden bg-[#faf8f5]">
      {/* Blurred Gradient Orb */}
      <div className="w-[300px] h-[300px] md:w-[500px] md:h-[500px] rounded-full orb-gradient absolute top-1/2 left-1/2 transform -translate-x-1/2 -translate-y-1/2 opacity-80" />

      {/* SVG Graphic */}
      <div className="relative z-10 w-[200px] h-[200px] md:w-[280px] md:h-[280px]">
        <svg
          viewBox="0 0 200 200"
          className="w-full h-full animate-spin-slow"
        >
          <defs>
            <path
              id="circlePath"
              d="M 100, 100 m -80, 0 a 80,80 0 1,1 160,0 a 80,80 0 1,1 -160,0"
            />
          </defs>
          <circle
            cx="100"
            cy="100"
            r="80"
            fill="none"
            stroke="white"
            strokeWidth="1.5"
            opacity="0.6"
          />
          <circle cx="20" cy="100" r="3" fill="white" />
          <text
            fill="white"
            fontSize="12"
            letterSpacing="1"
            fontFamily="Inter"
            fontWeight="500"
          >
            <textPath href="#circlePath" startOffset="50%" textAnchor="middle">
              Start creating for free today
            </textPath>
          </text>
        </svg>
      </div>
    </section>
  );
}
