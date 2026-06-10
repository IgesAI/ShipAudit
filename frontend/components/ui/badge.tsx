import { cn } from "@/lib/utils";
import type { HTMLAttributes } from "react";

type BadgeProps = HTMLAttributes<HTMLSpanElement> & {
  variant?: "default" | "secondary" | "success" | "warning" | "destructive";
};

export function Badge({ className, variant = "default", ...props }: BadgeProps) {
  const variants = {
    default: "border-primary/40 bg-primary/15 text-primary",
    secondary: "border-white/15 bg-white/5 text-muted-foreground",
    success: "border-emerald-500/40 bg-emerald-500/10 text-emerald-300",
    warning: "border-primary/50 bg-primary/10 text-primary",
    destructive: "border-red-500/40 bg-red-500/10 text-red-300",
  };
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-md border px-2 py-0.5 text-xs font-medium",
        variants[variant],
        className,
      )}
      {...props}
    />
  );
}
