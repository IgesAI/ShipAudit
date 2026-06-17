"use client";

import { useGSAP } from "@gsap/react";
import gsap from "gsap";
import {
  BookOpen,
  Gavel,
  Layers,
  Map,
  Play,
  Scale,
  Shield,
  Upload,
} from "lucide-react";
import { useRef, useState } from "react";

import { GlassCard, GlassCardContent, GlassCardDescription, GlassCardHeader, GlassCardTitle } from "@/components/ui/glass-card";
import { DOC_SECTIONS, type DocSection } from "@/lib/docs/sections";
import { renderSimpleMarkdown } from "@/lib/simple-markdown";
import { cn } from "@/lib/utils";

const ICONS = {
  book: BookOpen,
  shield: Shield,
  upload: Upload,
  scale: Scale,
  map: Map,
  gavel: Gavel,
  play: Play,
  layers: Layers,
} as const;

function SectionCard({ section, index }: { section: DocSection; index: number }) {
  const ref = useRef<HTMLElement>(null);
  const Icon = ICONS[section.icon];

  useGSAP(
    () => {
      const mm = gsap.matchMedia();
      mm.add("(prefers-reduced-motion: no-preference)", () => {
        gsap.from(ref.current, {
          y: 20,
          duration: 0.45,
          ease: "power2.out",
          delay: index * 0.03,
          clearProps: "transform",
        });
      });

      return () => mm.revert();
    },
    { scope: ref },
  );

  return (
    <section id={section.id} ref={ref} className="scroll-mt-28">
      <GlassCard variant={index === 0 ? "yellow" : "default"} className="doc-section-card">
        <GlassCardHeader>
          <div className="flex items-start gap-4">
            <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-primary/15 ring-1 ring-primary/30">
              <Icon className="h-5 w-5 text-primary" />
            </div>
            <div>
              <GlassCardTitle>{section.title}</GlassCardTitle>
              <GlassCardDescription>{section.subtitle}</GlassCardDescription>
            </div>
          </div>
        </GlassCardHeader>
        <GlassCardContent>
          <div className="docs-prose">{renderSimpleMarkdown(section.content)}</div>
        </GlassCardContent>
      </GlassCard>
    </section>
  );
}

export function DocsView() {
  const [activeId, setActiveId] = useState(DOC_SECTIONS[0].id);
  const navRef = useRef<HTMLDivElement>(null);

  useGSAP(
    () => {
      const mm = gsap.matchMedia();
      mm.add("(prefers-reduced-motion: no-preference)", () => {
        gsap.from(".docs-nav-item", {
          x: -10,
          duration: 0.35,
          stagger: 0.04,
          ease: "power2.out",
          clearProps: "transform",
        });
      });

      return () => mm.revert();
    },
    { scope: navRef },
  );

  return (
    <div className="flex flex-col gap-6 lg:flex-row lg:items-start">
      <aside ref={navRef} className="lg:sticky lg:top-6 lg:w-64 lg:shrink-0">
        <GlassCard variant="strong" className="p-4">
          <p className="mb-3 text-xs font-semibold uppercase tracking-wider text-primary">Contents</p>
          <nav className="flex flex-col gap-1">
            {DOC_SECTIONS.map((section) => {
              const Icon = ICONS[section.icon];
              return (
                <a
                  key={section.id}
                  href={`#${section.id}`}
                  onClick={() => setActiveId(section.id)}
                  className={cn(
                    "docs-nav-item flex items-center gap-2 rounded-lg px-3 py-2 text-sm transition",
                    activeId === section.id
                      ? "bg-primary/12 text-primary"
                      : "text-muted-foreground hover:bg-white/5 hover:text-foreground",
                  )}
                >
                  <Icon className="h-3.5 w-3.5 shrink-0" />
                  <span className="truncate">{section.title}</span>
                </a>
              );
            })}
          </nav>
        </GlassCard>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col gap-8">
        <GlassCard variant="yellow" className="p-6 md:p-8">
          <div className="flex items-start gap-4">
            <BookOpen className="mt-1 h-8 w-8 text-primary" />
            <div>
              <h1 className="text-2xl font-semibold tracking-tight md:text-3xl">Documentation & Tutorial</h1>
              <p className="mt-2 max-w-2xl text-sm leading-relaxed text-muted-foreground">
                Everything you need to understand ShipAudit&apos;s fail-closed architecture — from ingestion gates
                and verdict taxonomy to rate cards, area surcharges, and dispute evidence packets.
              </p>
            </div>
          </div>
        </GlassCard>

        {DOC_SECTIONS.map((section, index) => (
          <SectionCard key={section.id} section={section} index={index} />
        ))}
      </div>
    </div>
  );
}
