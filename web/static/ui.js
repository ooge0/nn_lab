// Sidebar-collapse + light/dark theme toggle. Every page is a fresh server render (no SPA), so
// both preferences persist via localStorage and are re-applied on each load. The actual "no flash
// of the wrong theme/collapsed state" work happens in the small inline blocking script each page's
// <head> carries (runs before first paint) -- this file only wires up the buttons and keeps their
// own labels in sync with whatever state is currently active.

const THEME_KEY = "nn_lab_theme";
const SIDEBAR_KEY = "nn_lab_sidebar_collapsed";

function syncThemeButtonLabel() {
  const btn = document.getElementById("theme-toggle-btn");
  if (!btn) return;
  const isLight = document.documentElement.getAttribute("data-theme") === "light";
  // Pictographic sun/moon glyphs (U+2600/U+263E) render inconsistently across fonts (came out
  // as an unrecognizable asterisk in testing) -- a half-shaded circle is a basic geometric
  // Unicode block character, not a font-specific pictograph, so it renders reliably everywhere.
  // Same glyph both states (rotated for the "other half" reading); the tooltip carries the
  // actual state, not the icon.
  btn.innerHTML = isLight ? "&#9681;" : "&#9680;";
  const label = isLight ? "Switch to dark theme" : "Switch to light theme";
  btn.title = label;
  btn.setAttribute("aria-label", label);
}

function toggleTheme() {
  const isLight = document.documentElement.getAttribute("data-theme") === "light";
  const next = isLight ? "dark" : "light";
  if (isLight) {
    document.documentElement.removeAttribute("data-theme");
  } else {
    document.documentElement.setAttribute("data-theme", "light");
  }
  localStorage.setItem(THEME_KEY, next);
  // Also mirrored into a cookie: server-rendered charts (Plotly/matplotlib,
  // baked-in colors) need to know the theme at request time, and localStorage
  // -- unlike a cookie -- is never sent with a request. See
  // web/plotting/render.py's set_chart_theme.
  document.cookie = `${THEME_KEY}=${next}; path=/; max-age=31536000; samesite=lax`;
  syncThemeButtonLabel();
}

function setSidebarCollapsed(collapsed) {
  document.documentElement.classList.toggle("sidebar-collapsed", collapsed);
  localStorage.setItem(SIDEBAR_KEY, collapsed ? "1" : "0");
}

document.addEventListener("DOMContentLoaded", () => {
  syncThemeButtonLabel();

  const themeBtn = document.getElementById("theme-toggle-btn");
  if (themeBtn) themeBtn.addEventListener("click", toggleTheme);

  const collapseBtn = document.getElementById("sidebar-collapse-btn");
  if (collapseBtn) collapseBtn.addEventListener("click", () => setSidebarCollapsed(true));

  const expandBtn = document.getElementById("sidebar-expand-btn");
  if (expandBtn) expandBtn.addEventListener("click", () => setSidebarCollapsed(false));
});
