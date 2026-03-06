"use client";

import Image from "next/image";
import { useScrollReveal } from "@/hooks/use-scroll-reveal";

const cards = [
  {
    id: 1,
    image: "/images/card-youtube.jpg",
    duration: "0:40",
    category: "YOUTUBE",
    title: "YouTube Shorts",
    tall: false,
  },
  {
    id: 2,
    image: "/images/card-product.jpg",
    duration: "1:00",
    category: "MARKETING",
    title: "Product Launch",
    tall: false,
  },
  {
    id: 3,
    image: "/images/card-testimonial.jpg",
    duration: "0:50",
    category: "TESTIMONIAL",
    title: "Customer Testimonial",
    tall: true,
  },
  {
    id: 4,
    image: "/images/card-social.jpg",
    duration: "0:45",
    category: "INSTAGRAM REELS",
    title: "Social Media Marketing",
    tall: false,
  },
  {
    id: 5,
    image: "/images/card-instagram.jpg",
    duration: "0:30",
    category: "SOCIAL MEDIA",
    title: "Instagram Reels Demo",
    tall: true,
  },
];

const allCards = [...cards, ...cards];

export default function ContentCardsSection() {
  const headerRef = useScrollReveal();
  const bridgeRef = useScrollReveal();

  return (
    <section className="bg-[#111111]">
      {/* Header row */}
      <div
        ref={headerRef as React.RefObject<HTMLDivElement>}
        className="reveal max-w-[1400px] mx-auto px-6 md:px-12 pt-16 pb-0"
      >
        <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-6">
          <h2
            className="text-4xl sm:text-5xl md:text-[56px] lg:text-[64px] font-bold leading-[1.05] text-balance max-w-[480px]"
            style={{
              background: "linear-gradient(to bottom, #FFFFFF, #999999)",
              WebkitBackgroundClip: "text",
              WebkitTextFillColor: "transparent",
            }}
          >
            Making movies should be easy
          </h2>
          <p
            className="text-sm md:text-base leading-relaxed max-w-[260px] sm:text-right sm:pt-2 hidden sm:block"
            style={{
              background: "linear-gradient(to bottom, #FFFFFF, #999999)",
              WebkitBackgroundClip: "text",
              WebkitTextFillColor: "transparent",
            }}
          >
            Turn any idea into a short film — just speak it, type it, or pick a
            preset.
          </p>
        </div>
      </div>

      {/* Infinite scroll strip */}
      <div className="mt-10 overflow-hidden">
        <div
          className="flex gap-4 animate-scroll"
          style={{ width: "max-content" }}
        >
          {allCards.map((card, idx) => {
            const isTall = idx % 2 === 0;
            return (
              <div
                key={`${card.id}-${idx}`}
                className="shrink-0"
                style={{
                  width: "220px",
                  paddingTop: isTall ? "0px" : "110px",
                }}
              >
                <VideoCard card={card} isTall={isTall} />
              </div>
            );
          })}
        </div>
      </div>

      {/* Bridge text — below cards */}
      <div
        ref={bridgeRef as React.RefObject<HTMLDivElement>}
        className="reveal  mx-auto px-6 md:px-12 pb-20 pt-12"
      >
        <p className="text-white text-2xl sm:text-3xl md:text-[36px] font-semibold leading-snug text-center">
          We bridge the gap between ideas and movie production{" "}
          <span className="text-[#70A8C2]">for everyone</span>
        </p>
      </div>

      <style jsx>{`
        @keyframes scroll {
          0% {
            transform: translateX(0);
          }
          100% {
            transform: translateX(-50%);
          }
        }
        .animate-scroll {
          animation: scroll 28s linear infinite;
        }
        .animate-scroll:hover {
          animation-play-state: paused;
        }
      `}</style>
    </section>
  );
}

function VideoCard({
  card,
  isTall: _isTall,
}: {
  card: (typeof cards)[0];
  isTall: boolean;
}) {
  return (
    <div className="video-card-hover w-full flex flex-col">
      {/* Image */}
      <div
        className="relative rounded-2xl overflow-hidden w-full shrink-0"
        style={{ height: "380px" }}
      >
        <Image
          src={card.image}
          alt={card.title}
          fill
          className="object-cover"
          sizes="220px"
        />
        <div className="absolute top-3 right-3 bg-black/80 text-white text-[11px] font-semibold px-2.5 py-1 rounded-full backdrop-blur-sm">
          {card.duration}
        </div>
      </div>

      {/* Info label */}
      <div className="bg-white rounded-2xl px-4 py-3 -mt-2 relative z-10">
        <p className="text-[#e84c1e] text-[10px] font-bold tracking-widest uppercase mb-0.5">
          {card.category}
        </p>
        <p className="text-[#111] text-sm font-semibold leading-snug">
          {card.title}
        </p>
      </div>
    </div>
  );
}
