import { useCallback, useEffect, useState } from "react";
import { fetchPrefs, savePrefs } from "../lib/api";

export type Theme = "auto" | "cockpit" | "refined" | "light";

const THEMES: Theme[] = ["auto", "cockpit", "refined", "light"];

function resolveTheme(theme: Theme): string {
  if (theme !== "auto") return theme;
  return window.matchMedia("(prefers-color-scheme: light)").matches
    ? "light"
    : "cockpit";
}

function applyTheme(theme: Theme) {
  document.documentElement.dataset.theme = resolveTheme(theme);
}

export function useTheme() {
  const [theme, setTheme] = useState<Theme>("auto");

  useEffect(() => {
    fetchPrefs().then((prefs) => {
      const saved = (prefs as Record<string, unknown>).theme as Theme | undefined;
      if (saved && THEMES.includes(saved)) {
        setTheme(saved);
        applyTheme(saved);
      } else {
        applyTheme("auto");
      }
    });
  }, []);

  // Listen for system theme changes when in auto mode
  useEffect(() => {
    if (theme !== "auto") return;
    const mq = window.matchMedia("(prefers-color-scheme: light)");
    const handler = () => applyTheme("auto");
    mq.addEventListener("change", handler);
    return () => mq.removeEventListener("change", handler);
  }, [theme]);

  const setAndPersist = useCallback((next: Theme) => {
    setTheme(next);
    applyTheme(next);
    savePrefs({ theme: next } as Record<string, unknown>);
  }, []);

  const cycleTheme = useCallback(() => {
    setTheme((prev) => {
      const idx = THEMES.indexOf(prev);
      const next = THEMES[(idx + 1) % THEMES.length];
      applyTheme(next);
      savePrefs({ theme: next } as Record<string, unknown>);
      return next;
    });
  }, []);

  return { theme, setTheme: setAndPersist, cycleTheme };
}
