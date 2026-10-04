// Thin Chart.js wrappers that read colours from CSS tokens (works in dark and light themes).
/* global Chart */

const charts = new WeakMap();
const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();

function base() {
  const text = css("--muted"), grid = css("--border");
  return {
    responsive: true, maintainAspectRatio: false, animation: { duration: 500 },
    plugins: { legend: { labels: { color: text, boxWidth: 12, font: { family: "Plus Jakarta Sans" } } },
      tooltip: { backgroundColor: css("--surface-2"), titleColor: css("--text"), bodyColor: css("--text"), borderColor: css("--border-strong"), borderWidth: 1 } },
    scales: {
      x: { ticks: { color: text, maxRotation: 0, autoSkip: true }, grid: { color: grid, drawBorder: false } },
      y: { ticks: { color: text, precision: 0 }, grid: { color: grid, drawBorder: false }, beginAtZero: true },
    },
  };
}

function render(canvas, config) {
  if (typeof Chart === "undefined") return null;
  charts.get(canvas)?.destroy();
  const chart = new Chart(canvas.getContext("2d"), config);
  charts.set(canvas, chart);
  return chart;
}

/** Render or show an empty message if there is no data. */
function guard(canvas, labels, emptyMsg) {
  const box = canvas.parentElement;
  box.querySelector(".chart-empty")?.remove();
  if (!labels.length) {
    charts.get(canvas)?.destroy();
    canvas.hidden = true;
    const p = document.createElement("p");
    p.className = "chart-empty state small";
    p.textContent = emptyMsg || "No data yet.";
    box.appendChild(p);
    return false;
  }
  canvas.hidden = false;
  return true;
}

export function lineChart(canvas, labels, data, { label = "", max, empty } = {}) {
  if (!guard(canvas, labels, empty)) return null;
  const opts = base();
  if (max) opts.scales.y.max = max;
  opts.plugins.legend.display = false;
  return render(canvas, { type: "line", data: { labels, datasets: [{ label, data, borderColor: css("--accent"),
    backgroundColor: css("--accent-soft"), fill: true, tension: .35, pointRadius: 3, pointBackgroundColor: css("--teal") }] }, options: opts });
}

export function barChart(canvas, labels, data, { label = "", horizontal = false, empty, color } = {}) {
  if (!guard(canvas, labels, empty)) return null;
  const opts = base();
  opts.plugins.legend.display = false;
  if (horizontal) opts.indexAxis = "y";
  return render(canvas, { type: "bar", data: { labels, datasets: [{ label, data, backgroundColor: color || css("--accent"), borderRadius: 6, maxBarThickness: 36 }] }, options: opts });
}

export function doughnut(canvas, labels, data, { empty } = {}) {
  if (!guard(canvas, labels.filter((_, i) => data[i] > 0), empty)) return null;
  const palette = [css("--accent"), css("--teal"), css("--info"), css("--warn"), css("--danger"), css("--faint")];
  return render(canvas, { type: "doughnut", data: { labels, datasets: [{ data, backgroundColor: palette, borderColor: css("--surface-2"), borderWidth: 2 }] },
    options: { responsive: true, maintainAspectRatio: false, cutout: "65%", plugins: { legend: { position: "bottom", labels: { color: css("--muted"), boxWidth: 12 } } } } });
}
