import { AlertTriangle, CheckCircle2, CircleDashed, ShieldCheck, XCircle } from "lucide-react";
import type { ReactNode } from "react";
import type { Tone } from "@/lib/selectors";
import { cn } from "@/lib/utils";

const STYLE: Record<Tone, string> = {
  success: "border-success/30 bg-success-subtle text-success",
  warning: "border-warning/30 bg-warning-subtle text-warning",
  danger: "border-danger/30 bg-danger-subtle text-danger",
  neutral: "border-border bg-muted text-muted-foreground",
};
const ICON = {
  success: CheckCircle2,
  warning: AlertTriangle,
  danger: XCircle,
  neutral: CircleDashed,
  shield: ShieldCheck,
};

/** A status with an icon and a word, never colour alone. */
export function StatusBadge({
  tone,
  children,
  icon,
  className,
}: {
  tone: Tone;
  children: ReactNode;
  icon?: keyof typeof ICON;
  className?: string;
}) {
  const Icon = ICON[icon ?? tone];
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-medium whitespace-nowrap",
        STYLE[tone],
        className,
      )}
    >
      <Icon className="size-3.5" aria-hidden />
      {children}
    </span>
  );
}

/** A run step's status in words. */
export function stepTone(status: string): { tone: Tone; label: string } {
  if (status === "done") return { tone: "success", label: "Done" };
  if (status === "failed") return { tone: "danger", label: "Failed" };
  return { tone: "warning", label: "Running" };
}
