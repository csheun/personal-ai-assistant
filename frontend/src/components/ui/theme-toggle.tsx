"use client";

import { Monitor, Moon, Sun } from "lucide-react";
import { useEffect, useSyncExternalStore } from "react";

type Theme = "system" | "light" | "dark";

const OPTIONS: { value: Theme; label: string; icon: typeof Sun }[] = [
  { value: "system", label: "System", icon: Monitor },
  { value: "light", label: "Light", icon: Sun },
  { value: "dark", label: "Dark", icon: Moon },
];

function apply(theme: Theme) {
  const dark = theme === "dark" || (theme === "system" && matchMedia("(prefers-color-scheme: dark)").matches);
  document.documentElement.classList.toggle("dark", dark);
}

// The saved preference lives in localStorage; this lets React read it without effects.
const listeners = new Set<() => void>();
const subscribe = (listener: () => void) => {
  listeners.add(listener);
  return () => listeners.delete(listener);
};
const readTheme = (): Theme => {
  try {
    const saved = localStorage.getItem("theme");
    return saved === "light" || saved === "dark" ? saved : "system";
  } catch {
    return "system";
  }
};

export function ThemeToggle() {
  const theme = useSyncExternalStore(subscribe, readTheme, () => "system" as Theme);

  useEffect(() => {
    if (theme !== "system") return;
    const media = matchMedia("(prefers-color-scheme: dark)");
    const onChange = () => apply("system");
    media.addEventListener("change", onChange);
    return () => media.removeEventListener("change", onChange);
  }, [theme]);

  const choose = (next: Theme) => {
    apply(next);
    try {
      if (next === "system") localStorage.removeItem("theme");
      else localStorage.setItem("theme", next);
    } catch {}
    listeners.forEach((listener) => listener());
  };

  return (
    <div role="radiogroup" aria-label="Theme" className="inline-flex rounded-lg bg-sunk p-0.5 ring-1 ring-inset ring-line">
      {OPTIONS.map(({ value, label, icon: Icon }) => (
        <button
          key={value}
          type="button"
          role="radio"
          aria-checked={theme === value}
          aria-label={label}
          title={label}
          onClick={() => choose(value)}
          className={`inline-flex size-7 items-center justify-center rounded-md transition-colors ${
            theme === value ? "bg-surface text-ink shadow-sm" : "text-faint hover:text-ink"
          }`}
        >
          <Icon className="size-3.5" aria-hidden />
        </button>
      ))}
    </div>
  );
}
