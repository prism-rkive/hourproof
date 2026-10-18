import { useSyncExternalStore } from "react";

const noop = () => () => {};

/** False on the server and during hydration, true afterwards: for parts that only make sense in a browser. */
export function useIsClient(): boolean {
  return useSyncExternalStore(
    noop,
    () => true,
    () => false,
  );
}
