import { cn } from "@/lib/utils";
import type { HTMLAttributes } from "react";

type GlassVariant = "default" | "strong" | "yellow";

const variantClass: Record<GlassVariant, string> = {
  default: "glass",
  strong: "glass-strong",
  yellow: "glass-yellow",
};

export function GlassCard({
  className,
  variant = "default",
  ...props
}: HTMLAttributes<HTMLDivElement> & { variant?: GlassVariant }) {
  return (
    <div
      className={cn("rounded-xl text-card-foreground", variantClass[variant], className)}
      {...props}
    />
  );
}

export function GlassCardHeader({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("flex flex-col gap-1.5 p-6", className)} {...props} />;
}

export function GlassCardTitle({ className, ...props }: HTMLAttributes<HTMLHeadingElement>) {
  return <h3 className={cn("text-lg font-semibold tracking-tight", className)} {...props} />;
}

export function GlassCardDescription({ className, ...props }: HTMLAttributes<HTMLParagraphElement>) {
  return <p className={cn("text-sm text-muted-foreground", className)} {...props} />;
}

export function GlassCardContent({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("p-6 pt-0", className)} {...props} />;
}
