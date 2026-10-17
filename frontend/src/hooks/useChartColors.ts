import { useMemo } from "react";
import { useTheme } from "@/lib/theme";

/** SVG chart colours resolved from the design tokens, re-read when the theme changes. */
export function useChartColors() {
  const [theme] = useTheme();
  return useMemo(() => {
    const css = getComputedStyle(document.documentElement);
    const v = (name: string) => css.getPropertyValue(name).trim();
    return {
      brand: v("--brand"),
      foreground: v("--foreground"),
      muted: v("--muted-foreground"),
      subtle: v("--subtle-foreground"),
      grid: v("--border"),
      card: v("--card"),
      theme,
    };
  }, [theme]);
}
