"use client";

import React, { useEffect, useRef } from "react";
import Link from "next/link";
import { CornerRightDown } from "lucide-react";
import TextReveal from "./TextReveal";

export default function Services() {
  const badgeRef = useRef<HTMLSpanElement>(null);
  const iconRef = useRef<HTMLSpanElement>(null);
  const sectionRef = useRef<HTMLElement>(null);

  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            if (badgeRef.current) {
              badgeRef.current.classList.remove("scale-0");
              badgeRef.current.classList.add("scale-100");
            }
            if (iconRef.current) {
              iconRef.current.classList.remove("opacity-0");
              iconRef.current.classList.add("opacity-100");
            }
            observer.unobserve(entry.target);
          }
        });
      },
      { threshold: 0.1 }
    );

    if (sectionRef.current) {
      observer.observe(sectionRef.current);
    }

    return () => {
      if (sectionRef.current) {
        observer.unobserve(sectionRef.current);
      }
    };
  }, []);

  return (
    <section
      ref={sectionRef}
      className="py-24 md:py-40 flex flex-col items-center justify-center text-center px-4"
    >
      <div className="flex items-center gap-2 mb-4">
        <TextReveal as="span" className="text-lg font-medium">
          Your Input. Your Story.
        </TextReveal>
        <span
          ref={badgeRef}
          className="bg-black text-white text-[10px] font-semibold px-2 py-0.5 rounded-full uppercase tracking-wider scale-0 transition-transform duration-700 delay-500"
        >
          Models
        </span>
        <span
          ref={iconRef}
          className="opacity-0 transition-opacity duration-700 delay-700"
        >
          <CornerRightDown size={18} />
        </span>
      </div>
      <Link href="/create" className="group relative inline-block">
        <TextReveal
          as="h3"
          className="text-4xl md:text-6xl lg:text-7xl font-normal tracking-tight leading-tight border-b-2 border-transparent hover:border-black transition-colors duration-300 pb-1"
        >
          Explore how Story Lab works
        </TextReveal>
      </Link>
    </section>
  );
}
