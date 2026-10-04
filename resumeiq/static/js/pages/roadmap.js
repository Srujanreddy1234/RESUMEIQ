import { api, qs } from "../core/api.js";
import { targetRole } from "../core/common.js";
import { $, emptyState, errorState, esc, icon, initTabs, load, loadingState, modal, params, progressBar, safeUrl, toast,
  toastError } from "../core/ui.js";

const plan = $("#plan");
const STATUSES = [["not_started", "Not started"], ["in_progress", "In progress"], ["completed", "Completed"]];
let current = null;

initTabs(document.querySelector(".tabs"), (t) => { if (t === "projects") loadProjects(); if (t === "resources") loadResources(); });

function statusSelect(value, attrs) {
  return `<select class="select" ${attrs} aria-label="Status">${STATUSES.map(([k, l]) => `<option value="${k}" ${k === value ? "selected" : ""}>${l}</option>`).join("")}</select>`;
}

async function loadStats() {
  try {
    const s = await api.get("/api/learning/stats");
    $("#stats").innerHTML = [
      ["Roadmap progress", s.roadmap_progress === null ? "-" : `${s.roadmap_progress}%`, s.roadmap_role || "No roadmap yet"],
      ["Skills completed", `${s.skills_completed}/${s.skills_total}`, "Roadmap phases"],
      ["Hours learned", s.hours_learned, `${s.resources_completed} resources done · ${s.resources_in_progress} in progress`],
      ["Courses · Projects · Certs", `${s.courses_completed} · ${s.projects_completed} · ${s.certifications.earned}`, `${s.certifications.in_progress} certification(s) in progress`],
    ].map(([l, v, n]) => `<div class="card stat"><span class="stat-label">${l}</span><span class="stat-value">${v}</span><span class="stat-note">${esc(n)}</span></div>`).join("");
  } catch { $("#stats").innerHTML = ""; }
}

function resRow(r) {
  return `<div class="res-row" data-res="${r.id}">
    <div class="grow"><a href="${esc(safeUrl(r.url))}" target="_blank" rel="noopener noreferrer">${esc(r.title)} ${icon("external", "sm")}</a>
      <div class="tiny muted">${esc(r.platform)} · ${esc(r.type)}${r.est_hours ? ` · ~${r.est_hours}h` : ""}${r.is_search_link ? " · search results" : ""}${r.is_free ? "" : " · paid"}</div></div>
    ${r.is_search_link ? "" : statusSelect(r.status, "data-res-status")}
  </div>`;
}

function renderPlan(rm) {
  current = rm;
  if (!rm.items.length) {
    plan.innerHTML = `<div class="card">${emptyState("No gaps to learn", rm.summary, "", "check")}</div>`;
    return;
  }
  plan.innerHTML = `
    <div class="card glow mb-3"><div class="flex between flex-wrap"><div><h2>Target: ${esc(rm.target_role)}</h2><p class="small">${esc(rm.summary)}</p></div>
      <div class="flex"><a class="btn btn-ghost btn-sm" href="/reports/roadmap" target="_blank" rel="noopener">${icon("printer")} Export</a></div></div>
      <div class="flex mt-2"><span class="grow">${progressBar(rm.progress, "lg")}</span><strong>${rm.progress}%</strong></div>
      <p class="tiny faint mt-1">~${rm.estimated_weeks} week(s) at ${rm.weekly_hours} h/week. Progress counts completed phases and completed curated resources.</p></div>
    <div class="stack-lg">${rm.items.map((it) => `
      <div class="phase ${it.status}" data-item="${it.id}">
        <div class="phase-num">${it.status === "completed" ? "✓" : it.phase}</div>
        <div class="card">
          <div class="card-head"><div><div class="tiny muted">PHASE ${it.phase}</div><h3>${esc(it.skill.name)}</h3></div>
            <div class="flex">${statusSelect(it.status, "data-item-status")}<span class="badge">~${it.est_hours}h</span></div></div>
          ${progressBar(it.progress, "sm")}
          <div class="grid-2 mt-3">
            <div><h4 class="mb-2">What to learn</h4><ul class="bullets small">${it.what_to_learn.map((t) => `<li>${esc(t)}</li>`).join("")}</ul></div>
            <div><h4 class="mb-2">Why it matters</h4><p class="small">${esc(it.why)}</p>
              ${it.prerequisites.length ? `<h4 class="mt-2 mb-2">Prerequisites</h4><div class="tags">${it.prerequisites.map((p) => `<span class="tag ${p.have ? "matched" : "missing"}">${esc(p.skill)}</span>`).join("")}</div>` : ""}</div>
          </div>
          <div class="grid-2 mt-3">
            <div><h4 class="mb-2">Beginner resources</h4>${it.resources.beginner.map(resRow).join("") || `<p class="small faint">None curated</p>`}</div>
            <div><h4 class="mb-2">Intermediate resources</h4>${it.resources.intermediate.map(resRow).join("") || `<p class="small faint">None curated</p>`}</div>
          </div>
          ${it.project_ideas.length ? `<h4 class="mt-3 mb-2">Projects to build</h4><div class="tags">${it.project_ideas.map((p) => `<span class="tag">${esc(p)}</span>`).join("")}</div>` : ""}
        </div>
      </div>`).join("")}</div>`;
}

plan.addEventListener("change", async (e) => {
  try {
    if (e.target.matches("[data-item-status]")) {
      const id = e.target.closest("[data-item]").dataset.item;
      renderPlan(await api.patch(`/api/roadmap/items/${id}`, { status: e.target.value }));
      toast("Phase updated", "success", 1800);
      loadStats();
    } else if (e.target.matches("[data-res-status]")) {
      const id = e.target.closest("[data-res]").dataset.res;
      let hours = null;
      if (e.target.value === "completed") {
        const h = await modal({ title: "Log hours", body: `<div class="field"><label for="hrs">Hours spent (optional)</label><input class="input" id="hrs" type="number" min="0" max="1000" step="0.5"></div>`,
          actions: [{ label: "Skip", value: "" }, { label: "Save", class: "btn-primary", handler: (m) => m.querySelector("#hrs").value || "" }] });
        hours = h ? +h : null;
      }
      await api.put(`/api/learning/progress/${id}`, { status: e.target.value, hours_spent: hours });
      const rm = await api.get("/api/roadmap");
      renderPlan(rm.roadmap);
      loadStats();
    }
  } catch (err) { toastError(err); }
});

async function loadPlan() {
  plan.innerHTML = loadingState();
  try {
    const { roadmap } = await api.get("/api/roadmap");
    if (roadmap && !params().get("role")) return renderPlan(roadmap);
    if (roadmap && params().get("role")?.toLowerCase() === roadmap.target_role.toLowerCase()) return renderPlan(roadmap);
    showGenerate(params().get("role") || (await targetRole()), !!roadmap);
  } catch (err) { errorState(plan, err, loadPlan); }
}

async function showGenerate(role = "", hasExisting = false) {
  const prof = await api.get("/api/profile").catch(() => null);
  plan.innerHTML = `<form id="gen-form" class="card">
    <h3 class="mb-2">${hasExisting ? "Create a new roadmap" : "Create your roadmap"}</h3>
    <p class="small mb-3">We'll prioritise skills by importance, job frequency, your current level and difficulty, then order them by prerequisites.</p>
    <div class="form-grid"><div class="field"><label for="gen-role">Target role</label><input class="input" id="gen-role" required maxlength="120" value="${esc(role)}"></div>
      <div class="field"><label for="gen-hours">Study time (hours per week)</label><input class="input" id="gen-hours" type="number" min="1" max="80" value="${prof?.profile?.weekly_study_hours || 8}"></div></div>
    <div class="flex mt-3"><button class="btn btn-grad" type="submit" id="gen-btn">${icon("map")} Generate roadmap</button>
      ${hasExisting ? `<button class="btn btn-ghost" type="button" id="gen-cancel">Back to current roadmap</button>` : ""}</div></form>`;
  $("#gen-cancel")?.addEventListener("click", () => { history.replaceState(null, "", "/roadmap"); loadPlan(); });
  $("#gen-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const r = $("#gen-role").value.trim();
    const hours = +$("#gen-hours").value || null;  // read before the form is replaced
    if (r.length < 2) return $("#gen-role").focus();
    plan.innerHTML = loadingState("Building your roadmap from skill gaps...");
    try {
      const rm = await api.post("/api/roadmap", { target_role: r, weekly_hours: hours });
      history.replaceState(null, "", "/roadmap");
      if (rm.ai_note) toast(rm.ai_note, "warn");
      renderPlan(rm);
      loadStats();
    } catch (err) { errorState(plan, err, () => showGenerate(r, hasExisting)); }
  });
}

$("#regen-btn").onclick = () => { document.querySelector('[data-tab="plan"]').click(); showGenerate(current?.target_role || "", !!current); };

function loadProjects() {
  const el = $("#projects");
  load(el, () => api.get(`/api/roadmap/projects${current ? `?role=${encodeURIComponent(current.target_role)}` : ""}`), (d) => {
    el.innerHTML = `${d.ai_note ? `<div class="callout warn small mb-3">${esc(d.ai_note)}</div>` : ""}
      ${d.projects.length ? `<div class="grid-2">${d.projects.map((p, i) => `<div class="card">
        <div class="card-head"><h3>${esc(p.title)}</h3><div class="flex"><span class="badge ${p.difficulty === "advanced" ? "danger" : p.difficulty === "intermediate" ? "warn" : "teal"}">${esc(p.difficulty)}</span>
          ${p.ai_generated ? `<span class="ai-label">AI idea</span>` : ""}</div></div>
        <p class="small"><strong>Skills you'll learn:</strong> ${esc(p.skills_learned.join(", "))}</p>
        <div class="tags mt-2">${p.technologies.map((t) => `<span class="tag">${esc(t)}</span>`).join("")}</div>
        <h4 class="mt-3 mb-2">Features</h4><ul class="bullets small">${p.features.map((f) => `<li>${esc(f)}</li>`).join("")}</ul>
        <p class="small mt-2"><strong>Expected duration:</strong> ~${p.duration_weeks} week(s)</p>
        <p class="small"><strong>Resume value:</strong> ${esc(p.resume_value)}</p>
        ${p.resources.length ? `<h4 class="mt-3 mb-2">Learning resources</h4>${p.resources.map((r) => `<div class="small"><a href="${esc(safeUrl(r.url))}" target="_blank" rel="noopener noreferrer">${esc(r.title)}</a> <span class="faint">(${esc(r.skill)})</span></div>`).join("")}` : ""}
        <button class="btn btn-ghost btn-sm mt-3" data-done="${i}">${icon("check")} I built this</button></div>`).join("")}</div>`
        : `<div class="card">${emptyState("No project suggestions", "No skill gaps to target right now.", "", "bolt")}</div>`}`;
    el.querySelectorAll("[data-done]").forEach((b) => (b.onclick = async () => {
      const p = d.projects[+b.dataset.done];
      const url = await modal({ title: "Add to your profile", body: `<p class="small mb-2">Great work! Add a link to the repo or demo (optional).</p><input class="input" id="purl" type="url" placeholder="https://github.com/...">`,
        actions: [{ label: "Cancel", value: null }, { label: "Add project", class: "btn-primary", handler: (m) => m.querySelector("#purl").value.trim() || "" }] });
      if (url === null) return;
      try { await api.post("/api/learning/projects", { title: p.title, technologies: p.technologies, url: url || null }); toast("Project added to your profile", "success"); loadStats(); }
      catch (err) { toastError(err); }
    }));
  });
}

function loadResources(e) {
  e?.preventDefault();
  const el = $("#resources");
  load(el, () => api.get(`/api/learning/resources${qs({ skill: $("#rf-skill").value.trim(), type: $("#rf-type").value, difficulty: $("#rf-diff").value,
    include_search: $("#rf-type").value === "youtube" ? "1" : "", per_page: 60 })}`), (d) => {
    el.innerHTML = d.items.length ? `<div class="table-wrap"><table class="table responsive"><thead><tr><th>Title</th><th>Skill</th><th>Platform</th><th>Type</th><th>Difficulty</th><th>Time</th><th>Progress</th></tr></thead><tbody>
      ${d.items.map((r) => `<tr data-res="${r.id}"><td data-label="Title"><a href="${esc(safeUrl(r.url))}" target="_blank" rel="noopener noreferrer">${esc(r.title)}</a></td><td data-label="Skill">${esc(r.skill)}</td>
        <td data-label="Platform">${esc(r.platform)}</td><td data-label="Type">${esc(r.type)}</td><td data-label="Difficulty">${esc(r.difficulty)}</td><td data-label="Time">${r.est_hours ? `~${r.est_hours}h` : "-"}</td>
        <td data-label="Progress">${r.is_search_link ? "-" : statusSelect("not_started", "data-res-status")}</td></tr>`).join("")}</tbody></table></div>
      <p class="tiny faint mt-2">Showing ${d.items.length} of ${d.total}. Links are curated from official documentation and established platforms; YouTube entries are search links, not specific videos.</p>`
      : emptyState("No resources found", "Try a different skill or filter.", "", "book");
    api.get("/api/learning/progress?per_page=100").then((p) => {
      const map = Object.fromEntries(p.items.map((x) => [x.resource.id, x.status]));
      el.querySelectorAll("tr[data-res]").forEach((tr) => { const s = tr.querySelector("select"); if (s && map[tr.dataset.res]) s.value = map[tr.dataset.res]; });
    }).catch(() => {});
    el.querySelectorAll("[data-res-status]").forEach((s) => (s.onchange = async () => {
      try { await api.put(`/api/learning/progress/${s.closest("[data-res]").dataset.res}`, { status: s.value }); toast("Progress saved", "success", 1500); loadStats(); }
      catch (err) { toastError(err); }
    }));
  });
}
$("#res-filter").addEventListener("submit", loadResources);

loadStats();
loadPlan();
