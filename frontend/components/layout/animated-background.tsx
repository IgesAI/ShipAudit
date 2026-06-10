"use client";

import { useGSAP } from "@gsap/react";
import gsap from "gsap";
import { useRef } from "react";

export function AnimatedBackground() {
  const containerRef = useRef<HTMLDivElement>(null);

  useGSAP(
    () => {
      const mm = gsap.matchMedia();

      mm.add("(prefers-reduced-motion: no-preference)", () => {
        const orbs = gsap.utils.toArray<HTMLElement>(".ambient-orb");
        orbs.forEach((orb, i) => {
          gsap.to(orb, {
            x: `random(-60, 60)`,
            y: `random(-40, 40)`,
            duration: 8 + i * 2,
            repeat: -1,
            yoyo: true,
            ease: "sine.inOut",
          });
        });
      });
    },
    { scope: containerRef },
  );

  return (
    <div ref={containerRef} className="ambient-bg" aria-hidden="true">
      <div className="ambient-orb ambient-orb-yellow h-[420px] w-[420px] -left-24 top-[-80px]" />
      <div className="ambient-orb ambient-orb-amber h-[360px] w-[360px] right-[-60px] top-[20%]" />
      <div className="ambient-orb ambient-orb-slate h-[500px] w-[500px] bottom-[-120px] left-[30%]" />
      <div className="ambient-orb ambient-orb-yellow h-[280px] w-[280px] bottom-[10%] right-[15%] opacity-30" />
    </div>
  );
}
