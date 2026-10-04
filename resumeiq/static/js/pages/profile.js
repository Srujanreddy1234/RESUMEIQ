import { api } from "../core/api.js";
import { $, confirmDialog, emptyState, esc, fmtDate, icon, levelDots, load, modal, params, progressBar, safeUrl, showFieldErrors,
  toast, toastError, withBusy } from "../core/ui.js";

const root = $("#profile");
if (params().get("welcome")) $("#welcome").hidden = false;
let data = null;

const SECTIONS = {
  education: { title: "Education", icon: "book", path: "education",
    fields: [["institution", "Institution *", "text", true], ["degree", "Degree"], ["field_of_study", "Field of study"], ["graduation_year", "Graduation year", "number"], ["gpa", "GPA"]],
    line: (e) => `<strong>${esc(e.degree || "Degree")}</strong>${e.field_of_study ? ` in ${esc(e.field_of_study)}` : ""}<div class="tiny muted">${esc(e.institution)}${e.graduation_year ? ` · ${e.graduation_year}` : ""}${e.gpa ? ` · GPA ${esc(e.gpa)}` : ""}</div>` },
  experience: { title: "Experience", icon: "briefcase", path: "experience",
    fields: [["company", "Company *", "text", true], ["title", "Title"], ["kind", "Type", "select:job,internship"], ["start_date", "Start"], ["end_date", "End"], ["description", "Description", "textarea"]],
    line: (e) => `<strong>${esc(e.title || "Role")}</strong> · ${esc(e.company)} ${e.kind === "internship" ? `<span class="badge info">Internship</span>` : ""}<div class="tiny muted">${esc(e.start_date || "")}${e.end_date ? ` - ${esc(e.end_date)}` : ""}</div>${e.description ? `<p class="small mt-1" style="white-space:pre-line">${esc(e.description.slice(0, 400))}</p>` : ""}` },
  projects: { title: "Projects", icon: "bolt", path: "projects",
    fields: [["name", "Name *", "text", true], ["description", "Description", "textarea"], ["technologies", "Technologies (comma separated)"], ["url", "URL", "url"]],
    line: (p) => `<strong>${esc(p.name)}</strong>${p.url ? ` <a href="${esc(safeUrl(p.url))}" target="_blank" rel="noopener noreferrer">${icon("external", "sm")}</a>` : ""}<div class="tags mt-1">${(p.technologies || []).map((t) => `<span class="tag">${esc(t)}</span>`).join("")}</div>${p.description ? `<p class="small mt-1">${esc(p.description.slice(0, 300))}</p>` : ""}` },
  certifications: { title: "Certifications", icon: "star", path: "certifications",
    fields: [["name", "Name *", "text", true], ["issuer", "Issuer"], ["issued_date", "Issued", "date"], ["status", "Status", "select:earned,in_progress,planned"], ["credential_url", "Credential URL", "url"]],
    line: (c) => `<strong>${esc(c.name)}</strong> <span class="badge ${c.status === "earned" ? "teal" : "warn"}">${esc(c.status.replace("_", " "))}</span><div class="tiny muted">${esc(c.issuer || "")}${c.issued_date ? ` · ${fmtDate(c.issued_date)}` : ""}</div>` },
  goals: { title: "Target roles & goals", icon: "target", path: "goals",
    fields: [["target_role", "Target role *", "text", true], ["target_date", "Target date", "date"], ["weekly_hours", "Study hours / week", "number"], ["status", "Status", "select:active,achieved,paused"], ["is_primary", "Primary goal", "checkbox"], ["notes", "Notes", "textarea"]],
    line: (g) => `<strong>${esc(g.target_role)}</strong> ${g.is_primary ? `<span class="badge accent">Primary</span>` : ""} <span class="badge">${esc(g.status)}</span><div class="tiny muted">${g.target_date ? `By ${fmtDate(g.target_date)}` : ""}${g.weekly_hours ? ` · ${g.weekly_hours} h/week` : ""}</div>` },
};

function fieldHtml([name, label, type = "text", required], value) {
  const v = value ?? "";
  if (type === "textarea") return `<div class="field full"><label>${label}</label><textarea class="textarea" name="${name}" rows="4">${esc(v)}</textarea><span class="field-error"></span></div>`;
  if (type === "checkbox") return `<div class="field"><label class="checkbox"><input type="checkbox" name="${name}" ${v ? "checked" : ""}> ${label}</label></div>`;
  if (type.startsWith("select:")) return `<div class="field"><label>${label}</label><select class="select" name="${name}">${type.slice(7).split(",").map((o) => `<option value="${o}" ${o === v ? "selected" : ""}>${o.replace("_", " ")}</option>`).join("")}</select></div>`;
  return `<div class="field"><label>${label}</label><input class="input" type="${type}" name="${name}" ${required ? "required" : ""} value="${esc(Array.isArray(v) ? v.join(", ") : v)}"><span class="field-error"></span></div>`;
}

async function editItem(key, item = null) {
  const s = SECTIONS[key];
  await modal({ title: `${item ? "Edit" : "Add"} ${s.title.toLowerCase().replace(/s$/, "")}`, wide: true,
    body: `<form class="form-grid" novalidate>${s.fields.map((f) => fieldHtml(f, item?.[f[0]])).join("")}</form>`,
    actions: [{ label: "Cancel" }, { label: "Save", class: "btn-primary", handler: async (m) => {
      const form = m.querySelector("form");
      const payload = {};
      s.fields.forEach(([name, , type = "text"]) => {
        const el = form.elements[name];
        if (type === "checkbox") payload[name] = el.checked;
        else if (type === "number") payload[name] = el.value ? +el.value : null;
        else if (name === "technologies") payload[name] = el.value.split(",").map((t) => t.trim()).filter(Boolean);
        else payload[name] = el.value.trim() || null;
      });
      try {
        if (item) await api.put(`/api/profile/${s.path}/${item.id}`, payload); else await api.post(`/api/profile/${s.path}`, payload);
        toast("Saved", "success"); refresh();
      } catch (err) { if (!showFieldErrors(form, err)) toastError(err); return false; }
    } }] });
}

function section(key) {
  const s = SECTIONS[key], items = data[key];
  return `<section class="card" data-section="${key}"><div class="card-head"><h3>${icon(s.icon)} ${s.title}</h3>
      <button class="btn btn-ghost btn-sm" data-add>${icon("plus")} Add</button></div>
    ${items.length ? `<div class="list">${items.map((it) => `<div class="list-item" data-id="${it.id}"><div class="grow">${s.line(it)}
        ${it.source && it.source !== "manual" ? `<span class="tiny faint">from ${esc(it.source)}</span>` : ""}</div>
        <button class="btn btn-ghost btn-sm" data-edit aria-label="Edit">${icon("edit")}</button><button class="btn btn-ghost btn-sm" data-del aria-label="Delete">${icon("trash")}</button></div>`).join("")}</div>`
      : emptyState(`No ${s.title.toLowerCase()} yet`, "", "", s.icon)}</section>`;
}

function render() {
  const p = data.profile, u = data.user;
  root.innerHTML = `
    <section class="card glow mb-3"><div class="flex flex-wrap" style="gap:20px">
      <div class="stack" style="align-items:center;gap:8px"><span class="avatar lg" id="avatar">${esc(u.full_name[0].toUpperCase())}</span>
        <label class="btn btn-ghost btn-sm" style="position:relative;overflow:hidden">${icon("upload")} Photo<input type="file" id="avatar-file" accept="image/png,image/jpeg,image/webp" style="position:absolute;inset:0;opacity:0;cursor:pointer"></label>
        ${p.has_avatar ? `<button class="link-btn tiny" id="avatar-del">Remove</button>` : ""}</div>
      <div class="grow stack"><h2>${esc(u.full_name)}</h2><p class="small">${esc(p.headline || "Add a headline")} · ${esc(u.email)}</p>
        <div class="flex"><span class="small">Profile completeness</span><span class="grow">${progressBar(p.completeness)}</span><strong>${p.completeness}%</strong></div>
        <div class="tags">${p.target_career ? `<span class="tag matched">${icon("target", "sm")} ${esc(p.target_career)}</span>` : ""}${(p.career_interests || []).map((i) => `<span class="tag">${esc(i)}</span>`).join("")}</div></div>
    </div></section>

    <form id="prof-form" class="card mb-3" novalidate><div class="card-head"><h3>${icon("user")} Profile & preferences</h3></div>
      <div class="form-grid">
        <div class="field"><label>Headline</label><input class="input" name="headline" maxlength="160" value="${esc(p.headline || "")}" placeholder="e.g. CS graduate · backend-focused"></div>
        <div class="field"><label>Target career</label><input class="input" name="target_career" maxlength="120" value="${esc(p.target_career || "")}" placeholder="e.g. Backend Developer"><span class="field-error"></span></div>
        <div class="field"><label>Years of experience</label><input class="input" type="number" step="0.5" min="0" max="60" name="years_experience" value="${p.years_experience ?? ""}"><span class="field-error"></span></div>
        <div class="field"><label>Location</label><input class="input" name="location" maxlength="120" value="${esc(p.location || "")}"></div>
        <div class="field"><label>Education</label><input class="input" name="education_summary" maxlength="255" value="${esc(p.education_summary || "")}"></div>
        <div class="field"><label>Preferred work type</label><select class="select" name="preferred_work_type">${["any", "remote", "hybrid", "onsite"].map((w) => `<option value="${w}" ${p.preferred_work_type === w ? "selected" : ""}>${w}</option>`).join("")}</select></div>
        <div class="field"><label>Preferred industries (comma separated)</label><input class="input" name="preferred_industries" value="${esc((p.preferred_industries || []).join(", "))}"></div>
        <div class="field"><label>Career interests (comma separated)</label><input class="input" name="career_interests" value="${esc((p.career_interests || []).join(", "))}"></div>
        <div class="field"><label>Salary min</label><input class="input" type="number" min="0" step="1000" name="salary_min" value="${p.salary_min ?? ""}"><span class="field-error"></span></div>
        <div class="field"><label>Salary max</label><input class="input" type="number" min="0" step="1000" name="salary_max" value="${p.salary_max ?? ""}"><span class="field-error"></span></div>
        <div class="field"><label>Currency</label><input class="input" name="salary_currency" maxlength="3" value="${esc(p.salary_currency || "USD")}"><span class="field-error"></span></div>
        <div class="field"><label>Study time (hours/week)</label><input class="input" type="number" min="1" max="80" name="weekly_study_hours" value="${p.weekly_study_hours}"><span class="field-error"></span></div>
        <div class="field"><label>LinkedIn URL</label><input class="input" type="url" name="linkedin_url" value="${esc(p.linkedin_url || "")}"><span class="field-error"></span></div>
        <div class="field"><label>GitHub URL</label><input class="input" type="url" name="github_url" value="${esc(p.github_url || "")}"><span class="field-error"></span></div>
        <div class="field full"><label>Bio</label><textarea class="textarea" name="bio" rows="3" maxlength="2000">${esc(p.bio || "")}</textarea></div>
      </div>
      <button class="btn btn-grad mt-3" type="submit" id="prof-save">${icon("check")} Save profile</button></form>

    <section class="card mb-3"><div class="card-head"><h3>${icon("graph")} Skills</h3><span class="small muted">Levels: 1 aware · 2 beginner · 3 working · 4 proficient · 5 expert</span></div>
      <form id="skill-form" class="flex flex-wrap mb-3"><input class="input" id="skill-name" placeholder="Add a skill, e.g. Docker" style="max-width:260px" maxlength="60">
        <select class="select" id="skill-level" style="max-width:180px">${[1, 2, 3, 4, 5].map((n) => `<option value="${n}" ${n === 3 ? "selected" : ""}>Level ${n}</option>`).join("")}</select>
        <button class="btn btn-primary" type="submit">${icon("plus")} Add / update</button></form>
      ${data.skills.length ? `<div class="grid-3">${data.skills.map((s) => `<div class="flex between card flat" style="padding:10px 12px" data-skill-id="${s.id}">
        <div class="grow"><strong class="small">${esc(s.skill.name)}</strong><div class="tiny faint">${esc(s.source)}</div></div>${levelDots(s.level)}
        <button class="btn btn-ghost btn-sm" data-skill-del aria-label="Remove ${esc(s.skill.name)}">${icon("x")}</button></div>`).join("")}</div>`
        : emptyState("No skills yet", "Upload a resume or add skills manually.", "", "graph")}</section>

    <div class="grid-2">${Object.keys(SECTIONS).map(section).join("")}</div>`;

  if (p.has_avatar) {
    const img = new Image(); img.alt = ""; img.onload = () => { $("#avatar").textContent = ""; $("#avatar").appendChild(img); }; img.src = `/api/profile/avatar?t=${Date.now()}`;
  }
}

root.addEventListener("submit", async (e) => {
  e.preventDefault();
  if (e.target.id === "prof-form") {
    const form = e.target;
    const f = Object.fromEntries(new FormData(form).entries());
    const num = (k) => (f[k] === "" ? null : +f[k]);
    const list = (k) => f[k].split(",").map((x) => x.trim()).filter(Boolean);
    const payload = { ...f, years_experience: num("years_experience"), salary_min: num("salary_min"), salary_max: num("salary_max"),
      weekly_study_hours: num("weekly_study_hours"), preferred_industries: list("preferred_industries"), career_interests: list("career_interests"),
      salary_currency: (f.salary_currency || "USD").toUpperCase() };
    ["headline", "target_career", "location", "education_summary", "linkedin_url", "github_url", "bio"].forEach((k) => { payload[k] = payload[k]?.trim() || null; });
    await withBusy($("#prof-save"), async () => {
      try { await api.put("/api/profile", payload); toast("Profile saved", "success"); refresh(); }
      catch (err) { if (!showFieldErrors(form, err)) toastError(err); }
    }, "Saving...");
  } else if (e.target.id === "skill-form") {
    const name = $("#skill-name").value.trim();
    if (!name) return;
    try { await api.post("/api/profile/skills", { skill: name, level: +$("#skill-level").value }); toast(`${name} saved`, "success"); refresh(); }
    catch (err) { toastError(err); }
  }
});

root.addEventListener("click", async (e) => {
  const sec = e.target.closest("[data-section]");
  try {
    if (e.target.closest("[data-skill-del]")) {
      await api.del(`/api/profile/skills/${e.target.closest("[data-skill-id]").dataset.skillId}`); refresh();
    } else if (e.target.closest("#avatar-del")) {
      await api.del("/api/profile/avatar"); refresh();
    } else if (sec && e.target.closest("[data-add]")) editItem(sec.dataset.section);
    else if (sec && e.target.closest("[data-edit]")) {
      const id = +e.target.closest("[data-id]").dataset.id;
      editItem(sec.dataset.section, data[sec.dataset.section].find((x) => x.id === id));
    } else if (sec && e.target.closest("[data-del]")) {
      if (!(await confirmDialog("Delete entry?", "This entry will be removed from your profile.", { danger: true, confirmLabel: "Delete" }))) return;
      await api.del(`/api/profile/${SECTIONS[sec.dataset.section].path}/${e.target.closest("[data-id]").dataset.id}`); refresh();
    }
  } catch (err) { toastError(err); }
});

root.addEventListener("change", async (e) => {
  if (e.target.id !== "avatar-file") return;
  const file = e.target.files[0];
  if (!file) return;
  if (file.size > 2 * 1024 * 1024) return toast("Image must be 2 MB or smaller.", "error");
  const fd = new FormData(); fd.append("avatar", file);
  try { await api.upload("/api/profile/avatar", fd); toast("Photo updated", "success"); refresh(); } catch (err) { toastError(err); }
});

function refresh() { return load(root, () => api.get("/api/profile"), (d) => { data = d; render(); }); }
refresh();
