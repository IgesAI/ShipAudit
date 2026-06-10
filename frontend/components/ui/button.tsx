import { cn } from "@/lib/utils";
import type { ButtonHTMLAttributes } from "react";

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "default" | "secondary" | "ghost" | "destructive";
};

export function Button({ className, variant = "default", ...props }: ButtonProps) {
  const variants = {
    default: "bg-primary text-primary-foreground shadow-[0_0_20px_rgba(245,197,24,0.2)] hover:brightness-110",
    secondary: "glass text-foreground hover:bg-white/10",
    ghost: "hover:bg-white/8",
    destructive: "bg-destructive text-white hover:opacity-90",
  };
  return (
    <button
      className={cn(
        "inline-flex h-10 items-center justify-center rounded-lg px-4 py-2 text-sm font-medium transition disabled:pointer-events-none disabled:opacity-50",
        variants[variant],
        className,
      )}
      {...props}
    />
  );
}
