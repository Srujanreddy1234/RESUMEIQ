// Theme preference: dark (default) | light | system. Persisted locally and to the user's profile.
import { api } from "./api.js";
import { icon } from "./ui.js";

export function applyTheme(pref, persist = true) {
  const theme = pref === "system" ? (matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark") : pref;
  document.documentElement.dataset.theme = theme;
  document.documentElement.dataset.themePref = pref;
  try { localStorage.setItem("riq-theme", pref); } catch { /* storage blocked */ }
  const btn = document.getElementById("theme-toggle");
  if (btn) btn.innerHTML = icon(theme === "dark" ? "sun" : "moon");
  if (persist) api.put("/api/profile", { theme: pref }).catch(() => {});
  document.dispatchEvent(new CustomEvent("themechange"));
}
