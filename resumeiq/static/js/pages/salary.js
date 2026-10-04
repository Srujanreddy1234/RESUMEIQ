import { api, qs } from "../core/api.js";
import { barChart } from "../core/charts.js";
import { targetRole } from "../core/common.js";
import { $, emptyState, errorState, esc, fmtMoney, icon, loadingState, toastError, withBusy } from "../core/ui.js";

const out = $("#sal-out");
const LEVELS = [["entry", "Entry level"], ["mid", "Mid level"], ["senior", "Senior level"]];
let lastQuery = null;

function render(d) {
  const p = d.postings;
  const cur = p.currency || "USD";
  out.innerHTML = `
    <section class="card mb-3">
      <div class="card-head"><h3>${icon("chart")} From job postings</h3><span class="data-label">Data</span></div>
      ${p.sample_size ? `
        <div class="grid-3 mb-3">${LEVELS.map(([k, label]) => {
          const l = p.levels[k];
          if (!l) return "";
          return `<div class="card flat stat"><span class="stat-label">${label}</span>
            ${l.sufficient ? `<span class="stat-value">${fmtMoney(l.median, cur)}</span><span class="stat-note">Middle 50%: ${fmtMoney(l.p25, cur)} - ${fmtMoney(l.p75, cur)}</span>`
              : `<span class="stat-value faint" style="font-size:1.1rem">Not enough data</span>`}
            <span class="tiny faint">${l.n} posting(s)</span></div>`;
        }).join("")}</div>
        <p class="small"><strong>Source:</strong> ${esc(p.sources.join(", "))} · <strong>Postings:</strong> ${p.sample_size}
          ${p.date_range ? ` · <strong>Posted:</strong> ${esc(p.date_range.from)} to ${esc(p.date_range.to)}` : ""}
          ${p.predicted_share ? ` · ${Math.round(p.predicted_share * 100)}% are provider estimates` : ""}
          ${p.unclassified_level ? ` · ${p.unclassified_level} without a clear seniority level` : ""}</p>`
        : emptyState("No salary data yet", "We only show salaries stated in real postings we've stored. Search jobs for this role (Adzuna includes most salaries) and try again.", `<a class="btn btn-primary btn-sm" href="/jobs?q=${encodeURIComponent(d.role)}">Search ${esc(d.role)} jobs</a>`, "coins")}
      <p class="tiny faint mt-2">${esc(d.method_note)}</p>
    </section>
    <section class="card mb-3">
      <div class="card-head"><h3>${icon("chart")} Adzuna salary distribution</h3><span class="data-label">Data</span></div>
      ${d.adzuna.available ? `<p class="small mb-2">${esc(d.adzuna.source)} · ${d.adzuna.total} adverts · fetched ${esc(d.adzuna.fetched_at)}</p><div class="chart-box"><canvas id="hist"></canvas></div>`
        : `<p class="small">${esc(d.adzuna.reason)}</p>`}
    </section>
    <section class="card">
      <div class="card-head"><h3>${icon("sparkles")} Interpretation</h3><span class="ai-label">AI interpretation</span></div>
      <p class="small mb-2">An AI summary of the data above only - it is told not to introduce outside salary figures.</p>
      <div id="interp"><button class="btn btn-ghost btn-sm" id="interp-btn" ${p.sample_size || d.adzuna.available ? "" : "disabled"}>${icon("sparkles")} Interpret this data</button></div>
    </section>`;
  if (d.adzuna.available) {
    barChart($("#hist"), d.adzuna.buckets.map((b) => fmtMoney(b.from, d.adzuna.currency)), d.adzuna.buckets.map((b) => b.count), { empty: "No histogram data." });
  }
  $("#interp-btn")?.addEventListener("click", async (e) => {
    await withBusy(e.target, async () => {
      try {
        const r = await api.post("/api/salary/interpret", lastQuery);
        const i = r.interpretation;
        $("#interp").innerHTML = i.available ? `<p style="color:var(--text)">${esc(i.interpretation)}</p>${i.caveats.length ? `<ul class="bullets mt-2 small">${i.caveats.map((c) => `<li>${esc(c)}</li>`).join("")}</ul>` : ""}`
          : `<div class="callout warn small">${esc(i.reason)}</div>`;
      } catch (err) { toastError(err); }
    }, "Interpreting...");
  });
}

async function run() {
  const f = Object.fromEntries(new FormData($("#sal-form")).entries());
  if (!f.role.trim()) return $("#s-role").focus();
  lastQuery = f;
  out.innerHTML = loadingState("Aggregating salary data...");
  try { render(await api.get(`/api/salary${qs(f)}`)); } catch (err) { errorState(out, err, run); }
}

$("#sal-form").addEventListener("submit", (e) => { e.preventDefault(); run(); });
targetRole().then((r) => { $("#s-role").value = r; if (r) run(); });
