import { api } from "../core/api.js";
import { barChart, doughnut, lineChart } from "../core/charts.js";
import { $, STAGE_LABELS, esc, icon, load, pct } from "../core/ui.js";

const root = $("#an");

function render(a, c, ins) {
  root.innerHTML = `
    ${a.sample_note ? `<div class="callout warn mb-3">${icon("info")} <span>${esc(a.sample_note)}</span></div>` : ""}
    <section class="grid-4 mb-3">
      ${[["Applications sent", a.applications_sent], ["Responses", a.responses, pct(a.response_rate) + " response rate"],
         ["Interviews", a.interviews, pct(a.interview_rate) + " interview rate"], ["Offers", a.offers, pct(a.offer_rate) + " offer rate"]]
        .map(([l, v, n]) => `<div class="card stat"><span class="stat-label">${l}</span><span class="stat-value">${v}</span>${n ? `<span class="stat-note">${n}</span>` : ""}</div>`).join("")}
    </section>
    <section class="grid-2 mb-3">
      <div class="card"><h3 class="mb-2">Applications by month</h3><div class="chart-box"><canvas id="c-month"></canvas></div></div>
      <div class="card"><h3 class="mb-2">Pipeline by stage</h3><div class="chart-box"><canvas id="c-stage"></canvas></div></div>
      <div class="card"><h3 class="mb-2">Applications by role</h3><div class="chart-box"><canvas id="c-role"></canvas></div></div>
      <div class="card"><h3 class="mb-2">Applications by company</h3><div class="chart-box"><canvas id="c-company"></canvas></div></div>
      <div class="card"><h3 class="mb-2">Resume score over time</h3><div class="chart-box"><canvas id="c-score"></canvas></div></div>
      <div class="card"><h3 class="mb-2">Learning resources completed</h3><div class="chart-box"><canvas id="c-learn"></canvas></div></div>
    </section>
    <section class="card"><div class="card-head"><h3>${icon("sparkles")} Career insights</h3><span class="data-label">Computed from your data</span></div>
      <div class="list">${ins.map((i) => `<div class="list-item"><div class="grow"><a href="${esc(i.link)}" style="color:var(--text)">${esc(i.text)}</a>
        <div class="tiny faint">Evidence: ${esc(i.evidence.join("; "))}</div></div></div>`).join("") || `<p class="small faint">No insights yet.</p>`}</div></section>`;
  lineChart($("#c-month"), a.by_month.map((x) => x.month), a.by_month.map((x) => x.count), { empty: "No applications sent yet." });
  const stages = Object.keys(STAGE_LABELS);
  doughnut($("#c-stage"), stages.map((s) => STAGE_LABELS[s]), stages.map((s) => a.by_stage[s] || 0), { empty: "Track applications to see your pipeline." });
  barChart($("#c-role"), a.by_role.map((x) => x.role), a.by_role.map((x) => x.count), { horizontal: true, empty: "No data yet." });
  barChart($("#c-company"), a.by_company.map((x) => x.company), a.by_company.map((x) => x.count), { horizontal: true, empty: "No data yet." });
  lineChart($("#c-score"), c.resume_scores.map((x) => x.date), c.resume_scores.map((x) => x.score), { max: 100, empty: "Analyse a resume to start tracking." });
  barChart($("#c-learn"), c.learning_by_month.map((x) => x.month), c.learning_by_month.map((x) => x.count), { empty: "Complete roadmap resources to see progress." });
}

function init() {
  load(root, () => Promise.all([api.get("/api/analytics/applications"), api.get("/api/analytics/charts"), api.get("/api/analytics/insights")]),
    ([a, c, i]) => render(a, c, i.insights));
}
document.addEventListener("themechange", init);
init();
