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
      <Popover.Trigger
        className="cursor-help rounded-sm text-left underline decoration-subtle-foreground/70 decoration-dotted underline-offset-[3px] hover:decoration-foreground"
        onMouseEnter={() => hover(true)}
        onMouseLeave={() => hover(false)}
        aria-label={`${sector.label}: Energinet's Danish name`}
      >
        {sector.label}
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
