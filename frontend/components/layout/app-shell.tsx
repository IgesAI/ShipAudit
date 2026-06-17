"use client";

import { useGSAP } from "@gsap/react";
import gsap from "gsap";
import { BookOpen, LayoutDashboard, UploadCloud } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useRef } from "react";

import { AnimatedBackground } from "@/components/layout/animated-background";
import { cn } from "@/lib/utils";

const NAV_ITEMS = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard },
  { href: "/upload", label: "Upload & Audit", icon: UploadCloud },
  { href: "/docs", label: "Docs & Tutorial", icon: BookOpen },
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const shellRef = useRef<HTMLDivElement>(null);

  useGSAP(
    () => {
      const mm = gsap.matchMedia();

      mm.add("(prefers-reduced-motion: no-preference)", () => {
        gsap.from(".shell-nav", {
          y: -12,
          duration: 0.5,
          ease: "power2.out",
          clearProps: "transform",
        });
        gsap.from(".shell-content > *", {
          y: 16,
          duration: 0.45,
          ease: "power2.out",
          delay: 0.1,
          clearProps: "transform",
        });
      });

      return () => mm.revert();
    },
    { scope: shellRef },
  );

  return (
    <div ref={shellRef} className="relative min-h-screen">
      <AnimatedBackground />

      <div className="relative z-10 mx-auto flex min-h-screen max-w-7xl flex-col gap-6 p-4 md:p-6">
        <nav className="shell-nav glass-strong flex flex-col gap-4 rounded-2xl px-5 py-4 md:flex-row md:items-center md:justify-between">
          <Link href="/" className="flex items-center gap-3 transition hover:opacity-90">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary/20 ring-1 ring-primary/40">
              <span className="text-lg font-bold text-primary">S</span>
            </div>
            <div>
              <p className="text-base font-semibold tracking-tight">ShipAudit</p>
              <p className="text-xs text-muted-foreground">Fail-closed parcel invoice audit</p>
            </div>
          </Link>

          <div className="flex gap-2">
            {NAV_ITEMS.map(({ href, label, icon: Icon }) => {
              const active = href === "/" ? pathname === "/" : pathname.startsWith(href);
              return (
                <Link
                  key={href}
                  href={href}
                  className={cn(
                    "inline-flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium transition",
                    active
                      ? "bg-primary/15 text-primary ring-1 ring-primary/35"
                      : "text-muted-foreground hover:bg-white/5 hover:text-foreground",
                  )}
                >
                  <Icon className="h-4 w-4" />
                  {label}
                </Link>
              );
            })}
          </div>
        </nav>

        <div className="shell-content flex flex-1 flex-col gap-6">{children}</div>
      </div>
    </div>
  );
}
