import { api } from "../core/api.js";
import { targetRole } from "../core/common.js";
import { $, emptyState, errorState, esc, icon, levelDots, loadingState, params, progressBar, safeUrl, scoreRing, toast,
  toastError } from "../core/ui.js";

const root = $("#gap");
let role = "";
const STATUS = { strong: ["Strong", "matched"], needs_improvement: ["Needs improvement", "partial"], missing: ["Missing", "missing"] };

async function run() {
  role = $("#g-role").value.trim();
  if (!role) {
    root.innerHTML = `<div class="card">${emptyState("Choose a target role", "Enter a role above or set a target career in your profile.", `<a class="btn btn-primary" href="/profile">Set target career</a>`, "target")}</div>`;
    return;
  }
  history.replaceState(null, "", `?role=${encodeURIComponent(role)}`);
  root.innerHTML = loadingState("Comparing your skills with role requirements...");
  try {
    const [g, graph] = await Promise.all([api.get(`/api/skills/gap?role=${encodeURIComponent(role)}`), api.get(`/api/skills/graph?role=${encodeURIComponent(role)}`)]);
    render(g, graph);
  } catch (err) { errorState(root, err, run); }
}

const chip = (name, extra = "", cls = "") => `<button class="tag ${cls}" data-skill="${esc(name)}">${esc(name)}${extra}</button>`;

function render(g, graph) {
  if (!g.items.length) {
    root.innerHTML = `<div class="card">${emptyState("No requirements found", g.data_note, "", "graph")}</div>`;
    return;
  }
  const by = (s) => g.items.filter((i) => i.status === s);
  root.innerHTML = `
    <section class="card glow mb-3"><div class="hero-card">
      ${scoreRing(g.readiness, "skill coverage")}
      <div class="stack"><h2>${esc(g.target_role)}${g.role_profile && g.role_profile !== g.target_role ? ` <span class="small muted">(mapped to ${esc(g.role_profile)})</span>` : ""}</h2>
        <p class="small">${by("strong").length} strong · ${by("needs_improvement").length} need improvement · ${by("missing").length} missing</p>
        <div class="callout small">${icon("info")} <span>${esc(g.data_note)} Requirements are never claimed as universal - see the evidence on each skill.</span></div>
        <div class="flex flex-wrap"><a class="btn btn-grad btn-sm" href="/roadmap?role=${encodeURIComponent(g.target_role)}">${icon("map")} Generate learning roadmap</a>
          <a class="btn btn-ghost btn-sm" href="/reports/skill-gap?role=${encodeURIComponent(g.target_role)}" target="_blank" rel="noopener">${icon("printer")} Export report</a></div>
      </div></div></section>

    <section class="card mb-3"><div class="card-head"><h3>${icon("graph")} Skill graph</h3><span class="small muted">Click any skill for details</span></div>
      <div class="skill-graph">
        <div class="sg-col"><h4>Current skills <span>${graph.current.length}</span></h4><div class="tags">${graph.current.slice(0, 18).map((s) => chip(s.skill, ` ${levelDots(s.level)}`)).join("") || `<span class="small faint">Add skills in your profile</span>`}${graph.current.length > 18 ? `<span class="tiny faint">+${graph.current.length - 18} more</span>` : ""}</div></div>
        <div class="sg-col"><h4>Target skills <span>${graph.target.length}</span></h4><div class="tags">${graph.target.map((s) => chip(s.skill, "", STATUS[s.status][1])).join("")}</div></div>
        <div class="sg-col"><h4>Missing / weak <span>${graph.missing.length}</span></h4><div class="tags">${graph.missing.map((s) => chip(s.skill, ` <span class="tiny">#${s.priority_rank}</span>`, STATUS[s.status][1])).join("") || `<span class="small faint">None</span>`}</div></div>
        <div class="sg-col"><h4>Learning path</h4><div class="tags">${graph.learning_path.map((p) => chip(p.skill, ` <span class="tiny">P${p.phase}</span>`, p.status === "completed" ? "matched" : "")).join("") || `<span class="small faint">-</span>`}</div>
          ${graph.roadmap_exists ? "" : `<p class="tiny faint mt-1">Suggested order - generate a roadmap to track it.</p>`}</div>
        <div class="sg-col"><h4>Job readiness</h4><div class="stat-value grad-text">${graph.readiness ?? "-"}%</div>${progressBar(graph.readiness || 0)}
          <p class="tiny faint mt-1">Importance-weighted coverage of required levels.</p></div>
      </div></section>

    <section class="grid-3">${["missing", "needs_improvement", "strong"].map((st) => `
      <div class="card"><div class="card-head"><h3>${STATUS[st][0]}</h3><span class="badge ${st === "strong" ? "teal" : st === "missing" ? "danger" : "warn"}">${by(st).length}</span></div>
        ${by(st).length ? `<div class="list">${by(st).map((i) => `
          <div class="list-item"><div class="grow">
            <div class="flex between"><button class="link-btn" data-skill="${esc(i.skill)}">${esc(i.skill)}</button>${levelDots(i.current_level, i.required_level)}</div>
            <div class="flex flex-wrap mt-1" style="gap:6px"><span class="badge ${i.importance === "core" ? "accent" : ""}">${esc(i.importance)}</span>
              ${i.priority_rank ? `<span class="badge warn">Priority #${i.priority_rank}</span>` : ""}
              ${i.job_frequency !== null ? `<span class="badge info">${Math.round(i.job_frequency * 100)}% of postings</span>` : ""}
              <span class="badge">~${i.est_hours}h</span></div>
            <div class="tiny faint mt-1">${esc(i.evidence.join(" · "))}</div>
          </div></div>`).join("")}</div>` : `<p class="small faint">None</p>`}
      </div>`).join("")}</section>`;
}

root.addEventListener("click", (e) => { const b = e.target.closest("[data-skill]"); if (b) openSkill(b.dataset.skill); });

async function openSkill(name) {
  $(".drawer")?.remove();
  const drawer = document.createElement("aside");
  drawer.className = "drawer";
  drawer.setAttribute("role", "dialog");
  drawer.setAttribute("aria-label", `${name} details`);
  drawer.innerHTML = `<div class="modal-head"><h3>${esc(name)}</h3><button class="btn btn-ghost btn-icon btn-sm" data-close aria-label="Close">${icon("x")}</button></div><div class="modal-body">${loadingState()}</div>`;
  document.body.appendChild(drawer);
  const close = () => { drawer.remove(); document.removeEventListener("keydown", onKey); };
  const onKey = (e) => { if (e.key === "Escape") close(); };
  document.addEventListener("keydown", onKey);
  drawer.querySelector("[data-close]").onclick = close;
  drawer.querySelector("[data-close]").focus();
  const body = drawer.querySelector(".modal-body");
  try {
    const d = await api.get(`/api/skills/detail?name=${encodeURIComponent(name)}&role=${encodeURIComponent(role)}`);
    const curated = d.resources.filter((r) => !r.is_search_link);
    body.innerHTML = `
      <p>${esc(d.skill.description || "No description available.")}</p>
      <div class="grid-2 mt-3">
        <div class="card flat stat"><span class="stat-label">Current level</span><span class="stat-value">${d.current_level}/5</span><span class="stat-note">${esc(d.level_source || "not on profile")}</span></div>
        <div class="card flat stat"><span class="stat-label">Required</span><span class="stat-value">${d.required_level ?? "-"}/5</span><span class="stat-note">${esc(d.status || "")}</span></div>
      </div>
      <div class="field mt-3"><label for="self-level">Self-assess your level</label>
        <div class="flex"><select class="select" id="self-level">${[1, 2, 3, 4, 5].map((n) => `<option value="${n}" ${n === (d.current_level || 2) ? "selected" : ""}>${n} - ${["Aware", "Beginner", "Working knowledge", "Proficient", "Expert"][n - 1]}</option>`).join("")}</select>
        <button class="btn btn-primary btn-sm" id="save-level">Save</button></div></div>
      ${d.evidence.length ? `<h4 class="mt-3 mb-2">Why it's required</h4><ul class="bullets small">${d.evidence.map((e) => `<li>${esc(e)}</li>`).join("")}</ul>` : ""}
      ${d.topics.length ? `<h4 class="mt-3 mb-2">What to learn</h4><ul class="bullets small">${d.topics.map((t) => `<li>${esc(t)}</li>`).join("")}</ul>` : ""}
      ${d.prerequisites.length ? `<p class="small mt-2"><strong>Prerequisites:</strong> ${esc(d.prerequisites.join(", "))}</p>` : ""}
      <h4 class="mt-3 mb-2">Learning progress</h4><p class="small">${d.learning_progress.completed} of ${d.learning_progress.total} curated resources completed · ${d.learning_progress.hours} h logged</p>
      <h4 class="mt-3 mb-2">Resources</h4>
      <div class="list">${d.resources.map((r) => `<div class="list-item"><div class="grow"><a href="${esc(safeUrl(r.url))}" target="_blank" rel="noopener noreferrer">${esc(r.title)} ${icon("external", "sm")}</a>
        <div class="tiny muted">${esc(r.platform)} · ${esc(r.type)} · ${esc(r.difficulty)}${r.est_hours ? ` · ~${r.est_hours}h` : ""}${r.is_search_link ? " · search results page" : ""}${r.is_free ? "" : " · paid"}</div></div></div>`).join("") || `<p class="small faint">No curated resources yet.</p>`}</div>
      ${!curated.length ? `<p class="tiny faint">Only search links are available for this skill; we don't invent course URLs.</p>` : ""}
      <h4 class="mt-3 mb-2">Jobs requiring it</h4><p class="small">${d.jobs_requiring.count} stored posting(s)</p>
      <div class="list">${d.jobs_requiring.examples.map((j) => `<div class="list-item"><a href="/jobs?job=${j.id}" class="small">${esc(j.title)} - ${esc(j.company || "")}</a></div>`).join("")}</div>`;
    $("#save-level", body).onclick = async () => {
      try { await api.post("/api/profile/skills", { skill: d.skill.name, level: +$("#self-level", body).value }); toast("Level saved", "success"); close(); run(); }
      catch (err) { toastError(err); }
    };
  } catch (err) { errorState(body, err, () => openSkill(name)); }
}

$("#role-form").addEventListener("submit", (e) => { e.preventDefault(); run(); });
(async () => {
  $("#g-role").value = params().get("role") || (await targetRole());
  await run();
  if (params().get("skill")) openSkill(params().get("skill"));
})();
