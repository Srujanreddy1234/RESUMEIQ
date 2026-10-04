import { api } from "../core/api.js";
import { barChart, lineChart } from "../core/charts.js";
import { $, emptyState, errorState, esc, icon, levelDots, modal, progressBar, scoreClass, scoreRing, timeAgo } from "../core/ui.js";

const root = $("#dash");

function greeting() {
  const h = new Date().getHours();
  return h < 12 ? "Good morning" : h < 18 ? "Good afternoon" : "Good evening";
}

const tile = (label, value, note = "", href = "") => `
  <${href ? `a href="${href}"` : "div"} class="card stat" style="text-decoration:none;color:inherit">
    <span class="stat-label">${esc(label)}</span>
    <span class="stat-value">${value ?? "-"}</span>
    ${note ? `<span class="stat-note">${esc(note)}</span>` : ""}
  </${href ? "a" : "div"}>`;

const QUICK = [["Analyze Resume", "/analyzer", "scan"], ["Find Jobs", "/jobs", "briefcase"], ["Analyze Job Description", "/job-matcher", "target"],
  ["Improve Resume", "/improve", "wand"], ["Practice Interview", "/interview", "mic"], ["Learning Roadmap", "/roadmap", "map"]];
const STAGES = [["wishlist", "Wishlist"], ["applied", "Applied"], ["assessment", "Assessment"], ["interview", "Interview"], ["offer", "Offer"]];
const ACT_ICON = { analysis: "scan", saved_job: "star", application: "kanban", learning: "book", interview: "mic" };

function render(d, insights) {
  const s = d.stats;
  const readiness = d.readiness.score;
  root.innerHTML = `
    <section class="card glow hero-card mb-3">
      ${scoreRing(readiness, "readiness")}
      <div class="stack">
        <span class="greeting">${greeting()}, ${esc(d.user.first_name)}</span>
        <h1>Your career readiness ${readiness === null ? "" : `is <span class="grad-text">${readiness}%</span>`}</h1>
        <p>${d.target_role ? `Target: <strong>${esc(d.target_role)}</strong>.` : `<a href="/profile">Set a target career</a> to unlock role-specific insights.`}
          <button class="link-btn small" id="why-readiness">How is this calculated?</button></p>
        <div class="quick-actions">${QUICK.map(([l, h, i]) => `<a href="${h}">${icon(i)}<span>${l}</span></a>`).join("")}</div>
      </div>
    </section>
    ${!d.has_resume ? `<div class="callout ai mb-3">${icon("upload")} <div><strong>Start here:</strong> upload your resume to unlock scoring, matching and gap analysis. <a href="/resumes">Upload resume →</a></div></div>` : ""}
    <section class="grid-4 mb-3">
      ${tile("Resume score", s.resume_score, "Latest primary analysis", "/analyzer")}
      ${tile("Profile completeness", s.profile_completeness + "%", "", "/profile")}
      ${tile("Skills", s.skills, "On your profile", "/profile")}
      ${tile("Skill gaps", d.target_role ? s.skill_gaps : "-", d.target_role ? "For your target role" : "Set a target role", "/skill-gap")}
      ${tile("Job matches", s.job_matches, "Stored postings scoring 60%+", "/jobs")}
      ${tile("Applications sent", s.applications_sent, "", "/applications")}
      ${tile("Interviews", s.interviews, "Applications that reached interview", "/applications")}
      ${tile("Interview readiness", s.interview_readiness === null ? "-" : s.interview_readiness + "%", s.interview_sessions ? `Last ${s.interview_sessions} mock session(s)` : "Try a mock interview", "/interview")}
    </section>
    <section class="grid-3 mb-3">
      <div class="card">
        <div class="card-head"><h3>${icon("graph")} Top skill gaps</h3><a class="small" href="/skill-gap">View all</a></div>
        ${d.top_gaps.length ? `<div class="stack">${d.top_gaps.map((g) => `
          <div><div class="flex between small"><strong>${esc(g.skill)}</strong>${levelDots(g.current_level, g.required_level)}</div>
          ${progressBar((g.current_level / g.required_level) * 100, "sm")}</div>`).join("")}</div>
          <a class="btn btn-ghost btn-sm mt-3" href="/roadmap">${icon("map")} View learning roadmap</a>`
        : emptyState(d.target_role ? "No gaps found" : "No target role", d.target_role ? "You meet the current requirements." : "Set one in your profile.", "", "graph")}
      </div>
      <div class="card">
        <div class="card-head"><h3>${icon("briefcase")} Recommended jobs</h3><a class="small" href="/jobs">Browse</a></div>
        ${d.recommended_jobs.length ? `<div class="list">${d.recommended_jobs.map((j) => `
          <div class="list-item"><div class="grow"><a href="/jobs?job=${j.id}" class="break"><strong>${esc(j.title)}</strong></a>
            <div class="tiny muted">${esc(j.company || "")} · ${esc(j.location || "")}</div></div>
            <span class="match-pill ${scoreClass(j.match.score)}">${j.match.score}%</span></div>`).join("")}</div>`
        : emptyState("No matches yet", "Search jobs for your target role to fetch live postings.", `<a class="btn btn-primary btn-sm" href="/jobs">Find jobs</a>`, "briefcase")}
      </div>
      <div class="card">
        <div class="card-head"><h3>${icon("book")} Learning progress</h3><a class="small" href="/roadmap">Roadmap</a></div>
        ${d.learning.progress !== null ? `<p class="small">${esc(d.learning.role)}</p>
          <div class="stat-value mt-1">${d.learning.progress}%</div>${progressBar(d.learning.progress, "lg")}`
        : emptyState("No roadmap yet", "Generate one from your skill gaps.", `<a class="btn btn-primary btn-sm" href="/roadmap">Create roadmap</a>`, "map")}
        <div class="divider"></div>
        <h4 class="mb-2">Application pipeline</h4>
        <div class="pipeline">${STAGES.map(([k, l]) => `<div class="pstep"><b>${d.pipeline[k] || 0}</b><span>${l}</span></div>`).join("")}</div>
      </div>
    </section>
    <section class="grid-2 mb-3">
      <div class="card"><div class="card-head"><h3>Resume score over time</h3></div><div class="chart-box"><canvas id="c-score"></canvas></div></div>
      <div class="card"><div class="card-head"><h3>Skills gained</h3></div><div class="chart-box"><canvas id="c-skills"></canvas></div></div>
      <div class="card"><div class="card-head"><h3>Applications over time</h3></div><div class="chart-box"><canvas id="c-apps"></canvas></div></div>
      <div class="card"><div class="card-head"><h3>Learning & interviews</h3></div><div class="chart-box"><canvas id="c-learn"></canvas></div></div>
    </section>
    <section class="grid-2">
      <div class="card"><div class="card-head"><h3>${icon("sparkles")} Career insights</h3><span class="data-label">From your data</span></div>
        ${insights.length ? `<div class="list">${insights.map((i) => `<div class="list-item"><span class="list-icon">${icon(i.type === "strength" ? "star" : i.type === "gap" ? "alert" : i.type === "trend" ? "chart" : "bolt")}</span>
          <div class="grow"><a href="${esc(i.link)}" style="color:var(--text)">${esc(i.text)}</a><div class="tiny faint">Evidence: ${esc(i.evidence.join("; "))}</div></div></div>`).join("")}</div>`
        : emptyState("No insights yet", "Add a resume and target role.")}
      </div>
      <div class="card"><div class="card-head"><h3>${icon("clock")} Recent activity</h3></div>
        ${d.recent_activity.length ? `<div class="list">${d.recent_activity.map((a) => `<div class="list-item"><span class="list-icon">${icon(ACT_ICON[a.type] || "info")}</span>
          <div class="grow"><a href="${esc(a.link)}" style="color:var(--text)" class="break">${esc(a.title)}</a><div class="tiny muted">${esc(a.detail || "")} · ${timeAgo(a.at)}</div></div></div>`).join("")}</div>`
        : emptyState("Nothing yet", "Your analyses, applications and learning will appear here.", "", "clock")}
      </div>
    </section>`;

  const c = d.charts;
  lineChart($("#c-score"), c.resume_scores.map((x) => x.date), c.resume_scores.map((x) => x.score), { max: 100, empty: "Analyse a resume to start tracking." });
  lineChart($("#c-skills"), c.skills_over_time.map((x) => x.month), c.skills_over_time.map((x) => x.total), { empty: "Skills you add will be tracked here." });
  barChart($("#c-apps"), c.applications_by_month.map((x) => x.month), c.applications_by_month.map((x) => x.count), { empty: "No applications sent yet." });
  const months = [...new Set([...c.learning_by_month.map((x) => x.month), ...c.interviews_by_month.map((x) => x.month)])].sort();
  const lc = $("#c-learn");
  if (months.length && typeof Chart !== "undefined") {
    const css = (n) => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
    barChart(lc, months, months.map((m) => c.learning_by_month.find((x) => x.month === m)?.count || 0));
    const chart = Chart.getChart(lc);
    chart.data.datasets[0].label = "Resources completed";
    chart.data.datasets.push({ label: "Interview sessions", data: months.map((m) => c.interviews_by_month.find((x) => x.month === m)?.count || 0), backgroundColor: css("--teal"), borderRadius: 6, maxBarThickness: 36 });
    chart.options.plugins.legend.display = true;
    chart.update();
  } else barChart(lc, [], [], { empty: "Complete resources or practise interviews to see progress." });

  $("#why-readiness").onclick = () => {
    modal({ title: "How career readiness is calculated", body: `<p class="small mb-2">${esc(d.readiness.formula)}</p>
      <div class="table-wrap"><table class="table"><thead><tr><th>Component</th><th>Value</th><th>Weight</th></tr></thead><tbody>
      ${d.readiness.components.map((x) => `<tr><td>${esc(x.label)}</td><td>${x.value === null ? "<span class='faint'>not available</span>" : x.value}</td><td>${Math.round(x.weight * 100)}%</td></tr>`).join("")}
      </tbody></table></div>`, actions: [{ label: "Close", class: "btn-primary" }] });
  };
}

async function init() {
  try {
    const [d, ins] = await Promise.all([api.get("/api/analytics/dashboard"), api.get("/api/analytics/insights").catch(() => ({ insights: [] }))]);
    render(d, ins.insights);
  } catch (err) {
    errorState(root, err, init);
  }
}
document.addEventListener("themechange", () => init());
init();
