import { useCallback, useEffect, useState } from "react";
import { fetchPrefs, savePrefs } from "../lib/api";

export type Theme = "cockpit" | "refined";

const THEMES: Theme[] = ["cockpit", "refined"];

function applyTheme(theme: Theme) {
  document.documentElement.dataset.theme = theme;
}

export function useTheme() {
  const [theme, setTheme] = useState<Theme>("cockpit");

  useEffect(() => {
    fetchPrefs().then((prefs) => {
      const saved = (prefs as Record<string, unknown>).theme as Theme | undefined;
      if (saved && THEMES.includes(saved)) {
        setTheme(saved);
        applyTheme(saved);
      } else {
        applyTheme("cockpit");
      }
    });
  }, []);

  const toggleTheme = useCallback(() => {
    setTheme((prev) => {
      const idx = THEMES.indexOf(prev);
      const next = THEMES[(idx + 1) % THEMES.length];
      applyTheme(next);
      savePrefs({ theme: next } as Record<string, unknown>);
      return next;
    });
  }, []);

  return { theme, toggleTheme };
}
