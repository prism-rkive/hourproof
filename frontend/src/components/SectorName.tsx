import * as Popover from "@radix-ui/react-popover";
import { useRef, useState } from "react";
import type { Sector } from "@/lib/sector";

/**
 * The buyer's sector in plain English, with Energinet's original Danish name one hover, tap or key press away (a
 * popover, like Term, so it also works on touch screens).
 */
export function SectorName({ sector }: { sector: Sector }) {
  const [open, setOpen] = useState(false);
  const hoverTimer = useRef<ReturnType<typeof setTimeout>>(undefined);
  const hover = (next: boolean) => {
    clearTimeout(hoverTimer.current);
    hoverTimer.current = setTimeout(() => setOpen(next), next ? 250 : 150);
  };
  return (
    <Popover.Root open={open} onOpenChange={setOpen}>
      {/* An inline span, not a <button>: a button is laid out as an inline block, so a label this long would break
          out of the sentence on a phone instead of wrapping with it. */}
      <Popover.Trigger asChild>
        <span
          role="button"
          tabIndex={0}
          className="cursor-help rounded-sm underline decoration-subtle-foreground/70 decoration-dotted underline-offset-[3px] hover:decoration-foreground"
          onMouseEnter={() => hover(true)}
          onMouseLeave={() => hover(false)}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") {
              e.preventDefault();
              setOpen((o) => !o);
            }
          }}
          aria-label={`${sector.label}: Energinet's Danish name`}
        >
          {sector.label}
        </span>
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content
          side="top"
          align="center"
          sideOffset={6}
          collisionPadding={16}
          onMouseEnter={() => hover(true)}
          onMouseLeave={() => hover(false)}
          onOpenAutoFocus={(e) => e.preventDefault()}
          className="z-50 w-72 max-w-[calc(100vw-2rem)] animate-in rounded-lg border border-border bg-popover p-3.5 text-left text-popover-foreground shadow-lg"
        >
          <p className="text-13 font-semibold">Energinet's name (Danish)</p>
          <p lang="da" className="mt-1 text-13 leading-relaxed text-muted-foreground">
            {sector.original}
          </p>
          <p className="mt-1 text-xs text-subtle-foreground">Industry branch {sector.code}, spelled as published.</p>
          <Popover.Arrow className="fill-popover" />
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  );
}

/** `text` with the sector's English label shown as a SectorName. */
export function WithSector({ text, sector }: { text: string; sector: Sector | null }) {
  const at = sector ? text.indexOf(sector.label) : -1;
  if (!sector || at < 0) return <>{text}</>;
  return (
    <>
      {text.slice(0, at)}
      <SectorName sector={sector} />
      {text.slice(at + sector.label.length)}
    </>
  );
}
