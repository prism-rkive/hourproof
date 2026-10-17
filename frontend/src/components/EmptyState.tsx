import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

export function EmptyState({
  icon: Icon,
  title,
  children,
  className,
}: {
  icon: LucideIcon;
  title: string;
  children?: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex flex-col items-center rounded-xl border border-dashed border-border-strong px-6 py-14 text-center",
        className,
      )}
    >
      <div className="mb-4 flex size-10 items-center justify-center rounded-lg border border-border bg-card shadow-xs">
        <Icon className="size-5 text-muted-foreground" aria-hidden />
      </div>
      <h2 className="text-base font-medium">{title}</h2>
      {children && <div className="mt-2 max-w-md text-sm text-muted-foreground">{children}</div>}
    </div>
  );
}
