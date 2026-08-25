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
  resizePlotlyChartsIn(panel);
  return true;
}

// Plotly measures a chart's width from its container the moment Plotly.newPlot() runs -- which,
// for every non-default tab (and in practice the "default" one too, since its own <script> tag
// can execute before initTabsets() has applied the .active class that actually makes it visible),
// happens while the panel is still `display: none` (zero width). Plotly has no way to know later
// that the container's real size changed, so the chart stays squished until something makes the
// browser fire a real `resize` event (e.g. a window/zoom change) -- confirmed live: this was
// reported as "charts render narrower than their container, fixed by nudging browser zoom".
// Plotly.Plots.resize() re-measures the container and redraws, doing programmatically what a real
// resize event would trigger by accident.
function resizePlotlyChartsIn(panel) {
  if (typeof Plotly === "undefined") return;
  panel.querySelectorAll(".plotly-graph-div").forEach((div) => {
    try {
      Plotly.Plots.resize(div);
    } catch (e) {
      // A chart that failed to initialize (e.g. a genuinely empty figure) has nothing to
      // resize -- not this function's job to diagnose that separately.
    }
  });
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
