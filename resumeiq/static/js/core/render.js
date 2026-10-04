// Shared renderers for analysis results.
import { esc, icon, progressBar, scoreRing } from "./ui.js";

export function breakdownView(components) {
  return `<div class="breakdown">${components.map((c) => `
    <div class="bd-item">
      <div class="bd-top"><strong>${esc(c.label)}</strong><span class="bd-score" style="color:${c.score >= 70 ? "var(--teal)" : c.score >= 50 ? "var(--accent)" : "var(--warn)"}">${c.score}</span></div>
      ${progressBar(c.score, `sm ${c.score < 50 ? "warn" : ""}`)}
      <p>${esc(c.explanation)}</p>
      ${c.suggestions?.length ? `<details><summary>How to improve</summary><ul class="bullets mt-1 small">${c.suggestions.map((s) => `<li>${esc(s)}</li>`).join("")}</ul></details>` : ""}
      ${c.weight ? `<span class="tiny faint">Weight in overall score: ${Math.round(c.weight * 100)}%</span>` : ""}
    </div>`).join("")}</div>`;
}

const STATUS = { matched: ["MATCHED", "matched", "check"], partial: ["PARTIAL MATCH", "partial", "layers"], missing: ["MISSING", "missing", "x"] };

export function atsView(r, { title = "" } = {}) {
  const group = (status) => r.skills.filter((s) => s.status === status);
  const col = (status) => {
    const [label, cls, ic] = STATUS[status];
    const items = group(status);
    return `<div class="card flat"><div class="card-head"><h4>${icon(ic)} ${label}</h4><span class="badge ${cls === "matched" ? "teal" : cls === "partial" ? "warn" : "danger"}">${items.length}</span></div>
      ${items.length ? `<div class="stack" style="gap:6px">${items.map((s) => `<div><span class="tag ${cls}">${esc(s.skill)}</span>
        ${s.importance === "preferred" ? `<span class="tiny faint"> preferred</span>` : ""}<div class="tiny muted">${esc(s.note)}</div></div>`).join("")}</div>`
        : `<p class="small faint">None</p>`}</div>`;
  };
  return `
    <div class="card glow mb-3"><div class="hero-card">
      ${scoreRing(r.ats_score, "ATS match")}
      <div class="stack"><h2>${esc(title || "ATS compatibility")}</h2>
        <div class="callout small">${icon("info")} <span>${esc(r.disclaimer)}</span></div>
        <div class="stack" style="gap:8px">${r.components.map((c) => `<div class="meter-row"><span>${esc(c.label)}</span>${progressBar(c.score, "sm")}<span class="val">${c.score}</span></div>
          <div class="tiny muted" style="margin:-4px 0 4px">${esc(c.explanation)}</div>`).join("")}</div>
      </div></div></div>
    <div class="grid-4 mb-3">${col("matched")}${col("partial")}${col("missing")}
      <div class="card flat"><div class="card-head"><h4>${icon("info")} NOT RELEVANT</h4><span class="badge">${r.not_relevant.length}</span></div>
        <p class="tiny muted mb-2">Skills on your resume this job doesn't ask for. Consider trimming them for this application.</p>
        <div class="tags">${r.not_relevant.map((s) => `<span class="tag neutral">${esc(s)}</span>`).join("") || `<span class="small faint">None</span>`}</div></div>
    </div>
    <div class="grid-2 mb-3">
      <div class="card"><h3 class="mb-2">Keywords</h3>
        <p class="small mb-2">Matching (${r.matched_keywords.length})</p><div class="tags mb-3">${r.matched_keywords.map((k) => `<span class="tag matched">${esc(k)}</span>`).join("") || `<span class="small faint">None</span>`}</div>
        <p class="small mb-2">Missing (${r.missing_keywords.length})</p><div class="tags">${r.missing_keywords.map((k) => `<span class="tag missing">${esc(k)}</span>`).join("") || `<span class="small faint">None</span>`}</div></div>
      <div class="card"><h3 class="mb-2">Requirements</h3>
        <div class="check-list">
          <div class="${r.experience.required_years === null || r.experience.estimated_years >= r.experience.required_years ? "ok" : "no"}">Experience: ${r.experience.required_years === null ? "not specified" : `${r.experience.required_years}+ years required`} · you ~${r.experience.estimated_years} yrs</div>
          <div class="${!r.education.required || r.education.required === r.education.have || r.components.find((c) => c.key === "education")?.score === 100 ? "ok" : "no"}">Education: ${esc(r.education.required || "not specified")} · you: ${esc(r.education.have)}</div>
          ${r.soft_skills.map((s) => `<div class="${s.status === "matched" ? "ok" : "no"}">Soft skill: ${esc(s.skill)}</div>`).join("")}
          ${r.certifications.map((c) => `<div class="${c.status === "matched" ? "ok" : "no"}">Certification: ${esc(c.certification)}</div>`).join("")}
        </div></div>
    </div>`;
}

export function jdRequirementsView(p) {
  const list = (arr) => (arr?.length ? `<div class="tags">${arr.map((s) => `<span class="tag">${esc(s)}</span>`).join("")}</div>` : `<span class="small faint">Not stated</span>`);
  return `<div class="grid-2">
    <div><h4 class="mb-2">Required skills</h4>${list(p.required_skills)}</div>
    <div><h4 class="mb-2">Preferred skills</h4>${list(p.preferred_skills)}</div>
    <div><h4 class="mb-2">Soft skills</h4>${list(p.soft_skills)}</div>
    <div><h4 class="mb-2">Certifications</h4>${list(p.certifications)}</div>
    <div><h4 class="mb-2">Experience</h4><p>${p.experience_years ? `${p.experience_years}+ years` : "Not stated"}</p></div>
    <div><h4 class="mb-2">Education</h4><p>${esc(p.education_level || "Not stated")}</p></div>
    <div><h4 class="mb-2">Salary</h4><p>${esc(p.salary_text || "Not stated")}</p></div>
    <div><h4 class="mb-2">Work type</h4><p>${esc(p.work_type || "unknown")}</p></div>
    <div class="span-2"><h4 class="mb-2">Responsibilities</h4>${p.responsibilities?.length ? `<ul class="bullets">${p.responsibilities.map((r) => `<li>${esc(r)}</li>`).join("")}</ul>` : `<span class="small faint">No bulleted responsibilities found</span>`}</div>
    <div class="span-2"><h4 class="mb-2">Keywords</h4>${list(p.keywords)}</div>
  </div>`;
}
