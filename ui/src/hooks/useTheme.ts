import { useCallback, useEffect, useState } from "react";
import { fetchPrefs, savePrefs } from "../lib/api";

export type Style = "cockpit" | "refined";
export type Scheme = "auto" | "dark" | "light";

const STYLES: Style[] = ["cockpit", "refined"];
const SCHEMES: Scheme[] = ["auto", "dark", "light"];

function resolveScheme(scheme: Scheme): "dark" | "light" {
  if (scheme !== "auto") return scheme;
  return window.matchMedia("(prefers-color-scheme: light)").matches
    ? "light"
    : "dark";
}

function apply(style: Style, scheme: Scheme) {
  const el = document.documentElement;
  el.dataset.style = style;
  el.dataset.scheme = resolveScheme(scheme);
}

export function useTheme() {
  const [style, setStyle] = useState<Style>("cockpit");
  const [scheme, setScheme] = useState<Scheme>("auto");

  useEffect(() => {
    fetchPrefs().then((prefs) => {
      const p = prefs as Record<string, unknown>;
      const savedStyle = p.style as Style | undefined;
      const savedScheme = p.scheme as Scheme | undefined;
      // Migrate old single "theme" pref
      const oldTheme = p.theme as string | undefined;

      const s = savedStyle && STYLES.includes(savedStyle) ? savedStyle :
                oldTheme === "refined" ? "refined" : "cockpit";
      const sc = savedScheme && SCHEMES.includes(savedScheme) ? savedScheme :
                 oldTheme === "light" ? "light" :
                 oldTheme === "auto" ? "auto" : "auto";

      setStyle(s);
      setScheme(sc);
      apply(s, sc);
    });
  }, []);

  // Listen for system scheme changes when in auto mode
  useEffect(() => {
    if (scheme !== "auto") return;
    const mq = window.matchMedia("(prefers-color-scheme: light)");
    const handler = () => apply(style, "auto");
    mq.addEventListener("change", handler);
    return () => mq.removeEventListener("change", handler);
  }, [scheme, style]);

  const cycleStyle = useCallback(() => {
    setStyle((prev) => {
      const next = STYLES[(STYLES.indexOf(prev) + 1) % STYLES.length];
      apply(next, scheme);
      savePrefs({ style: next } as Record<string, unknown>);
      return next;
    });
  }, [scheme]);

  const cycleScheme = useCallback(() => {
    setScheme((prev) => {
      const next = SCHEMES[(SCHEMES.indexOf(prev) + 1) % SCHEMES.length];
      apply(style, next);
      savePrefs({ scheme: next } as Record<string, unknown>);
      return next;
    });
  }, [style]);

  return { style, scheme, cycleStyle, cycleScheme };
}
