"use client";

import React, { useEffect, useRef } from "react";

interface TextRevealProps {
  children: string;
  className?: string;
  as?: React.ElementType;
}

export default function TextReveal({ children, className = "", as: Component = "div" }: TextRevealProps) {
  const elementRef = useRef<HTMLElement>(null);

  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            entry.target.classList.add("reveal-active");
            observer.unobserve(entry.target);
          }
        });
      },
      { threshold: 0.1 }
    );

    if (elementRef.current) {
      observer.observe(elementRef.current);
    }

    return () => {
      if (elementRef.current) {
        observer.unobserve(elementRef.current);
      }
    };
  }, []);

  const words = children.split(" ");

  return (
    <Component ref={elementRef} className={`${className}`}>
      {words.map((word, index) => (
        <span key={index} className="word-wrapper">
          <span
            className="word-inner"
            style={{ transitionDelay: `${index * 0.03}s` }}
          >
            {word}&nbsp;
          </span>
        </span>
      ))}
    </Component>
  );
}
