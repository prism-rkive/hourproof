import * as Dialog from "@radix-ui/react-dialog";
import { X } from "lucide-react";
import * as React from "react";
import { cn } from "@/lib/utils";

export const Sheet = Dialog.Root;
export const SheetTrigger = Dialog.Trigger;
export const SheetClose = Dialog.Close;
export const SheetTitle = Dialog.Title;
export const SheetDescription = Dialog.Description;

/** A panel that slides in from the right, with focus trap, Escape to close and a labelled close button (Radix). */
export function SheetContent({ className, children, ...props }: React.ComponentProps<typeof Dialog.Content>) {
  return (
    <Dialog.Portal>
      <Dialog.Overlay className="fixed inset-0 z-50 bg-black/40 animate-in backdrop-blur-[2px]" />
      <Dialog.Content
        className={cn(
          "fixed inset-y-0 right-0 z-50 flex w-full max-w-xs flex-col border-l border-border bg-background shadow-lg animate-slide-in focus:outline-none",
          className,
        )}
        {...props}
      >
        {children}
        <Dialog.Close
          className="absolute right-3 top-2.5 inline-flex size-9 items-center justify-center rounded-md text-muted-foreground hover:bg-accent hover:text-foreground"
          aria-label="Close menu"
        >
          <X className="size-5" aria-hidden />
        </Dialog.Close>
      </Dialog.Content>
    </Dialog.Portal>
  );
}
