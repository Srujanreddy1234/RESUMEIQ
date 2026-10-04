import { api } from "../core/api.js";
import { aiBadge, fillResumeSelect, targetRole } from "../core/common.js";
import { atsView, breakdownView } from "../core/render.js";
import { pollTask } from "../core/tasks.js";
import { $, emptyState, errorState, esc, fmtDate, icon, initTabs, loadingState, params, scoreRing, showFieldErrors,
  clearFieldErrors, toastError, withBusy } from "../core/ui.js";

const tabs = initTabs(document.querySelector(".tabs"));
const result = $("#result");

async function init() {
  const role = await targetRole();
  $("#a-role").value = params().get("role") || role;
  $("#ats-title").value = role;
  await Promise.all([fillResumeSelect($("#a-version"), { allVersions: true }), fillResumeSelect($("#ats-version"), { allVersions: true })]);
  const v = params().get("version");
  if (v) { $("#a-version").value = v; $("#ats-version").value = v; }
  try {
    const jds = await api.get("/api/job-descriptions?per_page=50");
    $("#a-jd").insertAdjacentHTML("beforeend", jds.items.map((j) => `<option value="${j.id}">${esc(j.title)}${j.company ? ` - ${esc(j.company)}` : ""} (${fmtDate(j.created_at)})</option>`).join(""));
  } catch { /* optional */ }
  if ($("#a-version").disabled) {
    result.innerHTML = emptyState("Upload a resume first", "You need at least one resume to analyze.", `<a class="btn btn-primary" href="/resumes">Upload resume</a>`, "file");
  }
  const id = params().get("analysis");
  if (id) openAnalysis(id);
}

async function openAnalysis(id) {
  result.innerHTML = loadingState("Loading analysis...");
  try {
    const a = await api.get(`/api/analysis/${id}`);
    if (a.kind === "resume") renderAnalysis(a);
    else { tabs.select("ats"); renderAts($("#ats-result"), a.result, a); }
  } catch (err) { errorState(result, err, () => openAnalysis(id)); }
}

$("#analyze-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const role = $("#a-role").value.trim();
  const roleErr = $("#a-role").closest(".field").querySelector(".field-error");
  $("#a-role").classList.toggle("invalid", role.length < 2);
  roleErr.textContent = role.length < 2 ? "Enter the role you're targeting." : "";
  if (role.length < 2) return $("#a-role").focus();
  const versionId = +$("#a-version").value;
  if (!versionId) return;
  await withBusy($("#analyze-btn"), async () => {
    result.innerHTML = "";
    $("#progress").hidden = false;
    try {
      const { task } = await api.post("/api/analysis", { resume_version_id: versionId, target_role: role, job_description_id: +$("#a-jd").value || null });
      const out = await pollTask(task, $("#stages"));
      history.replaceState(null, "", `?analysis=${out.analysis_id}`);
      renderAnalysis(await api.get(`/api/analysis/${out.analysis_id}`));
      $("#progress").hidden = true;
    } catch (err) {
      errorState(result, err, () => $("#analyze-btn").click());
    }
  }, "Analyzing...");
});

function renderAnalysis(a) {
  const r = a.result;
  const ai = r.ai_feedback;
  const skillGroups = Object.entries(r.skills || {}).filter(([, v]) => v.length);
  result.innerHTML = `
    <section class="card glow mb-3"><div class="hero-card">
      ${scoreRing(a.overall_score, r.grade)}
      <div class="stack">
        <div class="flex flex-wrap"><h2>${esc(r.candidate_name ? `${r.candidate_name} · ` : "")}${esc(a.target_role)}</h2>${aiBadge(a.ai_used)}</div>
        <p class="small">${a.resume ? `${esc(a.resume.name)} v${a.resume.version_number}` : "Deleted resume"} · ${fmtDate(a.created_at)} · ${a.skills_identified} skills identified
          ${r.role_profile ? ` · compared with our curated <strong>${esc(r.role_profile)}</strong> baseline` : ""}${a.job_description ? ` and "${esc(a.job_description.title)}"` : ""}</p>
        ${r.ai_note ? `<div class="callout warn small">${esc(r.ai_note)}</div>` : ""}
        <div class="flex flex-wrap">
          <a class="btn btn-primary btn-sm" href="/improve?version=${a.resume?.version_id || ""}">${icon("wand")} Improve resume</a>
          <a class="btn btn-ghost btn-sm" href="/skill-gap?role=${encodeURIComponent(a.target_role)}">${icon("graph")} Skill gap</a>
          <a class="btn btn-ghost btn-sm" href="/reports/analysis?id=${a.id}" target="_blank" rel="noopener">${icon("printer")} Export PDF</a>
        </div>
      </div></div></section>
    <section class="card mb-3"><div class="card-head"><h3>Score breakdown</h3><span class="small muted">Each score shows exactly why it was given</span></div>${breakdownView(a.score_breakdown)}</section>
    <section class="grid-2 mb-3">
      <div class="card"><h3 class="mb-2">${icon("star")} Strengths</h3>${r.strengths.length ? `<ul class="bullets">${r.strengths.map((s) => `<li>${esc(s)}</li>`).join("")}</ul>` : `<p class="small">No component scored above 65 yet.</p>`}</div>
      <div class="card"><h3 class="mb-2">${icon("alert")} Areas to improve</h3>${r.weaknesses.length ? `<ul class="bullets">${r.weaknesses.map((s) => `<li>${esc(s)}</li>`).join("")}</ul>` : `<p class="small">No weak areas below 65.</p>`}</div>
    </section>
    ${ai ? `<section class="card mb-3"><div class="card-head"><h3>${icon("sparkles")} Written feedback</h3><span class="ai-label">AI-generated · numbers above are rule-based</span></div>
      <p style="color:var(--text)">${esc(ai.summary)}</p>
      <div class="grid-2 mt-3"><div><h4 class="mb-2">Strengths</h4><ul class="bullets">${ai.strengths.map((s) => `<li>${esc(s)}</li>`).join("")}</ul></div>
        <div><h4 class="mb-2">Weaknesses</h4><ul class="bullets">${ai.weaknesses.map((s) => `<li>${esc(s)}</li>`).join("")}</ul></div></div>
      ${ai.section_feedback.length ? `<div class="divider"></div><div class="stack">${ai.section_feedback.map((f) => `<div><strong class="small">${esc(f.section)}</strong><p class="small">${esc(f.comment)}</p></div>`).join("")}</div>` : ""}
    </section>` : ""}
    <section class="grid-2">
      <div class="card"><h3 class="mb-2">Skills by category</h3>
        ${skillGroups.length ? skillGroups.map(([k, v]) => `<div class="mb-2"><div class="tiny muted mb-2">${esc(k.replace("_", " / "))}</div><div class="tags">${v.map((s) => `<span class="tag">${esc(s)}</span>`).join("")}</div></div>`).join("") : `<p class="small">No skills detected.</p>`}
      </div>
      <div class="card"><h3 class="mb-2">Role requirements</h3>
        <p class="small mb-2">Matching (${r.matched_skills.length})</p><div class="tags mb-3">${r.matched_skills.map((s) => `<span class="tag matched">${esc(s)}</span>`).join("") || `<span class="small faint">None</span>`}</div>
        <p class="small mb-2">Missing (${r.missing_skills.length})</p><div class="tags">${r.missing_skills.map((s) => `<span class="tag missing">${esc(s)}</span>`).join("") || `<span class="small faint">None</span>`}</div>
        ${r.missing_skills.length ? `<a class="btn btn-ghost btn-sm mt-3" href="/roadmap">${icon("map")} Build a learning roadmap</a>` : ""}
      </div>
    </section>`;
  result.scrollIntoView({ behavior: "smooth", block: "start" });
}

// ── ATS ────────────────────────────────────────────────
$("#ats-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const form = e.target;
  clearFieldErrors(form);
  const jd = $("#ats-jd").value.trim();
  const errs = [];
  if ($("#ats-title").value.trim().length < 2) errs.push({ field: "job_title", message: "Enter the job title." });
  if (jd.split(/\s+/).length < 15) errs.push({ field: "job_description", message: "Paste the full job description (at least a few sentences)." });
  if (errs.length) return showFieldErrors(form, { details: errs });
  await withBusy($("#ats-btn"), async () => {
    const out = $("#ats-result");
    out.innerHTML = loadingState("Comparing your resume with the job description...");
    try {
      const r = await api.post("/api/analysis/ats", { resume_version_id: +$("#ats-version").value, job_title: $("#ats-title").value.trim(),
        company: $("#ats-company").value.trim() || null, job_description: jd });
      history.replaceState(null, "", `?analysis=${r.analysis_id}`);
      renderAts(out, r, { id: r.analysis_id, target_role: $("#ats-title").value.trim() });
    } catch (err) {
      if (!showFieldErrors(form, err)) errorState(out, err, () => $("#ats-btn").click());
      else out.innerHTML = "";
    }
  }, "Checking...");
});

function renderAts(el, r, meta) {
  el.innerHTML = atsView(r, { title: `ATS match: ${meta.target_role}` }) + `<div class="flex flex-wrap">
    <a class="btn btn-ghost btn-sm" href="/reports/analysis?id=${meta.id}" target="_blank" rel="noopener">${icon("printer")} Export PDF</a>
    <a class="btn btn-ghost btn-sm" href="/cover-letters">${icon("mail")} Write a cover letter</a>
    <a class="btn btn-ghost btn-sm" href="/interview">${icon("mic")} Prepare for interview</a></div>`;
}

init().catch(toastError);
