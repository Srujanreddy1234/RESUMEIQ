import { api } from "../core/api.js";
import { aiBadge, fillResumeSelect } from "../core/common.js";
import { atsView, jdRequirementsView } from "../core/render.js";
import { $, clearFieldErrors, confirmDialog, emptyState, errorState, esc, fmtDate, icon, initTabs, load, loadingState,
  scoreClass, showFieldErrors, toast, toastError, withBusy } from "../core/ui.js";

const out = $("#jd-out");
initTabs(document.querySelector(".tabs"), (tab) => {
  if (tab === "matches") loadMatches();
  if (tab === "saved") loadSaved();
});

$("#jd-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const form = e.target;
  clearFieldErrors(form);
  const title = $("#jd-title").value.trim(), text = $("#jd-text").value.trim();
  const errs = [];
  if (title.length < 2) errs.push({ field: "title", message: "Enter the job title." });
  if (text.length < 80 || text.split(/\s+/).length < 15) errs.push({ field: "text", message: "This doesn't look like a full job description. Paste the complete posting." });
  if (errs.length) return showFieldErrors(form, { details: errs });
  await withBusy($("#jd-btn"), async () => {
    out.innerHTML = loadingState("Extracting requirements and comparing...");
    try {
      const v = $("#jd-version").value;
      const r = await api.post(`/api/job-descriptions${v ? `?resume_version_id=${v}` : ""}`, { title, company: $("#jd-company").value.trim() || null, text });
      render(r);
    } catch (err) {
      if (showFieldErrors(form, err)) out.innerHTML = "";
      else errorState(out, err, () => $("#jd-btn").click());
    }
  }, "Analyzing...");
});

function render(r) {
  const jd = r.job_description;
  out.innerHTML = `
    <section class="card mb-3"><div class="card-head"><h3>${icon("file")} Requirements: ${esc(jd.title)}${jd.company ? ` at ${esc(jd.company)}` : ""}</h3>${aiBadge(jd.ai_used)}</div>
      ${jd.parsed.ai_note ? `<div class="callout warn small mb-2">${esc(jd.parsed.ai_note)}</div>` : ""}
      ${jdRequirementsView(jd.parsed)}</section>
    ${r.comparison ? atsView(r.comparison, { title: `Your match for ${jd.title}` }) : `<div class="callout warn mb-3">Upload a resume to compare it against this job.</div>`}
    <div class="flex flex-wrap">
      <a class="btn btn-primary btn-sm" href="/cover-letters?jd=${jd.id}">${icon("mail")} Cover letter for this job</a>
      <a class="btn btn-ghost btn-sm" href="/interview?jd=${jd.id}&role=${encodeURIComponent(jd.title)}">${icon("mic")} Interview prep for this job</a>
      <a class="btn btn-ghost btn-sm" href="/analyzer?role=${encodeURIComponent(jd.title)}">${icon("scan")} Full resume analysis</a>
      <button class="btn btn-ghost btn-sm" id="track">${icon("kanban")} Add to applications</button>
    </div>`;
  $("#track").onclick = async () => {
    try {
      await api.post("/api/applications", { company: jd.company || "Unknown company", position: jd.title, stage: "wishlist",
        notes: "Added from Job Matcher." });
      toast("Added to your Wishlist", "success");
    } catch (err) { toastError(err); }
  };
}

function loadMatches() {
  const el = $("#matches");
  load(el, () => api.get("/api/matches?limit=12"), (d) => {
    el.innerHTML = d.items.length ? `<div class="grid-3">${d.items.map((j) => `
      <a class="card job-card" href="/jobs?job=${j.id}" style="color:inherit;text-decoration:none">
        <div class="flex between"><span class="job-title">${esc(j.title)}</span><span class="match-pill ${scoreClass(j.match.score)}">${j.match.score}%</span></div>
        <div class="meta"><span>${esc(j.company || "")}</span><span>${esc(j.location || "")}</span></div>
        <div class="small">${esc(j.match.explanation.verdict)}</div>
        <div class="check-list">${j.match.matched_skills.slice(0, 4).map((s) => `<span class="ok">${esc(s)}</span>`).join("")}
          ${j.match.missing_skills.slice(0, 3).map((s) => `<span class="no">${esc(s.skill)}</span>`).join("")}</div>
      </a>`).join("")}</div>`
      : `<div class="card">${emptyState("No matches yet", "Search jobs for your target role to fetch live postings, then come back.", `<a class="btn btn-primary" href="/jobs">Find jobs</a>`, "target")}</div>`;
  });
}

function loadSaved() {
  const el = $("#saved");
  load(el, () => api.get("/api/job-descriptions?per_page=50"), (d) => {
    el.innerHTML = d.items.length ? `<div class="list">${d.items.map((j) => `
      <div class="list-item" data-id="${j.id}"><span class="list-icon">${icon("file")}</span>
        <div class="grow"><strong>${esc(j.title)}</strong>${j.company ? ` · ${esc(j.company)}` : ""}
          <div class="tiny muted">${fmtDate(j.created_at)} · ${j.parsed.required_skills.length} required, ${j.parsed.preferred_skills.length} preferred skills</div></div>
        <button class="btn btn-ghost btn-sm" data-open>${icon("eye")} Open</button>
        <button class="btn btn-ghost btn-sm" data-del aria-label="Delete">${icon("trash")}</button></div>`).join("")}</div>`
      : emptyState("No saved descriptions", "Job descriptions you analyze are saved here.", "", "file");
    el.querySelectorAll("[data-open]").forEach((b) => (b.onclick = async () => {
      const jd = await api.get(`/api/job-descriptions/${b.closest("[data-id]").dataset.id}`);
      $("#jd-title").value = jd.title; $("#jd-company").value = jd.company || ""; $("#jd-text").value = jd.raw_text;
      document.querySelector('[data-tab="jd"]').click();
      $("#jd-btn").focus();
    }));
    el.querySelectorAll("[data-del]").forEach((b) => (b.onclick = async () => {
      if (!(await confirmDialog("Delete job description?", "Analyses that used it will keep their results.", { danger: true, confirmLabel: "Delete" }))) return;
      try { await api.del(`/api/job-descriptions/${b.closest("[data-id]").dataset.id}`); loadSaved(); } catch (err) { toastError(err); }
    }));
  });
}

fillResumeSelect($("#jd-version")).catch(toastError);
