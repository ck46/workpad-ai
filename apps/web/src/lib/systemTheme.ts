// System-level light/dark theme for the app shell (sidebar, header, chat,
// toolbar). This is orthogonal to the canvas theme — the canvas toggle
// controls whether the paper editor renders warm-ivory vs. warmer-still,
// while this controls the whole chrome around it. The paper stays warm in
// either mode (design decision: artifacts are always a document, never a
// chat-log surface).
//
// tokens.css defines a `:root.theme-dark` class with dark-shell values;
// this module wires it to localStorage + `prefers-color-scheme`.

import { useEffect, useState } from "react";

export type SystemTheme = "light" | "dark" | "auto";

const STORAGE_KEY = "workpad-system-theme";

function readStored(): SystemTheme {
  if (typeof window === "undefined") return "auto";
  const value = window.localStorage.getItem(STORAGE_KEY);
  if (value === "light" || value === "dark" || value === "auto") return value;
  return "auto";
}

function prefersDark(): boolean {
  if (typeof window === "undefined") return false;
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches ?? false;
}

function applyTheme(mode: SystemTheme): void {
  const root = document.documentElement;
  const effective = mode === "auto" ? (prefersDark() ? "dark" : "light") : mode;
  if (effective === "dark") {
    root.classList.add("theme-dark");
  } else {
    root.classList.remove("theme-dark");
  }
}

export function initSystemTheme(): void {
  const stored = readStored();
  applyTheme(stored);
}

export function useSystemTheme(): [SystemTheme, (mode: SystemTheme) => void] {
  const [mode, setMode] = useState<SystemTheme>(readStored);

  useEffect(() => {
    applyTheme(mode);
    if (typeof window !== "undefined") {
      window.localStorage.setItem(STORAGE_KEY, mode);
    }
  }, [mode]);

  useEffect(() => {
    if (mode !== "auto" || typeof window === "undefined") return;
    const media = window.matchMedia?.("(prefers-color-scheme: dark)");
    if (!media) return;
    const onChange = () => applyTheme("auto");
    media.addEventListener("change", onChange);
    return () => media.removeEventListener("change", onChange);
  }, [mode]);

  return [mode, setMode];
}
