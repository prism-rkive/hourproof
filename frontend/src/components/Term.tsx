import * as Popover from "@radix-ui/react-popover";
import { useRef, useState, type ReactNode } from "react";
import { GLOSSARY, type GlossaryId } from "@/content/glossary";

/**
 * A word with a plain-language definition: dotted underline, opens on tap, click, keyboard (Enter/Space) or hover.
 * Built on a popover rather than a tooltip so it also works on touch screens.
 */
export function Term({ id, children }: { id: GlossaryId; children?: ReactNode }) {
  const entry = GLOSSARY[id];
  const [open, setOpen] = useState(false);
  const hoverTimer = useRef<ReturnType<typeof setTimeout>>(undefined);
  const hover = (next: boolean) => {
    clearTimeout(hoverTimer.current);
    hoverTimer.current = setTimeout(() => setOpen(next), next ? 250 : 150);
  };
  return (
    <Popover.Root open={open} onOpenChange={setOpen}>
      <Popover.Trigger
        className="cursor-help rounded-sm underline decoration-subtle-foreground/70 decoration-dotted underline-offset-[3px] hover:decoration-foreground"
        onMouseEnter={() => hover(true)}
        onMouseLeave={() => hover(false)}
        aria-label={`${typeof children === "string" ? children : entry.term}: what does this mean?`}
      >
        {children ?? entry.term}
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
          <p className="text-13 font-semibold">{entry.term}</p>
          <p className="mt-1 text-13 leading-relaxed text-muted-foreground">{entry.definition}</p>
          <Popover.Arrow className="fill-popover" />
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  );
}
