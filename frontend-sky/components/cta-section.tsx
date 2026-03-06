"use client";

import Image from "next/image";
import { useScrollReveal } from "@/hooks/use-scroll-reveal";

const allImages = Array.from({ length: 30 }, (_, i) => `/CTA_images/image-${i + 1}.png`);

// 6 columns, each with 5 images
const columns: string[][] = [
  [allImages[0], allImages[1], allImages[2], allImages[3], allImages[4]],
  [allImages[5], allImages[6], allImages[7], allImages[8], allImages[9]],
  [allImages[10], allImages[11], allImages[12], allImages[13], allImages[14]],
  [allImages[15], allImages[16], allImages[17], allImages[18], allImages[19]],
  [allImages[20], allImages[21], allImages[22], allImages[23], allImages[24]],
  [allImages[25], allImages[26], allImages[27], allImages[28], allImages[29]],
];

function PhotoColumn({
  images,
  direction,
  speed,
}: {
  images: string[];
  direction: "up" | "down";
  speed: number;
}) {
  // Duplicate images for seamless loop
  const tiles = [...images, ...images, ...images];
  const totalImages = images.length;
  // Animation moves by 1 full set of images height
  // Each image is 160px + 8px gap = 168px, so total = images.length * 168px
  const singleSetHeight = totalImages * 168;

  return (
    <div className="relative flex-1 overflow-hidden h-full">
      <div
        className="flex flex-col gap-2 absolute top-0 left-0 right-0"
        style={
          {
            animation: `${direction === "up" ? "columnScrollUp" : "columnScrollDown"} ${speed}s linear infinite`,
            animationFillMode: "both",
            "--single-set-height": `${singleSetHeight}px`,
          } as React.CSSProperties
        }
      >
        {tiles.map((src, i) => (
          <div
            key={i}
            className="relative w-full flex-shrink-0 rounded-xl overflow-hidden"
            style={{ height: "160px" }}
          >
            <Image
              src={src}
              alt=""
              fill
              className="object-cover"
              sizes="200px"
            />
          </div>
        ))}
      </div>
    </div>
  );
}

export default function CTASection() {
  const contentRef = useScrollReveal();

  return (
    <section className="relative min-h-[680px] overflow-hidden flex items-center justify-center">
      {/* Photo grid columns — 6 columns, outer ones half visible */}
      <div className="absolute top-0 bottom-0 left-[-10%] w-[120%] flex gap-2">
        {columns.map((imgs, colIdx) => (
          <PhotoColumn
            key={colIdx}
            images={imgs}
            direction={colIdx % 2 === 0 ? "up" : "down"}
            speed={18 + colIdx * 3}
          />
        ))}
      </div>

      {/* Teal radial gradient overlay — center spotlight */}
      <div
        className="absolute inset-0"
        style={{
          background:
            "radial-gradient(ellipse 55% 80% at 50% 50%, rgba(58,130,155,0.92) 0%, rgba(58,130,155,0.82) 35%, rgba(58,100,130,0.55) 65%, rgba(30,60,90,0.2) 100%)",
        }}
      />

      {/* Grain texture */}
      <div
        className="absolute inset-0 opacity-[0.15] pointer-events-none"
        style={{
          backgroundImage: `url("data:image/svg+xml,%3Csvg viewBox='0 0 200 200' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='noise'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23noise)' opacity='1'/%3E%3C/svg%3E")`,
          backgroundRepeat: "repeat",
          backgroundSize: "150px",
        }}
      />

      {/* Content */}
      <div
        ref={contentRef as React.RefObject<HTMLDivElement>}
        className="reveal relative z-10 flex flex-col items-center text-center px-6 py-20 max-w-lg mx-auto"
      >
        <h2 className="text-5xl md:text-6xl font-bold text-white leading-tight text-balance">
          Stop planning.
          <br />
          Start creating.
        </h2>
        <p className="text-white/70 text-sm mt-4 mb-10">
          With our advanced technology, everyone can be a creator!
        </p>
        <a href="/login" className="btn-scale bg-white text-[#1a1a1a] font-semibold text-base px-12 py-4 rounded-full hover:bg-white/95 transition-all shadow-xl inline-block">
          Create now
        </a>
      </div>
    </section>
  );
}
