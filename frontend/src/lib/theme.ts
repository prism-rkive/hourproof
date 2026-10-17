/**
 * Theme: the visitor's saved choice, else the OS preference, else dark. index.html applies it before first paint;
 * this module keeps it in sync afterwards (toggle, OS changes while nothing is saved).
 */
import { useSyncExternalStore } from "react";

export type Theme = "light" | "dark";
export const THEME_KEY = "hp-theme";

function saved(): Theme | null {
  try {
    const v = localStorage.getItem(THEME_KEY);
    return v === "light" || v === "dark" ? v : null;
  } catch {
    return null; // storage blocked (private mode, sandbox): fall back to the OS preference
  }
}

function system(): Theme {
  return window.matchMedia?.("(prefers-color-scheme: light)").matches ? "light" : "dark";
}

export function resolveTheme(): Theme {
  return saved() ?? system();
}

const listeners = new Set<() => void>();

export function applyTheme(theme: Theme) {
  const root = document.documentElement;
  root.classList.toggle("dark", theme === "dark");
  root.style.colorScheme = theme;
  listeners.forEach((l) => l());
}

export function setTheme(theme: Theme) {
  try {
    localStorage.setItem(THEME_KEY, theme);
  } catch {
    /* not persisted, still applied */
  }
  applyTheme(theme);
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  const mq = window.matchMedia?.("(prefers-color-scheme: light)");
  const onSystem = () => {
    if (!saved()) applyTheme(system());
  };
  mq?.addEventListener("change", onSystem);
  return () => {
    listeners.delete(listener);
    mq?.removeEventListener("change", onSystem);
  };
}

function current(): Theme {
  return document.documentElement.classList.contains("dark") ? "dark" : "light";
}

export function useTheme(): [Theme, (t: Theme) => void] {
  const theme = useSyncExternalStore(subscribe, current, () => "dark" as Theme);
  return [theme, setTheme];
}
