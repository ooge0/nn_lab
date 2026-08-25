// web/static/tabs.js
//
// Generic, dependency-free tab widget shared by every page with sub-tabs (analytics, nlp,
// clusters). Event-delegated on `document` rather than bound per-button, so it keeps working
// after htmx swaps in fresh content (a run-picker change replaces the whole fragment; delegation
// means no re-binding is needed). Respects an incoming URL hash (e.g. a direct link to
// /analytics#zipf from the docs) by activating that tab instead of always defaulting to the first
// one -- those anchor links were already documented before tabs existed and must keep working.

function activateTab(tabset, panelId) {
  const btn = tabset.querySelector(`.tab-btn[data-tab="${panelId}"]`);
  const panel = tabset.querySelector(`#${panelId}`);
  if (!btn || !panel) return false;
  tabset.querySelectorAll(".tab-btn").forEach((b) => b.classList.toggle("active", b === btn));
  tabset.querySelectorAll(".tab-panel").forEach((p) => p.classList.toggle("active", p === panel));
  return true;
}

function initTabsets(root) {
  root.querySelectorAll(".tabset").forEach((tabset) => {
    const hashId = window.location.hash.replace("#", "");
    if (!hashId || !activateTab(tabset, hashId)) {
      const firstBtn = tabset.querySelector(".tab-btn");
      if (firstBtn) activateTab(tabset, firstBtn.dataset.tab);
    }
  });
}

document.addEventListener("click", (e) => {
  const btn = e.target.closest(".tab-btn");
  if (!btn) return;
  activateTab(btn.closest(".tabset"), btn.dataset.tab);
});

document.addEventListener("htmx:afterSwap", (e) => initTabsets(e.target));
document.addEventListener("DOMContentLoaded", () => initTabsets(document));
