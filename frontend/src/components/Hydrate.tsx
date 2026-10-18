import { Suspense, type ReactNode } from "react";

/**
 * A hydration boundary. Nothing inside suspends; the boundary only lets React hydrate this part of a prerendered
 * page as its own, interruptible unit of work instead of one long task for the whole page.
 */
export function Hydrate({ children }: { children: ReactNode }) {
  return <Suspense fallback={null}>{children}</Suspense>;
}
