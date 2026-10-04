import { api, qs } from "../core/api.js";
import { $, emptyState, errorState, esc, fmtDate, fmtMoney, icon, loadingState, modal, params, safeUrl, scoreClass, timeAgo,
  toast, toastError } from "../core/ui.js";

const results = $("#results"), pager = $("#pager"), status = $("#status");
let page = 1, lastItems = [];

function filters() {
  const f = new FormData($("#filters"));
  return { q: f.get("q"), location: f.get("location"), company: f.get("company"), skills: f.get("skills"),
    experience_level: f.get("experience_level"), salary_min: f.get("salary_min"), posted_within: f.get("posted_within"),
    sort: f.get("sort"), work_type: f.getAll("work_type"), saved: f.get("saved") ? "1" : "" };
}

const salary = (j) => j.salary_min || j.salary_max
  ? `${fmtMoney(j.salary_min || j.salary_max, j.salary_currency)}${j.salary_max && j.salary_min ? ` - ${fmtMoney(j.salary_max, j.salary_currency)}` : ""}${j.salary_is_predicted ? " (est.)" : ""}`
  : j.salary_text ? esc(j.salary_text) : null;

function card(j) {
  const m = j.match;
  return `<article class="card job-card" data-id="${j.id}">
    <div class="flex between" style="align-items:flex-start">
      <div class="grow"><div class="job-title">${esc(j.title)}</div><div class="small muted">${esc(j.company || "Unknown company")}</div></div>
      <span class="match-pill ${scoreClass(m.score)}" title="Match score">${m.score}%</span>
    </div>
    <div class="meta">
      <span>${icon("pin", "sm")} ${esc(j.location || "Not specified")}</span>
      <span class="badge">${esc(j.work_type === "unknown" ? "work type n/a" : j.work_type)}</span>
      ${j.experience_level ? `<span class="badge info">${esc(j.experience_level)}${j.experience_min_years ? ` · ${j.experience_min_years}+ yrs` : ""}</span>` : ""}
      ${salary(j) ? `<span>${icon("coins", "sm")} ${salary(j)}</span>` : ""}
      <span>${icon("calendar", "sm")} ${j.posted_at ? timeAgo(j.posted_at) : "date n/a"}</span>
    </div>
    <div class="tags">${j.skills.slice(0, 8).map((s) => `<span class="tag ${m.matched_skills.includes(s) ? "matched" : m.missing_skills.some((x) => x.skill === s) ? "missing" : ""}">${esc(s)}</span>`).join("")}</div>
    <details><summary class="small" style="cursor:pointer;color:var(--accent);font-weight:600">Why this matches: ${esc(m.explanation.verdict)}</summary>
      <ul class="bullets small mt-1">${m.explanation.why.map((w) => `<li>${esc(w)}</li>`).join("")}
        <li>Experience: ${esc(m.explanation.experience)}</li><li>Education: ${esc(m.explanation.education)}</li><li>${esc(m.explanation.location.join(" "))}</li></ul></details>
    <div class="flex flex-wrap" style="gap:6px">
      <button class="btn btn-primary btn-sm" data-act="view">${icon("eye")} View job</button>
      <button class="btn btn-ghost btn-sm" data-act="save">${icon("star")} ${j.saved ? "Saved" : "Save job"}</button>
      <a class="btn btn-ghost btn-sm" href="${esc(safeUrl(j.url))}" target="_blank" rel="noopener noreferrer" data-act="apply">${icon("external")} Apply</a>
      <button class="btn btn-ghost btn-sm" data-act="track">${icon("kanban")} Add to applications</button>
    </div>
    <span class="tiny faint">Source: ${esc(j.source_label)}</span>
  </article>`;
}

async function search(p = 1) {
  page = p;
  const f = filters();
  results.innerHTML = loadingState(f.q && p === 1 ? "Fetching live postings and scoring matches..." : "Loading...");
  pager.innerHTML = "";
  try {
    const d = await api.get(`/api/jobs${qs({ ...f, page: p, per_page: 12 })}`);
    lastItems = d.items;
    const src = Object.entries(d.sources || {}).map(([k, v]) => `${k}: ${v.replace("not_configured", "not configured")}`).join(" · ");
    status.innerHTML = `${d.total} job(s)${d.query ? ` for "${esc(d.query)}"` : ""}${src ? ` · ${esc(src)}` : ""}${!d.has_resume ? ` · <a href="/resumes">Upload a resume</a> for accurate matching` : ""}
      <br><span class="tiny faint">${esc(d.attribution)}</span>`;
    if (Object.values(d.sources || {}).includes("unavailable")) toast("Some job sources are temporarily unavailable - showing stored results.", "warn");
    results.innerHTML = d.items.length ? `<div class="grid-3">${d.items.map(card).join("")}</div>`
      : `<div class="card">${emptyState("No jobs found", f.q ? "Try broader keywords, a different location, or fewer filters." : "Search for a job title to fetch live postings.", "", "briefcase")}</div>`;
    if (d.pages > 1) {
      pager.innerHTML = `<button class="btn btn-ghost btn-sm" ${p <= 1 ? "disabled" : ""} data-page="${p - 1}">Previous</button>
        <span class="small muted">Page ${p} of ${d.pages}</span>
        <button class="btn btn-ghost btn-sm" ${p >= d.pages ? "disabled" : ""} data-page="${p + 1}">Next</button>`;
    }
  } catch (err) { errorState(results, err, () => search(p)); }
}

pager.addEventListener("click", (e) => { const b = e.target.closest("[data-page]"); if (b) { search(+b.dataset.page); window.scrollTo({ top: 0 }); } });
$("#filters").addEventListener("submit", (e) => { e.preventDefault(); search(1); });
$("#filters").addEventListener("reset", () => setTimeout(() => search(1), 0));

results.addEventListener("click", async (e) => {
  const btn = e.target.closest("[data-act]");
  if (!btn) return;
  const id = +btn.closest("[data-id]").dataset.id;
  const job = lastItems.find((j) => j.id === id);
  try {
    if (btn.dataset.act === "view") view(id);
    else if (btn.dataset.act === "save") {
      if (job.saved) { await api.del(`/api/jobs/${id}/save`); job.saved = false; toast("Removed from saved jobs"); }
      else { await api.post(`/api/jobs/${id}/save`, {}); job.saved = true; toast("Job saved", "success"); }
      btn.innerHTML = `${icon("star")} ${job.saved ? "Saved" : "Save job"}`;
    } else if (btn.dataset.act === "track") {
      await api.post(`/api/jobs/${id}/apply`, { stage: "wishlist" });
      toast("Added to your application tracker (Wishlist)", "success");
    } else if (btn.dataset.act === "apply") {
      api.post(`/api/jobs/${id}/apply`, { stage: "applied" }).then(() => toast("Tracked as Applied - update the stage as you hear back.", "success")).catch(() => {});
    }
  } catch (err) { toastError(err); }
});

async function view(id) {
  try {
    const j = await api.get(`/api/jobs/${id}`);
    const m = j.match;
    modal({ title: j.title, wide: true, body: `
      <div class="flex between flex-wrap mb-2"><div><strong>${esc(j.company || "")}</strong> · ${esc(j.location || "")}</div><span class="match-pill ${scoreClass(m.score)}">${m.score}% match</span></div>
      <div class="meta mb-3"><span>Posted ${fmtDate(j.posted_at)}</span><span>${esc(j.employment_type || "")}</span>${salary(j) ? `<span>${salary(j)}</span>` : ""}<span>Source: ${esc(j.source_label)}</span></div>
      <div class="grid-2 mb-3">
        <div class="card flat"><h4 class="mb-2">Skills</h4><div class="check-list">
          ${m.matched_skills.map((s) => `<span class="ok">${esc(s)}</span>`).join("")}
          ${(m.explanation.partial || []).map((p) => `<span class="part">${esc(p.skill)} (via ${esc(p.via)})</span>`).join("")}
          ${m.missing_skills.map((s) => `<span class="no">${esc(s.skill)}${s.importance === "preferred" ? " (preferred)" : ""}</span>`).join("")}
          ${!m.matched_skills.length && !m.missing_skills.length ? `<span class="small faint">No specific skills extracted from this posting.</span>` : ""}</div></div>
        <div class="card flat"><h4 class="mb-2">Why it matches</h4>
          ${Object.entries(m.components).map(([k, v]) => `<div class="meter-row small"><span>${esc(k)}</span><div class="progress sm"><span style="width:${v}%"></span></div><span class="val">${v}</span></div>`).join("")}
          <p class="small mt-2">Experience: ${esc(m.explanation.experience)}<br>Education: ${esc(m.explanation.education)}<br>Title: ${esc(m.explanation.title)}</p></div>
      </div>
      <h4 class="mb-2">Description</h4><div class="small" style="white-space:pre-wrap;max-height:40vh;overflow:auto;color:var(--muted)">${esc(j.description || "No description provided.")}</div>`,
    actions: [{ label: "Close" }, { label: "Open original posting", class: "btn-primary", handler: () => { window.open(safeUrl(j.url), "_blank", "noopener"); } }] });
  } catch (err) { toastError(err); }
}

async function init() {
  const p = params();
  if (p.get("saved")) $('#filters [name="saved"]').checked = true;
  if (p.get("q")) $("#f-q").value = p.get("q");
  await search(1);
  if (p.get("job")) view(+p.get("job"));
}
init();
